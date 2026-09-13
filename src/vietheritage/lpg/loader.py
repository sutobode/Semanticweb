"""Neo4j LPG projection loader (COMP-011)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
LINKING_DIR = REPO_ROOT / "data" / "linking"
REPORTS_DIR = REPO_ROOT / "reports"
_RELATION_TYPES = {
    "located_in": "LOCATED_IN",
    "parent_area": "LOCATED_IN",
    "associated_persons": "ASSOCIATED_WITH_PERSON",
    "associated_events": "ASSOCIATED_WITH_EVENT",
    "periods": "BELONGS_TO_PERIOD",
    "part_of": "PART_OF",
    "member_sites": "HAS_MEMBER",
    "recognized_by": "RECOGNIZED_BY",
    "architectural_styles": "HAS_ARCHITECTURAL_STYLE",
}
_ALLOWED_LABELS = {
    "CulturalHeritageEntity", "UNESCOHeritageSite",
    "HeritageSite", "AdministrativeArea", "HistoricalPerson", "HistoricalEvent",
    "HistoricalPeriod", "HeritageComplex", "Organization", "ArchitecturalStyle",
    "Museum", "IntangibleHeritage", "NationalTreasure", "DocumentaryHeritage",
    "Artisan", "CulturalObject",
}
_CULTURAL_ENTITY_TYPES = {
    "HeritageSite", "HeritageComplex", "Museum", "IntangibleHeritage",
    "NationalTreasure", "DocumentaryHeritage", "CulturalObject",
}


def _relationship_query(rel_type: str) -> str:
    return f"MATCH (a:Entity {{entityId: $source}}), (b:Entity {{entityId: $target}}) MERGE (a)-[:{rel_type}]->(b)"


def load_records(session: Any, records: list[dict[str, Any]]) -> int:
    count = 0
    for record in records:
        entity_type = record.get("entity_type")
        session.run(
            """MERGE (n:Entity {entityId: $entity_id})
               SET n.label = $label,
                   n.entityType = $entity_type,
                   n.labelEn = $label_en,
                   n.recognitionYear = $recognition_year,
                   n.lat = $lat,
                   n.lon = $lon""",
            entity_id=record["entity_id"],
            label=record.get("label_vi", ""),
            entity_type=entity_type,
            label_en=record.get("label_en"),
            recognition_year=record.get("recognition_year"),
            lat=(record.get("coordinates") or {}).get("lat"),
            lon=(record.get("coordinates") or {}).get("lon"),
        )
        if entity_type in _ALLOWED_LABELS:
            session.run(
                f"MATCH (n:Entity {{entityId: $entity_id}}) SET n:{entity_type}",
                entity_id=record["entity_id"],
            )
        if entity_type in _CULTURAL_ENTITY_TYPES:
            session.run(
                "MATCH (n:Entity {entityId: $entity_id}) SET n:CulturalHeritageEntity",
                entity_id=record["entity_id"],
            )
        if record.get("registry_category") == "world_heritage":
            session.run(
                "MATCH (n:Entity {entityId: $entity_id}) SET n:UNESCOHeritageSite",
                entity_id=record["entity_id"],
            )
        for relation_name, targets in (record.get("relations") or {}).items():
            rel_type = _RELATION_TYPES.get(relation_name)
            if not rel_type:
                continue
            if isinstance(targets, str):
                targets = [targets]
            if not isinstance(targets, list):
                continue
            for target in targets:
                session.run(_relationship_query(rel_type), source=record["entity_id"], target=target)
        wikidata_id = (record.get("external_ids") or {}).get("wikidata")
        if wikidata_id:
            external_uri = f"https://www.wikidata.org/entity/{wikidata_id}"
            session.run(
                """MATCH (n:Entity {entityId: $entity_id})
                   MERGE (external:External {uri: $uri})
                   MERGE (n)-[:SAME_AS]->(external)""",
                entity_id=record["entity_id"], uri=external_uri,
            )
        count += 1
    return count


def _load_verified_link_rows() -> list[dict[str, Any]]:
    path = LINKING_DIR / "link-review.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("status") == "verified":
                rows.append(row)
    return rows


def _project_verified_links(session: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        source_uri = str(row.get("source_uri", ""))
        target_uri = row.get("target_uri")
        if "/vietheritage/resource/" not in source_uri or not target_uri:
            continue
        entity_id = source_uri.rsplit("/", 1)[-1]
        session.run(
            """MATCH (n:Entity {entityId: $entity_id})
               MERGE (external:External {uri: $uri})
               MERGE (n)-[:SAME_AS]->(external)""",
            entity_id=entity_id,
            uri=target_uri,
        )


def run(run_mode: str = "sample") -> int:
    path = PROCESSED_DIR / "canonical.jsonl"
    if not path.exists():
        print(f"neo4j-load: {path} not found; run map first")
        return 1
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "change-me-local-only")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            count = load_records(session, records)
            session.run(
                """MERGE (n:Entity:Organization {entityId: $entity_id})
                   SET n.entityType = 'Organization',
                       n.label = 'UNESCO',
                       n.labelEn = 'UNESCO'""",
                entity_id="organization-unesco",
            )
            _project_verified_links(session, _load_verified_link_rows())
        driver.close()
    except Exception as exc:  # driver exposes several connection exception types
        print(f"neo4j-load: FAIL - {exc}")
        return 1
    report_dir = REPORTS_DIR / run_mode
    (report_dir / "neo4j_load.json").write_text(json.dumps({"status": "PASS", "nodes": count}, indent=2), encoding="utf-8")
    print(f"neo4j-load ({run_mode}): {count} nodes")
    return 0
