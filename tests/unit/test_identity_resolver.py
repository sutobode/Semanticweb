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
    event_entity_id,
    merge_duplicates,
    period_entity_id,
    person_entity_id,
    registry_entity_id,
    registry_fallback_id,
    resolve_identity,
    run,
    type_prefixed_id,
)


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
