"""Xuất 2 file JSON để soi bằng mắt kết quả khớp dsvh.gov.vn -> Wikipedia.

    python tools/m2_wiki_match_report.py [--out-dir reports/m2_wiki_match]

* ``m2_wiki_matched.json``: mỗi liên kết record -> bài Wikipedia (cách khớp, bằng chứng tỉnh,
  thành phần nếu record bị tách, thể loại, đoạn mở đầu, field lấy thêm từ Wikipedia, quan hệ
  với tên người/sự kiện đã giải).
* ``m2_wiki_unmatched.json``: record chưa khớp + lý do + các tiêu đề đã thử + link tìm kiếm.

Đọc data/raw (registry_records, pages, enrichment_failures) và data/processed/canonical.jsonl
(nếu đã chạy ``make map``). Không gọi mạng.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

RAW = REPO_ROOT / "data" / "raw"
PROCESSED = REPO_ROOT / "data" / "processed"
ORDER = ["world_heritage", "national_special_monuments", "national_monuments", "intangible_representative",
         "intangible_urgent", "national_intangible", "national_treasures"]
MAINTENANCE = ("Bài ", "Trang ", "Bản mẫu", "Tọa độ", "Quản lý CS1", "Mô tả ngắn", "sơ khai", "Hộp thông tin")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _order(category: str | None) -> int:
    return ORDER.index(category) if category in ORDER else len(ORDER)


def _reason_group(reason: str) -> str:
    if reason.startswith("alias"):   # tách theo loại bằng chứng còn thiếu (intangible_evidence)
        for needle, group in (("without ethnic evidence", "alias_without_ethnic_evidence"),
                              ("without region/province evidence", "alias_without_region_evidence"),
                              ("too short without evidence", "alias_too_short"),
                              ("(no evidence)", "alias_rejected_page_type")):
            if needle in reason:
                return group
    for prefix, group in (("no page found", "no_page_found"), ("no exact title match", "no_page_found"),
                          ("alias", "alias_without_province_evidence"), ("disambiguation", "disambiguation_without_specific_page"),
                          ("page type rejected", "rejected_page_type"), ("page lacks required category", "treasure_generic_page"),
                          ("ambiguous shared page", "ambiguous_shared_page"), ("province conflict", "province_conflict"),
                          ("component", "component_not_found"), ("components:", "component_not_found"),
                          ("override title", "override_title_not_found")):
        if reason.startswith(prefix):
            return group
    return "other"


def build(out_dir: Path) -> tuple[dict, dict]:
    records = {r["registry_id"]: r for r in _read(RAW / "registry_records.jsonl")}
    pages = _read(RAW / "pages.jsonl")
    failures = _read(RAW / "enrichment_failures.jsonl")
    canonical = _read(PROCESSED / "canonical.jsonl")
    by_entity = {r["entity_id"]: r for r in canonical}
    by_registry: dict[str, list[dict]] = {}
    for record in canonical:
        if record.get("registry_id"):
            by_registry.setdefault(record["registry_id"], []).append(record)

    matched = []
    for page in pages:
        links = page.get("registry_links") or [{"registry_id": rid, "match_method": page.get("match_method"),
                                                "match_evidence": page.get("match_evidence"), "part_label": None}
                                               for rid in page.get("registry_ids") or []]
        for link in links:
            record = records.get(link["registry_id"])
            if record is None:
                continue
            entity = next((e for e in by_registry.get(record["registry_id"], [])
                           if e.get("source_page_id") == page["page_id"]), None)
            relations = {}
            for name, targets in ((entity or {}).get("relations") or {}).items():
                if name in {"located_in", "recognized_by"}:
                    continue
                relations[name] = [{"entity_id": t, "label_vi": by_entity.get(t, {}).get("label_vi"),
                                    "wikidata_id": (by_entity.get(t, {}).get("external_ids") or {}).get("wikidata")}
                                   for t in targets]
            matched.append({
                "registry_id": record["registry_id"], "registry_category": record["registry_category"],
                "label_vi": record["label_vi"], "location": (record.get("registry_fields") or {}).get("location", ""),
                "registry_url": record["registry_url"],
                "match_method": link.get("match_method"), "match_evidence": link.get("match_evidence"),
                "split_part": link.get("part_label"), "canonical_entity_id": (entity or {}).get("entity_id"),
                "wiki_title": page["title"], "wiki_url": page["source_url"], "page_id": page["page_id"],
                "wikidata_id": page.get("wikidata_id"),
                "wiki_categories": [c.replace("Thể loại:", "") for c in page.get("categories") or []
                                    if not any(k in c for k in MAINTENANCE)][:8],
                "abstract_head": (page.get("abstract") or "")[:300],
                "wiki_derived_fields": {k: v for k, v in (
                    ("coordinates", (entity or {}).get("coordinates")),
                    ("construction_year", (entity or {}).get("construction_year")),
                    ("relations_from_infobox", relations)) if v},
            })
    matched.sort(key=lambda r: (_order(r["registry_category"]), r["label_vi"], r["split_part"] or ""))

    unmatched = []
    for failure in failures:
        record = records.get(failure.get("registry_id"))
        if record is None:
            continue
        reason = failure.get("reason", "")
        unmatched.append({
            "registry_id": record["registry_id"], "registry_category": record["registry_category"],
            "label_vi": record["label_vi"], "location": (record.get("registry_fields") or {}).get("location", ""),
            "registry_url": record["registry_url"], "reason": reason, "reason_group": _reason_group(reason),
            "titles_tried": failure.get("titles_tried", []),
            "wiki_search_url": "https://vi.wikipedia.org/w/index.php?search=" + quote(record["label_vi"]),
        })
    unmatched.sort(key=lambda r: (_order(r["registry_category"]), r["label_vi"]))

    matched_ids = {r["registry_id"] for r in matched}
    matched_doc = {"summary": {
        "registry_records_matched": len(matched_ids), "links": len(matched), "pages": len(pages),
        "split_records": sum(1 for rid, n in Counter(r["registry_id"] for r in matched if r["split_part"]).items() if n > 1),
        "by_category": dict(sorted(Counter(records[rid]["registry_category"] for rid in matched_ids).items(), key=lambda kv: _order(kv[0]))),
        "by_match_method": dict(Counter(r["match_method"] for r in matched).most_common()),
    }, "records": matched}
    unmatched_doc = {"summary": {
        "registry_records_unmatched": len(unmatched),
        "by_category": dict(sorted(Counter(r["registry_category"] for r in unmatched).items(), key=lambda kv: _order(kv[0]))),
        "by_reason": dict(Counter(r["reason_group"] for r in unmatched).most_common()),
        "note": "titles_tried = mọi tiêu đề đã tra (tên gốc, luật alias, tiền tố, thành phần). wiki_search_url để tự tìm tay.",
    }, "records": unmatched}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "m2_wiki_matched.json").write_text(json.dumps(matched_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "m2_wiki_unmatched.json").write_text(json.dumps(unmatched_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return matched_doc["summary"], unmatched_doc["summary"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Xuất báo cáo khớp Wikipedia để review")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "m2_wiki_match")
    args = parser.parse_args()
    matched, unmatched = build(args.out_dir)
    print(json.dumps({"matched": matched, "unmatched": unmatched}, ensure_ascii=False, indent=2))
    print(f"m2-wiki-report: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
