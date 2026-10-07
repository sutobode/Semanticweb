from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vietheritage.reporting import demo_smoke, verify


class _Response:
    def __init__(
        self,
        status_code: int = 200,
        *,
        content: bytes = b"",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload


def test_reasoning_freshness_tracks_asserted_and_ontology_inputs(
    monkeypatch: Any, tmp_path: Path
) -> None:
    ontology = tmp_path / "ontology.ttl"
    asserted = tmp_path / "asserted.ttl"
    inferred = tmp_path / "inferred.ttl"
    for path in (ontology, asserted, inferred):
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify, "ONTOLOGY", ontology)
    monkeypatch.setattr(verify, "ASSERTED", asserted)
    monkeypatch.setattr(verify, "INFERRED", inferred)

    os.utime(inferred, (1, 1))
    os.utime(ontology, (2, 2))
    os.utime(asserted, (2, 2))
    assert verify._reasoning_stale() is True

    os.utime(inferred, (3, 3))
    assert verify._reasoning_stale() is False


def test_production_resource_selects_registry_heritage_site() -> None:
    records = [
        {"entity_id": "area-a", "entity_type": "AdministrativeArea"},
        {"entity_id": "derived-site", "entity_type": "HeritageSite"},
        {
            "entity_id": "registry-site",
            "entity_type": "HeritageSite",
            "registry_id": "official-1",
        },
    ]
    assert verify._production_resource(records) == records[2]


def test_compact_jsonld_semantically_describes_canonical_resource() -> None:
    uri = "http://localhost:3030/vietheritage/resource/registry-site"
    payload = json.dumps(
        {
            "@context": {
                "vhr": "http://localhost:3030/vietheritage/resource/",
                "label": "http://www.w3.org/2000/01/rdf-schema#label",
            },
            "@id": "vhr:registry-site",
            "label": "Example site",
        }
    ).encode()

    assert verify._rdf_describes_resource(payload, "json-ld", uri) is True


def test_incorrect_jsonld_identifier_does_not_describe_canonical_resource() -> None:
    uri = "http://localhost:3030/vietheritage/resource/registry-site"
    payload = json.dumps(
        {
            "@context": {
                "vhr": "http://localhost:3030/vietheritage/resource/",
                "label": "http://www.w3.org/2000/01/rdf-schema#label",
            },
            "@id": "vhr:different-site",
            "label": "Different site",
        }
    ).encode()

    assert verify._rdf_describes_resource(payload, "json-ld", uri) is False


def test_missing_historical_coverage_is_explicit_and_non_blocking(
    monkeypatch: Any, tmp_path: Path
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(verify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(verify, "REPORTS_DIR", reports)
    records = [
        {
            "entity_id": "registry-site",
            "entity_type": "HeritageSite",
            "registry_id": "official-1",
            "coverage_snapshot": "snapshot-1",
        }
    ]

    status, evidence = verify._coverage_check(records, "full")

    assert status == "NOT_AVAILABLE"
    assert evidence["claim"] is None
    assert evidence["categories"] == 0
    assert verify._blocking_errors({"coverage": status}) == []


def test_demo_smoke_reports_all_eight_required_steps(
    monkeypatch: Any, tmp_path: Path
) -> None:
    entity_id = "registry-site"
    uri = f"http://localhost:3030/vietheritage/resource/{entity_id}"
    turtle = f"<{uri}> <http://www.w3.org/2000/01/rdf-schema#label> \"Site\"@en .".encode()

    def fake_get(url: str, **kwargs: Any) -> _Response:
        if url == "http://localhost:3030":
            return _Response()
        return _Response(content=turtle)

    reports = {
        "cq_results.json": {"passed": 10, "total": 10},
        "cypher_results.json": {"passed": 10, "total": 10, "parity_passed": 10},
    }
    monkeypatch.setattr(demo_smoke, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(demo_smoke, "_records", lambda: [])
    monkeypatch.setattr(
        demo_smoke,
        "_production_resource",
        lambda records: {
            "entity_id": entity_id,
            "entity_type": "HeritageSite",
            "registry_id": "official-1",
        },
    )
    monkeypatch.setattr(demo_smoke.requests, "get", fake_get)
    monkeypatch.setattr(demo_smoke, "is_fuseki_ready", lambda: True)
    monkeypatch.setattr(demo_smoke, "_sparql", lambda query: {"boolean": True})
    monkeypatch.setattr(demo_smoke, "load_golden", lambda: 0)
    monkeypatch.setattr(demo_smoke, "cq_run", lambda **kwargs: 0)
    monkeypatch.setattr(demo_smoke, "cypher_run", lambda: 0)
    monkeypatch.setattr(demo_smoke, "_neo4j_evidence", lambda: {"status": "PASS"})
    monkeypatch.setattr(
        demo_smoke,
        "_latest_report",
        lambda filename: (tmp_path / filename, reports[filename]),
    )

    assert demo_smoke.run() == 0
    report = json.loads(next(tmp_path.glob("*/demo_smoke.json")).read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert len(report["steps"]) == 8
    assert all(step["status"] == "PASS" for step in report["steps"])
