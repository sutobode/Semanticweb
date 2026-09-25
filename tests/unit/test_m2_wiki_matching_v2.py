"""Engine khớp Wikipedia v2 — hồi quy theo review thủ công 2026-09-24.

Chạy trên MediaWiki giả lập ``tests/fixtures/fake_viwiki.py`` với 860 registry record thật
(snapshot 20260923T141051Z): các cặp "tên dsvh -- tên wiki" từ review phải khớp, các bẫy
(sông, người, sự kiện, trang định hướng, di tích trùng tên khác tỉnh) phải bị loại.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from vietheritage.collector import wikipedia as wiki
from vietheritage.identity.resolver import supplement_merges
from vietheritage.mapping.mapper import PageIndex, load_mapping, map_entity, update_coverage_report

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "registry_records.jsonl"


def _fake_module():
    spec = importlib.util.spec_from_file_location("fake_viwiki", ROOT / "tests" / "fixtures" / "fake_viwiki.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def records():
    if not RAW.exists():
        pytest.skip("registry snapshot not present")
    return [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(records, tmp_path_factory):
    out = tmp_path_factory.mktemp("wiki")
    fake = _fake_module().FakeWiki()
    items = [{"registry_id": r["registry_id"], "label_vi": r["label_vi"], "registry_category": r["registry_category"],
              "location": (r.get("registry_fields") or {}).get("location")} for r in records]
    result = wiki.enrich_many(items, fetcher=fake, output_dir=out, sleeper=lambda _s: None)
    pages = [json.loads(l) for l in (out / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    failures = {json.loads(l)["label_vi"]: json.loads(l) for l in (out / "enrichment_failures.jsonl").read_text(encoding="utf-8").splitlines()}
    links: dict[str, list[tuple[str, dict]]] = {}
    for page in pages:
        for link in page["registry_links"]:
            links.setdefault(link["label_vi"], []).append((page["title"], link))
    return {"result": result, "pages": pages, "links": links, "failures": failures, "calls": fake.calls}


EXPECTED = {
    # tên dsvh                                                   : bài Wikipedia
    "DLTC Khu Bảo tồn thiên nhiên Na Hang - Lâm Bình": "Khu bảo tồn thiên nhiên Na Hang – Lâm Bình",   # hoa/thường + dấu gạch
    "DLTC Quần Đảo Cát Bà": "Quần đảo Cát Bà",                                                       # hoa/thường
    "DTKC Hang con Moong và các di tích phụ cận": "Hang Con Moong",                                  # thành phần duy nhất
    "DTKC Mộ Cự Thạch Hàng Gòn": "Mộ cự thạch Hàng Gòn",
    "DTKTNT và KC Tháp Pô Klong Garai": "Tháp Po Klong Garai",                                       # name_variants + tỉnh sau sáp nhập
    "DTLS An toàn khu (ATK) Định Hóa": "An toàn khu Định Hóa",                                       # bỏ ngoặc
    "DTLS Bạch Đằng": "Khu di tích lịch sử Bạch Đằng",                                               # tiền tố trước tên trần
    "Chiến trường Điện Biên Phủ": "Khu di tích chiến trường Điện Biên Phủ",
    "DTLS Khu di tích Nhà Trần tại Đông Triều": "Khu di tích nhà Trần tại Đông Triều",
    "DTLS Khu lưu niệm Chủ tịch Tôn Đức Thắng tại Mỹ Hòa Hưng": "Khu lưu niệm Chủ tịch Tôn Đức Thắng",
    "DTLS Nhà đày Buôn Mê Thuột": "Nhà đày Buôn Ma Thuột",
    "DTLS Những địa điểm Khởi nghĩa Yên Thế": "Khu di tích khởi nghĩa Yên Thế",                     # không ra bài "Khởi nghĩa Yên Thế"
    "DTLS Thành cổ Quảng Trị và những địa điểm lưu niệm sự kiện 81 ngày đêm năm 1972": "Thành cổ Quảng Trị",
    "DTLS Trại giam Phú Quốc": "Nhà tù Phú Quốc",
    "DTLS và KTNT Chùa Thầy và khu vực núi đá Sài Sơn, Hoàng Xá, Phượng Cách": "Chùa Thầy",
    "DTLS và KTNT Chùa Vĩnh Nghiêm": "Chùa Vĩnh Nghiêm (Bắc Ninh)",                                   # định hướng + Bắc Giang -> Bắc Ninh
    "DTLS và KTNT Côn Sơn - Kiếp Bạc": "Khu di tích Côn Sơn – Kiếp Bạc",                              # 1 bài, KHÔNG tách
    "DTLS Địa đạo Vịnh Mốc và hệ thống làng hầm Vĩnh Linh": "Địa đạo Vịnh Mốc",
    "Khu Trung tâm Hoàng thành Thăng Long - Hà Nội": "Hoàng thành Thăng Long",
    "Quần thể kiến trúc Cố đô Huế": "Quần thể di tích Cố đô Huế",
    "DTKTNT Chùa Keo": "Chùa Keo (Thái Bình)",                                                        # định hướng
    "DTKTNT Chùa Keo Hành Thiện": "Chùa Keo Hành Thiện",
    "Khu di tích Chăm Mỹ Sơn": "Thánh địa Mỹ Sơn",                                                    # override
    "DTLS Tân Trào": "Chiến khu Tân Trào",                                                            # override
    "DTLS và KTNT Khu di tích Bà Triệu": "Đền Bà Triệu",                                               # override
    "DTLS Đường Trường Sơn - Đường Hồ Chí Minh": "Đường Trường Sơn",                                   # override
    "Hát xoan Phú Thọ": "Hát xoan",
    "Hát Xoan ở Phú Thọ": "Hát xoan",
    "Dân ca Quan họ Bắc Ninh": "Quan họ",
    "Hát Ca trù": "Ca trù",
    "Hội đua bò Bảy Núi": "Lễ hội đua bò Bảy Núi",
    "Lễ hội Chọi trâu Đồ Sơn": "Lễ hội chọi trâu Đồ Sơn",
    "Chữ Nôm của người Tày": "Chữ Nôm Tày",
    "Tín ngưỡng thờ cúng Hùng Vương ở Phú Thọ": "Tín ngưỡng thờ cúng Hùng Vương",
}


@pytest.mark.parametrize("label, title", sorted(EXPECTED.items()))
def test_review_pairs_are_matched(run, label, title):
    titles = {t for t, _ in run["links"].get(label, [])}
    assert titles == {title}, run["failures"].get(label)


SPLIT = {
    "DTLS và DLTC Hồ Hoàn Kiếm và Đền Ngọc Sơn": {"Hồ Hoàn Kiếm", "Đền Ngọc Sơn"},
    "DTLS Đền Xưa - Chùa Giám - Đền Bia": {"Đền Xưa", "Chùa Giám", "Đền Bia"},
    "DTLS và KTNT Đền Trần và Chùa Phổ Minh": {"Đền Trần (Nam Định)", "Chùa Phổ Minh (Nam Định)"},
    "DTLS và DLTC Quần thể An Phụ - Kính Chủ - Nhẫm Dương": {"Đền Cao An Phụ", "Động Kính Chủ"},
}


@pytest.mark.parametrize("label, titles", sorted(SPLIT.items()))
def test_multi_site_records_link_one_page_per_component(run, label, titles):
    links = run["links"][label]
    assert {t for t, _ in links} == titles
    assert all(link["part_label"] for _, link in links)


@pytest.mark.parametrize("label", [
    "DTLS và KTNT Côn Sơn - Kiếp Bạc", "DTLS và KTNT Chùa Thầy và khu vực núi đá Sài Sơn, Hoàng Xá, Phượng Cách",
    "DTKC Hang con Moong và các di tích phụ cận",
])
def test_single_page_records_are_not_split(run, label):
    assert all(link["part_label"] is None for _, link in run["links"][label])


def test_traps_are_rejected(run):
    linked_titles = {t for items in run["links"].values() for t, _ in items}
    for trap in ("Sông Bạch Đằng", "Bà Triệu", "Khởi nghĩa Yên Thế", "Xoan", "Hoàng Xá", "Côn Sơn", "Kiếp Bạc",
                 "Chùa Keo", "Đền Trần", "Chùa Vĩnh Nghiêm (Thành phố Hồ Chí Minh)"):
        assert trap not in linked_titles, trap
    # Chùa Keo Hành Thiện (Nam Định) không bao giờ nhận bài Chùa Keo (Thái Bình)
    assert {t for t, _ in run["links"]["DTKTNT Chùa Keo Hành Thiện"]} == {"Chùa Keo Hành Thiện"}
    # Nguyễn Sinh Sắc: bài Wikipedia là di tích khác (Đồng Tháp) -> không map
    assert "Địa điểm lưu niệm Cụ Nguyễn Sinh Sắc tại huyện đường Bình Khê" in run["failures"]


def test_merged_province_evidence_is_explicit(run):
    _, link = run["links"]["DTKTNT và KC Tháp Pô Klong Garai"][0]
    assert link["match_evidence"] == ["province:Ninh Thuận->Khánh Hòa (sáp nhập 2025)"]


def test_unmatched_records_report_titles_tried(run):
    failure = run["failures"]["Địa điểm lưu niệm Cụ Nguyễn Sinh Sắc tại huyện đường Bình Khê"]
    assert failure["titles_tried"][0] == "Địa điểm lưu niệm Cụ Nguyễn Sinh Sắc tại huyện đường Bình Khê"


def test_prefixsearch_accepts_only_exact_normalized_titles(run):
    assert all(c.get("pslimit") for c in run["calls"] if c.get("list") == "prefixsearch")
    # "Xoan" (cây) có trong kết quả prefixsearch của "Xoan…" nhưng không bao giờ được nhận cho Hát xoan
    assert {t for t, _ in run["links"]["Hát xoan Phú Thọ"]} == {"Hát xoan"}


def test_supplement_record_is_merged_into_base(records):
    for record in records:
        record["_entity_id"] = record["registry_id"]
    merges = supplement_merges(records, load_mapping()["registry_supplements"])
    labels = {r["registry_id"]: r["label_vi"] for r in records}
    assert {labels[k]: labels[v] for k, v in merges.items()} == {
        "DTLS Chiến trường Điện Biên Phủ (bổ sung thêm 23 điểm di tích)": "Chiến trường Điện Biên Phủ",
        "DTLS Đường Trường Sơn - Đường Hồ Chí Minh (bổ sung thêm 09 điểm di tích)": "DTLS Đường Trường Sơn - Đường Hồ Chí Minh",
    }


def test_mapper_splits_multi_site_record_and_coverage_counts_rows(run, records, tmp_path):
    record = next(r for r in records if r["label_vi"] == "DTLS và DLTC Hồ Hoàn Kiếm và Đền Ngọc Sơn")
    entity = dict(record, _entity_id=record["registry_id"])
    types = {"national_special_monuments": "HeritageSite"}
    mapped = map_entity(entity, types, PageIndex(run["pages"]))
    assert sorted(r["label_vi"] for r in mapped) == ["Hồ Hoàn Kiếm", "Đền Ngọc Sơn"]
    assert len({r["entity_id"] for r in mapped}) == 2 and {r["registry_id"] for r in mapped} == {record["registry_id"]}
    assert all(record["label_vi"] in r["aliases_vi"] for r in mapped)
    assert all(r["site_types"] == ["di tích lịch sử", "danh lam thắng cảnh"] for r in mapped)
    assert {r["source_title"] for r in mapped} == {"Hồ Hoàn Kiếm", "Đền Ngọc Sơn"}

    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "coverage.json").write_text(json.dumps({
        "snapshot_id": "s", "claim": "100% of selected official registry snapshot",
        "categories": [{"registry_category": "national_special_monuments", "valid": 2, "canonicalized": 2, "coverage_percent": 100.0}]}),
        encoding="utf-8")
    raw = [{"registry_id": record["registry_id"], "registry_category": "national_special_monuments", "coverage_snapshot": "s"},
           {"registry_id": "registry-supplement", "registry_category": "national_special_monuments", "coverage_snapshot": "s"}]
    update_coverage_report(raw, mapped, tmp_path, merged_ids={"registry-supplement"})
    report = json.loads((tmp_path / "s" / "coverage.json").read_text(encoding="utf-8"))
    assert report["canonical_total"] == 2 and report["claim"] == "100% of selected official registry snapshot"
