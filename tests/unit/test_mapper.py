import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from rdflib import URIRef
from rdflib.namespace import DCTERMS

from vietheritage.mapping.mapper import DerivedRegistry, load_mapping, map_record
from vietheritage.rdf.generator import VHR, build_graph

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


def test_mapper_does_not_restore_reviewed_non_identity_wikidata_id() -> None:
    entity = {
        **_entity(),
        "_suppressed_external_ids": {"wikidata": ["Q18280"]},
    }
    page = {
        "page_id": 123, "title": "Vịnh Hạ Long",
        "source_url": "https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long",
        "retrieved_at": "2026-09-13T00:00:00Z", "wikidata_id": "Q18280",
    }
    result = map_record(entity, {"world_heritage": "HeritageSite"}, {"vịnh hạ long": page})
    assert "wikidata" not in result["external_ids"]
    assert result["source_page_id"] == 123


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


def test_thanh_nha_ho_reconciliation_handoff_keeps_one_whole_and_three_components():
    entity = {
        **_entity(),
        "_entity_id": "complex-0b2af36f62d1",
        "entity_type": "HeritageComplex",
        "registry_id": "registry-9aa10e718d44",
        "label_vi": "Di sản Văn hóa Thế giới Thành Nhà Hồ",
        "recognition_year": 2011,
        "identity_profile": {"granularity": "whole", "scope": "broad", "locations": ["Thanh Hóa"]},
        "source_records": [
            {
                "source_namespace": "dsvh", "source_record_id": "registry-9aa10e718d44",
                "source_url": "https://dsvh.gov.vn/di-tich-thanh-nha-ho-481",
                "label_vi": "Thành nhà Hồ", "registry_category": "world_heritage",
                "recognition_year": 2011, "retrieved_at": "2026-09-13T00:00:00Z",
                "provenance": {"source": "https://dsvh.gov.vn/di-tich-thanh-nha-ho-481",
                               "method": "registry", "license": "Official source"},
            },
            {
                "source_namespace": "dsvh", "source_record_id": "registry-aec3cbfb5219",
                "source_url": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-dac-biet-1752",
                "label_vi": "DTLS và KTNT Thành Nhà Hồ",
                "registry_category": "national_special_monuments", "recognition_year": 2012,
                "retrieved_at": "2026-09-13T00:00:00Z",
                "provenance": {"source": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-dac-biet-1752",
                               "method": "registry", "license": "Official source"},
            },
        ],
    }
    mapping = load_mapping()
    derived = DerivedRegistry()

    whole = map_record(entity, {"world_heritage": "HeritageSite"}, mapping=mapping, derived=derived)
    derived_records = derived.records()
    component_ids = {
        "site-4d19a4ce38d6", "site-b300f9a5ca4f", "site-c7bf6641dd4b",
    }

    assert whole["entity_id"] == "complex-0b2af36f62d1"
    assert whole["entity_type"] == "HeritageComplex"
    assert whole["recognition_year"] == 2011
    assert whole["source_records"][:2] == entity["source_records"]
    assert whole["source_records"][2]["source_namespace"] == "unesco"
    assert whole["source_records"][2]["source_record_id"] == "1358"
    assert whole["source_records"][2]["source_url"] == "https://whc.unesco.org/en/list/1358/"
    assert whole["external_ids"]["unesco"] == "1358"
    assert whole["relations"]["member_sites"] == sorted(component_ids)
    assert whole["relations"]["recognized_by"] == ["organization-unesco"]
    assert {record["entity_id"] for record in derived_records if record["entity_type"] == "HeritageSite"} == component_ids
    assert sum(record["entity_type"] == "HeritageComplex" for record in [whole, *derived_records]) == 1
    assert all(record["identity_profile"]["granularity"] == "component"
               for record in derived_records if record["entity_id"] in component_ids)
    graph = build_graph([*derived_records, whole])
    assert (VHR[whole["entity_id"]], DCTERMS.source,
            URIRef("https://whc.unesco.org/en/list/1358/")) in graph

    schema = json.loads((ROOT / "schema/canonical-record.schema.json").read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(whole))
