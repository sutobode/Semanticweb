"""G5 unit tests — Entity Resolver (COMP-003, TEST-012..016).

Kiểm tra deterministic identity theo Section 13.1/13.2, merge duplicate theo
13.3, và IDENTITY_COLLISION theo 13.4. KHÔNG dùng fuzzy matching (DEC-007).
"""
import json
from pathlib import Path

import pytest

from vietheritage.identity.resolver import (
    IdentityCollisionError,
    area_entity_id,
    canonical_entity_id,
    event_entity_id,
    merge_duplicates,
    period_entity_id,
    person_entity_id,
    reconcile_records,
    registry_entity_id,
    registry_fallback_id,
    resolve_identity,
    run,
    type_prefixed_id,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_registry_entity_id_uses_registry_prefix() -> None:
    assert registry_entity_id("dsvh-national-monument-000001") == "registry-dsvh-national-monument-000001"


def test_registry_entity_id_does_not_double_prefix() -> None:
    assert registry_entity_id("registry-abc") == "registry-abc"


def test_registry_fallback_id_is_deterministic() -> None:
    id1 = registry_fallback_id("https://x", "cat", "label")
    id2 = registry_fallback_id("https://x", "cat", "label")
    assert id1 == id2
    assert id1.startswith("registry-")


def test_person_entity_id_prefers_qid() -> None:
    assert person_entity_id("Q123", "nguyen van a") == "person-wikidata-q123"


def test_person_entity_id_falls_back_to_name_hash_when_no_qid() -> None:
    result = person_entity_id(None, "nguyen van a")
    assert result.startswith("person-name-")


def test_area_entity_id_prefers_qid() -> None:
    assert area_entity_id("Q456", "ha noi") == "area-wikidata-q456"


def test_event_entity_id_is_deterministic() -> None:
    id1 = event_entity_id("khoi nghia", 1789)
    id2 = event_entity_id("khoi nghia", 1789)
    assert id1 == id2
    assert id1.startswith("event-")


def test_period_entity_id_includes_start_and_end_year() -> None:
    id1 = period_entity_id("thoi ky", 1000, 1500)
    id2 = period_entity_id("thoi ky", 1000, 1600)
    assert id1 != id2


def test_type_prefixed_id_for_complex_organization_style() -> None:
    complex_id = type_prefixed_id("complex", "thang long")
    org_id = type_prefixed_id("organization", "unesco")
    style_id = type_prefixed_id("style", "gothic")
    assert complex_id.startswith("complex-")
    assert org_id.startswith("organization-")
    assert style_id.startswith("style-")


def test_type_prefixed_id_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        type_prefixed_id("unknown", "x")


def test_resolve_identity_registry_derived_uses_tier_1() -> None:
    record = {"registry_id": "dsvh-abc", "entity_type": "HeritageSite"}
    assert resolve_identity(record) == "registry-dsvh-abc"


def test_resolve_identity_person_with_qid_uses_tier_2() -> None:
    record = {"entity_type": "HistoricalPerson", "wikidata_id": "Q999", "_identity_key": "ly thuong kiet"}
    assert resolve_identity(record) == "person-wikidata-q999"


def test_resolve_identity_person_without_qid_uses_name_hash() -> None:
    record = {"entity_type": "HistoricalPerson", "_identity_key": "ly thuong kiet"}
    result = resolve_identity(record)
    assert result.startswith("person-name-")


def test_resolve_identity_is_stable_across_calls() -> None:
    record = {"entity_type": "AdministrativeArea", "_identity_key": "ha noi"}
    assert resolve_identity(record) == resolve_identity(dict(record))


def test_merge_duplicates_unions_aliases_and_categories() -> None:
    records = [
        {"_entity_id": "registry-a", "entity_type": "HeritageSite", "aliases_vi": ["A"], "categories": ["Cat1"]},
        {"_entity_id": "registry-a", "entity_type": "HeritageSite", "aliases_vi": ["B"], "categories": ["Cat2"]},
    ]
    merged, identity_map = merge_duplicates(records)
    assert len(merged) == 1
    assert set(merged[0]["aliases_vi"]) == {"A", "B"}
    assert set(merged[0]["categories"]) == {"Cat1", "Cat2"}
    assert len(identity_map) == 1


def test_merge_duplicates_raises_identity_collision_on_incompatible_types() -> None:
    records = [
        {"_entity_id": "shared-id", "entity_type": "HeritageSite"},
        {"_entity_id": "shared-id", "entity_type": "HistoricalPerson"},
    ]
    with pytest.raises(IdentityCollisionError):
        merge_duplicates(records)


def test_merge_duplicates_no_collision_when_same_type() -> None:
    records = [
        {"_entity_id": "registry-a", "entity_type": "HeritageSite"},
        {"_entity_id": "registry-b", "entity_type": "HistoricalPerson"},
    ]
    merged, _ = merge_duplicates(records)
    assert len(merged) == 2


def test_run_writes_entities_and_collision_report_pass(tmp_path: Path, monkeypatch) -> None:
    import vietheritage.identity.resolver as resolver_module

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    normalized_path = processed_dir / "normalized.jsonl"
    normalized_path.write_text(
        json.dumps({"registry_id": "dsvh-1", "entity_type": "HeritageSite", "label_vi": "A"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver_module, "PROCESSED_DIR", processed_dir)

    exit_code = run(run_mode="sample")
    assert exit_code == 0
    entities_path = processed_dir / "entities.jsonl"
    collision_path = processed_dir / "collision_report.json"
    assert entities_path.exists()
    collision_report = json.loads(collision_path.read_text(encoding="utf-8"))
    assert collision_report["status"] == "PASS"


def test_run_returns_nonzero_and_fail_status_on_collision(tmp_path: Path, monkeypatch) -> None:
    import vietheritage.identity.resolver as resolver_module

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    normalized_path = processed_dir / "normalized.jsonl"
    lines = [
        {"registry_id": "same-id", "entity_type": "HeritageSite", "label_vi": "A"},
        {"registry_id": "same-id", "entity_type": "HistoricalPerson", "label_vi": "B"},
    ]
    normalized_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(resolver_module, "PROCESSED_DIR", processed_dir)

    exit_code = run(run_mode="sample")
    assert exit_code == 1
    collision_report = json.loads((processed_dir / "collision_report.json").read_text(encoding="utf-8"))
    assert collision_report["status"] == "FAIL"


def _source_record(
    source_id: str,
    *,
    entity_type: str = "HeritageSite",
    label: str = "Di tích A",
    location: str = "Tỉnh A",
    **extra,
) -> dict:
    record = {
        "registry_id": source_id,
        "registry_category": "national_monuments",
        "entity_type": entity_type,
        "label_vi": label,
        "registry_url": f"https://dsvh.gov.vn/{source_id}",
        "retrieved_at": "2026-10-08T00:00:00Z",
        "registry_fields": {"location": location},
    }
    record.update(extra)
    return record


def _reconcile(records: list[dict], **kwargs):
    return reconcile_records(
        records,
        category_types={"national_monuments": "HeritageSite"},
        category_priority={"world_heritage": 0, "national_special_monuments": 1, "national_monuments": 2},
        **kwargs,
    )


def test_phase2_thanh_nha_ho_fixture_keeps_one_whole_and_three_components() -> None:
    fixture = json.loads((FIXTURES / "identity_phase2.json").read_text(encoding="utf-8"))
    entities, identity_map, decisions, report = reconcile_records(
        fixture["records"],
        pages=fixture["pages"],
        mapping=fixture["mapping"],
        category_types={
            "world_heritage": "HeritageSite",
            "national_special_monuments": "HeritageSite",
        },
        category_priority={"world_heritage": 0, "national_special_monuments": 1},
    )

    assert report["status"] == "PASS"
    assert {entity["_entity_id"] for entity in entities} == {
        "complex-0b2af36f62d1",
        "site-4d19a4ce38d6",
        "site-b300f9a5ca4f",
        "site-c7bf6641dd4b",
    }
    whole = next(entity for entity in entities if entity["entity_type"] == "HeritageComplex")
    assert whole["registry_id"] == "registry-9aa10e718d44"
    assert [item["source_record_id"] for item in whole["source_records"]] == [
        "registry-9aa10e718d44", "registry-aec3cbfb5219",
    ]
    assert [item["recognition_year"] for item in whole["source_records"]] == [2011, 2012]
    assert next(item for item in identity_map if item["entity_id"] == whole["_entity_id"])["merged_from"] == [
        "registry-aec3cbfb5219"
    ]
    assert len(decisions) == 5


def test_reconciliation_is_independent_of_input_order_and_labels() -> None:
    records = [
        _source_record("registry-b", wikidata_id="Q1", label="Tên B"),
        _source_record("registry-a", wikidata_id="Q1", label="Tên A"),
    ]
    first = _reconcile(records)
    renamed = [dict(record, label_vi=f"Nhãn mới {index}") for index, record in enumerate(reversed(records))]
    second = _reconcile(renamed)

    assert first[0][0]["_entity_id"] == second[0][0]["_entity_id"]
    assert first[1][0]["source_record_ids"] == second[1][0]["source_record_ids"] == ["registry-a", "registry-b"]


@pytest.mark.parametrize(
    ("left_extra", "right_extra", "expected_reason"),
    [
        ({"entity_type": "HeritageComplex"}, {}, "WHOLE_TYPE_CONFLICT"),
        ({"_identity_granularity": "whole"}, {"_identity_granularity": "component"}, "WHOLE_COMPONENT_CONFLICT"),
        ({"_identity_scope": "broad"}, {"_identity_scope": "localized"}, "BROAD_LOCALIZED_CONFLICT"),
        ({"wikidata_id": "Q1", "page_id": 10}, {"wikidata_id": "Q2", "page_id": 10}, "CONFLICTING_WIKIDATA_ID"),
        ({"wikidata_id": "Q1"}, {"wikidata_id": "Q1", "registry_fields": {"location": "Tỉnh B"}}, "INCOMPATIBLE_LOCATION"),
        ({"wikidata_id": "Q1", "relations": {"part_of": ["registry-b"]}}, {"wikidata_id": "Q1"}, "MERGE_CREATES_SELF_RELATION"),
    ],
)
def test_reconciliation_blocks_incompatible_strong_identity_components(
    left_extra: dict, right_extra: dict, expected_reason: str,
) -> None:
    left = _source_record("registry-a", **{"wikidata_id": "Q1", **left_extra})
    right = _source_record("registry-b", **{"wikidata_id": "Q1", **right_extra})
    entities, _, decisions, report = _reconcile([left, right])

    assert len(entities) == 2
    assert report["status"] == "FAIL"
    assert expected_reason in {reason for blocker in report["blockers"] for reason in blocker["reason_codes"]}
    assert {decision["decision"] for decision in decisions} == {"manual_review"}


def test_conflicting_identifiers_on_one_source_record_are_blocking() -> None:
    record = _source_record(
        "registry-a",
        _identity_evidence={"wikidata_ids": ["Q1", "Q2"]},
    )
    _, _, decisions, report = _reconcile([record])

    assert report["status"] == "FAIL"
    assert report["blockers"][0]["reason_codes"] == ["CONFLICTING_WIKIDATA_ID"]
    assert decisions[0]["decision"] == "manual_review"


def test_different_domain_namespaces_are_compatible() -> None:
    record = _source_record(
        "registry-a",
        external_ids={"unesco": "1358", "local": "TH-001"},
    )
    entities, _, _, report = _reconcile([record])

    assert len(entities) == 1
    assert report["status"] == "PASS"


def test_incompatible_member_does_not_prevent_compatible_subcomponent_merge() -> None:
    records = [
        _source_record("registry-a", wikidata_id="Q1", _identity_granularity="whole"),
        _source_record("registry-b", wikidata_id="Q1", _identity_granularity="component"),
        _source_record("registry-c", wikidata_id="Q1", _identity_granularity="component"),
    ]
    entities, identity_map, _, report = _reconcile(records)

    assert len(entities) == 2
    assert report["status"] == "FAIL"
    assert any(entry["source_record_ids"] == ["registry-b", "registry-c"] for entry in identity_map)


def test_alias_and_location_match_only_creates_manual_review_candidate() -> None:
    records = [
        _source_record("registry-a", label="Tên chính", location="Tỉnh A"),
        _source_record("registry-b", label="Tên khác", location="Tỉnh A", aliases_vi=["Tên chính"]),
    ]
    entities, _, decisions, report = _reconcile(records)

    assert len(entities) == 2
    assert report["status"] == "PASS"
    assert report["reviews"][0]["reason_codes"] == ["WEAK_ALIAS_SCOPE_CANDIDATE"]
    assert {decision["decision"] for decision in decisions} == {"manual_review"}


def test_component_page_link_is_not_used_as_whole_identity_evidence() -> None:
    records = [_source_record("registry-a"), _source_record("registry-b")]
    pages = [{
        "page_id": 10,
        "wikidata_id": "Q1",
        "registry_links": [
            {"registry_id": "registry-a", "part_label": "Thành phần A"},
            {"registry_id": "registry-b", "part_label": "Thành phần B"},
        ],
    }]
    entities, _, _, report = _reconcile(records, pages=pages)

    assert len(entities) == 2
    assert report["status"] == "PASS"


def test_run_enriches_before_reconciliation_and_writes_decision_manifest(tmp_path: Path, monkeypatch) -> None:
    import vietheritage.identity.resolver as resolver_module

    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    config_dir = tmp_path / "config"
    raw_dir.mkdir()
    processed_dir.mkdir()
    config_dir.mkdir()
    records = [_source_record("registry-a"), _source_record("registry-b")]
    (processed_dir / "normalized.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    page = {"page_id": 10, "wikidata_id": "Q1", "registry_ids": ["registry-a", "registry-b"]}
    (raw_dir / "pages.jsonl").write_text(json.dumps(page) + "\n", encoding="utf-8")
    registry_config = {
        "source_namespace": "dsvh",
        "categories": [{"key": "national_monuments", "entity_type": "HeritageSite"}],
    }
    (config_dir / "registry_sources.yaml").write_text(json.dumps(registry_config), encoding="utf-8")
    (config_dir / "mapping.yaml").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(resolver_module, "RAW_DIR", raw_dir)
    monkeypatch.setattr(resolver_module, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(resolver_module, "REGISTRY_CONFIG_PATH", config_dir / "registry_sources.yaml")
    monkeypatch.setattr(resolver_module, "MAPPING_PATH", config_dir / "mapping.yaml")

    assert run(run_mode="sample") == 0
    entities = [json.loads(line) for line in (processed_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines()]
    decisions = [json.loads(line) for line in (processed_dir / "identity_decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(entities) == 1
    assert len(entities[0]["source_records"]) == 2
    assert {decision["decision"] for decision in decisions} == {"selected_source", "attached_evidence"}
    assert canonical_entity_id("HeritageSite", "dsvh:registry-a") == entities[0]["_entity_id"]
