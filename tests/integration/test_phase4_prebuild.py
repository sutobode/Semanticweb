from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from vietheritage.identity.resolver import reconcile_records


ROOT = Path(__file__).resolve().parents[2]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_all_phase4_blockers_are_classified_and_backed_by_review_config() -> None:
    with (ROOT / "docs/phase4-identity-conflict-review.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    config = yaml.safe_load((ROOT / "config/identity_reviews.yaml").read_text(encoding="utf-8"))
    configured = {item["group_id"] for item in config["decisions"]}

    assert len(rows) == len({row["review_id"] for row in rows}) == 65
    assert Counter(row["classification"] for row in rows) == {
        "AUTO_RESOLVABLE_WITH_EXISTING_RULE": 7,
        "MANUAL_DISTINCT": 28,
        "GRANULARITY_EXCEPTION": 30,
    }
    assert all(row["conflict_reason"] == "INCOMPATIBLE_LOCATION" for row in rows)
    assert all(row["evidence"] and row["decision"] for row in rows)
    for row in rows:
        reference = row["config_or_manual_review_required"]
        if reference != "no":
            assert reference.startswith("identity_reviews:")
            assert reference.split(":", 1)[1] in configured


def test_current_snapshot_reconciles_in_memory_without_blocking_conflicts() -> None:
    normalized = ROOT / "data/processed/normalized.jsonl"
    if not normalized.exists():
        pytest.skip("full normalized snapshot is not present")
    registry = yaml.safe_load((ROOT / "config/registry_sources.yaml").read_text(encoding="utf-8"))
    categories = registry["categories"]
    exact = [
        *_jsonl(ROOT / "data/raw/wikidata_exact_enrichment.jsonl"),
        *_jsonl(ROOT / "data/raw/wikidata_sparql_exact_enrichment.jsonl"),
    ]
    entities, identity_map, decisions, report = reconcile_records(
        _jsonl(normalized),
        pages=_jsonl(ROOT / "data/raw/pages.jsonl"),
        exact_wikidata=exact,
        category_types={item["key"]: item["entity_type"] for item in categories},
        category_priority={item["key"]: index for index, item in enumerate(categories)},
        mapping=yaml.safe_load((ROOT / "config/mapping.yaml").read_text(encoding="utf-8")),
        identity_reviews=yaml.safe_load((ROOT / "config/identity_reviews.yaml").read_text(encoding="utf-8")),
        default_source_namespace=registry.get("source_namespace", "dsvh"),
    )

    assert report["status"] == "PASS"
    assert report["collisions"] == 0
    assert not report["blockers"]
    assert len(report["applied_identity_reviews"]) == 12
    assert len(entities) == len(identity_map) == 999
    assert len(decisions) == 1017


def test_conflict_inventory_exactly_matches_pre_phase4_replay() -> None:
    normalized = ROOT / "data/processed/normalized.jsonl"
    if not normalized.exists():
        pytest.skip("full normalized snapshot is not present")
    registry = yaml.safe_load((ROOT / "config/registry_sources.yaml").read_text(encoding="utf-8"))
    categories = registry["categories"]
    _, _, _, report = reconcile_records(
        _jsonl(normalized),
        pages=_jsonl(ROOT / "data/raw/pages.jsonl"),
        exact_wikidata=[
            *_jsonl(ROOT / "data/raw/wikidata_exact_enrichment.jsonl"),
            *_jsonl(ROOT / "data/raw/wikidata_sparql_exact_enrichment.jsonl"),
        ],
        category_types={item["key"]: item["entity_type"] for item in categories},
        category_priority={item["key"]: index for index, item in enumerate(categories)},
        mapping=yaml.safe_load((ROOT / "config/mapping.yaml").read_text(encoding="utf-8")),
        normalize_locations=False,
        default_source_namespace=registry.get("source_namespace", "dsvh"),
    )
    with (ROOT / "docs/phase4-identity-conflict-review.csv").open(encoding="utf-8", newline="") as handle:
        classified = list(csv.DictReader(handle))

    expected = {
        row["review_id"]: (
            row["source_record_ids"], row["conflict_reason"], row["evidence"],
        )
        for row in classified
    }
    actual = {
        row["review_id"]: (
            "|".join(row["source_record_ids"]),
            "|".join(row["reason_codes"]),
            "|".join(f"{item['type']}={item['value']}" for item in row["shared_evidence"]),
        )
        for row in report["blockers"]
    }
    assert report["collisions"] == 65
    assert actual == expected
