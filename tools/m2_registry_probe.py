"""M2-05 — khảo sát HTML thật của các category registry (CẦN MẠNG, chạy trên máy dev).

    python tools/m2_registry_probe.py                          # 10 category đang rỗng + national_monuments
    python tools/m2_registry_probe.py --all                    # cả 17 category
    python tools/m2_registry_probe.py --category artisans --save

Với mỗi category script in ra: số bảng, số dòng mỗi bảng + 2 dòng đầu, số dòng
parse được bằng config hiện tại, link phân trang ứng viên, file đính kèm
(PDF/DOC/XLS), iframe (bảng nhúng). ``--save`` lưu HTML vào
``data/fixtures/registry/<category>.html`` để viết unit test offline và sửa
``config/registry_sources.yaml`` — KHÔNG hard-code selector trong Python.
Kết quả tóm tắt ghi vào ``reports/m2_registry_probe.json``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from parsel import Selector  # noqa: E402

from vietheritage.registry.collector import CategoryConfig, fetch_page, load_config, parse_table_rows  # noqa: E402

PROBLEM_CATEGORIES = {
    "artisans", "artifacts_antiquities", "national_artisans", "meritorious_artisans", "national_museums",
    "ministry_museums", "central_organization_museums", "provincial_museums", "private_museums",
    "documentary_heritage", "national_monuments",
}
PAGINATION_HINT = re.compile(r"(page|trang|p=|paged|\bnext\b|sau|›|»)", re.IGNORECASE)
ATTACHMENT = re.compile(r"\.(pdf|docx?|xlsx?)(\?|$)", re.IGNORECASE)


def _text(node) -> str:
    return " ".join((node.xpath("string(.)").get() or "").replace("\xa0", " ").split())


def probe(category, raw_cfg: dict, save: bool) -> dict:
    html = fetch_page(category.url, raw_cfg.get("request", {}))
    selector = Selector(text=html)
    tables = []
    for index, table in enumerate(selector.css("table")):
        rows = table.css("tr")
        tables.append({
            "index": index,
            "rows": len(rows),
            "has_tbody": bool(table.css("tbody")),
            "sample": [[_text(cell) for cell in row.css("td, th")][:6] for row in rows[:3]],
        })
    anchors = [(a.attrib.get("href", ""), _text(a)) for a in selector.css("a")]
    pagination = sorted({urljoin(category.url, href) for href, text in anchors
                         if href and PAGINATION_HINT.search(href + " " + text) and "dsvh.gov.vn" in urljoin(category.url, href)})[:15]
    attachments = sorted({urljoin(category.url, href) for href, _ in anchors if ATTACHMENT.search(href)})
    iframes = [urljoin(category.url, src) for src in selector.css("iframe::attr(src)").getall()]
    footer = (raw_cfg.get("defaults") or {}).get("footer_patterns", ["^Tổng số"])
    parsed = parse_table_rows(html, footer, row_selector=category.row_selector)
    result = {
        "category": category.key, "url": category.url, "html_bytes": len(html),
        "configured_row_selector": category.row_selector, "configured_columns": category.columns,
        "rows_parsed_with_current_config": len(parsed),
        "first_parsed_row": parsed[0]["cells"] if parsed else None,
        "tables": tables, "pagination_candidates": pagination,
        "attachments": attachments, "iframes": iframes,
    }
    if save:
        folder = ("reports", "m2_probe_extra") if category.key.startswith("url:") else ("data", "fixtures", "registry")
        name = re.sub(r"[^a-z0-9-]+", "-", category.key.split(":", 1)[-1].lower()).strip("-")
        target = REPO_ROOT.joinpath(*folder) / f"{name}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        result["saved_fixture"] = str(target.relative_to(REPO_ROOT))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Khảo sát HTML registry dsvh.gov.vn")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--category", action="append")
    parser.add_argument("--save", action="store_true", help="lưu HTML làm fixture")
    parser.add_argument("--url", action="append", help="khảo sát thêm URL ứng viên (không thuộc config), ví dụ "
                        "https://dsvh.gov.vn/di-san-tu-lieu-1761; HTML lưu ở reports/m2_probe_extra/")
    args = parser.parse_args()
    raw_cfg, categories = load_config()
    wanted = set(args.category or []) or (None if args.all else PROBLEM_CATEGORIES)
    extra = [CategoryConfig(key=f"url:{url.rstrip('/').rsplit('/', 1)[-1]}", url=url, entity_type="?",
                            row_selector="table tr", columns={"label_vi": 1}) for url in (args.url or [])]
    if extra and not (args.all or args.category):
        wanted = set()
    categories = categories + extra
    if extra:
        wanted = (wanted or set()) | {c.key for c in extra} if wanted is not None else None
    results = []
    for category in categories:
        if wanted is not None and category.key not in wanted:
            continue
        try:
            result = probe(category, raw_cfg, args.save)
        except Exception as exc:  # báo cáo khảo sát, không dừng các category khác
            result = {"category": category.key, "url": category.url, "error": str(exc)}
        results.append(result)
        print(f"\n== {category.key}  {category.url}")
        if "error" in result:
            print(f"   ERROR {result['error']}")
        else:
            print(f"   parsed with current config: {result['rows_parsed_with_current_config']} rows")
            for table in result["tables"]:
                print(f"   table[{table['index']}] rows={table['rows']} tbody={table['has_tbody']} sample={table['sample'][:2]}")
            for key in ("pagination_candidates", "attachments", "iframes"):
                if result[key]:
                    print(f"   {key}: {result[key][:5]}")
        time.sleep(float((raw_cfg.get("request") or {}).get("delay_seconds", 1) or 0))
    out = REPO_ROOT / "reports" / "m2_registry_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nm2-registry-probe: {len(results)} categories -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
