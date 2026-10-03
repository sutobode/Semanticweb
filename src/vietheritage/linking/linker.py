"""External linking (COMP-007): deterministic QID + reviewed DBpedia candidates."""
from __future__ import annotations

import csv
import difflib
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL

from vietheritage.validation.semantic import Contract

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
LINKING_DIR = REPO_ROOT / "data" / "linking"
RDF_DIR = REPO_ROOT / "data" / "rdf"
VHR = Namespace("http://localhost:3030/vietheritage/resource/")

_QID_RE = re.compile(r"^Q[1-9][0-9]*$")

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _load_dbpedia_candidates() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for filename in ("dbpedia_lookup_candidates.jsonl", "dbpedia_wikidata_candidates.jsonl"):
        path = REPO_ROOT / "data" / "raw" / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                result.setdefault(row["entity_id"], []).append(row)
    return result


def _link_key(value: str) -> str:
    text = unicodedata.normalize("NFC", value).casefold()
    return "".join(ch for ch in text if ch.isalnum() or ch.isspace()).strip()


def dbpedia_score(source_label: str, target_label: str, type_compatible: bool = True) -> float:
    """Deterministic label score used for candidate review, not core identity."""
    if not type_compatible:
        return 0.0
    left, right = _link_key(source_label), _link_key(target_label)
    if not left or not right:
        return 0.0
    return round(difflib.SequenceMatcher(None, left, right).ratio(), 6)


def review_dbpedia_candidate(
    score: float,
    distance_km: float | None,
    type_compatible: bool,
) -> str:
    """Classify a candidate; PROJECT_SPEC 22.2 never auto-verifies DBpedia."""
    auto_score = float(os.getenv("DBPEDIA_AUTO_ACCEPT_SCORE", "0.90"))
    review_score = float(os.getenv("DBPEDIA_REVIEW_SCORE", "0.70"))
    auto_distance = float(os.getenv("DBPEDIA_AUTO_ACCEPT_DISTANCE_KM", "5"))
    review_distance = float(os.getenv("DBPEDIA_REVIEW_DISTANCE_KM", "20"))
    if not type_compatible or score < review_score:
        return "rejected"
    if distance_km is not None and distance_km > review_distance:
        return "rejected"
    if score >= auto_score:
        if distance_km is None:
            return "manual_review"
        if distance_km <= auto_distance:
            return "auto_candidate"
    if distance_km is not None and distance_km <= review_distance:
        return "manual_review"
    # Section 22.2 requires fail-closed handling of an uncovered combination.
    raise ValueError("LINK_POLICY_UNCOVERED: DBpedia score/distance has no specified decision")


def _review_row(source_uri: str, target_uri: str, dataset: str, method: str, score: float, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "source_uri": source_uri,
        "target_uri": target_uri,
        "target_dataset": dataset,
        "method": method,
        "score": score,
        "distance_km": extra.get("distance_km"),
        "type_compatible": bool(extra.get("type_compatible", True)),
        "status": status,
        "reviewer": extra.get("reviewer") or ("automated:vietheritage-linker/0.1.0" if status == "verified" else None),
        "reviewed_at": extra.get("reviewed_at") or (_now() if status == "verified" else None),
        "reason": extra.get("reason"),
    }


def _approved_dbpedia_review(candidate: dict, reviews: list[dict]) -> dict | None:
    """Only explicit reviewer/fixture decisions, not legacy auto-verification."""
    for row in reviews:
        reviewer = str(row.get("reviewer") or "").strip()
        if (row.get("source_uri") != candidate["source_uri"]
                or row.get("target_uri") != candidate["target_uri"]
                or row.get("target_dataset") != "dbpedia"
                or row.get("status") != "verified"
                or not reviewer or reviewer.casefold().startswith("automated:")
                or not row.get("reviewed_at") or not row.get("reason")
                or str(row.get("type_compatible")).lower() != "true"):
            continue
        # A review of different candidate evidence is not a current approval.
        try:
            distance = row.get("distance_km")
            distance = None if distance in (None, "") else float(distance)
            if float(row["score"]) == candidate["score"] and distance == candidate["distance_km"]:
                return row
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _reject_identity_conflicts(reviews: list[dict], assertions: Graph, ontology: Graph) -> None:
    """Reject the whole unsafe component, without choosing an arbitrary winner.

    Pending candidates participate too: later review must not approve a known
    inconsistent identity. Contract supplies ancestry and all disjoint constructs.
    """
    contract = Contract(assertions, ontology)
    neighbours: dict[URIRef, set[URIRef]] = defaultdict(set)
    pairs = list(assertions.subject_objects(OWL.sameAs))
    pairs.extend((URIRef(row["source_uri"]), URIRef(row["target_uri"]))
                 for row in reviews if row["status"] != "rejected")
    for source, target in pairs:
        neighbours[source].add(target)
        neighbours[target].add(source)
    disjoint = sorted(set(contract.disjoint_pairs()), key=lambda triple: tuple(map(str, triple)))
    visited = set()
    rejected = {}
    for start in sorted(neighbours, key=str):
        if start in visited:
            continue
        component, pending = set(), [start]
        while pending:
            node = pending.pop()
            if node not in component:
                component.add(node)
                pending.extend(neighbours[node] - component)
        visited.update(component)
        witnesses = {}
        for node in sorted(component, key=str):
            for cls in contract.types(node):
                witnesses.setdefault(cls, node)
        conflicts = [f"{axiom}: {witnesses[left]} ({left}) <> {witnesses[right]} ({right})"
                     for left, right, axiom in disjoint if left in witnesses and right in witnesses]
        if conflicts:
            reason = "IDENTITY_TYPE_CONFLICT: " + "; ".join(conflicts)
            rejected.update({str(node): reason for node in component})
    for row in reviews:
        if row["status"] != "rejected" and row["source_uri"] in rejected:
            row["status"] = "rejected"
            row["reason"] = rejected[row["source_uri"]] + "; evidence: " + (row["reason"] or "")


def link_records(
    records: list[dict[str, Any]], *, assertions: Graph | None = None,
    ontology: Graph | None = None, link_reviews: list[dict] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (review manifest, verified links) without making network calls."""
    if assertions is None:
        assertions = Graph().parse(RDF_DIR / "vietheritage.ttl", format="turtle")
    if ontology is None:
        ontology = Graph().parse(REPO_ROOT / "ontology" / "vietheritage.ttl", format="turtle")
    reviews: list[dict[str, Any]] = []
    for record in records:
        source_uri = str(VHR[record["entity_id"]])
        external = record.get("external_ids") or {}
        qid = external.get("wikidata")
        if qid:
            if _QID_RE.fullmatch(qid):
                row = _review_row(source_uri, f"https://www.wikidata.org/entity/{qid}", "wikidata", "wikidata-qid", 1.0, "verified", reason="normalized deterministic QID")
                reviews.append(row)
            else:
                reviews.append(_review_row(source_uri, "https://www.wikidata.org/entity/INVALID", "wikidata", "wikidata-qid", 0.0, "rejected", reason="invalid QID"))

        candidates = record.get("dbpedia_candidates") or []
        if isinstance(candidates, dict):
            candidates = [candidates]
        for candidate in candidates:
            target_uri = candidate.get("uri")
            if not target_uri:
                continue
            target_label = candidate.get("label", "")
            compatible = bool(candidate.get("type_compatible", True))
            score = float(candidate.get("score", dbpedia_score(record.get("label_vi", ""), target_label, compatible)))
            distance = candidate.get("distance_km")
            status = review_dbpedia_candidate(score, distance, compatible)
            evidence = candidate.get("evidence") or "deterministic label/type/distance review"
            bridge = candidate.get("method") == "dbpedia-wikidata-sameas" or "wikidata_id" in candidate
            stale_bridge = bridge and (not qid or candidate.get("wikidata_id") != qid
                                       or _QID_RE.fullmatch(qid) is None)
            if bridge:
                evidence += f"; evidence_qid={candidate.get('wikidata_id')}; canonical_qid={qid}"
            if stale_bridge:
                status = "rejected"
                reason = "STALE_QID_BRIDGE: " + evidence
            elif status == "rejected":
                reason = "DBPEDIA_POLICY_REJECTED: " + evidence
            else:
                # Section 22.4: even auto_candidate enters the review queue.
                status = "manual_review"
                reason = "DBPEDIA_REVIEW_REQUIRED: " + evidence
            row = _review_row(
                source_uri,
                target_uri,
                "dbpedia",
                "silk",
                score,
                status,
                distance_km=distance,
                type_compatible=compatible,
                reason=reason,
            )
            approval = _approved_dbpedia_review(row, link_reviews or [])
            if status != "rejected" and approval is not None:
                row.update({key: approval[key] for key in ("reviewer", "reviewed_at", "reason")})
                row["status"] = "verified"
            reviews.append(row)
    _reject_identity_conflicts(reviews, assertions, ontology)
    reviews.sort(key=lambda row: (row["source_uri"], row["target_uri"], row["reason"] or ""))
    return reviews, [row for row in reviews if row["status"] == "verified"]


def _write_turtle(verified: list[dict[str, Any]], path: Path) -> None:
    graph = Graph()
    graph.bind("owl", OWL)
    graph.bind("vhr", VHR)
    for row in verified:
        graph.add((URIRef(row["source_uri"]), OWL.sameAs, URIRef(row["target_uri"])))
    triples = sorted(graph, key=lambda t: tuple(map(str, t)))
    ordered = Graph()
    ordered.bind("owl", OWL)
    ordered.bind("vhr", VHR)
    for triple in triples:
        ordered.add(triple)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ordered.serialize(format="turtle"), encoding="utf-8")


def run(run_mode: str = "sample", *, refresh_metadata: bool = True) -> int:
    """`make link` — canonical.jsonl -> link review + verified external links."""
    canonical_path = PROCESSED_DIR / "canonical.jsonl"
    if not canonical_path.exists():
        print(f"link: {canonical_path} not found; run map first")
        return 1
    records = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dbpedia_candidates = _load_dbpedia_candidates()
    for record in records:
        candidates = dbpedia_candidates.get(record["entity_id"])
        if candidates:
            record["dbpedia_candidates"] = candidates
    review_path = LINKING_DIR / "link_review.csv"
    previous_reviews = []
    if review_path.is_file():
        with review_path.open(encoding="utf-8", newline="") as handle:
            previous_reviews = list(csv.DictReader(handle))
    reviews, verified = link_records(records, link_reviews=previous_reviews)
    LINKING_DIR.mkdir(parents=True, exist_ok=True)
    (LINKING_DIR / "link-review.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in reviews) + ("\n" if reviews else ""), encoding="utf-8")
    with (LINKING_DIR / "link_review.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["source_uri", "target_uri", "target_dataset", "method", "score", "distance_km", "type_compatible", "status", "reviewer", "reviewed_at", "reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(reviews)
    candidates = [row for row in reviews if row["target_dataset"] == "dbpedia"]
    with (LINKING_DIR / "dbpedia_candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["source_uri", "target_uri", "score", "status", "distance_km", "type_compatible"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in candidates:
            candidate = {key: row.get(key) for key in fields}
            if row["status"] != "rejected":
                candidate["status"] = review_dbpedia_candidate(row["score"], row["distance_km"], row["type_compatible"])
            writer.writerow(candidate)
    _write_turtle(verified, RDF_DIR / "external-links.ttl")
    if refresh_metadata:
        from vietheritage.rdf.generator import refresh_dataset_metadata_metrics
        refresh_dataset_metadata_metrics()
    print(f"link ({run_mode}): {len(verified)} verified, {len(reviews)} reviewed")
    return 0
