"""G4 unit tests — Normalizer NOR-001..NOR-015 (COMP-002, TEST-005..011).

Before/after fixture cho từng rule, đúng bảng Section 17 của PROJECT_SPEC.md.
"""
import json
from pathlib import Path

from vietheritage.normalization.normalizer import (
    canonical_dash,
    canonical_identity_key,
    canonical_label_for_display,
    dedupe_aliases,
    is_unknown_value,
    normalize_category,
    normalize_qid,
    normalize_record,
    normalize_text,
    normalize_url_strip_fragment,
    parse_latitude,
    parse_longitude,
    parse_year,
    parse_year_range,
    run,
    validate_coordinate,
)


def test_nor001_text_whitespace() -> None:
    assert normalize_text("  Văn   Miếu  ") == "Văn Miếu"


def test_nor002_unicode_nfd_to_nfc() -> None:
    nfd = unicodedata_nfd("Việt")
    assert canonical_label_for_display(nfd) == "Việt"


def unicodedata_nfd(s: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFD", s)


def test_nor003_newline_removed() -> None:
    assert normalize_text("Hà Nội\n") == "Hà Nội"


def test_nor004_display_keeps_original_dash() -> None:
    original = "Văn Miếu \u2013 Quốc Tử Giám"
    assert canonical_label_for_display(original) == original


def test_nor004_identity_key_normalizes_all_dash_variants_to_same_key() -> None:
    with_en_dash = "Văn Miếu \u2013 Quốc Tử Giám"
    with_hyphen = "Văn Miếu - Quốc Tử Giám"
    with_em_dash = "Văn Miếu \u2014 Quốc Tử Giám"
    assert canonical_identity_key(with_en_dash) == canonical_identity_key(with_hyphen)
    assert canonical_identity_key(with_en_dash) == canonical_identity_key(with_em_dash)


def test_canonical_dash_normalizes_unicode_dashes() -> None:
    assert canonical_dash("A\u2012B\u2013C\u2014D") == "A-B-C-D"


def test_nor005_year_parsing() -> None:
    assert parse_year("1070") == 1070
    assert parse_year("năm 1070") == 1070


def test_nor006_year_range() -> None:
    assert parse_year_range("1070\u20131075") == (1070, 1075)
    assert parse_year_range("1070-1075") == (1070, 1075)


def test_nor007_unknown_values_map_to_none() -> None:
    assert is_unknown_value("N/A") is True
    assert is_unknown_value("?") is True
    assert is_unknown_value("chưa rõ") is True
    assert is_unknown_value("Hà Nội") is False
    assert parse_year("N/A") is None


def test_nor008_latitude_string_to_decimal() -> None:
    assert parse_latitude("21.0278") == 21.0278


def test_nor009_longitude_comma_decimal() -> None:
    assert parse_longitude("105,8357") == 105.8357


def test_nor010_invalid_coordinate_out_of_range() -> None:
    lat, lon, error = validate_coordinate(121.0, 105.0)
    assert lat is None
    assert lon is None
    assert error == "INVALID_COORDINATE"


def test_nor010_valid_coordinate_passes() -> None:
    lat, lon, error = validate_coordinate(21.0278, 105.8357)
    assert lat == 21.0278
    assert lon == 105.8357
    assert error is None


def test_nor011_category_prefix_removed() -> None:
    assert normalize_category("Category:Di tích") == "Di tích"


def test_nor012_url_fragment_stripped() -> None:
    assert normalize_url_strip_fragment("https://vi.wikipedia.org/wiki/X#section") == "https://vi.wikipedia.org/wiki/X"


def test_nor013_qid_normalized() -> None:
    qid, error = normalize_qid(" q123 ")
    assert qid == "Q123"
    assert error is None


def test_nor014_invalid_qid_rejected() -> None:
    qid, error = normalize_qid("Q-1")
    assert qid is None
    assert error == "INVALID_QID"


def test_nor015_alias_dedup_against_label() -> None:
    aliases = dedupe_aliases("Văn Miếu", ["Văn Miếu", "Văn Miếu - Quốc Tử Giám", "Văn Miếu"])
    assert aliases == ["Văn Miếu - Quốc Tử Giám"]


def test_normalize_record_skips_when_missing_core_field() -> None:
    raw = {"registry_category": "world_heritage", "label_vi": "X"}
    normalized, skip_reason = normalize_record(raw)
    assert normalized is None
    assert skip_reason["error"] == "RAW_MISSING_CORE"


def test_normalize_record_accepts_valid_registry_only_record() -> None:
    raw = {
        "registry_id": "registry-abc123",
        "registry_category": "world_heritage",
        "label_vi": "  Vịnh   Hạ Long  ",
        "registry_url": "https://dsvh.gov.vn/x",
        "source_status": "registry_only",
        "coverage_snapshot": "snap-1",
        "retrieved_at": "2026-09-13T00:00:00Z",
    }
    normalized, skip_reason = normalize_record(raw)
    assert skip_reason is None
    assert normalized["label_vi"] == "Vịnh Hạ Long"


def test_run_produces_normalized_and_skipped_jsonl(tmp_path: Path, monkeypatch) -> None:
    import vietheritage.normalization.normalizer as normalizer_module

    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    records_path = raw_dir / "registry_records.jsonl"
    good_record = {
        "registry_id": "registry-1", "registry_category": "world_heritage",
        "label_vi": "A", "registry_url": "https://x", "source_status": "registry_only",
        "coverage_snapshot": "s1", "retrieved_at": "2026-09-13T00:00:00Z",
    }
    bad_record = {"registry_category": "world_heritage", "label_vi": "B"}
    records_path.write_text(
        json.dumps(good_record, ensure_ascii=False) + "\n" + json.dumps(bad_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(normalizer_module, "RAW_DIR", raw_dir)
    monkeypatch.setattr(normalizer_module, "PROCESSED_DIR", processed_dir)

    exit_code = run(run_mode="sample")
    assert exit_code == 0
    assert (processed_dir / "normalized.jsonl").exists()
    assert (processed_dir / "skipped_records.jsonl").exists()
    normalized_lines = (processed_dir / "normalized.jsonl").read_text(encoding="utf-8").strip().splitlines()
    skipped_lines = (processed_dir / "skipped_records.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(normalized_lines) == 1
    assert len(skipped_lines) == 1
