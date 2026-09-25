"""Official Cục Di sản văn hóa registry collector (COMP-000, Section 7).

Đọc cấu hình từ ``config/registry_sources.yaml``, thu thập mọi item hợp lệ từ
17 category chính thức, ghi ``data/raw/registry_records.jsonl``,
``data/raw/registry_failures.jsonl``, ``data/raw/registry_quarantine.jsonl`` và
``reports/<snapshot_id>/coverage.json``.

Trong unit test, network thật KHÔNG được gọi — mọi test dùng HTML fixture mock
(Section 37 TEST-001..004, TEST-076..081). ``fetch_page`` là điểm duy nhất gọi
HTTP thật, dễ patch/mock trong test.

Các quy tắc M2 (xem ``M2_REMAINING_WORK.md``):

* M2-02 — ``registry_url`` lấy từ link trong ô nhãn; href rỗng, trang chủ, host
  ngoài ``dsvh.gov.vn`` hoặc một URL bị nhiều nhãn khác nhau dùng chung đều
  quay về URL category (bằng chứng chính thức của snapshot).
* M2-03 — ``registry_id`` KHÔNG phụ thuộc số thứ tự hay href:
  ``registry-sha256(category_url | category | label_key)[:12]``; chỉ khi nhiều
  row cùng nhãn mới bổ sung lần lượt địa điểm, văn bản công nhận, số thứ tự để
  phân biệt (deterministic trên cùng snapshot).
* M2-04 — category trả HTTP 200 nhưng không có row là lỗi BLOCKING
  (``REGISTRY_EMPTY_SOURCE``), TRỪ KHI config khai ``allow_empty_source: true`` kèm
  ``empty_source_note.decision`` (DEC-M2-001): khi đó category vẫn nằm trong coverage
  universe với 0/0 dòng, được ghi ở ``registry_empty_sources.jsonl`` và tự động được thu
  thập khi trang chính thức có dữ liệu.
* M2-06/07 — pagination theo ``next_page_selector`` (dừng khi fingerprint lặp
  hoặc vượt ``max_pages``); detail page chỉ fetch khi category khai cả
  ``detail_link_selector`` và ``detail_fields``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import yaml
from parsel import Selector

from vietheritage.normalization.normalizer import (
    canonical_identity_key,
    normalize_registry_url,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"

COVERAGE_CLAIM = "100% of selected official registry snapshot"
ALLOW_PARTIAL_ENV = "VH_REGISTRY_ALLOW_PARTIAL"
SAVE_HTML_ENV = "VH_SAVE_REGISTRY_HTML"


class RegistryParseError(RuntimeError):
    """REGISTRY_PARSE_ERROR — selector đổi, thiếu column bắt buộc, hoặc HTML lỗi."""


class RegistryEmptySourceError(RuntimeError):
    """REGISTRY_EMPTY_SOURCE — page fetched but no entity rows were extractable."""


class RegistryIdCollisionError(RuntimeError):
    """REGISTRY_ID_COLLISION — hai record cùng registry_id nhưng label/source khác nhau."""


class RegistryDetailError(RuntimeError):
    """REGISTRY_DETAIL_MISSING — detail page khai báo trong config không lấy/parse được."""


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
    detail_fields: dict[str, str] | None = None
    max_pages: int = 50
    allow_empty_source: bool = False
    empty_source_note: dict[str, Any] | None = None


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
    *disambiguators: str,
) -> str:
    """Section 13.1 — giữ official ID nếu có, nếu không hash deterministic.

    ``source_url`` MUST là URL category (ổn định), không phải href của row.
    ``disambiguators`` chỉ được truyền khi nhiều row cùng nhãn trong một category.
    """
    if official_id:
        return official_id
    parts = [source_url, registry_category, normalized_label, *[d for d in disambiguators if d is not None]]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"registry-{digest}"


def load_config(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], list[CategoryConfig]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if "base_url" not in raw or "categories" not in raw:
        raise ConfigInvalidError("registry_sources.yaml missing base_url or categories")
    if not raw["base_url"].startswith("https://dsvh.gov.vn"):
        raise ConfigInvalidError("base_url must be official HTTPS dsvh.gov.vn host")

    defaults = raw.get("defaults", {}) or {}
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
                detail_fields=cat.get("detail_fields"),
                max_pages=int(cat.get("max_pages") or defaults.get("max_pages") or 50),
                allow_empty_source=bool(cat.get("allow_empty_source", False)),
                empty_source_note=cat.get("empty_source_note"),
            )
        )
        if categories[-1].allow_empty_source and not (cat.get("empty_source_note") or {}).get("decision"):
            raise ConfigInvalidError(
                f"category {cat['key']}: allow_empty_source requires empty_source_note.decision (DEC id)")
    return raw, categories


def fetch_page(url: str, request_cfg: dict[str, Any], session: requests.Session | None = None,
               sleeper: Callable[[float], None] = time.sleep) -> str:
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
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:  # HTTP_TIMEOUT / HTTP_SERVER_ERROR
            last_exc = exc
            if attempt < retries:
                sleeper(backoffs[min(attempt, len(backoffs) - 1)])
    raise RegistryParseError(f"failed to fetch {url} after {retries} retries: {last_exc}") from last_exc


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
    header rows, and footer rows are excluded. Mỗi row trả ``cells``, ``hrefs``
    (mọi link trong row, giữ tương thích) và ``cell_hrefs`` (link theo từng ô).
    """
    del label_column_index
    selector = Selector(text=page_html)
    footer_res = [re.compile(pattern, re.IGNORECASE) for pattern in footer_patterns]
    rows: list[dict[str, Any]] = []

    for row in selector.css(row_selector):
        cell_nodes = row.css("td, th")
        cells = [_clean_cell_text(cell.xpath("string(.)").get()) for cell in cell_nodes]
        if not cells or not any(cells):
            continue
        if any(any(pattern.search(cell) for pattern in footer_res) for cell in cells):
            continue
        if _looks_like_header(cells):
            continue
        rows.append({
            "cells": cells,
            "hrefs": row.css("a::attr(href)").getall(),
            "cell_hrefs": [cell.css("a::attr(href)").getall() for cell in cell_nodes],
        })
    return rows


def _label_href(row: dict[str, Any], label_idx: int) -> str:
    cell_hrefs = row.get("cell_hrefs")
    if cell_hrefs is not None:
        hrefs = cell_hrefs[label_idx] if label_idx < len(cell_hrefs) else []
        return hrefs[0] if hrefs else ""
    # Row dựng tay (test cũ) không có cell_hrefs.
    return row["hrefs"][0] if row.get("hrefs") else ""


def assign_registry_ids(records: list[RegistryRecord], category_url: str) -> list[RegistryRecord]:
    """M2-03 — gán ``registry_id`` ổn định cho mọi record của MỘT category.

    Khóa gốc: URL category + category + ``canonical_identity_key(label)``. Nếu
    nhiều record trùng khóa, bổ sung dần địa điểm -> văn bản công nhận -> số thứ
    tự cho đến khi phân biệt được. Record trùng hoàn toàn cả bốn trường là lỗi
    ``REGISTRY_ID_COLLISION`` (không tự merge).
    """
    def component(record: RegistryRecord, name: str) -> str:
        value = record.registry_fields.get(name)
        return canonical_identity_key(str(value)) if value else ""

    levels = (("location",), ("location", "recognition_text"), ("location", "recognition_text", "ordinal"))
    groups: dict[str, list[RegistryRecord]] = {}
    for record in records:
        groups.setdefault(canonical_identity_key(record.label_vi), []).append(record)

    for label_key, members in groups.items():
        if len(members) == 1:
            members[0].registry_id = deterministic_registry_id(None, category_url, members[0].registry_category, label_key)
            continue
        for level in levels:
            keys = [tuple(component(m, name) for name in level) for m in members]
            if len(set(keys)) == len(keys) or level == levels[-1]:
                for member, key in zip(members, keys):
                    member.registry_id = deterministic_registry_id(
                        None, category_url, member.registry_category, label_key, *key
                    )
                break

    seen: dict[str, RegistryRecord] = {}
    for record in records:
        existing = seen.get(record.registry_id)
        if existing is not None and existing is not record:
            raise RegistryIdCollisionError(
                f"registry_id collision: {record.registry_id} ({existing.label_vi} vs {record.label_vi})"
            )
        seen[record.registry_id] = record
    return records


def release_shared_registry_urls(records: list[RegistryRecord], category_url: str) -> list[RegistryRecord]:
    """M2-02 — một detail URL bị nhiều nhãn KHÁC NHAU dùng chung không phải bằng
    chứng riêng của entity nào: quay về URL category và ghi ``registry_url_repair``."""
    owners: dict[str, set[str]] = {}
    for record in records:
        owners.setdefault(record.registry_url, set()).add(canonical_identity_key(record.label_vi))
    for record in records:
        if record.registry_url != category_url and len(owners[record.registry_url]) > 1:
            record.registry_fields["registry_url_repair"] = "REGISTRY_URL_SHARED"
            record.registry_url = category_url
    return records


def rows_to_records_with_quarantine(
    rows: list[dict[str, Any]],
    category: CategoryConfig,
    coverage_snapshot: str,
    retrieved_at: str,
    base_url: str,
) -> tuple[list[RegistryRecord], list[dict[str, Any]]]:
    """Row -> RegistryRecord. Row thiếu nhãn vào quarantine (Raw rule §11.3)."""
    records: list[RegistryRecord] = []
    quarantine: list[dict[str, Any]] = []
    label_idx = category.columns["label_vi"]
    for row in rows:
        cells = row["cells"]
        if label_idx >= len(cells):
            raise RegistryParseError(
                f"{category.key}: row missing label_vi column at index {label_idx}"
            )
        label_vi = cells[label_idx]
        if not label_vi:
            quarantine.append({
                "registry_category": category.key,
                "registry_url": category.url,
                "error_code": "REGISTRY_RECORD_INVALID",
                "reason": "missing label_vi",
                "cells": cells,
                "snapshot_id": coverage_snapshot,
            })
            continue

        registry_fields: dict[str, Any] = {}
        for field_name, idx in category.columns.items():
            if idx < len(cells):
                registry_fields[field_name] = cells[idx]

        registry_url, repair = normalize_registry_url(_label_href(row, label_idx), category.url, base_url)
        if repair and repair != "REGISTRY_URL_EMPTY":
            registry_fields["registry_url_repair"] = repair

        records.append(
            RegistryRecord(
                registry_id="",
                registry_category=category.key,
                label_vi=label_vi,
                registry_url=registry_url,
                source_status="registry_only",
                coverage_snapshot=coverage_snapshot,
                retrieved_at=retrieved_at,
                registry_fields=registry_fields,
            )
        )
    release_shared_registry_urls(records, category.url)
    assign_registry_ids(records, category.url)
    return records, quarantine


def rows_to_records(
    rows: list[dict[str, Any]],
    category: CategoryConfig,
    coverage_snapshot: str,
    retrieved_at: str,
    base_url: str,
) -> list[RegistryRecord]:
    records, _ = rows_to_records_with_quarantine(rows, category, coverage_snapshot, retrieved_at, base_url)
    return records


def _page_fingerprint(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps([row["cells"] for row in rows], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_page_url(page_html: str, selector: str | None, current_url: str, base_url: str) -> str | None:
    if not selector:
        return None
    hrefs = Selector(text=page_html).css(f"{selector}::attr(href)").getall()
    for href in hrefs:
        url, repair = normalize_registry_url(href, "", base_url)
        if url and repair in {None, "REGISTRY_URL_HTTP", "REGISTRY_URL_DOUBLE_SCHEME"} and url != current_url:
            return url
    return None


def fetch_category_rows(
    category: CategoryConfig,
    request_cfg: dict[str, Any],
    footer_patterns: list[str],
    base_url: str,
    fetcher: Callable[..., str],
    sleeper: Callable[[float], None],
    source_checksums: dict[str, str],
    save_html_dir: Path | None = None,
    delay_state: dict[str, bool] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """M2-06 — đi hết pagination, trả (rows, page_urls). Row lặp giữa các trang bị bỏ."""
    delay = float(request_cfg.get("delay_seconds", 0) or 0)
    delay_state = delay_state if delay_state is not None else {"first": True}
    rows: list[dict[str, Any]] = []
    page_urls: list[str] = []
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    seen_row_hashes: set[str] = set()
    url: str | None = category.url
    while url and url not in seen_urls and len(page_urls) < category.max_pages:
        if not delay_state.get("first") and delay:
            sleeper(delay)
        delay_state["first"] = False
        page_html = fetcher(url, request_cfg)
        seen_urls.add(url)
        page_urls.append(url)
        source_checksums[url] = hashlib.sha256(page_html.encode("utf-8")).hexdigest()
        if save_html_dir is not None:
            save_html_dir.mkdir(parents=True, exist_ok=True)
            (save_html_dir / f"{category.key}-p{len(page_urls):03d}.html").write_text(page_html, encoding="utf-8")
        page_rows = parse_table_rows(page_html, footer_patterns, row_selector=category.row_selector)
        fingerprint = _page_fingerprint(page_rows)
        if page_rows and fingerprint in seen_fingerprints:
            break
        seen_fingerprints.add(fingerprint)
        for row in page_rows:
            row_hash = hashlib.sha256(json.dumps(row["cells"], ensure_ascii=False).encode("utf-8")).hexdigest()
            if row_hash in seen_row_hashes:
                continue
            seen_row_hashes.add(row_hash)
            rows.append(row)
        url = _next_page_url(page_html, category.next_page_selector, url, base_url)
    return rows, page_urls


def fetch_detail_fields(
    records: list[RegistryRecord],
    category: CategoryConfig,
    request_cfg: dict[str, Any],
    fetcher: Callable[..., str],
    sleeper: Callable[[float], None],
    source_checksums: dict[str, str],
) -> None:
    """M2-07 — chỉ chạy khi category khai ``detail_link_selector`` VÀ ``detail_fields``."""
    if not category.detail_link_selector or not category.detail_fields:
        return
    delay = float(request_cfg.get("delay_seconds", 0) or 0)
    for record in records:
        if record.registry_url == category.url:
            raise RegistryDetailError(f"{category.key}: {record.registry_id} has no detail link")
        if delay:
            sleeper(delay)
        try:
            page_html = fetcher(record.registry_url, request_cfg)
        except RegistryParseError as exc:
            raise RegistryDetailError(f"{category.key}: {record.registry_id} detail fetch failed: {exc}") from exc
        source_checksums[record.registry_url] = hashlib.sha256(page_html.encode("utf-8")).hexdigest()
        selector = Selector(text=page_html)
        for field_name, css in category.detail_fields.items():
            node = selector.css(css)
            value = _clean_cell_text(node.xpath("string(.)").get()) if node else ""
            if value:
                record.registry_fields[f"detail_{field_name}"] = value


def _category_report(key: str, **values: Any) -> dict[str, Any]:
    report = {
        "registry_category": key, "discovered": 0, "valid": 0, "invalid": 0,
        "retrieved": 0, "failed": 0, "canonicalized": 0, "coverage_percent": 0.0,
        "http_status": None,
    }
    report.update(values)
    return report


def collect(
    config_path: Path = CONFIG_PATH,
    output_dir: Path = RAW_DIR,
    fetcher=fetch_page,
    category_keys: list[str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    save_html_dir: Path | None = None,
    include_article_sources: bool = True,
) -> dict[str, Any]:
    """Thu thập toàn bộ (hoặc `category_keys` được chỉ định) category.

    ``include_article_sources``: chạy cả ``article_sources`` (M2-26) của category được chọn.

    Trả về coverage report dict đúng ``schema/coverage.schema.json``.
    """
    raw_cfg, categories = load_config(config_path)
    if category_keys is not None:
        categories = [c for c in categories if c.key in category_keys]

    coverage_snapshot = new_snapshot_id()
    retrieved_at = utc_now_iso()
    request_cfg = raw_cfg.get("request", {}) or {}
    footer_patterns = (raw_cfg.get("defaults", {}) or {}).get("footer_patterns", ["^Tổng số", "^Total"])
    base_url = raw_cfg["base_url"]
    html_dir = save_html_dir
    if html_dir is None and os.getenv(SAVE_HTML_ENV) == "1":
        html_dir = output_dir / "registry_html" / coverage_snapshot

    all_records: list[RegistryRecord] = []
    failures: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    category_reports: list[dict[str, Any]] = []
    seen_ids: dict[str, RegistryRecord] = {}
    source_checksums: dict[str, str] = {}
    source_urls: list[str] = []
    delay_state = {"first": True}

    empty_sources: list[dict[str, Any]] = []
    for category in categories:
        http_status: str | None = None
        try:
            rows, page_urls = fetch_category_rows(
                category, request_cfg, footer_patterns, base_url, fetcher, sleeper,
                source_checksums, html_dir, delay_state,
            )
            source_urls.extend(page_urls)
            http_status = "200"
            if not rows and category.allow_empty_source:
                # Nhóm quyết định giữ category trong coverage universe dù trang chính thức chưa
                # công bố dòng nào (DEC-M2-001): 0/0 dòng đã công bố được thu thập. Khi trang có
                # dữ liệu, category được thu thập bình thường ở lần crawl sau, không cần sửa code.
                empty_sources.append({
                    "registry_category": category.key, "registry_url": category.url,
                    "snapshot_id": coverage_snapshot, "http_status": http_status, "rows_found": 0,
                    **(category.empty_source_note or {}),
                })
                category_reports.append(_category_report(
                    category.key, coverage_percent=100.0, http_status=http_status,
                ))
                continue
            if not rows:
                raise RegistryEmptySourceError(
                    f"{category.key}: no extractable entity rows in official page (HTTP 200 empty snapshot)"
                )
            records, bad_rows = rows_to_records_with_quarantine(rows, category, coverage_snapshot, retrieved_at, base_url)
            fetch_detail_fields(records, category, request_cfg, fetcher, sleeper, source_checksums)

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
            quarantine.extend(bad_rows)
            category_reports.append(_category_report(
                category.key,
                discovered=len(rows),
                valid=len(records),
                invalid=len(bad_rows),
                retrieved=len(records),
                canonicalized=len(records),
                coverage_percent=100.0,
                http_status=http_status,
            ))
        except (RegistryParseError, RegistryEmptySourceError, RegistryIdCollisionError, RegistryDetailError) as exc:
            error_code = (
                "REGISTRY_ID_COLLISION" if isinstance(exc, RegistryIdCollisionError)
                else "REGISTRY_EMPTY_SOURCE" if isinstance(exc, RegistryEmptySourceError)
                else "REGISTRY_DETAIL_MISSING" if isinstance(exc, RegistryDetailError)
                else "REGISTRY_PARSE_ERROR"
            )
            failures.append({
                "registry_category": category.key,
                "registry_url": category.url,
                "error": str(exc),
                "error_code": error_code,
                "http_status": http_status,
                "retry_limit": request_cfg.get("retries", 3),
                "snapshot_id": coverage_snapshot,
            })
            category_reports.append(_category_report(
                category.key, failed=1, coverage_percent=0.0, http_status=http_status,
            ))

    article_reports, article_quarantine = [], []
    if include_article_sources:
        article_reports, article_quarantine = _collect_article_sources(
            raw_cfg, categories, request_cfg, base_url, coverage_snapshot, retrieved_at, all_records, seen_ids,
            category_reports, failures, source_urls, source_checksums, fetcher, sleeper, html_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    if article_reports or article_quarantine:
        from vietheritage.registry.articles import QUARANTINE_FILE, REPORT_FILE

        with (output_dir / QUARANTINE_FILE).open("w", encoding="utf-8") as fh:
            for item in article_quarantine:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        (output_dir / REPORT_FILE).write_text(json.dumps(
            {"snapshot_id": coverage_snapshot, "retrieved_at": retrieved_at, "sources": article_reports,
             "records_added": sum(r["records"] for r in article_reports), "registry_total": len(all_records)},
            ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "registry_records.jsonl").open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
    with (output_dir / "registry_failures.jsonl").open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
    with (output_dir / "registry_quarantine.jsonl").open("w", encoding="utf-8") as fh:
        for item in quarantine:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (output_dir / "registry_empty_sources.jsonl").open("w", encoding="utf-8") as fh:
        for item in empty_sources:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    registry_total = sum(c["valid"] for c in category_reports)
    canonical_total = len(all_records)
    all_100 = bool(category_reports) and all(c["coverage_percent"] == 100.0 for c in category_reports)
    claim = COVERAGE_CLAIM if (not failures and all_100) else "coverage_failed"

    return {
        "snapshot_id": coverage_snapshot,
        "retrieved_at": retrieved_at,
        "source_urls": list(dict.fromkeys(source_urls or [c.url for c in categories])),
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


def _collect_article_sources(raw_cfg, categories, request_cfg, base_url, coverage_snapshot, retrieved_at,
                             all_records, seen_ids, category_reports, failures, source_urls, source_checksums,
                             fetcher, sleeper, html_dir) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """M2-26 — nguồn dạng danh sách bài viết (``article_sources``), cộng vào category đích.

    Chỉ chạy cho category đang được thu thập. Lỗi mạng/parse ở trang danh sách là blocking cho
    category đó (ghi failure_manifest như category dạng bảng).
    """
    from vietheritage.registry.articles import collect_article_source, coverage_increment, load_article_sources

    selected = {c.key for c in categories}
    reports: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    by_category = {item["registry_category"]: item for item in category_reports}
    for source in load_article_sources(raw_cfg):
        if not source.enabled or source.registry_category not in selected:
            continue
        try:
            records, bad, report = collect_article_source(
                source, request_cfg, base_url, coverage_snapshot, retrieved_at,
                [r.to_dict() for r in all_records], fetcher, sleeper, html_dir, source_checksums)
            for rec in records:
                if rec.registry_id in seen_ids:
                    raise RegistryIdCollisionError(f"registry_id collision: {rec.registry_id} ({rec.label_vi})")
                seen_ids[rec.registry_id] = rec
        except (RegistryParseError, RegistryIdCollisionError) as exc:
            failures.append({
                "registry_category": source.registry_category, "registry_url": source.list_url, "error": str(exc),
                "error_code": "REGISTRY_ID_COLLISION" if isinstance(exc, RegistryIdCollisionError) else "REGISTRY_PARSE_ERROR",
                "http_status": None, "retry_limit": request_cfg.get("retries", 3), "snapshot_id": coverage_snapshot,
            })
            item = by_category.get(source.registry_category)
            if item is not None:
                item["failed"] = int(item.get("failed") or 0) + 1
                item["coverage_percent"] = 0.0
            continue
        all_records.extend(records)
        quarantine.extend(bad)
        report["coverage_increment"] = increment = coverage_increment(report)
        reports.append(report)
        source_urls.extend(report["page_urls"])
        item = by_category.get(source.registry_category)
        if item is not None:
            for counter, value in increment.items():
                item[counter] = int(item.get(counter) or 0) + value
            item["canonicalized"] = int(item.get("canonicalized") or 0) + increment["valid"]
    return reports, quarantine


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

    report = collect(fetcher=fixture_fetcher, category_keys=["world_heritage"], output_dir=RAW_DIR,
                     sleeper=lambda _seconds: None)
    report["claim"] = "SKIPPED_SAMPLE_MODE"
    run_id = report["snapshot_id"]
    path = write_coverage_report(report, run_id)
    print(f"collect-sample: wrote {path}, canonical_total={report['canonical_total']}")
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_full() -> int:
    """`make collect` — crawl official registry and enrich it via Wikipedia."""
    report = collect()
    records = _read_jsonl(RAW_DIR / "registry_records.jsonl")
    from vietheritage.collector.wikipedia import enrich_many

    enrichment = enrich_many([
        {
            "registry_id": record["registry_id"],
            "label_vi": record["label_vi"],
            "registry_category": record["registry_category"],
            "location": (record.get("registry_fields") or {}).get("location"),
        }
        for record in records
    ])
    report["wikipedia_matched"] = enrichment["matched_registry_records"]
    report["wikidata_linked"] = enrichment.get("wikidata_linked", 0)
    report["registry_only"] = report["canonical_total"] - enrichment["matched_registry_records"]
    # unresolved_registry_ids = registry ID hợp lệ chưa vào canonical (cập nhật lại sau `make map`);
    # nhãn thiếu Wikipedia nằm ở data/raw/enrichment_failures.jsonl, không phải ở đây.
    report["unresolved_registry_ids"] = []
    run_id = report["snapshot_id"]
    path = write_coverage_report(report, run_id)
    empty_sources = _read_jsonl(RAW_DIR / "registry_empty_sources.jsonl")
    (path.parent / "coverage_empty_sources.json").write_text(
        json.dumps(empty_sources, ensure_ascii=False, indent=2), encoding="utf-8")
    if empty_sources:
        print(f"collect: {len(empty_sources)} category có trang chính thức rỗng (được chấp nhận, vẫn trong phạm vi) "
              f"-> {path.parent / 'coverage_empty_sources.json'}")
    print(
        f"collect: wrote {path}, registry={report['registry_total']}, "
        f"wikipedia={enrichment['matched_registry_records']}/{enrichment['total']}, claim={report['claim']}"
    )
    if report["claim"] == COVERAGE_CLAIM:
        return 0
    failed = [f"{item['registry_category']}:{item['error_code']}" for item in report["failure_manifest"]]
    print(f"collect: coverage_failed -> {', '.join(failed) or 'category counters below 100%'}")
    if os.getenv(ALLOW_PARTIAL_ENV) == "1":
        print(f"collect: {ALLOW_PARTIAL_ENV}=1 -> tiếp tục pipeline với snapshot KHÔNG đầy đủ (claim vẫn là coverage_failed)")
        return 0
    return 1
