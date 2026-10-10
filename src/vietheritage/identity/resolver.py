"""Deterministic identity enrichment and global reconciliation (COMP-003).

The resolver treats registry rows as source observations.  It enriches them
with reviewed page/QID/domain identifiers, reconciles all observations in one
indexed pass, and only then mints canonical entity IDs.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from vietheritage.normalization.areas import default_resolver
from vietheritage.normalization.normalizer import canonical_identity_key, parse_recognition_year

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REGISTRY_CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
MAPPING_PATH = REPO_ROOT / "config" / "mapping.yaml"
IDENTITY_REVIEW_PATH = REPO_ROOT / "config" / "identity_reviews.yaml"
IDENTITY_REVIEW_SCHEMA_PATH = REPO_ROOT / "schema" / "identity-review.schema.json"
DECISIONS_FILENAME = "identity_decisions.jsonl"

_TYPE_PREFIXES = {
    "person", "area", "event", "period", "complex", "organization", "style",
}
_ENTITY_PREFIXES = {
    "HeritageSite": "site",
    "AdministrativeArea": "area",
    "HistoricalPerson": "person",
    "HistoricalEvent": "event",
    "HistoricalPeriod": "period",
    "HeritageComplex": "complex",
    "Organization": "organization",
    "ArchitecturalStyle": "style",
    "Museum": "museum",
    "IntangibleHeritage": "intangible",
    "NationalTreasure": "treasure",
    "DocumentaryHeritage": "documentary",
    "CulturalObject": "object",
}
_EVIDENCE_FIELDS = {
    "source_id": "source_ids",
    "wikidata_id": "wikidata_ids",
    "page_id": "page_ids",
    "domain_id": "domain_ids",
}
_RELATED_PAGE_ROLE = "related_subject"


class IdentityCollisionError(RuntimeError):
    """A proposed identity component violates a reconciliation blocker."""


def sha256_12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


# These helpers remain the ID contract for derived entities created by the
# mapper. Registry source records no longer use resolve_identity during run().
def registry_entity_id(registry_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", registry_id.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise ValueError(f"INVALID_REGISTRY_ID: {registry_id!r}")
    if slug.startswith("registry-"):
        return slug
    return f"registry-{slug}"


def registry_fallback_id(source_url: str, registry_category: str, normalized_label: str) -> str:
    digest = sha256_12(f"{source_url}{registry_category}{normalized_label}")
    return f"registry-{digest}"


def person_entity_id(qid: str | None, normalized_name: str) -> str:
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
    return f"style-{sha256_12(normalized_name)}"


def period_entity_id(normalized_name: str, start_year: Any, end_year: Any) -> str:
    start_part = str(start_year) if start_year else ""
    end_part = str(end_year) if end_year else ""
    return f"period-{sha256_12(normalized_name + start_part + end_part)}"


def type_prefixed_id(type_prefix: str, canonical_name: str) -> str:
    if type_prefix not in _TYPE_PREFIXES:
        raise ValueError(f"unknown type prefix: {type_prefix}")
    return f"{type_prefix}-{sha256_12(canonical_name)}"


def resolve_identity(record: dict[str, Any]) -> str:
    """Legacy derived-entity helper retained for mapper compatibility."""
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
    """Legacy exact-ID merger used by focused mapper tests."""
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
        existing["aliases_vi"] = list(dict.fromkeys(
            (existing.get("aliases_vi") or []) + (record.get("aliases_vi") or [])
        ))
        existing["categories"] = list(dict.fromkeys(
            (existing.get("categories") or []) + (record.get("categories") or [])
        ))
        for key, value in record.items():
            if value is not None and existing.get(key) is None:
                existing[key] = value
        identity_map.append({"entity_id": entity_id, "merged_from": record.get("registry_id") or record.get("page_id")})
    return list(by_id.values()), identity_map


def supplement_merges(records: list[dict[str, Any]], config: dict[str, Any] | None) -> dict[str, str]:
    """Return supplement source IDs mapped to the base record's temporary ID."""
    if not config:
        return {}
    supplement_re = re.compile(config["label_pattern"])
    abbreviation_re = re.compile(config.get("type_abbreviation_pattern", r"^\b$"))

    def core(label: str) -> str:
        return canonical_identity_key(abbreviation_re.sub("", supplement_re.sub("", label)))

    bases: dict[tuple[str, str], str] = {}
    for record in records:
        if record.get("registry_id") and not supplement_re.search(record.get("label_vi", "")):
            bases.setdefault((record.get("registry_category"), core(record["label_vi"])), record["_entity_id"])
    merges: dict[str, str] = {}
    for record in records:
        if record.get("registry_id") and supplement_re.search(record.get("label_vi", "")):
            base = bases.get((record.get("registry_category"), core(record["label_vi"])))
            if base:
                merges[record["registry_id"]] = base
    return merges


def canonical_entity_id(entity_type: str, stable_anchor: str) -> str:
    """Mint an order-independent ID without using a mutable label."""
    prefix = _ENTITY_PREFIXES.get(entity_type, "entity")
    return f"{prefix}-{sha256_12(stable_anchor)}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _source_namespace(record: dict[str, Any], default: str = "dsvh") -> str:
    explicit = record.get("source_namespace") or record.get("_source_namespace")
    if explicit:
        return str(explicit)
    source = str((record.get("registry_fields") or {}).get("source") or "")
    if source.startswith("wikipedia_list:"):
        return "viwiki"
    host = urlsplit(str(record.get("registry_url") or record.get("source_url") or "")).hostname or ""
    if host.endswith("dsvh.gov.vn"):
        return "dsvh"
    if host.endswith("unesco.org"):
        return "unesco"
    if host.endswith("wikipedia.org"):
        return "viwiki"
    return default


def _source_record_id(record: dict[str, Any]) -> str | None:
    value = record.get("source_record_id") or record.get("registry_id")
    return str(value) if value else None


def _normalize_qid(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"Q[0-9]+", text) else None


def _normalized_scope_values(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return sorted({canonical_identity_key(str(item)) for item in values if item not in (None, "")})


def _normalized_location_values(value: Any) -> list[str]:
    """Use the configured source-area identities before falling back to normalized text."""
    values = value if isinstance(value, list) else [value]
    normalized: set[str] = set()
    area_resolver = default_resolver()
    for item in values:
        if item in (None, ""):
            continue
        areas = area_resolver.resolve(str(item)).areas
        normalized.update(area.entity_id for area in areas)
        if not areas:
            normalized.add(canonical_identity_key(str(item)))
    return sorted(normalized)


def _page_index(pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        if page.get("page_role") == _RELATED_PAGE_ROLE:
            continue
        links = page.get("registry_links") or [
            {"registry_id": registry_id, "part_label": None}
            for registry_id in page.get("registry_ids") or []
        ]
        for link in links:
            source_id = link.get("registry_id")
            # A component page identifies the component, not the unsplit whole row.
            if source_id and not link.get("part_label"):
                by_source[str(source_id)].append(page)
    return by_source


def _exact_qid_index(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        qid = _normalize_qid(row.get("wikidata_id"))
        if row.get("entity_id") and qid:
            result[str(row["entity_id"])].add(qid)
    return result


def _identity_overrides(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for canonical_id, spec in (mapping.get("derived_entities") or {}).items():
        identity = spec.get("identity") or {}
        for source_id in identity.get("source_record_ids") or []:
            result[str(source_id)] = {
                "entity_type": spec.get("entity_type"),
                "canonical_id": canonical_id,
                "canonical_anchor": identity.get("canonical_anchor"),
                "granularity": identity.get("granularity"),
                "scope": identity.get("scope"),
                "external_ids": spec.get("external_ids") or {},
            }
    return result


def _reviewed_distinct_evidence(config: dict[str, Any]) -> dict[str, list[tuple[str, str, Any]]]:
    """Index reviewed shared-page evidence that must not be used as exact identity."""
    if not config:
        return {}
    schema = json.loads(IDENTITY_REVIEW_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(config),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        path = "/".join(map(str, error.path)) or "$"
        raise ValueError(f"IDENTITY_REVIEW_INVALID:{path}:{error.message}")
    group_ids = [str(item["group_id"]) for item in config["decisions"]]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("IDENTITY_REVIEW_INVALID:duplicate group_id")
    result: dict[str, list[tuple[str, str, Any]]] = defaultdict(list)
    for item in config.get("decisions") or []:
        group_id = str(item["group_id"])
        evidence = item.get("evidence") or {}
        for source_id in item["source_record_ids"]:
            if evidence.get("page_id") is not None:
                result[str(source_id)].append((group_id, "page_ids", int(evidence["page_id"])))
            if evidence.get("wikidata_id"):
                result[str(source_id)].append((group_id, "wikidata_ids", str(evidence["wikidata_id"]).upper()))
    return result


def _add_evidence(record: dict[str, Any], field: str, value: Any) -> None:
    if value in (None, ""):
        return
    values = record.setdefault("_identity_evidence", {}).setdefault(field, [])
    normalized: str | int = int(value) if field == "page_ids" else str(value)
    if normalized not in values:
        values.append(normalized)


def enrich_identity_evidence(
    records: list[dict[str, Any]],
    *,
    pages: list[dict[str, Any]] | None = None,
    exact_wikidata: list[dict[str, Any]] | None = None,
    category_types: dict[str, str] | None = None,
    mapping: dict[str, Any] | None = None,
    identity_reviews: dict[str, Any] | None = None,
    normalize_locations: bool = True,
    default_source_namespace: str = "dsvh",
) -> list[dict[str, Any]]:
    """Attach strong identity evidence before the single reconciliation pass."""
    page_index = _page_index(pages or [])
    qid_index = _exact_qid_index(exact_wikidata or [])
    overrides = _identity_overrides(mapping or {})
    reviewed_distinct = _reviewed_distinct_evidence(identity_reviews or {})
    expected_review_evidence = {
        (source_id, group_id, field, value)
        for source_id, suppressions in reviewed_distinct.items()
        for group_id, field, value in suppressions
    }
    matched_review_evidence: set[tuple[str, str, str, Any]] = set()
    observed_review_evidence: dict[tuple[str, Any], set[str]] = defaultdict(set)
    prepared: list[dict[str, Any]] = []

    for original in records:
        record = dict(original)
        record["_identity_evidence"] = {
            key: list(values) for key, values in (original.get("_identity_evidence") or {}).items()
        }
        source_record_id = _source_record_id(record)
        namespace = _source_namespace(record, default_source_namespace)
        record["_source_namespace"] = namespace
        record["_source_record_id"] = source_record_id
        if source_record_id:
            _add_evidence(record, "source_ids", f"{namespace}:{source_record_id}")

        entity_type = record.get("entity_type") or (category_types or {}).get(record.get("registry_category"))
        if entity_type:
            record["entity_type"] = entity_type

        qid = _normalize_qid(record.get("wikidata_id"))
        if qid:
            _add_evidence(record, "wikidata_ids", qid)
        if record.get("page_id"):
            _add_evidence(record, "page_ids", record["page_id"])
        for name, value in (record.get("external_ids") or {}).items():
            _add_evidence(record, "domain_ids", f"{str(name).casefold()}:{value}")

        if source_record_id:
            for exact_qid in sorted(qid_index.get(source_record_id, set())):
                _add_evidence(record, "wikidata_ids", exact_qid)
            for page in page_index.get(source_record_id, []):
                _add_evidence(record, "page_ids", page.get("page_id"))
                page_qid = _normalize_qid(page.get("wikidata_id"))
                if page_qid:
                    _add_evidence(record, "wikidata_ids", page_qid)
                if record.get("registry_category") == "world_heritage":
                    unesco_id = (page.get("infobox") or {}).get("id")
                    if unesco_id:
                        _add_evidence(record, "domain_ids", f"unesco:{unesco_id}")

            override = overrides.get(source_record_id)
            if override:
                if override.get("entity_type"):
                    record["entity_type"] = override["entity_type"]
                if override.get("canonical_anchor"):
                    record["_canonical_anchor"] = str(override["canonical_anchor"])
                if override.get("canonical_id"):
                    record["_configured_canonical_id"] = str(override["canonical_id"])
                if override.get("granularity"):
                    record["_identity_granularity"] = override["granularity"]
                if override.get("scope"):
                    record["_identity_scope"] = override["scope"]
                for name, value in override.get("external_ids", {}).items():
                    _add_evidence(record, "domain_ids", f"{str(name).casefold()}:{value}")

        for group_id, field, suppressed in reviewed_distinct.get(str(source_record_id), []):
            values = record["_identity_evidence"].get(field, [])
            if suppressed in values:
                record["_identity_evidence"][field] = [value for value in values if value != suppressed]
                matched_review_evidence.add((str(source_record_id), group_id, field, suppressed))
                if field == "wikidata_ids":
                    suppressed_ids = record.setdefault("_suppressed_external_ids", {}).setdefault("wikidata", [])
                    if suppressed not in suppressed_ids:
                        suppressed_ids.append(suppressed)
        for field in ("page_ids", "wikidata_ids"):
            for value in record["_identity_evidence"].get(field, []):
                observed_review_evidence[(field, value)].add(str(source_record_id))
        for group_id, field, suppressed in reviewed_distinct.get(str(source_record_id), []):
            if (str(source_record_id), group_id, field, suppressed) in matched_review_evidence:
                observed_review_evidence[(field, suppressed)].add(str(source_record_id))

        fields = record.get("registry_fields") or {}
        location = record.get("_identity_locations") or record.get("location") or fields.get("location")
        community = record.get("_identity_communities") or record.get("community")
        record["_identity_locations"] = (
            _normalized_location_values(location) if normalize_locations else _normalized_scope_values(location)
        )
        record["_identity_communities"] = _normalized_scope_values(community)
        for values in record["_identity_evidence"].values():
            values.sort(key=str)
        prepared.append(record)

    missing_review_evidence = sorted(expected_review_evidence - matched_review_evidence, key=str)
    if missing_review_evidence:
        source_id, group_id, field, value = missing_review_evidence[0]
        raise ValueError(
            f"IDENTITY_REVIEW_EVIDENCE_MISSING:{group_id}:{source_id}:{field}:{value}"
        )
    for item in (identity_reviews or {}).get("decisions") or []:
        expected_sources = set(map(str, item["source_record_ids"]))
        for name, value in (item.get("evidence") or {}).items():
            field = "page_ids" if name == "page_id" else "wikidata_ids"
            normalized = int(value) if field == "page_ids" else str(value).upper()
            actual_sources = observed_review_evidence.get((field, normalized), set())
            if actual_sources != expected_sources:
                raise ValueError(
                    f"IDENTITY_REVIEW_SCOPE_MISMATCH:{item['group_id']}:{field}:{normalized}:"
                    f"expected={','.join(sorted(expected_sources))}:actual={','.join(sorted(actual_sources))}"
                )
    _add_supplement_evidence(prepared, (mapping or {}).get("registry_supplements"))
    return prepared


def _add_supplement_evidence(records: list[dict[str, Any]], config: dict[str, Any] | None) -> None:
    if not config:
        return
    temporary = [dict(record, _entity_id=record.get("registry_id")) for record in records]
    merges = supplement_merges(temporary, config)
    by_id = {record.get("registry_id"): record for record in records}
    for supplement_id, base_id in merges.items():
        # supplement_merges returns the base temporary ID, which is its registry ID here.
        anchor = f"reviewed-supplement:{base_id}"
        if supplement_id in by_id:
            _add_evidence(by_id[supplement_id], "domain_ids", anchor)
        if base_id in by_id:
            _add_evidence(by_id[base_id], "domain_ids", anchor)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.members = {index: [index] for index in range(size)}

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> int:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return left_root
        if left_root > right_root:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.members[left_root].extend(self.members.pop(right_root))
        return left_root

    def component(self, root: int) -> list[int]:
        return self.members[self.find(root)]


def _component_blockers(records: list[dict[str, Any]]) -> list[str]:
    reasons: set[str] = set()
    types = {record.get("entity_type") for record in records if record.get("entity_type")}
    if len(types) > 1:
        reasons.add("WHOLE_TYPE_CONFLICT" if types == {"HeritageComplex", "HeritageSite"} else "INCOMPATIBLE_TYPE")

    granularities = {record.get("_identity_granularity") for record in records if record.get("_identity_granularity")}
    if "whole" in granularities and "component" in granularities:
        reasons.add("WHOLE_COMPONENT_CONFLICT")
    scopes = {record.get("_identity_scope") for record in records if record.get("_identity_scope")}
    if "broad" in scopes and "localized" in scopes:
        reasons.add("BROAD_LOCALIZED_CONFLICT")

    for evidence_field, reason in (
        ("wikidata_ids", "CONFLICTING_WIKIDATA_ID"),
        ("page_ids", "CONFLICTING_PAGE_ID"),
    ):
        values = {
            value
            for record in records
            for value in (record.get("_identity_evidence") or {}).get(evidence_field, [])
        }
        if len(values) > 1:
            reasons.add(reason)
    domain_values: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for value in (record.get("_identity_evidence") or {}).get("domain_ids", []):
            namespace, _, identifier = str(value).partition(":")
            domain_values[namespace].add(identifier)
    if any(len(values) > 1 for values in domain_values.values()):
        reasons.add("CONFLICTING_DOMAIN_ID")

    anchors = {record.get("_canonical_anchor") for record in records if record.get("_canonical_anchor")}
    if len(anchors) > 1:
        reasons.add("CONFLICTING_CANONICAL_ANCHOR")

    for field, reason in (
        ("_identity_locations", "INCOMPATIBLE_LOCATION"),
        ("_identity_communities", "INCOMPATIBLE_COMMUNITY"),
    ):
        sets = [set(record.get(field) or []) for record in records if record.get(field)]
        if len(sets) > 1 and not set.intersection(*sets):
            reasons.add(reason)

    source_ids = {
        record.get("_source_record_id") for record in records if record.get("_source_record_id")
    }
    for record in records:
        for targets in (record.get("relations") or {}).values():
            if source_ids.intersection(str(target) for target in targets):
                reasons.add("MERGE_CREATES_SELF_RELATION")
    return sorted(reasons)


def _review_entry(
    records: list[dict[str, Any]], reasons: list[str], evidence_type: str, evidence_value: Any,
    *, blocking: bool,
) -> dict[str, Any]:
    source_ids = sorted({str(record.get("_source_record_id")) for record in records if record.get("_source_record_id")})
    digest = sha256_12("|".join([*source_ids, *reasons]))
    return {
        "review_id": f"identity-review-{digest}",
        "status": "blocking" if blocking else "manual_review",
        "reason_codes": reasons,
        "source_record_ids": source_ids,
        "shared_evidence": [{"type": evidence_type, "value": evidence_value}],
    }


def _merge_review(reviews: dict[tuple[Any, ...], dict[str, Any]], entry: dict[str, Any]) -> None:
    key = (
        entry["status"], tuple(entry["reason_codes"]), tuple(entry["source_record_ids"]),
    )
    existing = reviews.get(key)
    if existing is None:
        reviews[key] = entry
        return
    for evidence in entry["shared_evidence"]:
        if evidence not in existing["shared_evidence"]:
            existing["shared_evidence"].append(evidence)
            existing["shared_evidence"].sort(key=lambda item: (item["type"], str(item["value"])))


def _source_observation(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("registry_fields") or {}
    source_url = record.get("registry_url") or record.get("source_url")
    observation: dict[str, Any] = {
        "source_namespace": record.get("_source_namespace") or "unknown",
        "source_record_id": record.get("_source_record_id"),
        "source_url": source_url,
        "label_vi": record.get("label_vi"),
        "registry_category": record.get("registry_category"),
        "recognition_year": parse_recognition_year(fields.get("recognition_text")),
        "retrieved_at": record.get("retrieved_at"),
        "provenance": {
            "source": source_url,
            "method": "mediawiki-api" if record.get("_source_namespace") == "viwiki" else "registry",
            "license": "CC BY-SA 4.0" if record.get("_source_namespace") == "viwiki" else "Official registry snapshot",
        },
    }
    return {key: value for key, value in observation.items() if value is not None}


def _primary_key(record: dict[str, Any], category_priority: dict[str, int]) -> tuple[Any, ...]:
    return (
        category_priority.get(str(record.get("registry_category")), len(category_priority)),
        str(record.get("_source_namespace") or ""),
        str(record.get("_source_record_id") or ""),
    )


def _cluster_anchor(records: list[dict[str, Any]], primary: dict[str, Any]) -> tuple[str, str]:
    anchors = sorted({str(record["_canonical_anchor"]) for record in records if record.get("_canonical_anchor")})
    if anchors:
        return anchors[0], "canonical_anchor"
    source_ids = (primary.get("_identity_evidence") or {}).get("source_ids") or []
    if source_ids:
        return str(source_ids[0]), "source_id"
    for evidence_field, source_name in (
        ("wikidata_ids", "wikidata_id"), ("page_ids", "page_id"), ("domain_ids", "domain_id"),
    ):
        values = sorted({
            str(value) for record in records
            for value in (record.get("_identity_evidence") or {}).get(evidence_field, [])
        })
        if values:
            return values[0], source_name
    raise IdentityCollisionError("source record has no stable identity anchor")


def _merge_component(
    records: list[dict[str, Any]], category_priority: dict[str, int], shared_kinds: set[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    ordered = sorted(records, key=lambda record: _primary_key(record, category_priority))
    primary = ordered[0]
    merged = dict(primary)
    anchor, identity_source = _cluster_anchor(ordered, primary)
    entity_type = str(primary.get("entity_type") or "Entity")
    entity_id = canonical_entity_id(entity_type, anchor)
    merged["_entity_id"] = entity_id
    merged["entity_type"] = entity_type

    aliases = [*(primary.get("aliases_vi") or [])]
    for record in ordered[1:]:
        if record.get("label_vi"):
            aliases.append(record["label_vi"])
        aliases.extend(record.get("aliases_vi") or [])
        for key, value in record.items():
            if key in {"registry_id", "registry_category", "registry_url", "registry_fields", "label_vi"}:
                continue
            if value is not None and merged.get(key) is None:
                merged[key] = value
    seen_aliases = {canonical_identity_key(str(primary.get("label_vi") or ""))}
    merged_aliases: list[str] = []
    for alias in aliases:
        key = canonical_identity_key(str(alias))
        if key and key not in seen_aliases:
            seen_aliases.add(key)
            merged_aliases.append(alias)
    merged["aliases_vi"] = merged_aliases
    merged["source_records"] = [_source_observation(record) for record in ordered]

    evidence_summary: dict[str, list[Any]] = {}
    for field in ("source_ids", "wikidata_ids", "page_ids", "domain_ids"):
        evidence_summary[field] = sorted({
            value for record in ordered for value in (record.get("_identity_evidence") or {}).get(field, [])
        }, key=str)
    merged["_identity_evidence"] = evidence_summary
    if len(evidence_summary["wikidata_ids"]) == 1:
        merged["wikidata_id"] = evidence_summary["wikidata_ids"][0]
    if len(evidence_summary["page_ids"]) == 1:
        merged["page_id"] = evidence_summary["page_ids"][0]

    source_record_ids = [str(record.get("_source_record_id")) for record in ordered if record.get("_source_record_id")]
    identity_entry = {
        "entity_id": entity_id,
        "identity_source": identity_source,
        "identity_anchor": anchor,
        "registry_id": primary.get("registry_id"),
        "registry_category": primary.get("registry_category"),
        "source_record_ids": source_record_ids,
        "merged_from": source_record_ids[1:],
        "merge_reason": "+".join(sorted(shared_kinds)) if len(ordered) > 1 else None,
    }
    decisions = [
        {
            "source_namespace": record.get("_source_namespace"),
            "source_record_id": record.get("_source_record_id"),
            "entity_id": entity_id,
            "decision": "selected_source" if index == 0 else "attached_evidence",
            "identity_evidence": record.get("_identity_evidence") or {},
        }
        for index, record in enumerate(ordered)
    ]
    return merged, identity_entry, decisions


def reconcile_records(
    records: list[dict[str, Any]],
    *,
    pages: list[dict[str, Any]] | None = None,
    exact_wikidata: list[dict[str, Any]] | None = None,
    category_types: dict[str, str] | None = None,
    mapping: dict[str, Any] | None = None,
    identity_reviews: dict[str, Any] | None = None,
    normalize_locations: bool = True,
    category_priority: dict[str, int] | None = None,
    default_source_namespace: str = "dsvh",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Enrich and reconcile records using strong-identifier indexes and union-find."""
    prepared = enrich_identity_evidence(
        records, pages=pages, exact_wikidata=exact_wikidata, category_types=category_types,
        mapping=mapping, identity_reviews=identity_reviews,
        normalize_locations=normalize_locations,
        default_source_namespace=default_source_namespace,
    )
    category_priority = category_priority or {
        category: index for index, category in enumerate(sorted({
            str(record.get("registry_category")) for record in prepared if record.get("registry_category")
        }))
    }
    valid: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for record in prepared:
        if not record.get("_source_record_id") or not record.get("entity_type"):
            quarantine.append({
                "source_record_id": record.get("_source_record_id"),
                "decision": "quarantine",
                "reason_codes": ["MISSING_SOURCE_ID" if not record.get("_source_record_id") else "MISSING_ENTITY_TYPE"],
            })
        else:
            valid.append(record)

    union_find = _UnionFind(len(valid))
    indexes: dict[str, dict[str, list[int]]] = {
        evidence_type: defaultdict(list) for evidence_type in _EVIDENCE_FIELDS
    }
    for index, record in enumerate(valid):
        evidence = record.get("_identity_evidence") or {}
        for evidence_type, field in _EVIDENCE_FIELDS.items():
            for value in evidence.get(field, []):
                indexes[evidence_type][str(value)].append(index)

    reviews: dict[tuple[Any, ...], dict[str, Any]] = {}
    preblocked: set[int] = set()
    for index, record in enumerate(valid):
        reasons = _component_blockers([record])
        if reasons:
            preblocked.add(index)
            _merge_review(
                reviews,
                _review_entry([record], reasons, "record", record.get("_source_record_id"), blocking=True),
            )
    shared_by_root: dict[int, set[str]] = defaultdict(set)
    for evidence_type in ("source_id", "wikidata_id", "page_id", "domain_id"):
        for evidence_value, members in sorted(indexes[evidence_type].items()):
            unique_members = sorted(
                set(members) - preblocked,
                key=lambda index: _primary_key(valid[index], category_priority),
            )
            if len(unique_members) < 2:
                continue
            representatives: list[int] = []
            for candidate in unique_members:
                candidate_root = union_find.find(candidate)
                if any(union_find.find(representative) == candidate_root for representative in representatives):
                    shared_by_root[candidate_root].add(evidence_type)
                    continue
                merged = False
                for representative in representatives:
                    left_root, right_root = union_find.find(representative), union_find.find(candidate)
                    if left_root == right_root:
                        merged = True
                        break
                    roots = {left_root, right_root}
                    component = [
                        valid[index]
                        for root in roots
                        for index in union_find.component(root)
                    ]
                    reasons = _component_blockers(component)
                    if reasons:
                        _merge_review(
                            reviews,
                            _review_entry(component, reasons, evidence_type, evidence_value, blocking=True),
                        )
                        continue
                    inherited = shared_by_root.pop(left_root, set()) | shared_by_root.pop(right_root, set())
                    union_find.union(representative, candidate)
                    new_root = union_find.find(representative)
                    shared_by_root[new_root].update(inherited | {evidence_type})
                    merged = True
                    break
                if not merged:
                    representatives.append(candidate)

    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(valid):
        components[union_find.find(index)].append(record)

    # Alias/location evidence creates review candidates only; it never unions components.
    weak_index: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for root, component in components.items():
        types = {str(record.get("entity_type")) for record in component}
        locations = {
            location for record in component for location in record.get("_identity_locations") or []
        }
        communities = {
            community for record in component for community in record.get("_identity_communities") or []
        }
        scopes = sorted(locations | communities)
        aliases = {
            canonical_identity_key(str(alias))
            for record in component
            for alias in [record.get("label_vi"), *(record.get("aliases_vi") or [])]
            if alias
        }
        for entity_type in types:
            for alias in aliases:
                for scope in scopes:
                    weak_index[(entity_type, alias, scope)].add(root)
    for (entity_type, alias, scope), roots in sorted(weak_index.items()):
        if len(roots) < 2:
            continue
        candidate_records = [record for root in sorted(roots) for record in components[root]]
        _merge_review(
            reviews,
            _review_entry(candidate_records, ["WEAK_ALIAS_SCOPE_CANDIDATE"], "alias_scope", f"{alias}|{scope}", blocking=False),
        )

    review_entries = sorted(reviews.values(), key=lambda item: item["review_id"])
    blocking_sources = {
        source_id for item in review_entries if item["status"] == "blocking"
        for source_id in item["source_record_ids"]
    }
    manual_sources = {
        source_id for item in review_entries if item["status"] == "manual_review"
        for source_id in item["source_record_ids"]
    }

    entities: list[dict[str, Any]] = []
    identity_map: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for root, component in components.items():
        entity, identity_entry, component_decisions = _merge_component(
            component, category_priority, shared_by_root.get(root, set())
        )
        entities.append(entity)
        identity_map.append(identity_entry)
        for decision in component_decisions:
            source_id = decision.get("source_record_id")
            if source_id in blocking_sources or source_id in manual_sources:
                decision["decision"] = "manual_review"
            decisions.append(decision)
    decisions.extend(quarantine)
    entities.sort(key=lambda record: record["_entity_id"])
    identity_map.sort(key=lambda entry: entry["entity_id"])
    decisions.sort(key=lambda entry: (str(entry.get("source_namespace") or ""), str(entry.get("source_record_id") or "")))

    blockers = [item for item in review_entries if item["status"] == "blocking"]
    manual_reviews = [item for item in review_entries if item["status"] == "manual_review"]
    report = {
        "status": "FAIL" if blockers else "PASS",
        "collisions": len(blockers),
        "manual_reviews": len(manual_reviews),
        "quarantined": len(quarantine),
        "blockers": blockers,
        "reviews": manual_reviews,
        "applied_identity_reviews": sorted(
            str(item["group_id"]) for item in (identity_reviews or {}).get("decisions") or []
        ),
    }
    return entities, identity_map, decisions, report


def _load_configuration() -> tuple[dict[str, str], dict[str, int], str, dict[str, Any], dict[str, Any]]:
    registry_config = yaml.safe_load(REGISTRY_CONFIG_PATH.read_text(encoding="utf-8")) if REGISTRY_CONFIG_PATH.exists() else {}
    categories = (registry_config or {}).get("categories") or []
    category_types = {item["key"]: item["entity_type"] for item in categories}
    category_priority = {item["key"]: index for index, item in enumerate(categories)}
    namespace = str((registry_config or {}).get("source_namespace") or "dsvh")
    mapping = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8")) if MAPPING_PATH.exists() else {}
    identity_reviews = yaml.safe_load(IDENTITY_REVIEW_PATH.read_text(encoding="utf-8")) if IDENTITY_REVIEW_PATH.exists() else {}
    return category_types, category_priority, namespace, mapping or {}, identity_reviews or {}


def run(run_mode: str = "sample") -> int:
    """``make resolve``: identity enrichment followed by one reconciliation pass."""
    normalized_path = PROCESSED_DIR / "normalized.jsonl"
    if not normalized_path.exists():
        print(f"resolve: {normalized_path} not found; run normalize first")
        return 1

    category_types, category_priority, namespace, mapping, identity_reviews = _load_configuration()
    exact_wikidata = [
        *_read_jsonl(RAW_DIR / "wikidata_exact_enrichment.jsonl"),
        *_read_jsonl(RAW_DIR / "wikidata_sparql_exact_enrichment.jsonl"),
    ]
    entities, identity_map, decisions, report = reconcile_records(
        _read_jsonl(normalized_path),
        pages=_read_jsonl(RAW_DIR / "pages.jsonl"),
        exact_wikidata=exact_wikidata,
        category_types=category_types,
        mapping=mapping,
        identity_reviews=identity_reviews,
        category_priority=category_priority,
        default_source_namespace=namespace,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "collision_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (PROCESSED_DIR / DECISIONS_FILENAME).open("w", encoding="utf-8") as handle:
        for entry in decisions:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if report["status"] == "FAIL":
        print(f"resolve ({run_mode}): IDENTITY_COLLISION - {report['collisions']} blocking review(s)")
        return 1

    with (PROCESSED_DIR / "entities.jsonl").open("w", encoding="utf-8") as handle:
        for record in entities:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (PROCESSED_DIR / "identity_map.jsonl").open("w", encoding="utf-8") as handle:
        for entry in identity_map:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    merged_count = sum(max(0, len(entry["source_record_ids"]) - 1) for entry in identity_map)
    print(
        f"resolve ({run_mode}): {len(entities)} entities, merged={merged_count}, "
        f"manual_review={report['manual_reviews']}, collision=0"
    )
    return 0
