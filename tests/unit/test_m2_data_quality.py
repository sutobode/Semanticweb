"""M2 regression tests (M2_REMAINING_WORK.md M2-01…M2-18).

Mọi test offline: HTTP được thay bằng fetcher/session giả, output ghi vào
``tmp_path`` (M2-21 — không đụng ``data/``).
"""
import json
from pathlib import Path

import pytest
import yaml
import requests

from vietheritage.collector import wikipedia as wiki
from vietheritage.mapping.mapper import (
    DerivedRegistry,
    PageIndex,
    load_mapping,
    map_record,
    site_types_from_label,
    update_coverage_report,
    validate_canonical,
)
from vietheritage.normalization.areas import AreaResolver, area_id_for_label, match_key
from vietheritage.normalization.normalizer import (
    normalize_record,
    normalize_registry_url,
    normalize_timestamp_utc,
    parse_recognition_year,
)
from vietheritage.registry import collector as registry
from vietheritage.registry.collector import (
    CategoryConfig,
    RegistryParseError,
    collect,
    fetch_page,
    parse_table_rows,
    rows_to_records,
)

ROOT = Path(__file__).resolve().parents[2]
CATEGORY_URL = "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-dac-biet-1752"


# ---------------------------------------------------------------------------
# M2-01 recognition year
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, year", [
    ("1272/QĐ-TTg Ngày 12/8/2009", 2009),
    ("4069/QĐ-BVHTTDL ngày 30/10/2018", 2018),
    ("5079/QĐ - BVHTTDL Ngày 27/12/2012", 2012),
    ("1426 /QĐ-TTg Ngày 01/12/2012", 2012),
    ("2382/ QĐ-TTg Ngày 25/12/2015", 2015),
    ("Quyết định 2082/QĐ-TTg ngày 25-12-2017", 2017),
    ("ngày 5 tháng 3 năm 2015", 2015),
    ("1993", 1993),
    ("1994 2000", 1994),
    ("2003 và 2015", 2003),
    ("86/QĐ-BVHTTDL", None),
    ("chưa rõ", None),
    ("năm 1070", None),  # ngoài miền năm công nhận
    ("", None),
])
def test_recognition_year_ignores_decision_numbers(text, year):
    assert parse_recognition_year(text) == year


def test_recognition_year_rejects_future_years():
    assert parse_recognition_year("ngày 1/1/2999") is None


# ---------------------------------------------------------------------------
# M2-02 registry URL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("href, expected, code", [
    ("", CATEGORY_URL, "REGISTRY_URL_EMPTY"),
    ("#", CATEGORY_URL, "REGISTRY_URL_EMPTY"),
    ("https://dsvh.gov.vn/", CATEGORY_URL, "REGISTRY_URL_HOMEPAGE"),
    ("http://dsvh.gov.vn/vinh-ha-long-476", "https://dsvh.gov.vn/vinh-ha-long-476", "REGISTRY_URL_HTTP"),
    ("https://https://dsvh.gov.vn/a-1", "https://dsvh.gov.vn/a-1", "REGISTRY_URL_DOUBLE_SCHEME"),
    ("http://di-tich-chua-keo-2964", CATEGORY_URL, "REGISTRY_URL_NOT_OFFICIAL"),
    ("https://example.com/x", CATEGORY_URL, "REGISTRY_URL_NOT_OFFICIAL"),
    ("/di-tich/x#top", "https://dsvh.gov.vn/di-tich/x", None),
])
def test_normalize_registry_url(href, expected, code):
    assert normalize_registry_url(href, CATEGORY_URL) == (expected, code)


def test_normalizer_repairs_homepage_registry_url_of_existing_snapshot():
    raw = {
        "registry_id": "registry-abc", "registry_category": "national_special_monuments",
        "label_vi": "Đền Hùng", "registry_url": "https://dsvh.gov.vn/", "source_status": "registry_only",
        "coverage_snapshot": "s", "retrieved_at": "2026-09-13T21:44:18+07:00",
    }
    normalized, skipped = normalize_record(raw)
    assert skipped is None
    assert normalized["registry_url"] == CATEGORY_URL
    assert "REGISTRY_URL_HOMEPAGE" in normalized["_warnings"]
    assert normalized["retrieved_at"] == "2026-09-13T14:44:18Z"


def test_normalizer_quarantines_raw_schema_violation():
    raw = {
        "registry_id": "registry-abc", "registry_category": "world_heritage", "label_vi": "X",
        "registry_url": "https://dsvh.gov.vn/x", "source_status": "not-a-status",
        "coverage_snapshot": "s", "retrieved_at": "2026-09-13T00:00:00Z",
    }
    normalized, skipped = normalize_record(raw)
    assert normalized is None and skipped["error"] == "RAW_SCHEMA_INVALID"


def test_timestamp_to_utc_z():
    assert normalize_timestamp_utc("2026-09-13T14:53:52+07:00") == "2026-09-13T07:53:52Z"


# ---------------------------------------------------------------------------
# M2-03 stable registry IDs
# ---------------------------------------------------------------------------

def _category(**overrides) -> CategoryConfig:
    values = dict(
        key="national_treasures", url="https://dsvh.gov.vn/bao-vat-quoc-gia-1758", entity_type="NationalTreasure",
        row_selector="table tbody tr",
        columns={"ordinal": 0, "label_vi": 1, "recognition_text": 2, "location": 3},
    )
    values.update(overrides)
    return CategoryConfig(**values)


ROWS_HTML = """
<table><tbody>
<tr><td>54</td><td><a href="/tuong-a-1">Tượng Avalokitesvara</a></td><td>2599/QĐ-TTg Ngày 30/12/2013</td><td>Bảo tàng Lịch sử TP.HCM</td></tr>
<tr><td>55</td><td>Tượng Avalokitesvara</td><td>2599/QĐ-TTg Ngày 30/12/2013</td><td>Bảo tàng Lịch sử TP.HCM</td></tr>
<tr><td>59</td><td>Tượng thần Visnu</td><td>2599/QĐ-TTg Ngày 30/12/2013</td><td>Bảo tàng tỉnh Đồng Tháp</td></tr>
<tr><td>60</td><td>Tượng thần Visnu</td><td>2599/QĐ-TTg Ngày 30/12/2013</td><td>Bảo tàng tỉnh Long An</td></tr>
<tr><td>1</td><td>Trống đồng Ngọc Lũ</td><td>1426 /QĐ-TTg</td><td>Bảo tàng Lịch sử quốc gia</td></tr>
</tbody></table>
"""


def _ids(rows):
    return {r.label_vi + "|" + r.registry_fields.get("location", "") + "|" + r.registry_fields["ordinal"]: r.registry_id
            for r in rows_to_records(rows, _category(), "snap", "2026-09-13T00:00:00Z", "https://dsvh.gov.vn/")}


def test_registry_ids_do_not_depend_on_row_order_or_href():
    rows = parse_table_rows(ROWS_HTML, ["^Tổng số"])
    forward = _ids(rows)
    backward = _ids(list(reversed(rows)))
    assert forward == backward
    assert len(set(forward.values())) == 5


def test_unique_label_id_ignores_ordinal_and_location():
    rows = parse_table_rows(ROWS_HTML, ["^Tổng số"])
    single = [row for row in rows if row["cells"][1] == "Trống đồng Ngọc Lũ"]
    moved = [dict(single[0], cells=["999", *single[0]["cells"][1:3], "Nơi khác"])]
    assert _ids(single).popitem()[1] == _ids(moved).popitem()[1]


def test_shared_detail_url_falls_back_to_category_url():
    html = """<table><tbody>
    <tr><td>1</td><td><a href="/x-2937">Dinh Độc Lập</a></td><td>2009</td><td>TP HCM</td></tr>
    <tr><td>2</td><td><a href="/x-2937">Khu bảo tồn Na Hang</a></td><td>2018</td><td>Tuyên Quang</td></tr>
    <tr><td>3</td><td><a href="/y-1">Đền Hùng</a></td><td>2009</td><td>Phú Thọ</td></tr>
    </tbody></table>"""
    records = rows_to_records(parse_table_rows(html, []), _category(url=CATEGORY_URL), "s", "t", "https://dsvh.gov.vn/")
    assert [r.registry_url for r in records] == [CATEGORY_URL, CATEGORY_URL, "https://dsvh.gov.vn/y-1"]
    assert records[0].registry_fields["registry_url_repair"] == "REGISTRY_URL_SHARED"


def test_row_without_label_is_quarantined_not_fatal(tmp_path):
    html = "<table><tbody><tr><td>1</td><td></td><td>2009</td><td>Hà Nội</td></tr>" \
           "<tr><td>2</td><td>Đền Hùng</td><td>2009</td><td>Phú Thọ</td></tr></tbody></table>"
    report = collect(fetcher=lambda url, cfg: html, category_keys=["national_special_monuments"],
                     output_dir=tmp_path, sleeper=lambda s: None)
    assert report["categories"][0]["valid"] == 1 and report["categories"][0]["invalid"] == 1
    quarantine = (tmp_path / "registry_quarantine.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(quarantine[0])["error_code"] == "REGISTRY_RECORD_INVALID"


# ---------------------------------------------------------------------------
# M2-06 pagination (TEST-002 / TEST-078), M2-07 detail (TEST-077 / TEST-079)
# ---------------------------------------------------------------------------

def _page(rows, next_href=None):
    body = "".join(f"<tr><td>{i}</td><td><a href='/d-{i}'>{label}</a></td><td>2009</td><td>Hà Nội</td></tr>" for i, label in rows)
    link = f"<a rel='next' href='{next_href}'>Sau</a>" if next_href else ""
    return f"<table><tbody>{body}</tbody></table>{link}"


def _config(tmp_path: Path, **category_extra) -> Path:
    category = {
        "key": "national_special_monuments", "url": "https://dsvh.gov.vn/list", "entity_type": "HeritageSite",
        "columns": {"ordinal": 0, "label_vi": 1, "recognition_text": 2, "location": 3},
        "next_page_selector": "a[rel=next]", **category_extra,
    }
    path = tmp_path / "registry_sources.yaml"
    path.write_text(json.dumps({"base_url": "https://dsvh.gov.vn/", "request": {"delay_seconds": 0},
                                "defaults": {"row_selector": "table tbody tr"}, "categories": [category]}),
                    encoding="utf-8")
    return path


def test_pagination_follows_next_links_and_stops_on_repeated_fingerprint(tmp_path):
    pages = {
        "https://dsvh.gov.vn/list": _page([(1, "A"), (2, "B")], "/list?page=2"),
        "https://dsvh.gov.vn/list?page=2": _page([(3, "C")], "/list?page=3"),
        "https://dsvh.gov.vn/list?page=3": _page([(3, "C")], "/list?page=4"),  # lặp nội dung trang 2
        "https://dsvh.gov.vn/list?page=4": _page([(9, "Z")]),
    }
    fetched = []

    def fetcher(url, cfg):
        fetched.append(url)
        return pages[url]

    report = collect(config_path=_config(tmp_path), output_dir=tmp_path, fetcher=fetcher, sleeper=lambda s: None)
    labels = [json.loads(line)["label_vi"] for line in (tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert labels == ["A", "B", "C"]
    assert fetched == list(pages)[:3]
    assert report["categories"][0]["discovered"] == 3
    assert len(set(json.loads(l)["registry_id"] for l in (tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines())) == 3
    assert set(report["source_checksums"]) == set(list(pages)[:3])


def test_pagination_respects_max_pages(tmp_path):
    def fetcher(url, cfg):
        number = int(url.rsplit("=", 1)[-1]) if "=" in url else 1
        return _page([(number, f"Di tích {number}")], f"/list?page={number + 1}")

    collect(config_path=_config(tmp_path, max_pages=4), output_dir=tmp_path, fetcher=fetcher, sleeper=lambda s: None)
    assert len((tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()) == 4


def test_detail_fields_are_fetched_when_configured(tmp_path):
    def fetcher(url, cfg):
        if url.endswith("/list"):
            return _page([(1, "A")])
        return "<html><div class='loai'>Di tích lịch sử</div></html>"

    collect(config_path=_config(tmp_path, detail_link_selector="td:nth-child(2) a", detail_fields={"type": "div.loai"}),
            output_dir=tmp_path, fetcher=fetcher, sleeper=lambda s: None)
    record = json.loads((tmp_path / "registry_records.jsonl").read_text(encoding="utf-8"))
    assert record["registry_fields"]["detail_type"] == "Di tích lịch sử"


def test_missing_detail_page_is_blocking(tmp_path):
    def fetcher(url, cfg):
        if url.endswith("/list"):
            return _page([(1, "A")])
        raise RegistryParseError("404")

    report = collect(config_path=_config(tmp_path, detail_link_selector="td a", detail_fields={"type": "div"}),
                     output_dir=tmp_path, fetcher=fetcher, sleeper=lambda s: None)
    assert report["claim"] == "coverage_failed"
    assert report["failure_manifest"][0]["error_code"] == "REGISTRY_DETAIL_MISSING"


# ---------------------------------------------------------------------------
# NFR-007 retry (TEST-003) and HTTP 500 (TEST-004)
# ---------------------------------------------------------------------------

class _Session:
    def __init__(self, error):
        self.error, self.calls = error, 0

    def get(self, *args, **kwargs):
        self.calls += 1
        raise self.error


def test_fetch_page_retries_three_times_with_backoff():
    session, sleeps = _Session(requests.Timeout("timeout")), []
    with pytest.raises(RegistryParseError):
        fetch_page("https://dsvh.gov.vn/x", {"timeout_seconds": 30, "retries": 3, "backoff_seconds": [2, 4, 8]},
                   session=session, sleeper=sleeps.append)
    assert session.calls == 4 and sleeps == [2, 4, 8]


def test_http_500_becomes_failure_record(tmp_path):
    def fetcher(url, cfg):
        raise RegistryParseError("HTTP 500")

    report = collect(fetcher=fetcher, category_keys=["world_heritage"], output_dir=tmp_path, sleeper=lambda s: None)
    assert report["claim"] == "coverage_failed"
    assert report["failure_manifest"][0]["error_code"] == "REGISTRY_PARSE_ERROR"
    assert report["categories"][0]["failed"] == 1


def test_collect_full_exit_code_blocks_partial_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "RAW_DIR", tmp_path)
    monkeypatch.setattr(registry, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(registry, "collect", lambda: {
        "snapshot_id": "s", "canonical_total": 0, "registry_total": 0, "claim": "coverage_failed",
        "failure_manifest": [{"registry_category": "artisans", "error_code": "REGISTRY_EMPTY_SOURCE"}],
    })
    monkeypatch.setattr(wiki, "enrich_many", lambda items: {"matched_registry_records": 0, "total": 0, "wikidata_linked": 0})
    monkeypatch.delenv(registry.ALLOW_PARTIAL_ENV, raising=False)
    assert registry.collect_full() == 1
    monkeypatch.setenv(registry.ALLOW_PARTIAL_ENV, "1")
    assert registry.collect_full() == 0


# ---------------------------------------------------------------------------
# M2-10 areas
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def areas():
    return AreaResolver.from_config()


@pytest.mark.parametrize("location, labels", [
    ("Thành phố Hà Nội", ["Hà Nội"]),
    ("Tình TT Huế", ["Thừa Thiên Huế"]),
    ("Tỉnh Thừa Thiên - Huế", ["Thừa Thiên Huế"]),
    ("Tỉnh Quảng Nình", ["Quảng Ninh"]),
    ("Tỉnh Thanh Hoá", ["Thanh Hóa"]),
    ("Tỉnh KonTum", ["Kon Tum"]),
    ("Tỉnh Nghệ An Tỉnh Hà Tĩnh", ["Nghệ An", "Hà Tĩnh"]),
    ("Tỉnh Quảng Ninh - Hải Phòng", ["Quảng Ninh", "Hải Phòng"]),
    ("Xã Noong Hẹt, huyện Điện Biên, tỉnh Điện Biên", ["Điện Biên"]),
    ("Huyện Cần Giờ, Tp. Hồ Chí Minh", ["Thành phố Hồ Chí Minh"]),
    ("Xã Hợp Thành, Huyện Sơn Dương", ["Tuyên Quang"]),
])
def test_area_resolver(areas, location, labels):
    assert [area.label for area in areas.resolve(location).areas] == labels


def test_area_resolver_reports_unmapped(areas):
    match = areas.resolve("Làng Không Tên, huyện Vô Danh")
    assert match.areas == [] and match.warnings == ["AREA_UNMAPPED"]


def test_area_config_has_63_unique_provinces(areas):
    assert len(areas.areas) == 63
    assert len({a.entity_id for a in areas.areas}) == 63
    assert area_id_for_label("Hà Nội").startswith("area-name-")
    assert match_key("Hoà Bình") == match_key("Hòa Bình")


# DEC-M2-004 — công bố theo 34 tỉnh/thành sau sắp xếp 2025 (Nghị quyết 202/2025/QH15)

def test_area_config_has_34_merged_units(areas):
    assert areas.publish_level == "merged_2025"
    assert len(areas.merged_areas) == 34 and len(areas.published_areas) == 34
    assert {a.group for a in areas.areas} == set(areas.merged_areas)
    cities = {a.label for a in areas.merged_areas.values() if a.level == "thành phố trực thuộc trung ương"}
    assert cities == {"Hà Nội", "Huế", "Hải Phòng", "Đà Nẵng", "Thành phố Hồ Chí Minh", "Cần Thơ"}
    # Tỉnh không đổi tên giữ nguyên entity_id (URI công bố ổn định).
    assert areas.merged_areas["Hà Nội"].entity_id == area_id_for_label("Hà Nội")


@pytest.mark.parametrize("location, labels", [
    ("Thành phố Hà Nội", ["Hà Nội"]),
    ("Tình TT Huế", ["Huế"]),
    ("Tỉnh Bắc Kạn", ["Thái Nguyên"]),
    ("Tỉnh Bà Rịa - Vũng Tàu", ["Thành phố Hồ Chí Minh"]),
    ("Tỉnh Bắc Giang Tỉnh Bắc Ninh", ["Bắc Ninh"]),                  # hai tỉnh cũ cùng nhóm -> 1
    ("Tỉnh Hà Nam Tỉnh Nam Định", ["Ninh Bình"]),
    ("Tỉnh Nghệ An Tỉnh Hà Tĩnh", ["Nghệ An", "Hà Tĩnh"]),          # hai tỉnh không sáp nhập -> giữ 2
    ("xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương (nay là xã Khúc Thừa Dụ, Thành phố Hải Phòng)", ["Hải Phòng"]),
    ("xã Phú Lạc, huyện Tuy Phong, tỉnh Bình Thuận (nay là xã Liên Hương, tỉnh Lâm Đồng)", ["Lâm Đồng"]),
    ("Xã Hợp Thành, Huyện Sơn Dương", ["Tuyên Quang"]),
    ("huyện Tây Sơn", ["Gia Lai"]),                                  # district hint Bình Định -> Gia Lai
])
def test_area_resolver_publishes_merged_units(areas, location, labels):
    assert [area.label for area in areas.resolve_published(location).areas] == labels


def test_area_resolver_source_level_keeps_old_names():
    config = yaml.safe_load((ROOT / "config" / "areas.yaml").read_text(encoding="utf-8"))
    resolver = AreaResolver({**config, "publish_level": "source"})
    assert [a.label for a in resolver.resolve_published("Tỉnh Bắc Giang Tỉnh Bắc Ninh").areas] == ["Bắc Giang", "Bắc Ninh"]
    assert len(resolver.published_areas) == 63


def test_area_config_rejects_unknown_merged_into():
    config = yaml.safe_load((ROOT / "config" / "areas.yaml").read_text(encoding="utf-8"))
    broken = {**config, "merged_areas": [m for m in config["merged_areas"] if m["label"] != "Ninh Bình"]}
    with pytest.raises(ValueError, match="CONFIG_INVALID"):
        AreaResolver(broken)


# ---------------------------------------------------------------------------
# COMP-004 mapper (TEST-017…020, M2-10…M2-15)
# ---------------------------------------------------------------------------

TYPES = {"world_heritage": "HeritageSite", "national_special_monuments": "HeritageSite",
         "national_treasures": "NationalTreasure", "national_intangible": "IntangibleHeritage"}


def _entity(category="national_special_monuments", **fields):
    return {
        "_entity_id": "registry-abc123", "registry_id": "registry-abc123", "registry_category": category,
        "label_vi": fields.pop("label", "DTLS và KTNT Văn Miếu - Quốc Tử Giám"), "registry_url": "https://dsvh.gov.vn/x",
        "source_status": "registry_only", "coverage_snapshot": "s", "retrieved_at": "2026-09-13T00:00:00Z",
        "registry_fields": {"recognition_text": "548/QĐ-TTg Ngày 10/5/2012", "location": "Thành phố Hà Nội", **fields},
    }


def test_mapper_links_site_to_area_and_emits_area_record():
    derived = DerivedRegistry()
    record = map_record(_entity(), TYPES, derived=derived)
    area = derived.records()[0]
    assert record["relations"]["located_in"] == [area["entity_id"]]
    assert area["label_vi"] == "Hà Nội" and area["entity_type"] == "AdministrativeArea"
    assert area["source_status"] == "derived" and area["provenance"]["method"] == "derived"
    assert record["recognition_year"] == 2012
    assert record["address"] == "Thành phố Hà Nội"


def test_mapper_site_types_from_label_abbreviation():
    record = map_record(_entity(), TYPES)
    assert record["site_types"] == ["di tích lịch sử", "di tích kiến trúc nghệ thuật"]
    assert site_types_from_label("DTKC Hang con Moong", load_mapping()) == ["di tích khảo cổ"]


def test_mapper_located_in_uses_merged_province():
    derived = DerivedRegistry()
    record = map_record(_entity(location="xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương "
                                         "(nay là xã Khúc Thừa Dụ, Thành phố Hải Phòng)"), TYPES, derived=derived)
    areas = derived.records()
    assert [a["label_vi"] for a in areas] == ["Hải Phòng"]
    assert record["relations"]["located_in"] == [areas[0]["entity_id"]]
    assert areas[0]["level"] == "thành phố trực thuộc trung ương"
    assert record["address"].startswith("xã Kiến Quốc")          # ô địa điểm gốc vẫn giữ nguyên


def test_mapper_treasure_location_is_holder_not_area():
    derived = DerivedRegistry()
    record = map_record(_entity("national_treasures", label="Trống đồng Ngọc Lũ",
                                location="Bảo tàng Lịch sử quốc gia"), TYPES, derived=derived)
    assert record["current_holder"] == "Bảo tàng Lịch sử quốc gia"
    assert "address" not in record and "located_in" not in record.get("relations", {})
    assert derived.records() == []


def test_mapper_site_types_only_for_heritage_sites():
    record = map_record(_entity("national_intangible", label="Lễ hội X", type="Lễ hội truyền thống"), TYPES)
    assert "site_types" not in record or record["site_types"] == []


def test_mapper_world_heritage_recognized_by_unesco():
    derived = DerivedRegistry()
    record = map_record(_entity("world_heritage", label="Vịnh Hạ Long"), TYPES, derived=derived)
    assert record["relations"]["recognized_by"] == ["organization-unesco"]
    unesco = next(r for r in derived.records() if r["entity_id"] == "organization-unesco")
    assert unesco["entity_type"] == "Organization" and unesco["label_vi"] == "UNESCO"


def test_mapper_joins_page_by_registry_id_and_uses_only_verified_relations():
    page = {
        "page_id": 7, "title": "Văn Miếu – Quốc Tử Giám", "source_url": "https://vi.wikipedia.org/wiki/V",
        "retrieved_at": "2026-09-13T00:00:00Z", "wikidata_id": "Q1", "registry_ids": ["registry-abc123"],
        "requested_labels": ["DTLS và KTNT Văn Miếu - Quốc Tử Giám"],
        "infobox": {"năm_xây_dựng": "[[1070]]"},
        "relation_candidates": [
            {"relation": "built_by", "target_type": "HistoricalPerson", "title": "Lý Thánh Tông", "page_id": 11, "qid": "Q2", "verified": True},
            {"relation": "associated_persons", "target_type": "HistoricalPerson", "title": "Hà Nội", "page_id": 12, "qid": "Q3", "verified": False},
        ],
    }
    derived = DerivedRegistry()
    record = map_record(_entity(), TYPES, PageIndex([page]), derived=derived)
    assert record["source_status"] == "registry+wikipedia" and record["source_title"] == page["title"]
    assert record["construction_year"] == 1070
    assert record["relations"]["built_by"] == ["person-wikidata-q2"]
    assert "associated_persons" not in record["relations"]
    person = next(r for r in derived.records() if r["entity_id"] == "person-wikidata-q2")
    assert person["external_ids"] == {"wikidata": "Q2"} and person["source_page_id"] == 11
    assert page["title"] in record["aliases_vi"]


def test_validate_canonical_reports_missing_required_field():
    record = map_record(_entity("national_intangible", label="Lễ hội X"), TYPES)
    record.pop("registry_url")
    assert "MAPPING_REQUIRED_MISSING:registry_url" in validate_canonical(record, load_mapping())


def test_coverage_report_is_updated_after_map_and_never_upgraded(tmp_path):
    report = {"snapshot_id": "s", "claim": "100% of selected official registry snapshot",
              "categories": [{"registry_category": "world_heritage", "valid": 2, "canonicalized": 2, "coverage_percent": 100.0}]}
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "coverage.json").write_text(json.dumps(report), encoding="utf-8")
    raw = [{"registry_id": "registry-a", "coverage_snapshot": "s"}, {"registry_id": "registry-b", "coverage_snapshot": "s"}]
    canonical = [{"entity_id": "registry-a", "registry_id": "registry-a", "registry_category": "world_heritage", "source_status": "registry_only"},
                 {"entity_id": "area-name-x", "entity_type": "AdministrativeArea"}]
    update_coverage_report(raw, canonical, tmp_path)
    updated = json.loads((tmp_path / "s" / "coverage.json").read_text(encoding="utf-8"))
    assert updated["canonical_total"] == 1
    assert updated["unresolved_registry_ids"] == ["registry-b"]
    assert updated["categories"][0]["coverage_percent"] == 50.0
    assert updated["claim"] == "coverage_failed"


# ---------------------------------------------------------------------------
# COMP-001 Wikipedia (M2-13…M2-15)
# ---------------------------------------------------------------------------

def test_infobox_parser_handles_nested_templates_and_links():
    text = ("{{Thông tin di tích\n| tên = Chùa Keo\n| hình = [[Tập tin:A.jpg|nhỏ]]\n"
            "| năm xây dựng = {{Start date|1061}} thời [[nhà Lý]]\n| người xây dựng = [[Lý Thánh Tông|vua Lý Thánh Tông]]\n}}\n"
            "'''Chùa Keo''' là ...")
    fields, links = wiki.parse_first_infobox_with_links(text)
    assert fields["tên"] == "Chùa Keo"
    assert fields["năm_xây_dựng"].startswith("{{Start date|1061}}")
    assert links == {"năm_xây_dựng": ["nhà Lý"], "người_xây_dựng": ["Lý Thánh Tông"]}


def _api(*pages, redirects=()):
    return {"query": {"pages": list(pages), "redirects": list(redirects)}}


def test_alias_match_requires_province_evidence():
    cfg = wiki.load_config()
    page_ok = {"pageid": 1, "title": "Chùa Keo", "categories": [{"title": "Thể loại:Chùa tại Thái Bình"}], "revisions": []}
    target = {"registry_id": "registry-1", "label_vi": "DTKTNT Chùa Keo", "location": "Tỉnh Thái Bình"}
    pages, failures = wiki.match_registry_labels_to_pages([target], _api(page_ok), "t", cfg, AreaResolver.from_config())
    assert not failures and pages[0].match_method == "alias:strip_heritage_type_abbreviation"
    assert pages[0].match_evidence == ["province:Thái Bình"] and pages[0].registry_ids == ["registry-1"]

    wrong_place = dict(target, location="Tỉnh Nam Định")
    pages, failures = wiki.match_registry_labels_to_pages([wrong_place], _api(page_ok), "t", cfg, AreaResolver.from_config())
    # Nam Định (nhóm Ninh Bình) vs page Thái Bình (nhóm Hưng Yên): xung đột tỉnh -> loại.
    assert pages == [] and "province conflict" in failures[0]["reason"]


def test_dash_variant_is_exact_equivalent():
    cfg = wiki.load_config()
    page = {"pageid": 2, "title": "Văn Miếu – Quốc Tử Giám", "revisions": []}
    pages, failures = wiki.match_registry_labels_to_pages(["Văn Miếu - Quốc Tử Giám"], _api(page), "t", cfg)
    assert not failures and pages[0].match_method in {"exact_title+dash_variant", "exact_title+normalized"}


def test_disambiguation_page_is_rejected():
    cfg = wiki.load_config()
    page = {"pageid": 3, "title": "Đền Hùng", "pageprops": {"disambiguation": ""}, "revisions": []}
    pages, failures = wiki.match_registry_labels_to_pages(["Đền Hùng"], _api(page), "t", cfg)
    assert pages == [] and failures[0]["reason"].startswith("disambiguation page")


def test_query_with_continuation_merges_links():
    responses = [
        {"query": {"pages": [{"pageid": 1, "title": "A", "links": [{"title": "X"}]}]}, "continue": {"plcontinue": "1|0|Y"}},
        {"query": {"pages": [{"pageid": 1, "title": "A", "links": [{"title": "Y"}]}]}},
    ]
    merged = wiki.query_with_continuation(lambda url, params, cfg: responses.pop(0), "api", {"titles": "A"}, {})
    assert merged["query"]["pages"][0]["links"] == [{"title": "X"}, {"title": "Y"}]


def test_relation_candidates_verified_by_wikidata_p31(tmp_path):
    cfg = wiki.load_config()
    page = wiki.WikipediaPage(page_id=1, title="Chùa Keo", source_url="u", retrieved_at="t",
                              infobox_links={"người_xây_dựng": ["Lý Thánh Tông", "Nhà Lý"]})

    def fetcher(url, params, request_cfg):
        if "wikidata" in url:
            return {"entities": {
                "Q8": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}},
                "Q9": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q164950"}}}}]}},
            }}
        return {"query": {"pages": [
            {"pageid": 80, "title": "Lý Thánh Tông", "pageprops": {"wikibase_item": "Q8"}},
            {"pageid": 90, "title": "Nhà Lý", "pageprops": {"wikibase_item": "Q9"}},
        ]}}

    stats = wiki.resolve_relation_candidates([page], dict(cfg, request={"delay_seconds": 0}), fetcher)
    verified = {c["title"]: c["verified"] for c in page.relation_candidates}
    assert verified == {"Lý Thánh Tông": True, "Nhà Lý": False}  # triều đại không phải người xây dựng
    assert stats == {"candidates": 2, "verified": 1}


def test_enrich_many_writes_registry_ids_and_real_title(tmp_path):
    def fetcher(url, params, cfg):
        return {"query": {"redirects": [{"from": "Chùa Một Cột", "to": "Chùa Diên Hựu"}],
                          "pages": [{"pageid": 5, "title": "Chùa Diên Hựu", "revisions": []}]}}

    result = wiki.enrich_many([{"registry_id": "registry-9", "label_vi": "Chùa Một Cột", "location": "Hà Nội"}],
                              fetcher=fetcher, output_dir=tmp_path, sleeper=lambda s: None)
    page = json.loads((tmp_path / "pages.jsonl").read_text(encoding="utf-8"))
    assert result["matched_registry_records"] == 1
    assert page["title"] == "Chùa Diên Hựu" and page["registry_ids"] == ["registry-9"]
    assert page["source_url"].startswith("https://vi.wikipedia.org/wiki/Ch%C3%B9a_Di%C3%AAn")
    assert page["match_method"] == "redirect"


# ---------------------------------------------------------------------------
# Snapshot migration tool (M2-02/03)
# ---------------------------------------------------------------------------

def test_migration_tool_is_idempotent(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("m2_migrate", ROOT / "tools" / "m2_migrate_registry_ids.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [
        {"registry_id": "registry-old1", "registry_category": "world_heritage", "label_vi": "Vịnh Hạ Long",
         "registry_url": "http://dsvh.gov.vn/vinh-ha-long-476", "source_status": "registry_only",
         "coverage_snapshot": "s", "retrieved_at": "t", "registry_fields": {"ordinal": "2", "location": "Tỉnh Quảng Ninh"}},
    ]
    (tmp_path / "registry_records.jsonl").write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "wikidata_exact_enrichment.jsonl").write_text(json.dumps({"entity_id": "registry-old1", "wikidata_id": "Q1"}) + "\n", encoding="utf-8")
    first = module.migrate(tmp_path, apply=True)
    second = module.migrate(tmp_path, apply=True)
    assert first["entity_ids_changed"] == 1 and second["entity_ids_changed"] == 0
    migrated = json.loads((tmp_path / "registry_records.jsonl").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "wikidata_exact_enrichment.jsonl").read_text(encoding="utf-8"))
    assert migrated["registry_url"] == "https://dsvh.gov.vn/vinh-ha-long-476"
    assert manifest["entity_id"] == migrated["registry_id"]


# ---------------------------------------------------------------------------
# Kaggle run 2026-09-23 follow-ups
# ---------------------------------------------------------------------------

from vietheritage.normalization.normalizer import iri_to_uri, is_valid_uri  # noqa: E402


@pytest.mark.parametrize("iri, uri", [
    ("https://vi.wikipedia.org/wiki/Vịnh_Hạ_Long", "https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long"),
    ("https://dsvh.gov.vn/di-tich-lich-su-dèn-thò-nguyẽn-bỉnh-khiem-2993",
     "https://dsvh.gov.vn/di-tich-lich-su-d%C3%A8n-th%C3%B2-nguy%E1%BA%BDn-b%E1%BB%89nh-khiem-2993"),
    ("https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long", "https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long"),
    ("https://dsvh.gov.vn/list?page=2", "https://dsvh.gov.vn/list?page=2"),
])
def test_iri_to_uri_is_strict_and_idempotent(iri, uri):
    assert iri_to_uri(iri) == uri
    assert iri_to_uri(uri) == uri
    assert is_valid_uri(uri) and (iri == uri or not is_valid_uri(iri))


def test_registry_url_with_vietnamese_path_is_encoded():
    url, _ = normalize_registry_url("/di-tich-lich-su-dèn-thò-2993", CATEGORY_URL)
    assert url == "https://dsvh.gov.vn/di-tich-lich-su-d%C3%A8n-th%C3%B2-2993"


def test_mapper_emits_ascii_uris_for_legacy_unencoded_pages():
    page = {"page_id": 1, "title": "Vịnh Hạ Long", "source_url": "https://vi.wikipedia.org/wiki/Vịnh_Hạ_Long",
            "retrieved_at": "t"}
    entity = _entity("world_heritage", label="Vịnh Hạ Long")
    entity["registry_url"] = "https://dsvh.gov.vn/vịnh-476"
    record = map_record(entity, TYPES, {"vịnh hạ long": page})
    assert is_valid_uri(record["source_url"]) and is_valid_uri(record["registry_url"])
    assert validate_canonical(record, load_mapping()) == []


def test_validate_canonical_rejects_non_ascii_uri_without_format_libraries():
    record = map_record(_entity("world_heritage", label="Vịnh Hạ Long"), TYPES)
    record["source_url"] = "https://vi.wikipedia.org/wiki/Vịnh"
    assert any(p.startswith("CANONICAL_INVALID_URI:source_url") for p in validate_canonical(record, load_mapping()))


def _empty_allowed_config(tmp_path: Path, with_decision: bool = True) -> Path:
    path = tmp_path / "registry_sources.yaml"
    museums = {"key": "national_museums", "url": "https://dsvh.gov.vn/museums", "entity_type": "Museum",
               "columns": {"recognition_text": 0, "label_vi": 2, "location": 3}, "allow_empty_source": True,
               "empty_source_note": {"decision": "DEC-TEST", "reason": "empty template"} if with_decision else {}}
    path.write_text(json.dumps({
        "base_url": "https://dsvh.gov.vn/", "request": {"delay_seconds": 0},
        "defaults": {"row_selector": "table tbody tr"},
        "categories": [
            {"key": "world_heritage", "url": "https://dsvh.gov.vn/wh", "entity_type": "HeritageSite",
             "columns": {"ordinal": 0, "label_vi": 1, "recognition_text": 2, "location": 3}},
            museums,
        ],
    }), encoding="utf-8")
    return path


EMPTY_TEMPLATE = ("<table><tbody><tr><td>Số Quyết định</td><td>Ngày tháng năm</td><td>Tên Bảo tàng</td><td>Địa chỉ</td></tr>"
                  + "<tr><td></td><td></td><td></td><td></td></tr>" * 23
                  + "<tr><td></td><td>Tổng số</td><td></td><td></td></tr></tbody></table>")


def test_empty_source_allowed_by_decision_stays_in_coverage_universe(tmp_path):
    pages = {"https://dsvh.gov.vn/wh": _page([(1, "Vịnh Hạ Long")]), "https://dsvh.gov.vn/museums": EMPTY_TEMPLATE}
    report = collect(config_path=_empty_allowed_config(tmp_path), output_dir=tmp_path,
                     fetcher=lambda url, cfg: pages[url], sleeper=lambda s: None)
    assert report["claim"] == "100% of selected official registry snapshot"
    museums = next(c for c in report["categories"] if c["registry_category"] == "national_museums")
    assert (museums["valid"], museums["failed"], museums["coverage_percent"]) == (0, 0, 100.0)
    note = json.loads((tmp_path / "registry_empty_sources.jsonl").read_text(encoding="utf-8"))
    assert note["decision"] == "DEC-TEST" and note["rows_found"] == 0


def test_empty_allowed_category_is_collected_when_source_has_data(tmp_path):
    museum = "<table><tbody><tr><td>12/QĐ</td><td>2010</td><td>Bảo tàng A</td><td>Hà Nội</td></tr></tbody></table>"
    pages = {"https://dsvh.gov.vn/wh": _page([(1, "Vịnh Hạ Long")]), "https://dsvh.gov.vn/museums": museum}
    report = collect(config_path=_empty_allowed_config(tmp_path), output_dir=tmp_path,
                     fetcher=lambda url, cfg: pages[url], sleeper=lambda s: None)
    assert report["claim"] == "100% of selected official registry snapshot"
    labels = [json.loads(l)["label_vi"] for l in (tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "Bảo tàng A" in labels
    assert (tmp_path / "registry_empty_sources.jsonl").read_text(encoding="utf-8") == ""


def test_empty_allowed_category_still_fails_on_http_error(tmp_path):
    def fetcher(url, cfg):
        if url.endswith("/museums"):
            raise RegistryParseError("HTTP 500")
        return _page([(1, "Vịnh Hạ Long")])

    report = collect(config_path=_empty_allowed_config(tmp_path), output_dir=tmp_path, fetcher=fetcher, sleeper=lambda s: None)
    assert report["claim"] == "coverage_failed"
    assert report["failure_manifest"][0]["error_code"] == "REGISTRY_PARSE_ERROR"


def test_allow_empty_source_requires_decision(tmp_path):
    with pytest.raises(registry.ConfigInvalidError):
        registry.load_config(_empty_allowed_config(tmp_path, with_decision=False))


def test_real_config_keeps_all_17_categories_with_empty_ones_documented():
    _, categories = registry.load_config()
    assert len(categories) == 17
    allowed = {c.key for c in categories if c.allow_empty_source}
    assert allowed == {"artisans", "artifacts_antiquities", "national_artisans", "meritorious_artisans",
                       "national_museums", "ministry_museums", "central_organization_museums",
                       "provincial_museums", "private_museums", "documentary_heritage"}
    assert all(c.empty_source_note["decision"].startswith("DEC-M2-001") for c in categories if c.allow_empty_source)


# ---------------------------------------------------------------------------
# Real registry HTML (Kaggle probe 2026-09-23) and Wikipedia match policies
# ---------------------------------------------------------------------------

REAL_HTML = ROOT / "data" / "fixtures" / "registry"
EXPECTED_ROWS = {"world_heritage": 9, "national_special_monuments": 107, "national_monuments": 6,
                 "intangible_representative": 13, "intangible_urgent": 2, "national_intangible": 486,
                 "national_treasures": 237}


EMPTY_AT_SOURCE = {"artisans", "artifacts_antiquities", "national_artisans", "meritorious_artisans",
                   "national_museums", "ministry_museums", "central_organization_museums",
                   "provincial_museums", "private_museums", "documentary_heritage"}


def _replay_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("m2_replay", ROOT / "tools" / "m2_replay_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not REAL_HTML.exists(), reason="real registry HTML fixtures not present")
def test_real_registry_html_replays_to_full_selected_coverage(tmp_path):
    report = _replay_module().replay_registry(REAL_HTML, "20260923T141051Z", "2026-09-23T14:10:51Z", tmp_path)
    counts = {c["registry_category"]: c["valid"] for c in report["categories"]}
    assert counts == {**EXPECTED_ROWS, **{key: 0 for key in EMPTY_AT_SOURCE}}
    assert report["claim"] == "100% of selected official registry snapshot"
    empty = [json.loads(line) for line in (tmp_path / "registry_empty_sources.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {e["registry_category"] for e in empty} == EMPTY_AT_SOURCE
    records = [json.loads(line) for line in (tmp_path / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    cat_ba = next(r for r in records if r["label_vi"] == "Vịnh Hạ Long - Quần đảo Cát Bà")
    assert cat_ba["registry_url"].endswith("-22117")  # href "//https://dsvh.gov.vn/...-22117"
    assert all(is_valid_uri(r["registry_url"]) for r in records)


@pytest.mark.skipif(not REAL_HTML.exists(), reason="real registry HTML fixtures not present")
@pytest.mark.parametrize("key", ["national_museums", "national_artisans", "private_museums"])
def test_real_empty_template_pages_have_no_data_rows(key):
    html = (REAL_HTML / f"{key}.html").read_text(encoding="utf-8")
    assert parse_table_rows(html, ["^Tổng số"], row_selector="table tr") == []


MATCHING = wiki.load_config()["matching"]


@pytest.mark.parametrize("categories, registry_category, rejected", [
    (["Thể loại:Danh sách xã Việt Nam", "Thể loại:Đơn vị hành chính thuộc tỉnh Tuyên Quang"], "national_special_monuments", True),
    (["Thể loại:Sông của Việt Nam", "Thể loại:Di tích tại Quảng Ninh"], "national_special_monuments", True),
    (["Thể loại:Mất năm 248", "Thể loại:Người Thanh Hóa"], "national_special_monuments", True),
    (["Thể loại:Khởi nghĩa Bắc Sơn"], "national_special_monuments", True),
    (["Thể loại:Di tích quốc gia đặc biệt", "Thể loại:Di tích tại Hà Nội"], "national_special_monuments", False),
    (["Thể loại:Người Mường", "Thể loại:Văn học dân gian"], "national_intangible", False),
    (["Thể loại:Bảo vật quốc gia của Việt Nam"], "national_treasures", False),
    (["Thể loại:Đồ vật có phép thuật"], "national_treasures", True),
    ([], "national_treasures", True),
])
def test_page_rejection_policy(categories, registry_category, rejected):
    assert (wiki.page_rejection_reason(categories, registry_category, MATCHING) is not None) == rejected


def test_page_shared_by_different_labels_in_same_category_is_ambiguous():
    assignments = [(1, "national_intangible", "Dân ca Cao Lan"), (1, "national_intangible", "Dân ca Sán Chí"),
                   (2, "world_heritage", "Vịnh Hạ Long"), (2, "national_special_monuments", "Vịnh Hạ Long"),
                   (3, "national_intangible", "Nghệ thuật Khèn của người Mông"),
                   (3, "national_intangible", "Nghệ thuật Khèn của người Mông")]
    assert wiki.ambiguous_shared_pages(assignments) == {1}


def test_live_matching_rejects_person_page_and_tries_next_candidate():
    person = {"pageid": 7, "title": "Bà Triệu", "categories": [{"title": "Thể loại:Mất năm 248"}], "revisions": []}
    target = {"registry_id": "r1", "label_vi": "DTLS và KTNT Khu di tích Bà Triệu", "location": "Tỉnh Thanh Hóa",
              "registry_category": "national_special_monuments"}
    pages, failures = wiki.match_registry_labels_to_pages([target], _api(person), "t", wiki.load_config(), AreaResolver.from_config())
    assert pages == [] and "Mất năm 248" in failures[0]["reason"]


def test_architectural_style_relation_is_mapped():
    page = {"page_id": 7, "title": "Nhà thờ Lớn Hà Nội", "source_url": "https://vi.wikipedia.org/wiki/N",
            "retrieved_at": "t", "registry_ids": ["registry-abc123"],
            "relation_candidates": [{"relation": "architectural_styles", "target_type": "ArchitecturalStyle",
                                     "title": "Kiến trúc Gothic Phục hưng", "page_id": 9, "qid": "Q1", "verified": True}]}
    derived = DerivedRegistry()
    record = map_record(_entity(), TYPES, PageIndex([page]), derived=derived)
    style_id = record["relations"]["architectural_styles"][0]
    assert style_id.startswith("style-")
    assert next(r for r in derived.records() if r["entity_id"] == style_id)["entity_type"] == "ArchitecturalStyle"
