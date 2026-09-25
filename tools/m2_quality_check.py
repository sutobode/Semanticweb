"""M2-23 — data quality gate cho output của M2 (chạy sau `make map`).

    python tools/m2_quality_check.py                       # kiểm tra, exit 1 nếu vi phạm
    python tools/m2_quality_check.py --json reports/m2_quality.json
    python tools/m2_quality_check.py --previous path/to/old_canonical.jsonl

Không gọi network. Đọc data/raw/registry_records.jsonl, data/processed/*.jsonl,
config/*.yaml, schema/canonical-record.schema.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from vietheritage.mapping.mapper import load_mapping, merged_registry_ids, validate_canonical  # noqa: E402
from vietheritage.normalization.normalizer import is_valid_uri  # noqa: E402

RAW = REPO_ROOT / "data" / "raw"
PROCESSED = REPO_ROOT / "data" / "processed"
BASE_URL = "https://dsvh.gov.vn"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_checks(previous: Path | None = None) -> dict:
    canonical = _read(PROCESSED / "canonical.jsonl")
    raw = _read(RAW / "registry_records.jsonl")
    failures = _read(RAW / "registry_failures.jsonl")
    categories = yaml.safe_load((REPO_ROOT / "config" / "registry_sources.yaml").read_text(encoding="utf-8"))["categories"]
    mapping = load_mapping()
    validator = Draft202012Validator(json.loads((REPO_ROOT / "schema" / "canonical-record.schema.json").read_text(encoding="utf-8")))
    registry = [record for record in canonical if record.get("registry_id")]
    ids = [record["entity_id"] for record in canonical]
    known = set(ids)
    year_now = datetime.now(timezone.utc).year
    checks: list[dict] = []

    def check(name: str, ok: bool, detail, blocking: bool = True) -> None:
        checks.append({"check": name, "status": "PASS" if ok else ("FAIL" if blocking else "WARN"), "detail": detail})

    invalid = {record["entity_id"]: validate_canonical(record, mapping, validator) for record in canonical}
    invalid = {key: value for key, value in invalid.items() if value}
    check("canonical_schema_and_required_fields", not invalid, {"invalid": len(invalid), "sample": dict(list(invalid.items())[:3])})
    check("entity_id_unique", len(ids) == len(set(ids)), {"total": len(ids), "unique": len(set(ids))})
    raw_ids = {record["registry_id"] for record in raw}
    merged = merged_registry_ids(_read(PROCESSED / "identity_map.jsonl"))
    represented = {record["registry_id"] for record in registry} | (merged & raw_ids)
    missing = sorted(raw_ids - represented)
    check("registry_records_all_canonicalized", not missing,
          {"raw": len(raw_ids), "represented": len(represented), "merged_supplements": len(merged & raw_ids),
           "canonical_registry_records": len(registry), "missing": missing[:10]})
    split = Counter(record["registry_id"] for record in registry)
    split = {rid: n for rid, n in split.items() if n > 1}
    check("split_multi_site_records", True, {"registry_rows_split": len(split), "entities_from_split": sum(split.values())},
          blocking=False)
    homepage = [r["entity_id"] for r in registry if (r.get("registry_url") or "").rstrip("/") == BASE_URL]
    check("registry_url_not_homepage", not homepage, {"count": len(homepage), "sample": homepage[:5]})
    not_https = [r["entity_id"] for r in registry if not (r.get("registry_url") or "").startswith(BASE_URL + "/")]
    check("registry_url_official_https", not not_https, {"count": len(not_https), "sample": not_https[:5]})
    bad_years = [(r["entity_id"], r.get("recognition_year")) for r in canonical
                 if r.get("recognition_year") is not None and not (1900 <= r["recognition_year"] <= year_now)]
    check("recognition_year_in_range", not bad_years, {"count": len(bad_years), "sample": bad_years[:5]})
    wh_bad = [(r["entity_id"], r.get("recognition_year")) for r in registry
              if r.get("registry_category") == "world_heritage" and not (r.get("recognition_year") or 0) >= 1993]
    check("world_heritage_year_ge_1993", not wh_bad, wh_bad)
    dangling = sorted({(r["entity_id"], t) for r in canonical for ts in (r.get("relations") or {}).values() for t in ts if t not in known})
    check("relations_resolve_to_canonical_entities", not dangling, dangling[:10])
    with_location = [r for r in registry if r.get("location")]
    unlinked = [r["entity_id"] for r in with_location if not (r.get("relations") or {}).get("located_in")]
    ratio = 1 - len(unlinked) / len(with_location) if with_location else 1.0
    check("location_linked_ratio_ge_95pct", ratio >= 0.95, {"ratio": round(ratio, 4), "unlinked": unlinked[:10]})
    area_warnings = _read(PROCESSED / "area_warnings.jsonl")
    check("area_unmapped_reviewed", not area_warnings, {"count": len(area_warnings), "sample": area_warnings[:5]}, blocking=False)
    derived_first = all(r.get("registry_id") is None for r in canonical[: len(canonical) - len(registry)])
    check("derived_entities_before_registry_records", derived_first, "LPG loader one-pass contract")
    empty_allowed = {c["key"] for c in categories if c.get("allow_empty_source")}
    # Snapshot crawl trước khi có allow_empty_source vẫn ghi REGISTRY_EMPTY_SOURCE cho các category này -> không tính.
    empty = [f"{f['registry_category']}:{f['error_code']}" for f in failures
             if not (f["registry_category"] in empty_allowed and f.get("error_code") == "REGISTRY_EMPTY_SOURCE")]
    check("registry_categories_all_collected", not empty, {"failed_categories": empty, "configured": len(categories)})
    empty_now = sorted({row["registry_category"] for row in _read(RAW / "registry_empty_sources.jsonl")})
    check("registry_categories_empty_at_source", not empty_now,
          {"empty_but_in_scope": empty_now, "allowed_by_decision": sorted(empty_allowed)}, blocking=False)
    bad_uris = [(r["entity_id"], field) for r in canonical
                for field, value in (("registry_url", r.get("registry_url")), ("source_url", r.get("source_url")),
                                     ("provenance.source", (r.get("provenance") or {}).get("source")))
                if value is not None and not is_valid_uri(value)]
    check("urls_are_ascii_rfc3986", not bad_uris, {"count": len(bad_uris), "sample": bad_uris[:5]})
    skipped = _read(PROCESSED / "mapping_skipped.jsonl")
    check("no_mapping_quarantine", not skipped, {"count": len(skipped)}, blocking=False)

    stats = {
        "canonical_total": len(canonical),
        "registry_derived": len(registry),
        "by_entity_type": dict(Counter(r["entity_type"] for r in canonical)),
        "by_category": dict(Counter(r.get("registry_category") for r in registry)),
        "by_source_status": dict(Counter(r["source_status"] for r in canonical)),
        "relations": dict(Counter(name for r in canonical for name, ts in (r.get("relations") or {}).items() for _ in ts)),
        "canonical_sha256": hashlib.sha256((PROCESSED / "canonical.jsonl").read_bytes()).hexdigest() if canonical else None,
    }
    if previous:
        old_ids = {r["entity_id"] for r in _read(previous) if r.get("registry_id")}
        new_ids = {r["entity_id"] for r in registry}
        kept = len(old_ids & new_ids) / len(old_ids) if old_ids else 1.0
        stats["id_retention_vs_previous"] = round(kept, 4)
        check("id_retention_vs_previous_ge_95pct", kept >= 0.95, {"retained": round(kept, 4)}, blocking=False)
    status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS"
    return {"status": status, "checks": checks, "stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 data quality gate")
    parser.add_argument("--json", type=Path, help="ghi báo cáo JSON")
    parser.add_argument("--previous", type=Path, help="canonical.jsonl của snapshot trước để đo độ ổn định ID")
    args = parser.parse_args()
    report = run_checks(args.previous)
    for item in report["checks"]:
        print(f"[{item['status']:4}] {item['check']}")
        if item["status"] != "PASS":
            print(f"        {json.dumps(item['detail'], ensure_ascii=False)[:300]}")
    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print(f"m2-quality: {report['status']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
