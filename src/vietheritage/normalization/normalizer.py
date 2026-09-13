"""Normalizer — NOR-001..NOR-015 (COMP-002, Section 17).

Input: ``data/raw/registry_records.jsonl`` (+ ``data/raw/pages.jsonl`` khi có
enrichment). Output: ``data/processed/normalized.jsonl``,
``data/processed/skipped_records.jsonl``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

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


def normalize_record(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Áp toàn bộ 15 rule lên một raw record. Trả (normalized, skip_reason)."""
    missing = [f for f in CORE_REQUIRED_FIELDS if not raw.get(f)]
    if missing:
        return None, {"registry_id": raw.get("registry_id"), "error": "RAW_MISSING_CORE", "missing_fields": missing}

    normalized: dict[str, Any] = dict(raw)
    normalized["label_vi"] = canonical_label_for_display(raw["label_vi"])
    normalized["_identity_key"] = canonical_identity_key(raw["label_vi"])

    warnings: list[str] = []

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
