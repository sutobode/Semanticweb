"""Entity Resolver — deterministic identity contract (COMP-003, Section 13/18).

Input: ``data/processed/normalized.jsonl``.
Output: ``data/processed/entities.jsonl``, ``identity_map.jsonl``, ``collision_report.json``.

Registry-derived entity đã có `registry_id` từ COMP-000 (Section 13.1, bậc 1).
Module này resolve identity cho derived entity (person/area/event/period/
complex/organization/style) theo Section 13.2 bậc 2-5, và merge duplicate
theo Section 13.3. Không dùng fuzzy matching (DEC-007).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

_TYPE_PREFIXES = {
    "person", "area", "event", "period", "complex", "organization", "style",
}


class IdentityCollisionError(RuntimeError):
    """IDENTITY_COLLISION — một identity key ánh xạ tới hai entity type khác nhau."""


def sha256_12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def registry_entity_id(registry_id: str) -> str:
    """Section 13.1 — registry-derived entity dùng registry-{slug(registry_id)}."""
    slug = re.sub(r"[^a-z0-9-]+", "-", registry_id.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise ValueError(f"INVALID_REGISTRY_ID: {registry_id!r}")
    if slug.startswith("registry-"):
        return slug
    return f"registry-{slug}"


def registry_fallback_id(source_url: str, registry_category: str, normalized_label: str) -> str:
    """Section 13.1 — fallback khi registry không có official ID."""
    digest = sha256_12(f"{source_url}{registry_category}{normalized_label}")
    return f"registry-{digest}"


def person_entity_id(qid: str | None, normalized_name: str) -> str:
    """Section 13.1 — person-wikidata-{QID} hoặc person-name-{hash}."""
    if qid:
        return f"person-wikidata-{qid.lower()}"
    return f"person-name-{sha256_12(normalized_name)}"


def area_entity_id(qid: str | None, normalized_name: str) -> str:
    if qid:
        return f"area-wikidata-{qid.lower()}"
    return f"area-name-{sha256_12(normalized_name)}"


def event_entity_id(normalized_name: str, start_year: int | str | None) -> str:
    year_part = str(start_year) if start_year else ""
    return f"event-{sha256_12(normalized_name + year_part)}"


def style_entity_id(normalized_name: str) -> str:
    """ArchitecturalStyle — ``style-{sha256(normalized_name)[:12]}`` (cùng họ ID với event/period)."""
    return f"style-{sha256_12(normalized_name)}"


def period_entity_id(normalized_name: str, start_year: Any, end_year: Any) -> str:
    start_part = str(start_year) if start_year else ""
    end_part = str(end_year) if end_year else ""
    return f"period-{sha256_12(normalized_name + start_part + end_part)}"


def type_prefixed_id(type_prefix: str, canonical_name: str) -> str:
    """Complex/organization/style — type prefix + canonical-name hash."""
    if type_prefix not in _TYPE_PREFIXES:
        raise ValueError(f"unknown type prefix: {type_prefix}")
    return f"{type_prefix}-{sha256_12(canonical_name)}"


def resolve_identity(record: dict[str, Any]) -> str:
    """Section 13.2 — thứ tự resolution 5 bậc, áp dụng cho derived entity.

    Registry-derived entity (có registry_id) luôn dùng bậc 1 và KHÔNG đi qua
    logic dưới đây — resolve_identity chỉ áp dụng khi record không có
    registry_id (derived/enrichment entity).
    """
    if record.get("registry_id"):
        return registry_entity_id(record["registry_id"])

    entity_type = record.get("entity_type", "")
    qid = record.get("wikidata_id")
    page_id = record.get("page_id")
    normalized_name = record.get("_identity_key") or record.get("label_vi", "").strip().lower()

    if entity_type == "HistoricalPerson":
        return person_entity_id(qid, normalized_name)
    if entity_type == "AdministrativeArea":
        return area_entity_id(qid, normalized_name)
    if entity_type == "HistoricalEvent":
        return event_entity_id(normalized_name, record.get("start_year"))
    if entity_type == "HistoricalPeriod":
        return period_entity_id(normalized_name, record.get("start_year"), record.get("end_year"))
    if entity_type == "HeritageComplex":
        return type_prefixed_id("complex", normalized_name)
    if entity_type == "Organization":
        return type_prefixed_id("organization", normalized_name)
    if entity_type == "ArchitecturalStyle":
        return type_prefixed_id("style", normalized_name)

    if qid:
        return f"derived-wikidata-{qid.lower()}"
    if page_id:
        return f"derived-page-{page_id}"
    return f"derived-{sha256_12(f'{entity_type}{normalized_name}')}"


def merge_duplicates(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Section 13.3 — merge duplicate theo entity_id, union alias/category.

    Trả (merged_records, identity_map_entries).
    """
    by_id: dict[str, dict[str, Any]] = {}
    identity_map: list[dict[str, Any]] = []

    for record in records:
        entity_id = record["_entity_id"]
        if entity_id not in by_id:
            by_id[entity_id] = dict(record)
            continue

        existing = by_id[entity_id]
        existing_type = existing.get("entity_type")
        new_type = record.get("entity_type")
        if existing_type and new_type and existing_type != new_type:
            raise IdentityCollisionError(
                f"entity_id {entity_id} maps to incompatible types: {existing_type} vs {new_type}"
            )

        merged_aliases = list(dict.fromkeys((existing.get("aliases_vi") or []) + (record.get("aliases_vi") or [])))
        existing["aliases_vi"] = merged_aliases
        merged_categories = list(dict.fromkeys((existing.get("categories") or []) + (record.get("categories") or [])))
        existing["categories"] = merged_categories
        for key, value in record.items():
            if value is not None and existing.get(key) is None:
                existing[key] = value

        identity_map.append({"entity_id": entity_id, "merged_from": record.get("registry_id") or record.get("page_id")})

    return list(by_id.values()), identity_map


MAPPING_PATH = Path(__file__).resolve().parents[3] / "config" / "mapping.yaml"


def supplement_merges(records: list[dict[str, Any]], config: dict[str, Any] | None) -> dict[str, str]:
    """Bản ghi "(bổ sung …)" -> entity_id của bản gốc cùng category (Section 13.3 merge).

    Trả {registry_id của bản bổ sung: entity_id bản gốc}. Chỉ gộp khi có đúng bản gốc
    (tên trùng sau khi bỏ viết tắt loại hình và phần bổ sung).
    """
    if not config:
        return {}
    from vietheritage.normalization.normalizer import canonical_identity_key

    supplement_re = re.compile(config["label_pattern"])
    abbreviation_re = re.compile(config.get("type_abbreviation_pattern", r"^\b$"))

    def core(label: str) -> str:
        return canonical_identity_key(abbreviation_re.sub("", supplement_re.sub("", label)))

    bases: dict[tuple[str, str], str] = {}
    for record in records:
        if record.get("registry_id") and not supplement_re.search(record.get("label_vi", "")):
            bases.setdefault((record.get("registry_category"), core(record["label_vi"])), record["_entity_id"])
    merges = {}
    for record in records:
        if record.get("registry_id") and supplement_re.search(record.get("label_vi", "")):
            base = bases.get((record.get("registry_category"), core(record["label_vi"])))
            if base:
                merges[record["registry_id"]] = base
    return merges


def run(run_mode: str = "sample") -> int:
    """`make resolve` — normalized.jsonl -> entities.jsonl + identity_map.jsonl."""
    normalized_path = PROCESSED_DIR / "normalized.jsonl"
    if not normalized_path.exists():
        print(f"resolve: {normalized_path} not found; run normalize first")
        return 1

    records: list[dict[str, Any]] = []
    with normalized_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record["_entity_id"] = resolve_identity(record)
            records.append(record)

    mapping_cfg = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8")) if MAPPING_PATH.exists() else {}
    supplements = supplement_merges(records, (mapping_cfg or {}).get("registry_supplements"))
    for record in records:
        if record.get("registry_id") in supplements:
            record["_entity_id"] = supplements[record["registry_id"]]
    # Bản gốc đứng trước bản bổ sung để merge_duplicates giữ nhãn/field của bản gốc.
    records.sort(key=lambda record: record.get("registry_id") in supplements)

    try:
        merged, identity_map = merge_duplicates(records)
    except IdentityCollisionError as exc:
        collision_report = {"status": "FAIL", "error": str(exc)}
        (PROCESSED_DIR / "collision_report.json").write_text(
            json.dumps(collision_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"resolve ({run_mode}): IDENTITY_COLLISION - {exc}")
        return 1

    entities_path = PROCESSED_DIR / "entities.jsonl"
    identity_map_path = PROCESSED_DIR / "identity_map.jsonl"
    merged_from: dict[str, list] = {}
    for entry in identity_map:
        merged_from.setdefault(entry["entity_id"], []).append(entry["merged_from"])
    for record in merged:   # registry_id của entity phải là của bản gốc
        if record.get("registry_id") in supplements:
            raise IdentityCollisionError(f"supplement {record['registry_id']} kept as primary record")
    with entities_path.open("w", encoding="utf-8") as fh:
        for record in merged:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    # Section 13.3 — mọi entity có một dòng: nguồn identity (bậc resolution) và các record đã merge.
    with identity_map_path.open("w", encoding="utf-8") as fh:
        for record in merged:
            entry = {
                "entity_id": record["_entity_id"],
                "identity_source": "registry_id" if record.get("registry_id") else (
                    "wikidata_id" if record.get("wikidata_id") else "page_id" if record.get("page_id") else "canonical_key"
                ),
                "registry_id": record.get("registry_id"),
                "registry_category": record.get("registry_category"),
                "merged_from": merged_from.get(record["_entity_id"], []),
                "merge_reason": "registry_supplement" if any(
                    rid in supplements for rid in merged_from.get(record["_entity_id"], [])) else None,
            }
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    collision_report = {"status": "PASS", "collisions": 0}
    (PROCESSED_DIR / "collision_report.json").write_text(
        json.dumps(collision_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"resolve ({run_mode}): {len(supplements)} registry supplement(s) merged into base record")
    print(f"resolve ({run_mode}): {len(merged)} entities, collision=0")
    return 0
