"""Canonical Mapper (COMP-004).

Maps resolved registry entities into the frozen canonical-record contract.
Registry category configuration supplies the canonical entity type; optional
Wikipedia pages enrich, but never define, registry membership.

Quy tắc M2 (``M2_REMAINING_WORK.md``):

* Ý nghĩa cột registry đọc từ ``config/mapping.yaml`` (``registry_field_roles``),
  required field theo ``entity_types[*].required_fields`` (TEST-020 quarantine).
* M2-01: ``recognition_year`` bỏ qua số hiệu quyết định.
* M2-10: ``location`` -> ``AdministrativeArea`` (``config/areas.yaml``) +
  ``relations.located_in``; record ``AdministrativeArea`` được sinh thêm.
  DEC-M2-004: tỉnh công bố là đơn vị SAU sắp xếp 2025 (34 tỉnh/thành).
* M2-11: ``site_types`` chỉ cho ``HeritageSite``.
* M2-12: ``world_heritage`` -> ``relations.recognized_by = [organization-unesco]``
  và record ``Organization`` tương ứng (DEC-013).
* M2-13/15: page Wikipedia join theo ``registry_ids``; quan hệ Wikipedia chỉ
  được map khi collector đã xác minh bằng Wikidata P31.
* Output: entity phái sinh (area, organization, person, …) đứng TRƯỚC registry
  record để loader một lượt (Neo4j MATCH) luôn thấy node đích.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vietheritage.identity.resolver import (
    event_entity_id,
    period_entity_id,
    person_entity_id,
    style_entity_id,
)
from vietheritage.normalization.normalizer import (
    canonical_identity_key,
    dedupe_aliases,
    iri_to_uri,
    is_valid_uri,
    parse_recognition_year,
    parse_year,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RAW_DIR = REPO_ROOT / "data" / "raw"
REPORTS_DIR = REPO_ROOT / "reports"
CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
MAPPING_PATH = REPO_ROOT / "config" / "mapping.yaml"
SCHEMA_PATH = REPO_ROOT / "schema" / "canonical-record.schema.json"

COVERAGE_CLAIM = "100% of selected official registry snapshot"
REGISTRY_LICENSE = "Official registry snapshot"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"

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

_DEFAULT_ROLES = {
    "location": ["address", "location", "located_in"],
    "recognition_text": ["recognition_year"],
    "type": ["site_types"],
}


def _norm_title(value: str) -> str:
    return " ".join(value.casefold().split())


def _load_category_types() -> dict[str, str]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return {item["key"]: item["entity_type"] for item in config["categories"]}


def _load_category_urls() -> dict[str, str]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return {item["key"]: item["url"] for item in config["categories"]}


def load_mapping(path: Path = MAPPING_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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


class PageIndex:
    """Page Wikipedia theo ``registry_id`` (M2-13); fallback theo tiêu đề cho
    ``pages.jsonl`` thế hệ cũ chưa có ``registry_ids``.

    ``registry_links`` (collector v2) ghi từng liên kết record -> page kèm ``part_label``:
    record có >= 2 liên kết có ``part_label`` là di tích gộp và được tách (``links_for``).
    """

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.by_registry_id: dict[str, dict[str, Any]] = {}
        self.links: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        self.by_title: dict[str, dict[str, Any]] = {}
        for page in pages:
            links = page.get("registry_links") or [
                {"registry_id": registry_id, "part_label": None} for registry_id in page.get("registry_ids") or []]
            if links:
                for link in links:
                    self.by_registry_id.setdefault(link["registry_id"], page)
                    self.links.setdefault(link["registry_id"], []).append((page, link))
            else:
                self.by_title[_norm_title(page.get("title", ""))] = page

    def for_entity(self, entity: dict[str, Any]) -> dict[str, Any] | None:
        registry_id = entity.get("registry_id")
        if registry_id and registry_id in self.by_registry_id:
            return self.by_registry_id[registry_id]
        return self.by_title.get(_norm_title(entity.get("label_vi", "")))

    def parts_for(self, entity: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
        """[(page, part_label)] nếu record là di tích gộp có >= 2 thành phần có bài, ngược lại []."""
        parts = [(page, link["part_label"]) for page, link in self.links.get(entity.get("registry_id") or "", [])
                 if link.get("part_label")]
        return parts if len(parts) >= 2 else []

    def __len__(self) -> int:
        return len(self.by_registry_id) + len(self.by_title)


def _load_pages() -> PageIndex:
    path = RAW_DIR / "pages.jsonl"
    pages: list[dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            pages = [json.loads(line) for line in handle if line.strip()]
    return PageIndex(pages)


def _first_year(value: Any) -> int | None:
    """Tương thích API cũ: năm đầu tiên trong chuỗi (dùng cho NOR-005)."""
    if not isinstance(value, str):
        return value if isinstance(value, int) else None
    return parse_year(value)


def _roles_for(mapping: dict[str, Any], category: str | None) -> dict[str, list[str]]:
    roles = mapping.get("registry_field_roles") or {}
    if category and category in roles:
        return roles[category]
    return roles.get("default") or _DEFAULT_ROLES


def _default_area_resolver():
    from vietheritage.normalization.areas import default_resolver

    return default_resolver()


def _wiki_url(title: str) -> str:
    from vietheritage.collector.wikipedia import wiki_url

    return wiki_url(title)


class DerivedRegistry:
    """Gom entity phái sinh (area, organization, person, …) được record tham chiếu."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.area_warnings: list[dict[str, Any]] = []

    def add(self, entity_id: str, entity_type: str, *, sources: list[str], retrieved_at: str | None,
            coverage_snapshot: str | None, method: str, license_text: str, **fields: Any) -> str:
        item = self.items.get(entity_id)
        if item is None:
            item = {"entity_id": entity_id, "entity_type": entity_type, "_sources": set(),
                    "_retrieved": set(), "_snapshots": set(), "_methods": set(), "_licenses": set(), **fields}
            self.items[entity_id] = item
        elif item["entity_type"] != entity_type:
            raise ValueError(f"IDENTITY_COLLISION: {entity_id} maps to {item['entity_type']} and {entity_type}")
        item["_sources"].update(iri_to_uri(s) for s in sources if s)
        if retrieved_at:
            item["_retrieved"].add(retrieved_at)
        if coverage_snapshot:
            item["_snapshots"].add(coverage_snapshot)
        item["_methods"].add(method)
        item["_licenses"].add(license_text)
        return entity_id

    def records(self) -> list[dict[str, Any]]:
        out = []
        for entity_id in sorted(self.items):
            item = dict(self.items[entity_id])
            sources = sorted(item.pop("_sources"))
            retrieved = sorted(item.pop("_retrieved"))
            snapshots = sorted(item.pop("_snapshots"))
            methods = item.pop("_methods")
            licenses = sorted(item.pop("_licenses"))
            record = {
                **item,
                "source_status": "derived",
                "coverage_snapshot": snapshots[-1] if snapshots else None,
                "retrieved_at": retrieved[0] if retrieved else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "provenance": {
                    "source": sources[0],
                    "method": "mediawiki-api" if methods == {"mediawiki-api"} else "derived",
                    "license": "; ".join(licenses),
                },
            }
            if item.get("source_url") is None:
                record.pop("source_url", None)
            out.append({key: value for key, value in record.items() if key in _CANONICAL_FIELDS and value is not None})
        return out


def _add_relation(record: dict[str, Any], name: str, target_id: str) -> None:
    targets = record["relations"].setdefault(name, [])
    if target_id not in targets:
        targets.append(target_id)


def _map_wikipedia_relations(record: dict[str, Any], page: dict[str, Any], mapping: dict[str, Any],
                             derived: DerivedRegistry | None) -> None:
    if derived is None or record["entity_type"] != "HeritageSite":
        return
    allowed = mapping.get("wikipedia_relations") or {}
    for candidate in page.get("relation_candidates") or []:
        relation = candidate.get("relation")
        target_type = allowed.get(relation)
        if not candidate.get("verified") or target_type != candidate.get("target_type") or not candidate.get("title"):
            continue
        title = candidate["title"]
        name_key = canonical_identity_key(title)
        qid = candidate.get("qid")
        if target_type == "HistoricalPerson":
            target_id = person_entity_id(qid, name_key)
        elif target_type == "HistoricalEvent":
            target_id = event_entity_id(name_key, None)
        elif target_type == "HistoricalPeriod":
            target_id = period_entity_id(name_key, None, None)
        elif target_type == "ArchitecturalStyle":
            target_id = style_entity_id(name_key)
        else:
            continue
        extra: dict[str, Any] = {"label_vi": title, "source_url": iri_to_uri(_wiki_url(title))}
        if candidate.get("page_id"):
            extra.update(source_page_id=candidate["page_id"], source_title=title)
        if qid:
            extra["external_ids"] = {"wikidata": qid}
        derived.add(
            target_id, target_type, sources=[_wiki_url(title)], retrieved_at=page.get("retrieved_at"),
            coverage_snapshot=record.get("coverage_snapshot"), method="mediawiki-api",
            license_text=WIKIPEDIA_LICENSE, **extra,
        )
        _add_relation(record, relation, target_id)


def site_types_from_label(label: str, mapping: dict[str, Any]) -> list[str]:
    """M2-11 — loại hình từ tiền tố viết tắt trong tên (DTLS, DTKTNT, DTKC, DLTC…)."""
    spec = mapping.get("site_type_label_abbreviations") or {}
    if not spec:
        return []
    match = re.match(spec["prefix_pattern"], label or "")
    if not match:
        return []
    tokens = spec.get("tokens") or {}
    found = re.findall(r"\b(" + "|".join(sorted(map(re.escape, tokens), key=len, reverse=True)) + r")\b", match.group(0))
    return list(dict.fromkeys(tokens[token] for token in found))


def _construction_year(page: dict[str, Any], mapping: dict[str, Any]) -> int | None:
    spec = (mapping.get("infobox_fields") or {}).get("construction_year")
    if not spec:
        return None
    pattern = re.compile(spec["key_pattern"])
    for key, value in (page.get("infobox") or {}).items():
        if pattern.search(key):
            year = parse_recognition_year(value, min_year=int(spec.get("min_year", 1)))
            if year is not None:
                return year
    return None


def map_record(
    entity: dict[str, Any],
    category_types: dict[str, str],
    pages: dict[str, dict[str, Any]] | PageIndex | None = None,
    exact_wikidata: dict[str, str] | None = None,
    *,
    mapping: dict[str, Any] | None = None,
    area_resolver=None,
    derived: DerivedRegistry | None = None,
    category_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    mapping = mapping if mapping is not None else load_mapping()
    category = entity.get("registry_category")
    entity_type = category_types.get(category)
    if not entity_type:
        raise ValueError(f"MAPPING_UNKNOWN_CATEGORY: {category}")
    entity_id = entity.get("_entity_id") or entity.get("entity_id")
    if not entity_id or not re.fullmatch(r"[a-z0-9-]+", entity_id):
        raise ValueError(f"MAPPING_INVALID_ENTITY_ID: {entity_id}")

    fields = entity.get("registry_fields") or {}
    if isinstance(pages, PageIndex):
        page = pages.for_entity(entity)
    else:
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
    registry_url = iri_to_uri(entity.get("registry_url"))
    provenance_method = "registry-plus-mediawiki-enrichment" if page else "registry"
    record: dict[str, Any] = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "label_vi": entity["label_vi"],
        "registry_id": entity.get("registry_id"),
        "registry_category": category,
        "registry_url": registry_url,
        "source_status": source_status,
        "coverage_snapshot": entity.get("coverage_snapshot"),
        "source_page_id": (page or {}).get("page_id"),
        "source_title": (page or {}).get("title"),
        "source_url": iri_to_uri((page or {}).get("source_url")) or registry_url,
        "retrieved_at": entity["retrieved_at"],
        "aliases_vi": [],
        "description_vi": (page or {}).get("abstract"),
        "coordinates": (page or {}).get("coordinates") or entity.get("coordinates"),
        "external_ids": external_ids,
        "relations": {key: list(value) for key, value in (entity.get("relations") or {}).items()},
        "parent_area": entity.get("parent_area"),
        "site_types": [],
        "provenance": {
            "source": registry_url,
            "method": provenance_method,
            "license": WIKIPEDIA_LICENSE if page else REGISTRY_LICENSE,
        },
    }

    for column, targets in _roles_for(mapping, category).items():
        value = fields.get(column)
        if value in (None, ""):
            continue
        for target in targets:
            if target == "recognition_year":
                record["recognition_year"] = parse_recognition_year(value)
            elif target == "site_types":
                if entity_type == "HeritageSite":
                    record["site_types"] = [value]
            elif target == "located_in":
                resolver = area_resolver or _default_area_resolver()
                # DEC-M2-004: công bố theo đơn vị sau sắp xếp 2025 (config/areas.yaml > publish_level).
                match = resolver.resolve_published(value)
                for area in match.areas:
                    _add_relation(record, "located_in", area.entity_id)
                    if derived is not None:
                        source = (category_urls or {}).get(category) or registry_url
                        derived.add(
                            area.entity_id, "AdministrativeArea", sources=[source],
                            retrieved_at=entity.get("retrieved_at"), coverage_snapshot=entity.get("coverage_snapshot"),
                            method="derived", license_text=REGISTRY_LICENSE,
                            label_vi=area.label, aliases_vi=list(area.display_aliases),
                            level=area.level, country_code=resolver.country_code,
                        )
                if derived is not None and match.warnings:
                    derived.area_warnings.append({
                        "entity_id": entity_id, "registry_category": category,
                        "location": value, "warnings": match.warnings,
                    })
            elif target in _CANONICAL_FIELDS:
                record[target] = value

    for derived_id, spec in (mapping.get("derived_entities") or {}).items():
        attach = spec.get("attach") or {}
        if attach.get("registry_category") == category and entity_type == "HeritageSite":
            _add_relation(record, attach["relation"], derived_id)
            if derived is not None:
                source = (category_urls or {}).get(category) or registry_url
                extra = {k: v for k, v in spec.items() if k not in {"entity_type", "attach"}}
                derived.add(derived_id, spec["entity_type"], sources=[source],
                            retrieved_at=entity.get("retrieved_at"), coverage_snapshot=entity.get("coverage_snapshot"),
                            method="derived", license_text=REGISTRY_LICENSE, **extra)

    if entity_type == "HeritageSite":
        # Record tách từ di tích gộp giữ loại hình của TÊN TRONG REGISTRY ("DTLS và DLTC …").
        for site_type in site_types_from_label(entity.get("_registry_label") or record["label_vi"], mapping):
            if site_type not in record["site_types"]:
                record["site_types"].append(site_type)

    if page:
        if entity_type == "HeritageSite":
            record["construction_year"] = _construction_year(page, mapping)
        _map_wikipedia_relations(record, page, mapping, derived)

    alias_inputs = list(entity.get("aliases_vi") or [])
    if page:
        alias_inputs += [page.get("title") or "", *(page.get("requested_labels") or [])]
    record["aliases_vi"] = dedupe_aliases(record["label_vi"], [a for a in alias_inputs if a])
    record["relations"] = {name: sorted(targets) for name, targets in sorted(record["relations"].items()) if targets}
    return {key: value for key, value in record.items() if key in _CANONICAL_FIELDS and value is not None}


def map_entity(
    entity: dict[str, Any],
    category_types: dict[str, str],
    pages: PageIndex,
    exact_wikidata: dict[str, str] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Một registry entity -> 1 canonical record, hoặc N record nếu là di tích gộp.

    Record tách ("Hồ Hoàn Kiếm và Đền Ngọc Sơn" -> "Hồ Hoàn Kiếm", "Đền Ngọc Sơn"): cùng
    ``registry_id`` và thông tin dsvh (năm, địa chỉ, tỉnh, loại hình), nhãn = tên thành phần,
    tên đầy đủ trong registry vào ``aliases_vi``, thông tin Wikipedia lấy từ bài của thành phần.
    ``entity_id`` = ``<entity_id gốc>-<sha256(tên thành phần)[:6]>``.
    """
    parts = pages.parts_for(entity)
    if not parts:
        return [map_record(entity, category_types, pages, exact_wikidata, **kwargs)]
    records = []
    base_id = entity.get("_entity_id") or entity.get("entity_id")
    for page, part_label in parts:
        part = dict(entity)
        part["_entity_id"] = f"{base_id}-{hashlib.sha256(canonical_identity_key(part_label).encode('utf-8')).hexdigest()[:6]}"
        part["label_vi"] = part_label
        part["_registry_label"] = entity["label_vi"]
        part["aliases_vi"] = list(dict.fromkeys([*(entity.get("aliases_vi") or []), entity["label_vi"]]))
        part.pop("wikidata_id", None)
        records.append(map_record(part, category_types, PageIndex([dict(page, registry_links=[], registry_ids=[entity["registry_id"]])]),
                                  None, **kwargs))
    return records


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

def _schema_validator():
    from jsonschema import Draft202012Validator, FormatChecker

    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker())


def validate_canonical(record: dict[str, Any], mapping: dict[str, Any], validator=None) -> list[str]:
    """TEST-020 — lỗi JSON Schema + required field theo entity type (mapping.yaml)."""
    problems = []
    required = ((mapping.get("entity_types") or {}).get(record.get("entity_type"), {}) or {}).get("required_fields") or []
    for name in required:
        if record.get(name) in (None, "", [], {}):
            problems.append(f"MAPPING_REQUIRED_MISSING:{name}")
    for path, value in (("registry_url", record.get("registry_url")), ("source_url", record.get("source_url")),
                        ("provenance/source", (record.get("provenance") or {}).get("source"))):
        if value is not None and not is_valid_uri(value):
            problems.append(f"CANONICAL_INVALID_URI:{path}:{value}")
    if validator is not None:
        problems.extend(f"CANONICAL_INVALID:{'/'.join(map(str, e.path)) or '$'}:{e.message}" for e in validator.iter_errors(record))
    return problems


def _prune_dangling_relations(records: list[dict[str, Any]]) -> int:
    known = {record["entity_id"] for record in records}
    pruned = 0
    for record in records:
        relations = record.get("relations") or {}
        for name in list(relations):
            kept = [target for target in relations[name] if target in known]
            pruned += len(relations[name]) - len(kept)
            if kept:
                relations[name] = kept
            else:
                del relations[name]
    return pruned


def merged_registry_ids(identity_map: list[dict[str, Any]]) -> set[str]:
    """registry_id đã được gộp vào entity khác (bản ghi "(bổ sung …)")."""
    return {rid for entry in identity_map for rid in entry.get("merged_from") or [] if isinstance(rid, str)}


def update_coverage_report(
    registry_records: list[dict[str, Any]],
    canonical_records: list[dict[str, Any]],
    reports_dir: Path = REPORTS_DIR,
    merged_ids: set[str] | None = None,
) -> Path | None:
    """Cập nhật counter ``canonicalized`` của coverage report sau khi map (§12.4.3).

    Không bao giờ nâng một claim ``coverage_failed`` lên 100%; chỉ có thể hạ.
    """
    snapshots = {record.get("coverage_snapshot") for record in registry_records if record.get("coverage_snapshot")}
    if len(snapshots) != 1:
        return None
    path = reports_dir / next(iter(snapshots)) / "coverage.json"
    if not path.exists():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    registry_ids = {record["registry_id"] for record in registry_records}
    canonical_registry = [record for record in canonical_records if record.get("registry_id")]
    category_of = {record["registry_id"]: record.get("registry_category") for record in registry_records}
    category_of.update({record["registry_id"]: record.get("registry_category") for record in canonical_registry})
    # Một dòng registry được "canonicalized" nếu có >= 1 canonical record (kể cả khi tách
    # thành nhiều thành phần) hoặc đã được gộp vào bản gốc (identity_map).
    canonical_ids = {record["registry_id"] for record in canonical_registry} | ((merged_ids or set()) & registry_ids)
    per_category: dict[str, int] = {}
    for registry_id in canonical_ids:
        per_category[category_of[registry_id]] = per_category.get(category_of[registry_id], 0) + 1
    for item in report.get("categories", []):
        item["canonicalized"] = per_category.get(item["registry_category"], 0)
        if item.get("valid"):
            item["coverage_percent"] = round(100.0 * item["canonicalized"] / item["valid"], 4)
    report["canonical_total"] = len(canonical_ids)
    enriched = {record["registry_id"] for record in canonical_registry if record.get("source_status") != "registry_only"}
    report["wikipedia_matched"] = len(enriched)
    report["registry_only"] = len(canonical_ids) - len(enriched)
    report["wikidata_linked"] = len({record["registry_id"] for record in canonical_registry
                                     if (record.get("external_ids") or {}).get("wikidata")})
    report["unresolved_registry_ids"] = sorted(registry_ids - canonical_ids)
    if report.get("claim") == COVERAGE_CLAIM and (
        report["unresolved_registry_ids"]
        or any(item.get("coverage_percent") != 100.0 for item in report.get("categories", []))
    ):
        report["claim"] = "coverage_failed"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(run_mode: str = "sample") -> int:
    """`make map` — entities.jsonl -> canonical.jsonl."""
    entities_path = PROCESSED_DIR / "entities.jsonl"
    if not entities_path.exists():
        print(f"map: {entities_path} not found; run resolve first")
        return 1
    mapping = load_mapping()
    category_types = _load_category_types()
    category_urls = _load_category_urls()
    pages = _load_pages()
    exact_wikidata = _load_exact_wikidata()
    area_resolver = _default_area_resolver()
    derived = DerivedRegistry()
    validator = _schema_validator()

    mapped: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        for entity in _read_jsonl(entities_path):
            for record in map_entity(entity, category_types, pages, exact_wikidata, mapping=mapping,
                                     area_resolver=area_resolver, derived=derived, category_urls=category_urls):
                problems = validate_canonical(record, mapping, validator)
                if problems:
                    skipped.append({"entity_id": record.get("entity_id"), "registry_id": record.get("registry_id"), "errors": problems})
                    continue
                mapped.append(record)
        derived_records = derived.records()
    except ValueError as exc:
        print(f"map ({run_mode}): FAIL - {exc}")
        return 1

    for record in derived_records:
        problems = validate_canonical(record, mapping, validator)
        if problems:
            print(f"map ({run_mode}): FAIL - derived entity {record['entity_id']} invalid: {problems}")
            return 1
    output_records = derived_records + mapped
    ids = [record["entity_id"] for record in output_records]
    if len(ids) != len(set(ids)):
        duplicates = sorted({entity_id for entity_id in ids if ids.count(entity_id) > 1})
        print(f"map ({run_mode}): IDENTITY_COLLISION - {duplicates[:5]}")
        return 1
    pruned = _prune_dangling_relations(output_records)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output = PROCESSED_DIR / "canonical.jsonl"
    with output.open("w", encoding="utf-8") as target:
        for record in output_records:
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (PROCESSED_DIR / "mapping_skipped.jsonl").open("w", encoding="utf-8") as handle:
        for item in skipped:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (PROCESSED_DIR / "area_warnings.jsonl").open("w", encoding="utf-8") as handle:
        for item in derived.area_warnings:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    coverage_path = None
    if run_mode == "full":
        coverage_path = update_coverage_report(_read_jsonl(RAW_DIR / "registry_records.jsonl"), output_records,
                                               merged_ids=merged_registry_ids(_read_jsonl(PROCESSED_DIR / "identity_map.jsonl")))
    by_type: dict[str, int] = {}
    for record in output_records:
        by_type[record["entity_type"]] = by_type.get(record["entity_type"], 0) + 1
    relation_count = sum(len(targets) for record in output_records for targets in (record.get("relations") or {}).values())
    print(
        f"map ({run_mode}): {len(mapped)} registry + {len(derived_records)} derived canonical records -> {output}; "
        f"relations={relation_count}, skipped={len(skipped)}, area_warnings={len(derived.area_warnings)}, "
        f"pruned_relations={pruned}, types={json.dumps(by_type, ensure_ascii=False, sort_keys=True)}"
        + (f"; coverage updated {coverage_path}" if coverage_path else "")
    )
    if skipped:
        print(f"map ({run_mode}): WARNING {len(skipped)} record(s) quarantined in {PROCESSED_DIR / 'mapping_skipped.jsonl'}")
    return 0
