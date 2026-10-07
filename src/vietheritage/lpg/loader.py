from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Iterator
from uuid import uuid4

from neo4j import GraphDatabase


ROOT = Path(__file__).resolve().parents[3]

_CANONICAL_LABELS = {
    "HeritageSite",
    "AdministrativeArea",
    "HistoricalPerson",
    "HistoricalEvent",
    "HistoricalPeriod",
    "HeritageComplex",
    "Organization",
    "ArchitecturalStyle",
    "Museum",
    "IntangibleHeritage",
    "NationalTreasure",
    "DocumentaryHeritage",
    "Artisan",
    "CulturalObject",
}

_SITE_TYPE_LABELS = {
    "historicalsite": "HistoricalSite",
    "di tích lịch sử": "HistoricalSite",
    "religioussite": "ReligiousSite",
    "di tích tôn giáo": "ReligiousSite",
    "archaeologicalsite": "ArchaeologicalSite",
    "di tích khảo cổ": "ArchaeologicalSite",
    "architecturalsite": "ArchitecturalSite",
    "di tích kiến trúc nghệ thuật": "ArchitecturalSite",
}

_RELATION_TYPES = {
    "located_in": "LOCATED_IN",
    "part_of": "PART_OF",
    "member_sites": "HAS_MEMBER",
    "associated_persons": "ASSOCIATED_WITH_PERSON",
    "associated_events": "ASSOCIATED_WITH_EVENT",
    "periods": "BELONGS_TO_PERIOD",
    "built_by": "BUILT_BY",
    "recognized_by": "RECOGNIZED_BY",
    "architectural_styles": "HAS_ARCHITECTURAL_STYLE",
}

_OPTIONAL_PROPERTIES = {
    "description_vi": "descriptionVi",
    "construction_year": "constructionYear",
    "recognition_year": "recognitionYear",
    "address": "address",
    "birth_year": "birthYear",
    "death_year": "deathYear",
    "start_year": "startYear",
    "end_year": "endYear",
    "level": "areaLevel",
}

_INTEGER_PROPERTIES = {
    "constructionYear",
    "recognitionYear",
    "birthYear",
    "deathYear",
    "startYear",
    "endYear",
}

_IDENTIFIER_RE = re.compile(r"^[a-z0-9-]+$")


def _utc_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:6]}"


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _read_links(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)
        return
    yield from _read_jsonl(path)


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe entity identifier: {value}")
    return value


def _labels_for(record: dict[str, Any]) -> list[str]:
    entity_type = record.get("entity_type")
    if entity_type not in _CANONICAL_LABELS:
        raise ValueError(f"unsupported entity_type: {entity_type}")

    labels = [entity_type]
    if entity_type == "HeritageSite":
        for site_type in record.get("site_types", []) or []:
            if isinstance(site_type, str):
                label = _SITE_TYPE_LABELS.get(site_type.casefold())
                if label and label not in labels:
                    labels.append(label)
        recognized_by = (record.get("relations") or {}).get("recognized_by", [])
        if "organization-unesco" in recognized_by:
            labels.append("UNESCOHeritageSite")
    return labels


def _property_map(record: dict[str, Any]) -> dict[str, Any]:
    entity_id = _safe_identifier(str(record.get("entity_id", "")))
    label_vi = record.get("label_vi")
    retrieved_at = record.get("retrieved_at")
    source_url = record.get("source_url") or (record.get("provenance") or {}).get("source")
    if not isinstance(label_vi, str) or not label_vi.strip():
        raise ValueError("label_vi must be a non-empty string")
    if not isinstance(retrieved_at, str):
        raise ValueError("retrieved_at must be an ISO date-time string")
    try:
        datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retrieved_at must be an ISO date-time string") from exc
    if not isinstance(source_url, str) or not source_url:
        raise ValueError("source_url or provenance.source is required")

    base_uri = os.getenv("VH_BASE_URI", "http://localhost:3030/vietheritage").rstrip("/")
    properties: dict[str, Any] = {
        "entityId": entity_id,
        "uri": f"{base_uri}/resource/{entity_id}",
        "labelVi": label_vi,
        "sourceUrl": source_url,
        "retrievedAt": retrieved_at,
    }
    for source, target in _OPTIONAL_PROPERTIES.items():
        value = record.get(source)
        if value is not None:
            properties[target] = int(value) if target in _INTEGER_PROPERTIES else str(value)

    coordinates = record.get("coordinates")
    if coordinates:
        properties["lat"] = float(coordinates["lat"])
        properties["lon"] = float(coordinates["lon"])

    wikidata_id = (record.get("external_ids") or {}).get("wikidata")
    if wikidata_id:
        properties["wikidataId"] = str(wikidata_id)
    return properties


def _node_query(labels: Iterable[str]) -> str:
    label_clause = "".join(f":{label}" for label in labels)
    return (
        "MERGE (n:Resource {entityId: $entityId}) "
        "SET n = $properties "
        "SET n.retrievedAt = datetime($retrievedAt) "
        f"SET n{label_clause}"
    )


def _relationship_query(rel_type: str) -> str:
    return (
        "MATCH (s:Resource {entityId: $source}) "
        "MATCH (t:Resource {entityId: $target}) "
        f"MERGE (s)-[:{rel_type}]->(t)"
    )


def _counter(summary: Any, name: str) -> int:
    return int(getattr(getattr(summary, "counters", None), name, 0))


def _empty_relationship_counts() -> dict[str, dict[str, int]]:
    return {
        rel_type: {"created": 0, "merged": 0, "total": 0}
        for rel_type in [*_RELATION_TYPES.values(), "SAME_AS"]
    }


def load_records(
    session: Any,
    records: Iterable[dict[str, Any]],
    external_links: Iterable[dict[str, Any]] | None = None,
    *,
    ensure_constraint: bool = True,
) -> dict[str, Any]:
    if ensure_constraint:
        session.run(
            "CREATE CONSTRAINT resource_entity_id IF NOT EXISTS "
            "FOR (n:Resource) REQUIRE n.entityId IS UNIQUE"
        ).consume()

    record_list = list(records)
    rejected_records: list[dict[str, Any]] = []
    accepted: list[tuple[dict[str, Any], list[str], dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(record_list, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            relations = record.get("relations", {})
            if not isinstance(relations, dict):
                raise ValueError("relations must be an object")
            site_types = record.get("site_types", [])
            if not isinstance(site_types, list):
                raise ValueError("site_types must be a list")
            labels = _labels_for(record)
            properties = _property_map(record)
            entity_id = properties["entityId"]
            if entity_id in seen_ids:
                raise ValueError(f"duplicate entity_id: {entity_id}")
            seen_ids.add(entity_id)
            accepted.append((record, labels, properties))
        except (KeyError, TypeError, ValueError) as exc:
            rejected_records.append(
                {"record": index, "error": "LPG_INVALID_RECORD", "reason": str(exc)}
            )

    nodes_created = 0
    nodes_merged = 0
    nodes_by_label: Counter[str] = Counter()
    uri_to_entity_id: dict[str, str] = {}
    for _record, labels, properties in accepted:
        result = session.run(
            _node_query(labels),
            entityId=properties["entityId"],
            retrievedAt=properties["retrievedAt"],
            properties=properties,
        )
        summary = result.consume()
        if _counter(summary, "nodes_created"):
            nodes_created += 1
        else:
            nodes_merged += 1
        nodes_by_label.update(["Resource", *labels])
        uri_to_entity_id[properties["uri"]] = properties["entityId"]

    relationship_counts = _empty_relationship_counts()
    dangling_references: list[dict[str, Any]] = []
    unsupported_relationships: list[dict[str, Any]] = []
    accepted_ids = set(uri_to_entity_id.values())
    for record, _labels, properties in accepted:
        source_id = properties["entityId"]
        relations = dict(record.get("relations", {}))
        parent_area = record.get("parent_area")
        if parent_area:
            relations["located_in"] = list(dict.fromkeys([*relations.get("located_in", []), parent_area]))
        for relation_name, targets in relations.items():
            if not isinstance(targets, list):
                unsupported_relationships.append(
                    {"sourceEntityId": source_id, "relation": relation_name, "reason": "targets must be a list"}
                )
                continue
            rel_type = _RELATION_TYPES.get(relation_name)
            if rel_type is None:
                for target_id in targets:
                    unsupported_relationships.append(
                        {"sourceEntityId": source_id, "targetEntityId": target_id, "relation": relation_name}
                    )
                continue
            for target_id in targets:
                if not isinstance(target_id, str) or target_id not in accepted_ids:
                    dangling_references.append(
                        {
                            "sourceEntityId": source_id,
                            "targetEntityId": target_id,
                            "relation": rel_type,
                            "error": "LPG_DANGLING_REF",
                        }
                    )
                    continue
                result = session.run(
                    _relationship_query(rel_type),
                    source=source_id,
                    target=target_id,
                )
                summary = result.consume()
                key = "created" if _counter(summary, "relationships_created") else "merged"
                relationship_counts[rel_type][key] += 1
                relationship_counts[rel_type]["total"] += 1

    external_nodes_created = 0
    external_nodes_merged = 0
    external_target_uris: set[str] = set()
    rejected_external_links: list[dict[str, Any]] = []
    for index, link in enumerate(external_links or [], start=1):
        if link.get("status") != "verified":
            continue
        source_uri = link.get("source_uri")
        target_uri = link.get("target_uri")
        target_dataset = link.get("target_dataset")
        label_en = link.get("label_en") or None
        if not all(isinstance(value, str) and value for value in (source_uri, target_uri, target_dataset)):
            rejected_external_links.append(
                {"record": index, "error": "LPG_INVALID_EXTERNAL_LINK"}
            )
            continue
        if source_uri not in uri_to_entity_id:
            dangling_references.append(
                {
                    "sourceUri": source_uri,
                    "targetUri": target_uri,
                    "relation": "SAME_AS",
                    "error": "LPG_DANGLING_REF",
                }
            )
            continue
        result = session.run(
            "MATCH (s:Resource {uri: $sourceUri}) "
            "MERGE (e:ExternalResource {uri: $targetUri}) "
            "MERGE (s)-[r:SAME_AS]->(e) "
            "SET r.targetDataset = $targetDataset "
            "FOREACH (_ IN CASE WHEN $labelEn IS NULL THEN [] ELSE [1] END | SET e.labelEn = $labelEn)",
            sourceUri=source_uri,
            targetUri=target_uri,
            targetDataset=target_dataset,
            labelEn=label_en,
        )
        summary = result.consume()
        if target_uri not in external_target_uris:
            if _counter(summary, "nodes_created"):
                external_nodes_created += 1
            else:
                external_nodes_merged += 1
            external_target_uris.add(target_uri)
        key = "created" if _counter(summary, "relationships_created") else "merged"
        relationship_counts["SAME_AS"][key] += 1
        relationship_counts["SAME_AS"]["total"] += 1

    relationships_created = sum(row["created"] for row in relationship_counts.values())
    relationships_merged = sum(row["merged"] for row in relationship_counts.values())
    return {
        "canonical_records": len(record_list),
        "nodes_created": nodes_created,
        "nodes_merged": nodes_merged,
        "resource_nodes": len(accepted),
        "nodes_by_label": dict(sorted(nodes_by_label.items())),
        "external_resource_nodes": len(external_target_uris),
        "external_nodes_created": external_nodes_created,
        "external_nodes_merged": external_nodes_merged,
        "relationships_created": relationships_created,
        "relationships_merged": relationships_merged,
        "relationships_by_type": relationship_counts,
        "external_links": relationship_counts["SAME_AS"]["total"],
        "same_as": relationship_counts["SAME_AS"]["total"],
        "skipped_dangling": len(dangling_references),
        "dangling_references": dangling_references,
        "skipped_unsupported_relationships": len(unsupported_relationships),
        "unsupported_relationships": unsupported_relationships,
        "skipped_records": len(rejected_records),
        "rejected_records": rejected_records,
        "rejected_external_links": rejected_external_links,
        "status": "FAIL" if rejected_records or rejected_external_links else "PASS",
    }


def _neo4j_config() -> tuple[str, tuple[str, str], str]:
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        raise ValueError("NEO4J_PASSWORD is required")
    return (
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        (os.getenv("NEO4J_USER", "neo4j"), password),
        os.getenv("NEO4J_DATABASE", "neo4j"),
    )


def run(run_mode: str = "sample") -> int:
    canonical_path = (
        ROOT / "data" / "processed" / "canonical.jsonl"
        if run_mode == "full"
        else ROOT / "data" / "fixtures" / "canonical.jsonl"
    )
    links_path = (
        ROOT / "data" / "linking" / "link_review.csv"
        if run_mode == "full"
        else ROOT / "data" / "fixtures" / "cq-links.csv"
    )
    run_id = _utc_run_id()
    report_path = ROOT / "reports" / run_id / "neo4j_load.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter()

    try:
        uri, auth, database = _neo4j_config()
        with GraphDatabase.driver(uri, auth=auth) as driver:
            with driver.session(database=database) as session:
                report = load_records(
                    session,
                    _read_jsonl(canonical_path),
                    _read_links(links_path),
                )
    except Exception as exc:
        report = {
            "run_id": run_id,
            "canonical_records": 0,
            "nodes_created": 0,
            "nodes_merged": 0,
            "relationships_created": 0,
            "external_links": 0,
            "skipped_dangling": 0,
            "status": "FAIL",
            "error": str(exc),
        }
    report["run_id"] = run_id
    report["duration_seconds"] = round(perf_counter() - started, 3)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report_path)
    return 0 if report["status"] == "PASS" else 1
