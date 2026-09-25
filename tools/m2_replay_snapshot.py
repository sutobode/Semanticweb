"""Dựng lại snapshot registry + Wikipedia từ HTML/page đã tải, KHÔNG gọi network.

Dùng khi code parse/matching thay đổi sau một lần crawl thật (ví dụ crawl trên Kaggle):
parse lại HTML đã lưu bằng collector hiện tại và lọc lại ``pages.jsonl`` bằng chính sách
matching hiện tại, giữ nguyên ``snapshot_id``/``retrieved_at`` của lần crawl gốc.

    python tools/m2_replay_snapshot.py \
        --html-dir data/fixtures/registry \
        --pages path/to/pages.jsonl \
        --coverage path/to/reports/<snapshot>/coverage.json \
        --apply

HTML trong ``--html-dir`` đặt tên ``<category>.html`` (output của tools/m2_registry_probe.py
--save) hoặc ``<category>-p001.html`` (output của VH_SAVE_REGISTRY_HTML=1).
Chỉ trang đầu mỗi category được replay (site hiện không phân trang).
Quan hệ Wikipedia (relation_candidates) được giữ nguyên như lúc crawl; muốn áp pattern
quan hệ mới thì phải crawl lại có mạng.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vietheritage.collector import wikipedia as wiki  # noqa: E402
from vietheritage.registry import collector  # noqa: E402

RAW = REPO_ROOT / "data" / "raw"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _html_for(html_dir: Path, key: str) -> Path:
    for name in (f"{key}.html", f"{key}-p001.html"):
        if (html_dir / name).exists():
            return html_dir / name
    raise FileNotFoundError(f"no saved HTML for category {key} in {html_dir}")


def replay_registry(html_dir: Path, snapshot_id: str, retrieved_at: str, out_dir: Path) -> dict:
    _, categories = collector.load_config()
    by_url = {category.url: _html_for(html_dir, category.key) for category in categories}

    def fetcher(url, request_cfg):  # noqa: ARG001
        if url not in by_url:
            raise collector.RegistryParseError(f"replay: no saved HTML for {url}")
        return by_url[url].read_text(encoding="utf-8")

    original = (collector.new_snapshot_id, collector.utc_now_iso)
    collector.new_snapshot_id = lambda: snapshot_id
    collector.utc_now_iso = lambda: retrieved_at
    try:
        # Snapshot 2026-09-23 chỉ có HTML các trang BẢNG; nguồn bài viết (M2-26) có sau -> không replay.
        return collector.collect(output_dir=out_dir, fetcher=fetcher, sleeper=lambda _s: None,
                                 include_article_sources=False)
    finally:
        collector.new_snapshot_id, collector.utc_now_iso = original


def refilter_pages(pages: list[dict], records: list[dict], matching: dict) -> tuple[list[dict], list[dict]]:
    """Áp lại page_rejection_reason + ambiguous_shared_pages lên page đã crawl."""
    by_id = {record["registry_id"]: record for record in records}
    kept: list[dict] = []
    failures: list[dict] = []
    assignments = []
    for page in pages:
        valid_links = []
        links = page.get("registry_links") or [{"registry_id": rid, "part_label": None, "match_method": page.get("match_method")}
                                               for rid in page.get("registry_ids") or []]
        for link in links:
            record = by_id.get(link["registry_id"])
            if record is None:
                continue
            reason = None if link.get("match_method") == "manual_override" else \
                wiki.page_rejection_reason(page.get("categories") or [], record["registry_category"], matching)
            if reason:
                failures.append({"registry_id": record["registry_id"], "label_vi": record["label_vi"],
                                 "error_code": "ENRICHMENT_MISSING", "reason": f"{reason} (replay of {page['title']!r})"})
                continue
            valid_links.append(dict(link, label_vi=record["label_vi"]))
            if link.get("match_method") != "manual_override":
                assignments.append((page["page_id"], record["registry_category"], link.get("part_label") or record["label_vi"]))
        if valid_links:
            valid_ids = list(dict.fromkeys(link["registry_id"] for link in valid_links))
            kept.append(dict(page, registry_ids=valid_ids, registry_links=valid_links,
                             requested_labels=list(dict.fromkeys(by_id[i]["label_vi"] for i in valid_ids))))
    ambiguous = wiki.ambiguous_shared_pages(assignments) if matching.get("reject_shared_page_different_labels", True) else set()
    result = []
    for page in kept:
        if page["page_id"] in ambiguous:
            for registry_id in page["registry_ids"]:
                failures.append({"registry_id": registry_id, "label_vi": by_id[registry_id]["label_vi"],
                                 "error_code": "ENRICHMENT_MISSING", "reason": f"ambiguous shared page {page['title']!r}"})
            continue
        result.append(page)
    return result, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay registry HTML + re-filter Wikipedia pages offline")
    parser.add_argument("--html-dir", type=Path, default=REPO_ROOT / "data" / "fixtures" / "registry")
    parser.add_argument("--pages", type=Path, required=True, help="pages.jsonl của lần crawl gốc")
    parser.add_argument("--enrichment-failures", type=Path, help="enrichment_failures.jsonl của lần crawl gốc")
    parser.add_argument("--coverage", type=Path, required=True, help="coverage.json của lần crawl gốc")
    parser.add_argument("--apply", action="store_true", help="ghi vào data/raw và reports/<snapshot>/")
    args = parser.parse_args()

    coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        report = replay_registry(args.html_dir, coverage["snapshot_id"], coverage["retrieved_at"], out)
        records = _read(out / "registry_records.jsonl")
        matching = (wiki.load_config().get("matching") or {})
        pages, new_failures = refilter_pages(_read(args.pages), records, matching)
        previous_failures = _read(args.enrichment_failures) if args.enrichment_failures else []
        ids_known = {record["registry_id"] for record in records}
        failures = [f for f in previous_failures if f.get("registry_id") in ids_known] + new_failures

        matched = {registry_id for page in pages for registry_id in page["registry_ids"]}
        report["wikipedia_matched"] = len(matched)
        report["registry_only"] = report["canonical_total"] - len(matched)
        report["wikidata_linked"] = sum(1 for page in pages if page.get("wikidata_id"))
        old_ids = {row["registry_id"] for row in _read(RAW / "registry_records.jsonl")}
        summary = {
            "snapshot_id": report["snapshot_id"],
            "claim": report["claim"],
            "registry_records": len(records),
            "registry_failures": [f"{f['registry_category']}:{f['error_code']}" for f in report["failure_manifest"]],
            "empty_categories_in_scope": [row["registry_category"] for row in _read(out / "registry_empty_sources.jsonl")],
            "registry_url_repairs": dict(Counter(r["registry_fields"].get("registry_url_repair", "none") for r in records)),
            "id_retention_vs_current_raw": round(len(ids_known & old_ids) / len(old_ids), 4) if old_ids else None,
            "pages_before": len(_read(args.pages)),
            "pages_after": len(pages),
            "registry_records_enriched": len(matched),
            "rejected_by_policy": [f"{f['label_vi']} -> {f['reason']}" for f in new_failures],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.apply:
            for name in ("registry_records.jsonl", "registry_failures.jsonl", "registry_quarantine.jsonl", "registry_empty_sources.jsonl"):
                shutil.copy(out / name, RAW / name)
            (RAW / "registry_exclusions.jsonl").unlink(missing_ok=True)  # file của cơ chế cũ (đã bỏ)
            _write(RAW / "pages.jsonl", pages)
            _write(RAW / "enrichment_failures.jsonl", failures)
            report_dir = collector.write_coverage_report(report, report["snapshot_id"]).parent
            for stale in ("registry_exclusions.jsonl", "coverage_exclusions.json"):
                (report_dir / stale).unlink(missing_ok=True)
            (report_dir / "coverage_empty_sources.json").write_text(
                json.dumps(_read(out / "registry_empty_sources.jsonl"), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"replay: applied to {RAW} and {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
