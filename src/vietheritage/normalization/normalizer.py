"""Normalizer — NOR-001..NOR-015 (COMP-002, Section 17).

Input: ``data/raw/registry_records.jsonl``. Output: ``data/processed/normalized.jsonl``,
``data/processed/skipped_records.jsonl``.

Ghi chú M2: enrichment Wikipedia (``data/raw/pages.jsonl``) được ghép ở COMP-004
(mapper) theo ``registry_id``; page đã được chuẩn hóa ngay trong collector
(NFC, tiêu đề thật, URL không fragment). Stage này còn:

* validate raw theo ``schema/raw-page.schema.json`` (FR-002, ``RAW_SCHEMA_INVALID``);
* sửa ``registry_url`` của snapshot cũ (trang chủ/``http``/``https://https://``, M2-02);
* chuẩn hóa ``retrieved_at`` về UTC ``Z`` và text trong ``registry_fields``;
* cung cấp ``parse_recognition_year`` (M2-01) cho mapper.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REGISTRY_CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
RAW_SCHEMA_PATH = REPO_ROOT / "schema" / "raw-page.schema.json"

OFFICIAL_REGISTRY_HOST = "dsvh.gov.vn"

CORE_REQUIRED_FIELDS = [
    "registry_id", "registry_category", "label_vi", "registry_url",
    "source_status", "coverage_snapshot", "retrieved_at",
]

_DASH_CHARS = ["\u2012", "\u2013", "\u2014"]  # ‒ – —
_UNKNOWN_VALUES = {"n/a", "N/A", "?", "chưa rõ", "chua ro", ""}


def normalize_text(value: str) -> str:
    """NOR-001 (whitespace) + NOR-003 (newline)."""
    text = value.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_nfc(value: str) -> str:
    """NOR-002 — Unicode NFD -> NFC."""
    return unicodedata.normalize("NFC", value)


def canonical_dash(value: str) -> str:
    """NOR-004 — chuẩn hóa mọi dash Unicode thành '-' (U+002D) cho identity key."""
    result = value
    for dash in _DASH_CHARS:
        result = result.replace(dash, "-")
    return result


def canonical_label_for_display(value: str) -> str:
    """NOR-004 — display literal giữ nguyên dash gốc, chỉ normalize NFC + whitespace."""
    return normalize_nfc(normalize_text(value))


def canonical_identity_key(label_vi: str) -> str:
    """Section 17 — NFC(lowercase(canonical_dash(trim(collapse_whitespace(label_vi))))) ."""
    text = normalize_text(label_vi)
    text = canonical_dash(text)
    text = normalize_nfc(text)
    return text.casefold()


_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_YEAR_RANGE_RE = re.compile(r"(?<!\d)(\d{4})\s*[-\u2012\u2013\u2014]\s*(\d{4})(?!\d)")


def parse_year(value: str) -> int | None:
    """NOR-005 — '1070', 'năm 1070' -> integer 1070."""
    if is_unknown_value(value):
        return None
    match = _YEAR_RE.search(value)
    if not match:
        return None
    return int(match.group(1))


def parse_year_range(value: str) -> tuple[int | None, int | None]:
    """NOR-006 — '1070–1075' -> (start_year=1070, end_year=1075)."""
    match = _YEAR_RANGE_RE.search(value)
    if match:
        return int(match.group(1)), int(match.group(2))
    single = parse_year(value)
    return single, None


def is_unknown_value(value: str | None) -> bool:
    """NOR-007 — 'N/A', '?', 'chưa rõ' -> None."""
    if value is None:
        return True
    normalized = normalize_text(value).casefold()
    return normalized in {v.casefold() for v in _UNKNOWN_VALUES} or normalized == ""


def parse_latitude(value: str) -> float | None:
    """NOR-008 — string '21.0278' -> decimal 21.0278."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def parse_longitude(value: str) -> float | None:
    """NOR-009 — comma decimal '105,8357' -> decimal 105.8357."""
    try:
        return float(value.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def validate_coordinate(lat: float | None, lon: float | None) -> tuple[float | None, float | None, str | None]:
    """NOR-010 — latitude ngoài [-90,90] hoặc longitude ngoài [-180,180] -> null + INVALID_COORDINATE."""
    if lat is None or lon is None:
        return lat, lon, None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None, None, "INVALID_COORDINATE"
    return lat, lon, None


def normalize_category(value: str) -> str:
    """NOR-011 — 'Category:Di tích' -> 'Di tích'."""
    text = normalize_text(value)
    return re.sub(r"^Category:", "", text, flags=re.IGNORECASE).strip()


def normalize_url_strip_fragment(value: str) -> str:
    """NOR-012 — URL có fragment -> URL không fragment."""
    return value.split("#", 1)[0]


_QID_RE = re.compile(r"^[Qq]\s*([0-9]+)$")


def normalize_qid(value: str | None) -> tuple[str | None, str | None]:
    """NOR-013 (' q123 ' -> 'Q123') + NOR-014 ('Q-1' -> null + INVALID_QID)."""
    if value is None or is_unknown_value(value):
        return None, None
    text = normalize_text(value)
    match = _QID_RE.match(text)
    if not match:
        return None, "INVALID_QID"
    return f"Q{match.group(1)}", None


def dedupe_aliases(label_vi: str, aliases: list[str]) -> list[str]:
    """NOR-015 — aliases trùng label -> unique, stable order."""
    label_key = canonical_identity_key(label_vi)
    seen: set[str] = {label_key}
    result: list[str] = []
    for alias in aliases:
        key = canonical_identity_key(alias)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalize_text(alias))
    return result


# ---------------------------------------------------------------------------
# Recognition year (M2-01)
# ---------------------------------------------------------------------------

# Số hiệu văn bản như "1272/QĐ-TTg", "5079/QĐ - BVHTTDL", "1426 /QĐ-TTg" là số
# quyết định, KHÔNG phải năm. Chúng bị loại khỏi chuỗi trước khi tìm năm.
_DECISION_NUMBER_RE = re.compile(r"(?<!\d)\d+\s*/\s*(?:QĐ|QD|NĐ|ND|TTg|CT|TB|VBHN)\b[^\s,;]*", re.IGNORECASE)
_FULL_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?!\d)")
_VI_DATE_RE = re.compile(r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+(\d{4})(?!\d)", re.IGNORECASE)
_NAM_YEAR_RE = re.compile(r"năm\s+(\d{4})(?!\d)", re.IGNORECASE)
RECOGNITION_MIN_YEAR = 1900


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def parse_recognition_year(value: Any, min_year: int = RECOGNITION_MIN_YEAR, max_year: int | None = None) -> int | None:
    """M2-01 — năm công nhận/xếp hạng từ ô văn bản registry.

    Thứ tự ưu tiên (quyết định đầu tiên trong ô = công nhận gốc):
      1. ngày đầy đủ ``dd/mm/yyyy`` (hoặc ``-``/``.``);
      2. ``ngày … tháng … năm yyyy``;
      3. ``năm yyyy``;
      4. năm 4 chữ số đứng riêng (ví dụ ``"1993"``, ``"1994 2000"``, ``"2003 và 2015"``).
    Số hiệu quyết định (``1272/QĐ-TTg``) bị loại trước khi tìm. Năm ngoài
    ``[min_year, max_year]`` trả ``None`` (OWA: thà thiếu còn hơn sai).
    """
    if value is None:
        return None
    if isinstance(value, int):
        year = value
    else:
        text = normalize_nfc(normalize_text(str(value)))
        if is_unknown_value(text):
            return None
        stripped = _DECISION_NUMBER_RE.sub(" ", text)
        year = None
        for pattern in (_FULL_DATE_RE, _VI_DATE_RE, _NAM_YEAR_RE):
            match = pattern.search(stripped)
            if match:
                year = int(match.group(match.lastindex))
                break
        if year is None:
            match = _YEAR_RE.search(stripped)
            if match:
                year = int(match.group(1))
    upper = max_year if max_year is not None else _current_year()
    if year is None or not (min_year <= year <= upper):
        return None
    return year


# ---------------------------------------------------------------------------
# Registry URL repair (M2-02, NOR-012)
# ---------------------------------------------------------------------------

_DOUBLE_SCHEME_RE = re.compile(r"^(?:https?://|/+)+(?=https?://)", re.IGNORECASE)  # "https://https://x", "//https://x"


_PATH_SAFE = "/%:@!$&'()*+,;=-._~"
_QUERY_SAFE = "/%:@!$&'()*+,;=-._~?"
_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[\x21-\x7e]+$")


def iri_to_uri(url: str | None) -> str | None:
    """IRI -> URI hợp lệ RFC 3986 (percent-encode UTF-8 ngoài ASCII, host IDNA).

    Ví dụ ``https://vi.wikipedia.org/wiki/Vịnh_Hạ_Long`` ->
    ``https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long``. Ký tự đã
    percent-encode giữ nguyên, nên hàm idempotent.
    """
    if not url:
        return url
    parts = urlsplit(normalize_nfc(url.strip()))
    netloc = parts.netloc
    if parts.hostname and not parts.hostname.isascii():
        host = parts.hostname.encode("idna").decode("ascii")
        netloc = netloc.replace(parts.hostname, host)
    return urlunsplit((
        parts.scheme, netloc,
        quote(parts.path, safe=_PATH_SAFE),
        quote(parts.query, safe=_QUERY_SAFE),
        quote(parts.fragment, safe=_QUERY_SAFE),
    ))


def is_valid_uri(value: Any) -> bool:
    """Kiểm tra URI tuyệt đối chỉ gồm ASCII in được — không phụ thuộc thư viện format
    tùy chọn của jsonschema (Kaggle có, máy dev có thể không)."""
    return isinstance(value, str) and bool(_URI_RE.match(value))


def _is_official_host(host: str | None) -> bool:
    host = (host or "").lower()
    return host == OFFICIAL_REGISTRY_HOST or host.endswith("." + OFFICIAL_REGISTRY_HOST)


def normalize_registry_url(href: str | None, category_url: str, base_url: str = "https://dsvh.gov.vn/") -> tuple[str, str | None]:
    """Trả ``(registry_url, repair_code)``.

    - href rỗng/``#``/``javascript:`` hoặc resolve ra trang chủ -> URL category;
    - sửa ``https://https://...``; ép ``https`` cho host chính thức; bỏ fragment;
    - href trỏ ra ngoài ``dsvh.gov.vn`` -> URL category.
    ``repair_code`` là ``None`` nếu href dùng được nguyên trạng.
    """
    fallback = category_url
    raw = (href or "").strip()
    if not raw or raw.startswith("#") or raw.lower().startswith(("javascript:", "mailto:", "tel:")):
        return fallback, "REGISTRY_URL_EMPTY"
    code = None
    fixed = _DOUBLE_SCHEME_RE.sub("", raw)
    if fixed != raw:
        code = "REGISTRY_URL_DOUBLE_SCHEME"
    absolute = urljoin(base_url, fixed)
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not _is_official_host(parts.hostname) or any(ch.isspace() for ch in absolute):
        return fallback, "REGISTRY_URL_NOT_OFFICIAL"
    if parts.scheme != "https":
        code = code or "REGISTRY_URL_HTTP"
    path = parts.path or "/"
    normalized = iri_to_uri(urlunsplit(("https", parts.netloc.lower(), path, parts.query, "")))
    base_parts = urlsplit(urljoin(base_url, "/"))
    if normalized.rstrip("/") == urlunsplit(("https", base_parts.netloc.lower(), "", "", "")).rstrip("/"):
        return fallback, "REGISTRY_URL_HOMEPAGE"
    return normalized, code


@lru_cache(maxsize=4)
def _category_urls(config_path: str) -> tuple[dict[str, str], str]:
    path = Path(config_path)
    if not path.exists():
        return {}, "https://dsvh.gov.vn/"
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {item["key"]: item["url"] for item in config.get("categories", [])}, config.get("base_url", "https://dsvh.gov.vn/")


def repair_registry_url(record: dict[str, Any], config_path: Path | None = None) -> tuple[str | None, str | None]:
    """Áp ``normalize_registry_url`` lên record raw đã có (snapshot cũ)."""
    url = record.get("registry_url")
    category = record.get("registry_category")
    categories, base = _category_urls(str(config_path or REGISTRY_CONFIG_PATH))
    category_url = categories.get(category)
    if not url or not category_url:
        return url, None
    host = urlsplit(_DOUBLE_SCHEME_RE.sub("", url)).hostname
    if not _is_official_host(host):
        # URL không thuộc registry chính thức (ví dụ fixture/test): giữ nguyên.
        return url, None
    return normalize_registry_url(url, category_url, base)


def normalize_timestamp_utc(value: str | None) -> str | None:
    """RFC3339 bất kỳ -> UTC với hậu tố ``Z`` (Raw rule §11.3)."""
    if not value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=2)
def _raw_validator(schema_path: str):
    from jsonschema import Draft202012Validator

    return Draft202012Validator(json.loads(Path(schema_path).read_text(encoding="utf-8")))


def validate_raw_record(raw: dict[str, Any]) -> list[str]:
    """FR-002 / TEST-005 — lỗi JSON Schema của một registry record raw."""
    if not RAW_SCHEMA_PATH.exists():
        return []
    return [f"{'/'.join(map(str, error.path)) or '$'}: {error.message}" for error in _raw_validator(str(RAW_SCHEMA_PATH)).iter_errors(raw)]


def normalize_record(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Áp toàn bộ 15 rule lên một raw record. Trả (normalized, skip_reason)."""
    missing = [f for f in CORE_REQUIRED_FIELDS if not raw.get(f)]
    if missing:
        return None, {"registry_id": raw.get("registry_id"), "error": "RAW_MISSING_CORE", "missing_fields": missing}

    schema_errors = validate_raw_record(raw)
    if schema_errors:
        return None, {"registry_id": raw.get("registry_id"), "error": "RAW_SCHEMA_INVALID", "details": schema_errors}

    normalized: dict[str, Any] = dict(raw)
    normalized["label_vi"] = canonical_label_for_display(raw["label_vi"])
    normalized["_identity_key"] = canonical_identity_key(raw["label_vi"])

    warnings: list[str] = []

    registry_url, url_repair = repair_registry_url(raw)
    if url_repair:
        warnings.append(url_repair)
        normalized["registry_url"] = registry_url
    elif registry_url:
        normalized["registry_url"] = iri_to_uri(normalize_url_strip_fragment(registry_url))

    for time_field in ("retrieved_at",):
        if raw.get(time_field):
            normalized[time_field] = normalize_timestamp_utc(raw[time_field])

    fields = raw.get("registry_fields")
    if isinstance(fields, dict):
        normalized["registry_fields"] = {
            key: (normalize_nfc(normalize_text(value)) if isinstance(value, str) else value)
            for key, value in fields.items()
        }

    aliases = raw.get("aliases_vi")
    if isinstance(aliases, list):
        normalized["aliases_vi"] = dedupe_aliases(normalized["label_vi"], aliases)

    coords = raw.get("coordinates")
    if isinstance(coords, dict):
        lat = coords.get("lat")
        lon = coords.get("lon")
        if isinstance(lat, str):
            lat = parse_latitude(lat)
        if isinstance(lon, str):
            lon = parse_longitude(lon)
        lat, lon, coord_error = validate_coordinate(lat, lon)
        if coord_error:
            warnings.append(coord_error)
            normalized["coordinates"] = None
        elif lat is not None and lon is not None:
            normalized["coordinates"] = {"lat": lat, "lon": lon}

    wikidata_id = raw.get("wikidata_id")
    if wikidata_id is not None:
        qid, qid_error = normalize_qid(wikidata_id)
        if qid_error:
            warnings.append(qid_error)
        normalized["wikidata_id"] = qid

    categories = raw.get("categories")
    if isinstance(categories, list):
        normalized["categories"] = [normalize_category(c) for c in categories]

    if warnings:
        normalized["_warnings"] = warnings

    return normalized, None


def run(run_mode: str = "sample") -> int:
    """`make normalize` — raw JSONL -> normalized JSONL."""
    records_path = RAW_DIR / "registry_records.jsonl"
    if not records_path.exists():
        print(f"normalize: {records_path} not found; run collect-sample or collect first")
        return 1

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    normalized_path = PROCESSED_DIR / "normalized.jsonl"
    skipped_path = PROCESSED_DIR / "skipped_records.jsonl"

    normalized_count = 0
    skipped_count = 0
    with records_path.open(encoding="utf-8") as src, \
         normalized_path.open("w", encoding="utf-8") as out_norm, \
         skipped_path.open("w", encoding="utf-8") as out_skip:
        for line in src:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            normalized, skip_reason = normalize_record(raw)
            if normalized is not None:
                out_norm.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                normalized_count += 1
            else:
                out_skip.write(json.dumps(skip_reason, ensure_ascii=False) + "\n")
                skipped_count += 1

    print(f"normalize ({run_mode}): {normalized_count} normalized, {skipped_count} skipped")
    return 0
