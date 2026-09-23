import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from vietheritage.mapping.mapper import map_record

ROOT = Path(__file__).resolve().parents[2]


def _entity() -> dict:
    return {
        "_entity_id": "registry-abc123",
        "registry_id": "registry-abc123",
        "registry_category": "world_heritage",
        "label_vi": "Vịnh Hạ Long",
        "registry_url": "https://dsvh.gov.vn/item/1",
        "source_status": "registry_only",
        "coverage_snapshot": "20260913T000000Z",
        "retrieved_at": "2026-09-13T00:00:00Z",
        "registry_fields": {"recognition_text": "1994", "location": "Quảng Ninh", "type": "Tự nhiên"},
        "aliases_vi": [],
    }


def test_mapper_uses_registry_category_for_canonical_entity_type() -> None:
    result = map_record(_entity(), {"world_heritage": "HeritageSite"})
    assert result["entity_type"] == "HeritageSite"
    assert result["source_status"] == "registry_only"
    assert result["recognition_year"] == 1994
    assert result["site_types"] == ["Tự nhiên"]
    assert "source_page_id" not in result
    assert "source_title" not in result


def test_mapper_merges_wikipedia_page_without_changing_membership() -> None:
    page = {
        "page_id": 123,
        "title": "Vịnh Hạ Long",
        "source_url": "https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long",
        "retrieved_at": "2026-09-13T00:00:00Z",
        "wikidata_id": "Q18280",
        "abstract": "Mô tả",
        "coordinates": {"lat": 20.9, "lon": 107.1},
    }
    result = map_record(_entity(), {"world_heritage": "HeritageSite"}, {"vịnh hạ long": page})
    assert result["source_status"] == "registry+wikipedia"
    assert result["external_ids"] == {"wikidata": "Q18280"}
    assert result["source_page_id"] == 123
    assert result["source_title"] == page["title"]
    assert result["registry_id"] == "registry-abc123"
    schema = json.loads((ROOT / "schema/canonical-record.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(result))


def test_mapper_output_validates_against_canonical_schema() -> None:
    schema = json.loads((ROOT / "schema/canonical-record.schema.json").read_text(encoding="utf-8"))
    result = map_record(_entity(), {"world_heritage": "HeritageSite"})
    errors = list(Draft202012Validator(schema).iter_errors(result))
    assert errors == []


def test_mapper_preserves_administrative_parent_id():
    entity = dict(_entity(), registry_category="derived_area", parent_area="area-parent")
    result = map_record(entity, {"derived_area": "AdministrativeArea"})
    assert result["parent_area"] == "area-parent"


@pytest.mark.parametrize("missing", ["source_page_id", "source_title"])
def test_enriched_canonical_schema_rejects_missing_page_metadata(missing):
    record = map_record(_entity(), {"world_heritage": "HeritageSite"})
    record.update(source_status="registry+wikipedia", source_page_id=123, source_title="Vịnh Hạ Long")
    record.pop(missing)
    schema = json.loads((ROOT / "schema/canonical-record.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(record))
