"""Nguồn registry dạng danh sách bài viết (M2-26): dsvh.gov.vn/di-tich-quoc-gia-130.

Fixture HTML (``data/fixtures/registry_articles``, sinh bởi ``tools/m2_make_article_fixtures.py``)
dựng lại từ nội dung thật; không gọi mạng.
"""
import json
import shutil
from pathlib import Path

import pytest

from vietheritage.normalization.normalizer import parse_recognition_year
from vietheritage.registry import articles
from vietheritage.registry.collector import collect, load_config

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "fixtures" / "registry_articles"
RAW_CFG, _ = load_config()
SOURCE = articles.load_article_sources(RAW_CFG)[0]
BASE = RAW_CFG["base_url"]


def fixture_fetcher(url, request_cfg=None):  # noqa: ARG001
    if "_pageIndex=" in url:
        path = FIX / f"list-p{int(url.rsplit('=', 1)[1]):03d}.html"
    elif url == "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753":
        path = ROOT / "data" / "fixtures" / "registry" / "national_monuments.html"
    else:
        path = FIX / f"article-{url.rsplit('-', 1)[1]}.html"
    if not path.exists():
        raise articles.RegistryParseError(f"no fixture for {url}")
    return path.read_text(encoding="utf-8")


def _existing():
    return [{"registry_id": "registry-32689fc75c8e", "registry_category": "national_monuments", "label_vi": "Đền Gôi Vị"}]


@pytest.fixture(scope="module")
def result():
    return articles.collect_article_source(SOURCE, {"delay_seconds": 0}, BASE, "snap", "2026-09-25T00:00:00Z",
                                           _existing(), fixture_fetcher, lambda _s: None)


def test_config_declares_national_monuments_article_source():
    assert SOURCE.registry_category == "national_monuments"
    assert SOURCE.list_url == "https://dsvh.gov.vn/di-tich-quoc-gia-130"


def test_list_pages_are_crawled_and_page_chrome_is_dropped():
    items, info = articles.crawl_list(SOURCE, {"delay_seconds": 0}, BASE, fixture_fetcher, lambda _s: None)
    assert info["pages_declared"] == 3 and info["pages_fetched"] == 3 and not info["warnings"]
    ids = [url.rsplit("-", 1)[1] for url, _ in items]
    assert ids == ["22364", "22366", "22340", "22300", "22301", "22302", "22354"]   # menu + sidebar bị loại


def test_pagination_that_ignores_page_param_is_reported():
    def stuck(url, cfg=None):
        return fixture_fetcher(url.split("?")[0] + "?_pageIndex=1", cfg)

    items, info = articles.crawl_list(SOURCE, {}, BASE, stuck, lambda _s: None)
    assert info["pages_fetched"] == 2 and any("PAGINATION_NOT_ADVANCING" in w for w in info["warnings"])


def test_records_follow_registry_schema(result):
    records, _, _ = result
    by_label = {r.label_vi: r for r in records}
    assert set(by_label) == {"Đình Đạm Xuyên", "Đình Tri Lễ", "Đền thờ Khúc Thừa Dụ", "Phủ Phụ Chính"}
    dam = by_label["Đình Đạm Xuyên"]
    assert dam.registry_category == "national_monuments"
    assert dam.registry_url == "https://dsvh.gov.vn/dinh-dam-xuyen-thanh-pho-ha-noi-22364"
    assert dam.registry_fields["location"] == "xã Mê Linh, Thành phố Hà Nội"
    assert dam.registry_fields["recognition_text"] == "15/2003/QĐ-BVHTT ngày 14/04/2003"
    assert dam.registry_fields["type"] == "di tích kiến trúc nghệ thuật"
    assert dam.registry_fields["source"] == "article_list:national_monuments_articles"
    assert dam.registry_id.startswith("registry-") and len({r.registry_id for r in records}) == 4


def test_location_keeps_new_province_and_appends_title_province(result):
    by_label = {r.label_vi: r.registry_fields for r in result[0]}
    assert by_label["Đền thờ Khúc Thừa Dụ"]["location"] == (
        "xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương (nay là xã Khúc Thừa Dụ, Thành phố Hải Phòng)")
    assert by_label["Đình Tri Lễ"]["location"] == "thôn Tri Lễ, xã Tri Trung, Thành phố Hà Nội"
    assert by_label["Phủ Phụ Chính"]["location"] == "phường Kim Long, thành phố Huế"


def test_recognition_at_end_and_vietnamese_date(result):
    by_label = {r.label_vi: r.registry_fields for r in result[0]}
    khuc = by_label["Đền thờ Khúc Thừa Dụ"]
    assert khuc["recognition_text"] == "2103/QĐ-BVHTTDL ngày 08/07/2014" and khuc["type"] == "di tích lịch sử"
    assert parse_recognition_year(khuc["recognition_text"]) == 2014
    assert by_label["Đình Tri Lễ"]["types_all"] == "di tích lịch sử; di tích kiến trúc nghệ thuật"


def test_quarantine_special_missing_decision_and_duplicates(result):
    _, quarantine, report = result
    codes = {q["list_title"]: q["error_code"] for q in quarantine}
    assert codes == {
        "Đền Thượng, tỉnh Phú Thọ": "ARTICLE_SPECIAL_RANK",
        "Miếu Không Quyết Định, tỉnh Nam Định": "REGISTRY_RECORD_INVALID",
        "Đền Gôi Vị, tỉnh Tuyên Quang": "ARTICLE_DUPLICATE",
    }
    assert report["records"] == 4 and report["candidates"] == 7
    assert articles.coverage_increment(report) == {"discovered": 6, "valid": 4, "invalid": 2, "retrieved": 4}


def test_article_outside_section_is_ignored():
    html = (FIX / "article-22370.html").read_text(encoding="utf-8")
    assert articles.parse_article(html, "https://dsvh.gov.vn/x-22370", SOURCE, BASE)["error_code"] == "ARTICLE_OUTSIDE_SECTION"


@pytest.mark.parametrize("title, expected", [
    ("Đình Tri Lễ, Thành phố Hà Nội", ("Đình Tri Lễ", "Thành phố Hà Nội")),
    ("Mộ Tổng bí thư Trần Phú, tỉnh Hà Tĩnh", ("Mộ Tổng bí thư Trần Phú", "tỉnh Hà Tĩnh")),
    ("Đền thờ Khúc Thừa Dụ", ("Đền thờ Khúc Thừa Dụ", None)),
    ("Chùa A, B và C", ("Chùa A, B và C", None)),
])
def test_split_title(title, expected):
    assert articles.split_title(title) == expected


def test_collect_adds_article_records_to_category(tmp_path):
    report = collect(fetcher=fixture_fetcher, category_keys=["national_monuments"], output_dir=tmp_path,
                     sleeper=lambda _s: None)
    records = [json.loads(l) for l in (tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 6 + 4
    category = report["categories"][0]
    assert category["valid"] == 10 and category["canonicalized"] == 10 and category["invalid"] == 2
    assert report["claim"] == "100% of selected official registry snapshot"
    assert "https://dsvh.gov.vn/di-tich-quoc-gia-130?_pageIndex=1" in report["source_urls"]
    assert (tmp_path / articles.QUARANTINE_FILE).exists() and (tmp_path / articles.REPORT_FILE).exists()


def test_merge_into_existing_snapshot_is_idempotent(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(ROOT / "data" / "raw" / "registry_records.jsonl", raw / "registry_records.jsonl")
    # Snapshot trong repo có thể đã chứa record của nguồn bài viết (sau lần chạy thật) -> merge thay thế chúng.
    base = [r for r in (json.loads(l) for l in (raw / "registry_records.jsonl").read_text(encoding="utf-8").splitlines())
            if not str((r.get("registry_fields") or {}).get("source", "")).startswith(articles.SOURCE_PREFIX)]
    snapshot = base[0]["coverage_snapshot"]
    reports = tmp_path / "reports"
    (reports / snapshot).mkdir(parents=True)
    coverage = {"snapshot_id": snapshot, "source_urls": [], "source_checksums": {}, "registry_total": len(base),
                "categories": [{"registry_category": "national_monuments", "discovered": 6, "valid": 6, "invalid": 0,
                                "retrieved": 6, "failed": 0, "canonicalized": 6, "coverage_percent": 100.0}]}
    (reports / snapshot / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    for _ in range(2):
        summary = articles.merge_into_snapshot(raw_dir=raw, reports_root=reports, fetcher=fixture_fetcher,
                                               sleeper=lambda _s: None)
    records = [json.loads(l) for l in (raw / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert summary["records_added"] == 4 and len(records) == len(base) + 4
    assert {r["coverage_snapshot"] for r in records} == {snapshot}
    cov = json.loads((reports / snapshot / "coverage.json").read_text(encoding="utf-8"))["categories"][0]
    assert cov["valid"] == 10 and cov["discovered"] == 12 and cov["invalid"] == 2   # không cộng dồn khi chạy lại
    quarantine = (raw / articles.QUARANTINE_FILE).read_text(encoding="utf-8").splitlines()
    assert len(quarantine) == 3


# Chuỗi thật từ probe Kaggle 2026-09-25 (cụm địa điểm bắt đầu bên trong ngoặc của bài).
@pytest.mark.parametrize("raw, expected", [
    ("thôn Tri Lễ, xã Tân Ước, huyện Thanh Oai cũ, nay thuộc xã Dân Hoà, Thành phố Hà Nội), thờ Thành hoàng làng "
     "Cao Sơn Đại vương, được Bộ trưởng Bộ Văn hoá xếp hạng",
     "thôn Tri Lễ, xã Tân Ước, huyện Thanh Oai cũ, nay thuộc xã Dân Hoà, Thành phố Hà Nội"),
    ("thôn Hưng Thắng , xã Cẩm Hưng, tỉnh Hà Tĩnh ) , là nơi yên nghỉ của Tổng Bí thư",
     "thôn Hưng Thắng, xã Cẩm Hưng, tỉnh Hà Tĩnh"),
    ("xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương (nay là xã Khúc Thừa Dụ, Thành phố Hải Phòng)",
     "xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương (nay là xã Khúc Thừa Dụ, Thành phố Hải Phòng)"),
    ("thôn Châu Linh xã Đức Thọ, tỉnh Hà Tĩnh", "thôn Châu Linh xã Đức Thọ, tỉnh Hà Tĩnh"),
])
def test_trim_location_real_cases(raw, expected):
    assert articles._trim_location(raw) == expected


def test_listing_page_linked_from_breadcrumb_is_ignored():
    """Probe Kaggle: link breadcrumb "Di tích" (di-tich-1746) lọt vào danh sách ứng viên."""
    html = (FIX / "list-p002.html").read_text(encoding="utf-8").replace(
        '<div class="breadcrumb">', '<div class="breadcrumb"><a href="https://dsvh.gov.vn/di-tich-quoc-gia-130">x</a>')
    assert articles.parse_article(html, "https://dsvh.gov.vn/di-tich-1746", SOURCE, BASE)["error_code"] == "ARTICLE_IS_LISTING"


# Câu xếp hạng thật của 4 bài bị quarantine oan ở lần chạy Kaggle 2026-09-25 (trang 1-2).
@pytest.mark.parametrize("sentence, recognition, year", [
    ("Nhà tù Hỏa Lò được Bộ trưởng Bộ Văn hoá, Thể thao và Du lịch xếp hạng Di tích lịch sử quốc gia theo "
     "Quyết định số 1543 QĐ/VH ngày 18 tháng 6 năm 1997.", "1543 QĐ/VH ngày 18/06/1997", 1997),
    ("Linh Quang Tự được Bộ trưởng Bộ Văn hoá, Thể thao và Du lịch xếp hạng Di tích quốc gia theo "
     "Quyết định số 51 QĐ/BT ngày 12 tháng 01 năm 1996.", "51 QĐ/BT ngày 12/01/1996", 1996),
    ("Phủ Phụ Chính đã được Bộ trưởng Bộ Văn hóa, Thể thao và Du lịch xếp hạng Di tích lịch sử quốc gia "
     "(theo Quyết định số 320/QÐ-BVHTTDL ngày 12 tháng 02 năm 2026).", "320/QĐ-BVHTTDL ngày 12/02/2026", 2026),
    ("Đình được xếp hạng di tích lịch sử quốc gia theo Quyết định số 310-QĐ/BT ngày 13/02/1996.",
     "310-QĐ/BT ngày 13/02/1996", 1996),
])
def test_recognition_real_decision_formats(sentence, recognition, year):
    result = articles.extract_recognition(articles._nfc(sentence))
    text = f"{result['decision']} ngày {result['date']}"
    assert text == recognition and parse_recognition_year(text) == year
