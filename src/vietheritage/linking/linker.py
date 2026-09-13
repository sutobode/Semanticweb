"""External linking (COMP-007): deterministic QID + reviewed DBpedia candidates."""
from __future__ import annotations

import csv
import difflib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
LINKING_DIR = REPO_ROOT / "data" / "linking"
RDF_DIR = REPO_ROOT / "data" / "rdf"
VHR = Namespace("http://localhost:3030/vietheritage/resource/")

_QID_RE = re.compile(r"^Q[1-9][0-9]*$")

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    auto_score = float(os.getenv("DBPEDIA_AUTO_ACCEPT_SCORE", "0.90"))
    review_score = float(os.getenv("DBPEDIA_REVIEW_SCORE", "0.70"))
    auto_distance = float(os.getenv("DBPEDIA_AUTO_ACCEPT_DISTANCE_KM", "5"))
    review_distance = float(os.getenv("DBPEDIA_REVIEW_DISTANCE_KM", "20"))
    if type_compatible and score >= auto_score and (distance_km is None or distance_km <= auto_distance):
        return "verified"
    if type_compatible and score >= review_score and (distance_km is None or distance_km <= review_distance):
        return "manual_review"
    return "rejected"


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
        "reviewer": None,
        "reviewed_at": None,
        "reason": extra.get("reason"),
    }


def link_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (review manifest, verified links) without making network calls."""
    reviews: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    for record in records:
        source_uri = str(VHR[record["entity_id"]])
        external = record.get("external_ids") or {}
        qid = external.get("wikidata")
        if qid:
            if _QID_RE.fullmatch(qid):
                row = _review_row(source_uri, f"https://www.wikidata.org/entity/{qid}", "wikidata", "wikidata-qid", 1.0, "verified", reason="normalized deterministic QID")
                reviews.append(row)
                verified.append(row)
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
            row = _review_row(source_uri, target_uri, "dbpedia", "silk", score, status, distance_km=distance, type_compatible=compatible, reason="deterministic label/type/distance review")
            reviews.append(row)
            if status == "verified":
                verified.append(row)
    return reviews, verified


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


def run(run_mode: str = "sample") -> int:
    """`make link` — canonical.jsonl -> link review + verified external links."""
    canonical_path = PROCESSED_DIR / "canonical.jsonl"
    if not canonical_path.exists():
        print(f"link: {canonical_path} not found; run map first")
        return 1
    records = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    reviews, verified = link_records(records)
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
        writer.writerows({key: row.get(key) for key in fields} for row in candidates)
    _write_turtle(verified, RDF_DIR / "external-links.ttl")
    print(f"link ({run_mode}): {len(verified)} verified, {len(reviews)} reviewed")
    return 0
