from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vietheritage.lpg.loader import _neo4j_config, load_records


ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, *, nodes_created: int = 0, relationships_created: int = 0) -> None:
        self._summary = SimpleNamespace(
            counters=SimpleNamespace(
                nodes_created=nodes_created,
                relationships_created=relationships_created,
            )
        )

    def consume(self) -> Any:
        return self._summary


class _Session:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.resource_ids: set[str] = set()
        self.external_uris: set[str] = set()
        self.relationships: set[tuple[str, str, str]] = set()

    def run(self, query: str, **params: Any) -> _Result:
        self.queries.append((query, params))
        if query.startswith("MERGE (n:Resource"):
            created = params["entityId"] not in self.resource_ids
            self.resource_ids.add(params["entityId"])
            return _Result(nodes_created=int(created))
        if "MERGE (e:ExternalResource" in query:
            node_created = params["targetUri"] not in self.external_uris
            self.external_uris.add(params["targetUri"])
            edge = (params["sourceUri"], "SAME_AS", params["targetUri"])
            relationship_created = edge not in self.relationships
            self.relationships.add(edge)
            return _Result(
                nodes_created=int(node_created),
                relationships_created=int(relationship_created),
            )
        match = re.search(r"MERGE \(s\)-\[:([A-Z_]+)\]->\(t\)", query)
        if match:
            edge = (params["source"], match.group(1), params["target"])
            relationship_created = edge not in self.relationships
            self.relationships.add(edge)
            return _Result(relationships_created=int(relationship_created))
        return _Result()


def _record(entity_id: str, entity_type: str = "HeritageSite", **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "label_vi": entity_id,
        "source_url": f"https://example.org/{entity_id}",
        "retrieved_at": "2026-10-07T00:00:00Z",
        "relations": {},
        "provenance": {"source": "https://example.org/source"},
    }
    record.update(overrides)
    return record


def test_constraint_required_properties_type_and_site_labels() -> None:
    session = _Session()
    record = _record(
        "site-a",
        source_url=None,
        site_types=[
            "di tích lịch sử",
            "di tích tôn giáo",
            "di tích khảo cổ",
            "di tích kiến trúc nghệ thuật",
        ],
        construction_year="1010",
        recognition_year=2010,
        coordinates={"lat": 21, "lon": 105.5},
        external_ids={"wikidata": "Q123"},
        registry_id="registry-a",
        registry_category="world_heritage",
        source_records=[
            {
                "source_namespace": "dsvh", "source_record_id": "registry-a",
                "source_url": "https://example.org/registry-a",
            },
            {
                "source_namespace": "unesco", "source_record_id": "1358",
                "source_url": "https://whc.unesco.org/en/list/1358/",
            },
        ],
        identity_profile={"granularity": "whole", "scope": "broad", "locations": ["Thanh Hóa"],
                          "communities": ["Cộng đồng địa phương"]},
        relations={"recognized_by": ["organization-unesco"]},
    )

    report = load_records(session, [record])

    constraint = session.queries[0][0]
    assert "FOR (n:Resource) REQUIRE n.entityId IS UNIQUE" in constraint
    node_query, params = next(row for row in session.queries if row[0].startswith("MERGE (n:Resource"))
    assert "SET n:HeritageSite:HistoricalSite:ReligiousSite:ArchaeologicalSite:ArchitecturalSite:UNESCOHeritageSite" in node_query
    assert "datetime($retrievedAt)" in node_query
    assert params["properties"] == {
        "entityId": "site-a",
        "uri": "http://localhost:3030/vietheritage/resource/site-a",
        "labelVi": "site-a",
        "sourceUrl": "https://example.org/source",
        "retrievedAt": "2026-10-07T00:00:00Z",
        "registryId": "registry-a",
        "registryCategory": "world_heritage",
        "sourceRecordCount": 2,
        "sourceRecordIds": ["1358", "registry-a"],
        "sourceNamespaces": ["dsvh", "unesco"],
        "sourceUrls": ["https://example.org/registry-a", "https://whc.unesco.org/en/list/1358/"],
        "identityGranularity": "whole",
        "identityScope": "broad",
        "identityLocations": ["Thanh Hóa"],
        "identityCommunities": ["Cộng đồng địa phương"],
        "constructionYear": 1010,
        "recognitionYear": 2010,
        "lat": 21.0,
        "lon": 105.5,
        "wikidataId": "Q123",
    }
    assert report["nodes_by_label"]["Resource"] == 1
    assert report["nodes_by_label"]["UNESCOHeritageSite"] == 1


def test_all_appendix_c_relationships_are_mapped() -> None:
    session = _Session()
    relations = {
        "located_in": ["target"],
        "part_of": ["target"],
        "member_sites": ["target"],
        "associated_persons": ["target"],
        "associated_events": ["target"],
        "periods": ["target"],
        "built_by": ["target"],
        "recognized_by": ["target"],
        "architectural_styles": ["target"],
    }

    report = load_records(
        session,
        [_record("source", relations=relations), _record("target", "AdministrativeArea")],
    )

    expected = {
        "LOCATED_IN",
        "PART_OF",
        "HAS_MEMBER",
        "ASSOCIATED_WITH_PERSON",
        "ASSOCIATED_WITH_EVENT",
        "BELONGS_TO_PERIOD",
        "BUILT_BY",
        "RECOGNIZED_BY",
        "HAS_ARCHITECTURAL_STYLE",
    }
    assert expected == {rel_type for _, rel_type, _ in session.relationships}
    assert report["relationships_created"] == len(expected)
    assert all(report["relationships_by_type"][rel_type]["created"] == 1 for rel_type in expected)


def test_only_verified_external_links_create_same_as_with_metadata() -> None:
    session = _Session()
    source_uri = "http://localhost:3030/vietheritage/resource/site-a"
    links = [
        {
            "source_uri": source_uri,
            "target_uri": "https://www.wikidata.org/entity/Q1",
            "target_dataset": "wikidata",
            "status": "verified",
        },
        {
            "source_uri": source_uri,
            "target_uri": "https://dbpedia.org/resource/Rejected",
            "target_dataset": "dbpedia",
            "status": "rejected",
        },
    ]

    report = load_records(session, [_record("site-a")], links)

    same_as = [row for row in session.queries if "MERGE (s)-[r:SAME_AS]" in row[0]]
    assert len(same_as) == 1
    assert "(e:ExternalResource {uri: $targetUri})" in same_as[0][0]
    assert "SET r.targetDataset = $targetDataset" in same_as[0][0]
    assert same_as[0][1]["targetDataset"] == "wikidata"
    assert report["external_resource_nodes"] == 1
    assert report["same_as"] == 1


def test_dangling_and_unsupported_references_are_reported() -> None:
    session = _Session()
    records = [
        _record(
            "site-a",
            relations={
                "located_in": ["missing-area"],
                "related_sites": ["missing-site"],
            },
        )
    ]
    links = [
        {
            "source_uri": "http://localhost:3030/vietheritage/resource/missing-site",
            "target_uri": "https://www.wikidata.org/entity/Q1",
            "target_dataset": "wikidata",
            "status": "verified",
        }
    ]

    report = load_records(session, records, links)

    assert report["skipped_dangling"] == 2
    assert {row["relation"] for row in report["dangling_references"]} == {"LOCATED_IN", "SAME_AS"}
    assert all(row["error"] == "LPG_DANGLING_REF" for row in report["dangling_references"])
    assert report["skipped_unsupported_relationships"] == 1
    assert report["unsupported_relationships"][0]["relation"] == "related_sites"


def test_repeated_loading_creates_no_duplicate_nodes_or_relationships() -> None:
    session = _Session()
    records = [
        _record("site-a", relations={"located_in": ["area-a"]}),
        _record("area-a", "AdministrativeArea"),
    ]
    links = [
        {
            "source_uri": "http://localhost:3030/vietheritage/resource/site-a",
            "target_uri": "https://www.wikidata.org/entity/Q1",
            "target_dataset": "wikidata",
            "status": "verified",
        }
    ]

    first = load_records(session, records, links)
    second = load_records(session, records, links)

    assert first["nodes_created"] == 2
    assert first["relationships_created"] == 2
    assert first["external_nodes_created"] == 1
    assert second["nodes_created"] == 0
    assert second["nodes_merged"] == 2
    assert second["relationships_created"] == 0
    assert second["relationships_merged"] == 2
    assert second["external_nodes_created"] == 0
    assert second["external_nodes_merged"] == 1
    assert len(session.resource_ids) == 2
    assert len(session.external_uris) == 1
    assert len(session.relationships) == 2


def test_neo4j_auth_uses_one_environment_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    monkeypatch.setenv("NEO4J_USER", "test-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setenv("NEO4J_DATABASE", "test-database")
    assert _neo4j_config() == (
        "bolt://example:7687",
        ("test-user", "test-password"),
        "test-database",
    )

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert '${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}' in compose
    assert "NEO4J_AUTH=" not in env_example

    monkeypatch.delenv("NEO4J_PASSWORD")
    with pytest.raises(ValueError, match="NEO4J_PASSWORD is required"):
        _neo4j_config()
