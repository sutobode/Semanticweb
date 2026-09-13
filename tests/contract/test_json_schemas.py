"""G1 contract tests — xác nhận 5 JSON Schema ở schema/ là JSON Draft 2020-12 hợp lệ
và validate đúng theo Phụ lục B của PROJECT_SPEC.md.
"""
import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"

SCHEMA_FILES = [
    "raw-page.schema.json",
    "canonical-record.schema.json",
    "run-report.schema.json",
    "coverage.schema.json",
    "link-review.schema.json",
]


@pytest.mark.parametrize("filename", SCHEMA_FILES)
def test_schema_file_is_valid_json_schema(filename: str) -> None:
    schema_path = SCHEMA_DIR / filename
    assert schema_path.exists(), f"missing schema file: {schema_path}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def _load(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def test_raw_page_schema_accepts_registry_only_record() -> None:
    schema = _load("raw-page.schema.json")
    record = {
        "registry_id": "registry-dsvh-national-monument-000001",
        "registry_category": "national_monuments",
        "label_vi": "Văn Miếu – Quốc Tử Giám",
        "registry_url": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753",
        "source_status": "registry_only",
        "coverage_snapshot": "20260913T000000Z-sample",
        "retrieved_at": "2026-09-13T00:00:00Z",
    }
    jsonschema.validate(record, schema)


def test_raw_page_schema_rejects_missing_required_field() -> None:
    schema = _load("raw-page.schema.json")
    record = {
        "registry_category": "national_monuments",
        "label_vi": "Thiếu registry_id",
        "registry_url": "https://dsvh.gov.vn/x",
        "source_status": "registry_only",
        "coverage_snapshot": "20260913T000000Z-sample",
        "retrieved_at": "2026-09-13T00:00:00Z",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(record, schema)


def test_canonical_record_schema_requires_registry_fields_when_registry_only() -> None:
    schema = _load("canonical-record.schema.json")
    record = {
        "entity_id": "registry-dsvh-national-monument-000001",
        "entity_type": "HeritageSite",
        "label_vi": "Văn Miếu – Quốc Tử Giám",
        "source_status": "registry_only",
        "retrieved_at": "2026-09-13T00:00:00Z",
        "provenance": {
            "source": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753",
            "method": "registry",
            "license": "CC BY-SA 4.0",
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(record, schema)

    record["registry_id"] = "dsvh-national-monument-000001"
    record["registry_category"] = "national_monuments"
    record["registry_url"] = "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753"
    record["coverage_snapshot"] = "20260913T000000Z-sample"
    jsonschema.validate(record, schema)


def test_canonical_record_schema_rejects_entity_type_outside_enum() -> None:
    schema = _load("canonical-record.schema.json")
    record = {
        "entity_id": "registry-x",
        "entity_type": "NationalIntangibleHeritage",
        "label_vi": "Sai entity_type",
        "source_status": "derived",
        "retrieved_at": "2026-09-13T00:00:00Z",
        "provenance": {"source": "https://example.org", "method": "derived", "license": "CC0"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(record, schema)


def test_coverage_schema_claim_enum() -> None:
    schema = _load("coverage.schema.json")
    report = {
        "snapshot_id": "20260913T000000Z-sample",
        "retrieved_at": "2026-09-13T00:00:00Z",
        "source_urls": ["https://dsvh.gov.vn/"],
        "source_checksums": {},
        "categories": [],
        "registry_total": 0,
        "canonical_total": 0,
        "registry_only": 0,
        "wikipedia_matched": 0,
        "wikidata_linked": 0,
        "dbpedia_verified": 0,
        "unresolved_registry_ids": [],
        "failure_manifest": [],
        "claim": "SKIPPED_SAMPLE_MODE",
    }
    jsonschema.validate(report, schema)


def test_link_review_schema_status_enum() -> None:
    schema = _load("link-review.schema.json")
    row = {
        "source_uri": "http://localhost:3030/vietheritage/resource/registry-x",
        "target_uri": "https://www.wikidata.org/entity/Q123",
        "target_dataset": "wikidata",
        "method": "wikidata-qid",
        "score": 1.0,
        "status": "verified",
    }
    jsonschema.validate(row, schema)


def test_run_report_schema_run_id_pattern() -> None:
    schema = _load("run-report.schema.json")
    report = {
        "run_id": "20260913T000000Z-abc123",
        "mode": "sample",
        "started_at": "2026-09-13T00:00:00Z",
        "finished_at": "2026-09-13T00:00:01Z",
        "status": "PASS",
        "counts": {"collected": 0},
        "stages": [],
        "warnings": [],
        "errors": [],
        "artifacts": [],
    }
    jsonschema.validate(report, schema)
