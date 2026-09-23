"""Canonical Mapper (COMP-004).

Maps resolved registry entities into the frozen canonical-record contract.
Registry category configuration supplies the canonical entity type; optional
Wikipedia pages enrich, but never define, registry membership.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from vietheritage.normalization.normalizer import parse_year

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RAW_DIR = REPO_ROOT / "data" / "raw"
CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"

_CANONICAL_FIELDS = {
    "entity_id", "entity_type", "label_vi", "registry_id", "registry_category",
    "registry_url", "source_status", "coverage_snapshot", "source_page_id", "source_title",
    "source_url", "retrieved_at", "aliases_vi", "description_vi", "coordinates",
    "external_ids", "relations", "site_types", "construction_year",
    "recognition_year", "address", "birth_year", "death_year", "start_year",
    "end_year", "level", "country_code", "parent_area", "museum_type",
    "organization_type", "artisan_title", "community", "location",
    "current_holder", "custodian", "object_type", "associated_intangible_heritage",
    "provenance",
}


def _norm_title(value: str) -> str:
    return " ".join(value.casefold().split())


def _load_category_types() -> dict[str, str]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return {item["key"]: item["entity_type"] for item in config["categories"]}


def _load_exact_wikidata() -> dict[str, str]:
    result: dict[str, str] = {}
    for filename in ("wikidata_exact_enrichment.jsonl", "wikidata_sparql_exact_enrichment.jsonl"):
        path = RAW_DIR / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    if row.get("entity_id") and row.get("wikidata_id"):
                        result.setdefault(row["entity_id"], row["wikidata_id"])
    return result



def _load_pages() -> dict[str, dict[str, Any]]:
    path = RAW_DIR / "pages.jsonl"
    if not path.exists():
        return {}
    pages: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                page = json.loads(line)
                pages[_norm_title(page.get("title", ""))] = page
    return pages


def _first_year(value: Any) -> int | None:
    if not isinstance(value, str):
        return value if isinstance(value, int) else None
    return parse_year(value)


def map_record(
    entity: dict[str, Any],
    category_types: dict[str, str],
    pages: dict[str, dict[str, Any]] | None = None,
    exact_wikidata: dict[str, str] | None = None,
) -> dict[str, Any]:
    category = entity.get("registry_category")
    entity_type = category_types.get(category)
    if not entity_type:
        raise ValueError(f"MAPPING_UNKNOWN_CATEGORY: {category}")
    entity_id = entity.get("_entity_id") or entity.get("entity_id")
    if not entity_id or not re.fullmatch(r"[a-z0-9-]+", entity_id):
        raise ValueError(f"MAPPING_INVALID_ENTITY_ID: {entity_id}")

    fields = entity.get("registry_fields") or {}
    page = (pages or {}).get(_norm_title(entity.get("label_vi", "")))
    external_ids: dict[str, str] = {}
    qid = (
        entity.get("wikidata_id")
        or (page or {}).get("wikidata_id")
        or (exact_wikidata or {}).get(entity_id)
    )
    if qid:
        external_ids["wikidata"] = qid

    source_status = "registry+wikipedia" if page else "registry_only"
    source_url = entity.get("registry_url")
    provenance_method = "registry-plus-mediawiki-enrichment" if page else "registry"
    record: dict[str, Any] = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "label_vi": entity["label_vi"],
        "registry_id": entity.get("registry_id"),
        "registry_category": category,
        "registry_url": source_url,
        "source_status": source_status,
        "coverage_snapshot": entity.get("coverage_snapshot"),
        "source_page_id": (page or {}).get("page_id"),
        "source_title": (page or {}).get("title"),
        "source_url": (page or {}).get("source_url") or source_url,
        "retrieved_at": entity["retrieved_at"],
        "aliases_vi": list(dict.fromkeys(entity.get("aliases_vi") or [])),
        "description_vi": (page or {}).get("abstract"),
        "coordinates": (page or {}).get("coordinates") or entity.get("coordinates"),
        "external_ids": external_ids,
        "relations": entity.get("relations") or {},
        "parent_area": entity.get("parent_area"),
        "site_types": [],
        "recognition_year": _first_year(fields.get("recognition_text")),
        "address": fields.get("location"),
        "location": fields.get("location"),
        "provenance": {
            "source": source_url,
            "method": provenance_method,
            "license": "CC BY-SA 4.0" if page else "Official registry snapshot",
        },
    }
    if fields.get("type"):
        record["site_types"] = [fields["type"]]
    if page:
        record["aliases_vi"].append(page["title"])
        record["aliases_vi"] = list(dict.fromkeys(record["aliases_vi"]))
    return {key: value for key, value in record.items() if key in _CANONICAL_FIELDS and value is not None}


def run(run_mode: str = "sample") -> int:
    """`make map` — entities.jsonl -> canonical.jsonl."""
    entities_path = PROCESSED_DIR / "entities.jsonl"
    if not entities_path.exists():
        print(f"map: {entities_path} not found; run resolve first")
        return 1
    category_types = _load_category_types()
    pages = _load_pages()
    exact_wikidata = _load_exact_wikidata()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output = PROCESSED_DIR / "canonical.jsonl"
    count = 0
    with entities_path.open(encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            canonical = map_record(json.loads(line), category_types, pages, exact_wikidata)
            target.write(json.dumps(canonical, ensure_ascii=False) + "\n")
            count += 1
    print(f"map ({run_mode}): {count} canonical records -> {output}")
    return 0
