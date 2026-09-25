"""Hồi quy trên HTML THẬT của dsvh.gov.vn/di-tich-quoc-gia-130 (crawl Kaggle 2026-09-25, đã bỏ script/style).

Mỗi ca là một lỗi đã gặp ở lần chạy thật: 13 bài bị quarantine oan (động từ "công nhận", số quyết định
"95-1998-QĐ/BVHTT", "1288VH/QĐ", "8 87/QĐ", "3238/ QĐ", câu xếp hạng không có "quốc gia"), ngày bị HTML cắt
số ("202 4"), địa điểm lấy nhầm quê quán nhân vật, bài là điểm của di tích quốc gia đặc biệt (Bến K15).
"""
from pathlib import Path

import pytest

from vietheritage.normalization.areas import default_resolver
from vietheritage.normalization.normalizer import parse_recognition_year
from vietheritage.registry import articles
from vietheritage.registry.collector import load_config

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data" / "fixtures" / "registry_articles_real"
RAW_CFG, _ = load_config()
SOURCE = articles.load_article_sources(RAW_CFG)[0]
BASE = RAW_CFG["base_url"]
RESOLVER = default_resolver()

# article_id: (label_vi, recognition_text, năm, type, nhóm tỉnh của location, location_source)
CASES = {
    "22364": ("Đình Đạm Xuyên", "15/2003/QĐ-BVHTT ngày 14/04/2003", 2003, "di tích kiến trúc nghệ thuật", "Hà Nội", "recognition_sentence"),
    "22366": ("Đình Tri Lễ", "52/2008/QĐ-BVHTTDL ngày 17/07/2008", 2008, "di tích kiến trúc nghệ thuật", "Hà Nội", "recognition_sentence"),
    "22353": ("Khu lưu niệm Phạm Thận Duật", "322/QĐ-BVHTTDL ngày 12/02/2026", 2026, "di tích lịch sử", "Ninh Bình", "recognition_sentence"),
    "22354": ("Phủ Phụ Chính", "320/QĐ-BVHTTDL ngày 12/02/2026", 2026, "di tích lịch sử", "Huế", "title"),
    "22340": ("Đền thờ Khúc Thừa Dụ", "2103/QĐ-BVHTTDL ngày 08/07/2014", 2014, "di tích lịch sử", "Hải Phòng", "intro"),
    "22342": ("Nhà tù Hỏa Lò", "1543 QĐ/VH ngày 18/06/1997", 1997, "di tích lịch sử", "Hà Nội", "intro"),
    "22286": ("Hang Ngườm Sâu", "3238/QĐ-BVHTTDL ngày 09/09/2025", 2025, "di tích khảo cổ", "Lạng Sơn", "intro"),
    "22277": ("Đình Thanh Sầm", "887/QĐ-BVHTTDL ngày 15/04/2022", 2022, None, "Hưng Yên", "intro"),
    "22262": ("Đền Hoả Thần", "1964/QĐ-VH ngày 27/08/1996", 1996, None, "Hà Nội", "title"),
    "22211": ("Bến K15 - Điểm xuất phát đường Hồ Chí Minh trên biển", "63/2008/QĐ-BVHTTDL ngày 18/08/2008", 2008,
              "di tích lịch sử", "Hải Phòng", "intro"),
    "22135": ("Chùa Sở Thượng", "95-1998-QĐ/BVHTT ngày 24/01/1998", 1998, "di tích kiến trúc nghệ thuật", "Hà Nội", "intro"),
    "22114": ("Chùa Thiên Phúc", "1288VH/QĐ ngày 16/11/1988", 1988, "di tích kiến trúc nghệ thuật", "Hà Nội", "intro"),
    "3412": ("Đình Lại Yên", "1991/QĐ-BVHTTDL ngày 29/06/2021", 2021, "di tích kiến trúc nghệ thuật", "Hà Nội", "recognition_sentence"),
    "3184": ("Quần thể di tích làng Nôm", "50/QĐ-BVHTTDL ngày 07/01/2020", 2020, "di tích lịch sử", "Hưng Yên", "title"),
}

pytestmark = pytest.mark.skipif(not REAL.exists(), reason="real article HTML fixtures not present")


def _parse(article_id):
    html = (REAL / f"{article_id}.html").read_text(encoding="utf-8")
    return articles.parse_article(html, f"https://dsvh.gov.vn/x-{article_id}", SOURCE, BASE)


@pytest.mark.parametrize("article_id", sorted(CASES))
def test_real_article_fields(article_id):
    label, recognition, year, site_type, group, source = CASES[article_id]
    fields = _parse(article_id)["fields"]
    assert fields["label_vi"] == label
    assert fields["recognition_text"] == recognition and parse_recognition_year(recognition) == year
    assert fields.get("type") == site_type
    assert fields["location_source"] == source
    groups = {area.group for area in RESOLVER.resolve(fields["location"]).areas}
    assert groups == {next(a.group for a in RESOLVER.resolve(group).areas)}, fields["location"]


def test_birthplace_in_intro_is_not_used_as_location():
    assert "Sơn Tây" not in _parse("22353")["fields"]["location"]


def test_site_without_any_modern_location_stays_empty():
    fields = _parse("22292")["fields"]   # Đình Thái Khê: bài chỉ nhắc địa danh cũ "tỉnh Sơn Tây, phủ Quốc Oai"
    assert "location" not in fields and fields["location_source"] == "none"
    assert fields["recognition_text"] == "3234/QĐ-BVHTTDL ngày 09/09/2025"


def test_real_list_pages():
    first = (REAL / "list-p001.html").read_text(encoding="utf-8")
    last = (REAL / "list-p016.html").read_text(encoding="utf-8")
    assert articles.parse_page_info(first) == (1, 16) and articles.parse_page_info(last) == (16, 16)
    items = articles.parse_list_items(first, SOURCE, BASE)
    ids = [url.rsplit("-", 1)[1] for url, _ in items]
    assert "22364" in ids and len([i for i in ids if i != "1746"]) == 10   # 10 bài + breadcrumb "Di tích"
