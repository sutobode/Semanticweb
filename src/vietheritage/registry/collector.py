"""Official Cục Di sản văn hóa registry collector (COMP-000, Section 7).

Đọc cấu hình từ ``config/registry_sources.yaml``, thu thập mọi item hợp lệ từ
17 category chính thức, ghi ``data/raw/registry_records.jsonl``,
``data/raw/registry_failures.jsonl`` và ``reports/<run_id>/coverage.json``.

Trong RUN_MODE=sample, network thật KHÔNG được gọi trong lúc unit test — mọi
test dùng HTML fixture mock (Section 37 TEST-076..081). ``fetch_page`` là điểm
duy nhất gọi HTTP thật, dễ patch/mock trong test.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"


class RegistryParseError(RuntimeError):
    """REGISTRY_PARSE_ERROR — selector đổi, thiếu column bắt buộc, hoặc HTML lỗi."""


class RegistryEmptySourceError(RuntimeError):
    """REGISTRY_EMPTY_SOURCE — page fetched but no entity rows were extractable."""


class RegistryIdCollisionError(RuntimeError):
    """REGISTRY_ID_COLLISION — hai record cùng registry_id nhưng label/source khác nhau."""


class ConfigInvalidError(RuntimeError):
    """CONFIG_INVALID — registry_sources.yaml thiếu key bắt buộc hoặc sai host."""


@dataclass
class CategoryConfig:
    key: str
    url: str
    entity_type: str
    row_selector: str
    columns: dict[str, int]
    detail_link_selector: str | None = None
    next_page_selector: str | None = None
    ontology_subclass: str | None = None


@dataclass
class RegistryRecord:
    registry_id: str
    registry_category: str
    label_vi: str
    registry_url: str
    source_status: str
    coverage_snapshot: str
    retrieved_at: str
    registry_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "registry_category": self.registry_category,
            "label_vi": self.label_vi,
            "registry_url": self.registry_url,
            "source_status": self.source_status,
            "coverage_snapshot": self.coverage_snapshot,
            "retrieved_at": self.retrieved_at,
            "registry_fields": self.registry_fields,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_snapshot_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def deterministic_registry_id(
    official_id: str | None,
    source_url: str,
    registry_category: str,
    normalized_label: str,
) -> str:
    """Section 13.1 — giữ official ID nếu có, nếu không hash deterministic."""
    if official_id:
        return official_id
    digest = hashlib.sha256(
        f"{source_url}|{registry_category}|{normalized_label}".encode("utf-8")
    ).hexdigest()[:12]
    return f"registry-{digest}"


def load_config(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], list[CategoryConfig]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if "base_url" not in raw or "categories" not in raw:
        raise ConfigInvalidError("registry_sources.yaml missing base_url or categories")
    if not raw["base_url"].startswith("https://dsvh.gov.vn"):
        raise ConfigInvalidError("base_url must be official HTTPS dsvh.gov.vn host")

    defaults = raw.get("defaults", {})
    categories: list[CategoryConfig] = []
    for cat in raw["categories"]:
        row_selector = cat.get("row_selector") or defaults.get("row_selector")
        if not row_selector or "columns" not in cat or "label_vi" not in cat.get("columns", {}):
            raise RegistryParseError(
                f"category {cat.get('key')} missing row_selector or columns.label_vi"
            )
        categories.append(
            CategoryConfig(
                key=cat["key"],
                url=cat["url"],
                entity_type=cat["entity_type"],
                row_selector=row_selector,
                columns=cat["columns"],
                detail_link_selector=cat.get("detail_link_selector"),
                next_page_selector=cat.get("next_page_selector") or defaults.get("next_page_selector"),
                ontology_subclass=cat.get("ontology_subclass"),
            )
        )
    return raw, categories


def fetch_page(url: str, request_cfg: dict[str, Any], session: requests.Session | None = None) -> str:
    """Điểm duy nhất gọi HTTP thật (NFR-007: timeout 30s, 3 retry, backoff 2/4/8s)."""
    sess = session or requests.Session()
    timeout = request_cfg.get("timeout_seconds", 30)
    retries = request_cfg.get("retries", 3)
    backoffs = request_cfg.get("backoff_seconds", [2, 4, 8])
    headers = {"User-Agent": request_cfg.get("user_agent", "VietHeritageLOD/1.0")}

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:  # HTTP_TIMEOUT / HTTP_SERVER_ERROR
            last_exc = exc
            if attempt < retries:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
    raise RegistryParseError(f"failed to fetch {url}: {last_exc}") from last_exc


from scrapy import Selector


def _clean_cell_text(value: str | None) -> str:
    """Return normalized descendant text, including nested spans and links."""
    if not value:
        return ""
    return " ".join(value.replace("\xa0", " ").split())


def _looks_like_header(cells: list[str]) -> bool:
    first = cells[0].casefold()
    if first in {"tt", "stt", "số tt", "no", "no."}:
        return True
    header_tokens = (
        "tên di sản", "tên di tích", "tên hiện vật", "tên bảo tàng",
        "họ và tên", "quyết định", "số quyết định", "ngày tháng năm",
        "địa điểm", "địa chỉ", "loại hình ghi danh", "tỉnh/thành phố",
    )
    header_hits = sum(
        any(token in cell.casefold() for token in header_tokens)
        for cell in cells
    )
    return header_hits >= 2 or any(
        token in cells[0].casefold()
        for token in ("số quyết định", "ngày tháng năm")
    )


def parse_table_rows(
    page_html: str,
    footer_patterns: list[str],
    label_column_index: int = 1,
    row_selector: str = "table tbody tr",
) -> list[dict[str, Any]]:
    """Extract configured rows with Parsel/lxml CSS selectors.

    ``string(.)`` is used instead of ``td::text`` because dsvh.gov.vn puts
    values inside nested anchors/spans on some tables. Empty layout rows,
    header rows, and footer rows are excluded. ``label_column_index`` remains
    for backwards API compatibility; footer detection checks every cell.
    """
    del label_column_index
    selector = Selector(text=page_html)
    footer_res = [re.compile(pattern, re.IGNORECASE) for pattern in footer_patterns]
    rows: list[dict[str, Any]] = []

    for row in selector.css(row_selector):
        cells = [
            _clean_cell_text(cell.xpath("string(.)").get())
            for cell in row.css("td, th")
        ]
        if not cells or not any(cells):
            continue
        if any(any(pattern.search(cell) for pattern in footer_res) for cell in cells):
            continue
        if _looks_like_header(cells):
            continue
        rows.append({"cells": cells, "hrefs": row.css("a::attr(href)").getall()})
    return rows


def rows_to_records(
    rows: list[dict[str, Any]],
    category: CategoryConfig,
    coverage_snapshot: str,
    retrieved_at: str,
    base_url: str,
) -> list[RegistryRecord]:
    records: list[RegistryRecord] = []
    for row in rows:
        cells = row["cells"]
        label_idx = category.columns["label_vi"]
        if label_idx >= len(cells):
            raise RegistryParseError(
                f"{category.key}: row missing label_vi column at index {label_idx}"
            )
        label_vi = cells[label_idx]
        if not label_vi:
            continue

        registry_fields: dict[str, Any] = {}
        for field_name, idx in category.columns.items():
            if idx < len(cells):
                registry_fields[field_name] = cells[idx]

        href = row["hrefs"][0] if row["hrefs"] else ""
        candidate_url = urljoin(base_url, href)
        parsed_url = urlparse(candidate_url)
        if (
            parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.netloc)
            and not any(char.isspace() for char in candidate_url)
        ):
            registry_url = candidate_url
        else:
            # Keep the official category snapshot as authoritative evidence when
            # an HTML href contains display text or another malformed URL.
            registry_url = category.url

        identity_parts = [label_vi.strip().lower()]
        for field_name in ("ordinal", "recognition_text", "location"):
            value = registry_fields.get(field_name)
            if value:
                identity_parts.append(str(value).strip().lower())
        registry_id = deterministic_registry_id(
            official_id=None,
            source_url=registry_url,
            registry_category=category.key,
            normalized_label="|".join(identity_parts),
        )

        records.append(
            RegistryRecord(
                registry_id=registry_id,
                registry_category=category.key,
                label_vi=label_vi,
                registry_url=registry_url,
                source_status="registry_only",
                coverage_snapshot=coverage_snapshot,
                retrieved_at=retrieved_at,
                registry_fields=registry_fields,
            )
        )
    return records


def collect(
    config_path: Path = CONFIG_PATH,
    output_dir: Path = RAW_DIR,
    fetcher=fetch_page,
    category_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Thu thập toàn bộ (hoặc `category_keys` được chỉ định) category.

    Trả về coverage report dict đúng ``schema/coverage.schema.json``.
    """
    raw_cfg, categories = load_config(config_path)
    if category_keys is not None:
        categories = [c for c in categories if c.key in category_keys]

    coverage_snapshot = new_snapshot_id()
    retrieved_at = utc_now_iso()
    request_cfg = raw_cfg.get("request", {})
    footer_patterns = raw_cfg.get("defaults", {}).get("footer_patterns", ["^Tổng số", "^Total"])

    all_records: list[RegistryRecord] = []
    failures: list[dict[str, Any]] = []
    category_reports: list[dict[str, Any]] = []
    seen_ids: dict[str, RegistryRecord] = {}
    source_checksums: dict[str, str] = {}

    for category in categories:
        http_status: str | None = None
        try:
            page_html = fetcher(category.url, request_cfg)
            http_status = "200"
            source_checksums[category.url] = hashlib.sha256(page_html.encode("utf-8")).hexdigest()
            rows = parse_table_rows(
                page_html,
                footer_patterns,
                label_column_index=category.columns.get("label_vi", 1),
                row_selector=category.row_selector,
            )
            if not rows:
                failures.append(
                    {
                        "registry_category": category.key,
                        "registry_url": category.url,
                        "error": f"{category.key}: no extractable entity rows in official page (HTTP 200 empty snapshot)",
                        "error_code": "REGISTRY_EMPTY_SOURCE",
                        "snapshot_id": coverage_snapshot,
                    }
                )
                category_reports.append(
                    {
                        "registry_category": category.key,
                        "discovered": 0,
                        "valid": 0,
                        "invalid": 0,
                        "retrieved": 0,
                        "failed": 0,
                        "canonicalized": 0,
                        "coverage_percent": 100.0,
                        "http_status": http_status,
                    }
                )
                continue
            records = rows_to_records(rows, category, coverage_snapshot, retrieved_at, raw_cfg["base_url"])
            if len(records) != len(rows):
                raise RegistryParseError(
                    f"{category.key}: {len(rows) - len(records)} rows missing required label_vi"
                )

            for rec in records:
                existing = seen_ids.get(rec.registry_id)
                if existing is not None and (
                    existing.label_vi != rec.label_vi or existing.registry_url != rec.registry_url
                ):
                    raise RegistryIdCollisionError(
                        f"registry_id collision: {rec.registry_id} ({existing.label_vi} vs {rec.label_vi})"
                    )
                seen_ids[rec.registry_id] = rec

            all_records.extend(records)
            category_reports.append(
                {
                    "registry_category": category.key,
                    "discovered": len(rows),
                    "valid": len(records),
                    "invalid": len(rows) - len(records),
                    "retrieved": len(records),
                    "failed": 0,
                    "canonicalized": len(records),
                    "coverage_percent": 100.0 if rows else 0.0,
                    "http_status": "200",
                }
            )
        except (RegistryParseError, RegistryEmptySourceError, RegistryIdCollisionError) as exc:
            failures.append(
                {
                    "registry_category": category.key,
                    "registry_url": category.url,
                    "error": str(exc),
                    "error_code": (
                        "REGISTRY_ID_COLLISION"
                        if isinstance(exc, RegistryIdCollisionError)
                        else "REGISTRY_EMPTY_SOURCE"
                        if isinstance(exc, RegistryEmptySourceError)
                        else "REGISTRY_PARSE_ERROR"
                    ),
                    "snapshot_id": coverage_snapshot,
                }
            )
            category_reports.append(
                {
                    "registry_category": category.key,
                    "discovered": 0,
                    "valid": 0,
                    "invalid": 0,
                    "retrieved": 0,
                    "failed": 1,
                    "canonicalized": 0,
                    "coverage_percent": 0.0,
                    "http_status": http_status,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "registry_records.jsonl"
    failures_path = output_dir / "registry_failures.jsonl"
    with records_path.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
    with failures_path.open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(failure, ensure_ascii=False) + "\n")

    registry_total = sum(c["valid"] for c in category_reports)
    canonical_total = len(all_records)
    all_100 = all(c["coverage_percent"] == 100.0 for c in category_reports)
    blocking_failures = [
        failure for failure in failures if failure.get("error_code") != "REGISTRY_EMPTY_SOURCE"
    ]
    claim = "100% of selected official registry snapshot" if (not blocking_failures and all_100) else "coverage_failed"

    coverage_report = {
        "snapshot_id": coverage_snapshot,
        "retrieved_at": retrieved_at,
        "source_urls": [c.url for c in categories],
        "source_checksums": source_checksums,
        "categories": category_reports,
        "registry_total": registry_total,
        "canonical_total": canonical_total,
        "registry_only": canonical_total,
        "wikipedia_matched": 0,
        "wikidata_linked": 0,
        "dbpedia_verified": 0,
        "unresolved_registry_ids": [],
        "failure_manifest": failures,
        "claim": claim,
    }
    return coverage_report


def write_coverage_report(report: dict[str, Any], run_id: str, reports_root: Path | None = None) -> Path:
    root = reports_root or (REPO_ROOT / "reports")
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = run_dir / "coverage.json"
    coverage_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return coverage_path


def collect_sample() -> int:
    """`make collect-sample` — dùng fixture HTML, KHÔNG gọi network thật."""
    fixture_html_path = FIXTURES_DIR / "registry_sample_page.html"
    fixture_html = fixture_html_path.read_text(encoding="utf-8")

    def fixture_fetcher(url: str, request_cfg: dict[str, Any]) -> str:  # noqa: ARG001
        return fixture_html

    report = collect(fetcher=fixture_fetcher, category_keys=["world_heritage"], output_dir=RAW_DIR)
    report["claim"] = "SKIPPED_SAMPLE_MODE"
    run_id = report["snapshot_id"]
    path = write_coverage_report(report, run_id)
    print(f"collect-sample: wrote {path}, canonical_total={report['canonical_total']}")
    return 0


def collect_full() -> int:
    """`make collect` — crawl official registry and enrich it via Wikipedia."""
    report = collect()
    records_path = RAW_DIR / "registry_records.jsonl"
    labels = []
    if records_path.exists():
        with records_path.open(encoding="utf-8") as fh:
            labels = [json.loads(line)["label_vi"] for line in fh if line.strip()]
    from vietheritage.collector.wikipedia import enrich_many

    enrichment = enrich_many(labels)
    report["wikipedia_matched"] = enrichment["matched"]
    report["wikidata_linked"] = enrichment.get("wikidata_linked", 0)
    by_label = {record["label_vi"]: record["registry_id"] for record in (
        json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()
    )}
    failures_path = RAW_DIR / "enrichment_failures.jsonl"
    report["unresolved_registry_ids"] = [
        by_label.get(item.get("label_vi"), item.get("label_vi", ""))
        for item in (
            json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    ] if failures_path.exists() else []
    run_id = report["snapshot_id"]
    path = write_coverage_report(report, run_id)
    print(
        f"collect: wrote {path}, registry={report['registry_total']}, "
        f"wikipedia={enrichment['matched']}/{enrichment['total']}, claim={report['claim']}"
    )
    return 0 if report["claim"] == "100% of selected official registry snapshot" else 1

