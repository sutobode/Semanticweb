"""M2-30/31 — nguồn danh sách Wikipedia (di sản tư liệu) và tỉnh của nơi lưu giữ (bảo vật).

Không gọi mạng: MediaWiki giả lập ngay trong file (action=parse, action=query, prefixsearch, search).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vietheritage.mapping.mapper import DerivedRegistry, PageIndex, map_record
from vietheritage.normalization.areas import default_resolver
from vietheritage.registry import holder_locations as hl
from vietheritage.registry import wikipedia_lists as wl

ROOT = Path(__file__).resolve().parents[2]
TYPES = {"documentary_heritage": "DocumentaryHeritage", "national_treasures": "NationalTreasure"}

SECTION_HTML_LISTS = """
<div class="mw-heading mw-heading2"><h2 id="Việt_Nam">Việt Nam</h2><span class="mw-editsection">[sửa]</span></div>
<p>Việt Nam có các di sản tư liệu sau.<sup class="reference"><a href="#cite_note-1">[1]</a></sup></p>
<div class="mw-heading mw-heading3"><h3>Di sản tư liệu thế giới</h3></div>
<ul>
<li><a href="/wiki/M%E1%BB%99c_b%E1%BA%A3n_tri%E1%BB%81u_Nguy%E1%BB%85n" title="Mộc bản triều Nguyễn">Mộc bản triều Nguyễn</a> (2009)<sup class="reference">[2]</sup></li>
<li><a href="/wiki/Bia_ti%E1%BA%BFn_s%C4%A9_V%C4%83n_Mi%E1%BA%BFu" title="Bia tiến sĩ Văn Miếu">Bia Tiến sĩ tại Văn Miếu - Quốc Tử Giám</a> (2011)</li>
<li><a href="/wiki/Ch%C3%A2u_b%E1%BA%A3n_tri%E1%BB%81u_Nguy%E1%BB%85n" title="Châu bản triều Nguyễn">Châu bản triều Nguyễn</a> (2017)</li>
<li>Bộ sưu tập tài liệu của nhạc sĩ Hoàng Vân (1930 – 2018), ghi danh năm 2025</li>
</ul>
<div class="mw-heading mw-heading3"><h3>Di sản tư liệu khu vực Châu Á - Thái Bình Dương</h3></div>
<ul>
<li><a href="/wiki/M%E1%BB%99c_b%E1%BA%A3n_ch%C3%B9a_V%C4%A9nh_Nghi%C3%AAm" title="Mộc bản chùa Vĩnh Nghiêm">Mộc bản chùa Vĩnh Nghiêm</a> (2012)</li>
<li><a href="/wiki/Ch%C3%A2u_b%E1%BA%A3n_tri%E1%BB%81u_Nguy%E1%BB%85n" title="Châu bản triều Nguyễn">Châu bản triều Nguyễn</a> (2014)</li>
<li><a class="new" href="/w/index.php?title=Ho%C3%A0ng_hoa_s%E1%BB%A9_tr%C3%ACnh_%C4%91%E1%BB%93&amp;redlink=1">Hoàng hoa sứ trình đồ</a> (2018)</li>
</ul>
<div class="mw-heading mw-heading3"><h3>Hồ sơ đề cử</h3></div>
<ul><li>Hồ sơ Văn bản Hán Nôm XYZ (dự kiến 2027)</li></ul>
<div class="navbox"><ul><li><a href="/wiki/UNESCO">UNESCO</a> 2001</li></ul></div>
"""

SECTION_HTML_TABLE = """
<h2>Việt Nam</h2>
<table class="wikitable">
<tbody>
<tr><th>STT</th><th>Tên di sản</th><th>Năm công nhận</th><th>Cấp</th><th>Nơi lưu giữ</th></tr>
<tr><td>1</td><td><a href="/wiki/M%E1%BB%99c_b%E1%BA%A3n_tri%E1%BB%81u_Nguy%E1%BB%85n" title="Mộc bản triều Nguyễn">Mộc bản triều Nguyễn</a></td>
    <td>2009</td><td rowspan="2">Thế giới</td><td>Trung tâm Lưu trữ quốc gia IV, Đà Lạt, tỉnh Lâm Đồng</td></tr>
<tr><td>2</td><td>Bộ sưu tập tài liệu của nhạc sĩ Hoàng Vân</td><td>2025</td><td></td></tr>
<tr><td colspan="5">Khu vực Châu Á - Thái Bình Dương</td></tr>
<tr><td>3</td><td><a href="/wiki/Th%C6%A1_v%C4%83n" title="Thơ văn trên kiến trúc cung đình Huế">Thơ văn trên kiến trúc cung đình Huế</a></td>
    <td>2016</td><td>Khu vực</td><td>Huế</td></tr>
<tr><td>4</td><td>Hồ sơ đang đề cử ABC</td><td>2026</td><td>Thế giới</td><td>Hà Nội</td></tr>
</tbody></table>
"""


class FakeWiki:
    def __init__(self, section_html: str, sections: list[dict] | None = None) -> None:
        self.section_html = section_html
        self.sections = sections if sections is not None else [
            {"toclevel": 1, "level": "2", "line": "Lịch sử", "number": "1", "index": "1"},
            {"toclevel": 1, "level": "2", "line": "Việt Nam", "number": "2", "index": "2"},
            {"toclevel": 2, "level": "3", "line": "Di sản tư liệu thế giới", "number": "2.1", "index": "3"},
        ]
        self.pages: dict[str, dict] = {}
        self.redirects: dict[str, str] = {}
        self.calls: list[dict] = []
        next_id = [5000]

        def add(title, extract, qid=None, categories=(), content=""):
            next_id[0] += 1
            props = {"wikibase_item": qid} if qid else {}
            self.pages[title] = {"pageid": next_id[0], "title": title, "extract": extract, "pageprops": props,
                                 "categories": [{"title": "Thể loại:" + c} for c in categories],
                                 "revisions": [{"revid": next_id[0] * 10, "slots": {"main": {"content": content}}}]}
        add("Mộc bản triều Nguyễn", "Mộc bản triều Nguyễn là …", "Q101", ["Di sản tư liệu thế giới"],
            "{{Thông tin di sản\n| vị trí = [[Đà Lạt]], [[Lâm Đồng]]\n}}")
        add("Bia tiến sĩ Văn Miếu", "82 tấm bia …", "Q102")
        add("Châu bản triều Nguyễn", "Châu bản …", "Q103")
        add("Mộc bản chùa Vĩnh Nghiêm", "Mộc bản …", "Q104")
        add("Thơ văn trên kiến trúc cung đình Huế", "Thơ văn …", "Q105")
        add("Hoàng Vân (nhạc sĩ)", "Hoàng Vân là nhạc sĩ sinh tại Hà Nội.", "Q999", ["Nhạc sĩ Việt Nam"])
        add("Di sản tư liệu thế giới", "Chương trình Ký ức thế giới …", "Q500")
        # Bảo tàng
        add("Bảo tàng Lịch sử Quốc gia", "Bảo tàng Lịch sử quốc gia là bảo tàng ở Hà Nội.", "Q201",
            ["Bảo tàng tại Hà Nội"], "{{Infobox museum\n| location = 1 Tràng Tiền, [[Hoàn Kiếm]], [[Hà Nội]]\n}}")
        add("Bảo tàng Hồ Chí Minh", "Bảo tàng Hồ Chí Minh là bảo tàng tưởng niệm Chủ tịch Hồ Chí Minh ở Hà Nội.", "Q202",
            ["Bảo tàng tại Hà Nội"])
        add("Bảo tàng Quân khu 7", "Bảo tàng ở Thành phố Hồ Chí Minh.", None, ["Bảo tàng tại Thành phố Hồ Chí Minh"])
        add("Bảo tàng Hải quân (Việt Nam)", "Bảo tàng của Quân chủng Hải quân tại Hải Phòng.", None)
        add("Bảo tàng Mơ hồ", "Bảo tàng có chi nhánh ở Hà Nội và Đà Nẵng.", None)
        self.redirects["Bảo tàng Lịch sử quốc gia"] = "Bảo tàng Lịch sử Quốc gia"
        self.list_html = "<p>Danh sách</p>"

    def __call__(self, api_url, params, request_cfg):
        self.calls.append(dict(params))
        if params.get("action") == "parse":
            page = self.pages[params["page"]]
            if params.get("section") is not None:
                return {"parse": {"title": page["title"], "pageid": page["pageid"], "text": self.section_html}}
            return {"parse": {"title": page["title"], "pageid": page["pageid"], "text": self.list_html,
                              "sections": self.sections}}
        if params.get("list") == "prefixsearch":
            key = params["pssearch"].casefold()
            return {"query": {"prefixsearch": [{"title": t} for t in self.pages if t.casefold().startswith(key)]}}
        if params.get("list") == "search":
            words = params["srsearch"].casefold().split()
            return {"query": {"search": [{"title": t} for t in self.pages if all(w in t.casefold() for w in words)]}}
        titles = params["titles"].split("|")
        pages, redirects = [], []
        for title in titles:
            target = self.redirects.get(title, title)
            if target != title:
                redirects.append({"from": title, "to": target})
            pages.append(self.pages.get(target) or {"title": target, "missing": True})
        return {"query": {"pages": pages, "redirects": redirects}}


@pytest.fixture()
def source():
    return next(s for s in wl.load_wikipedia_list_sources() if s.key == "documentary_heritage_viwiki")


def _run(tmp_path, fake, source_html=None):
    raw = tmp_path / "raw"
    raw.mkdir()
    base = {"registry_id": "registry-aaaaaaaaaaaa", "registry_category": "world_heritage", "label_vi": "X",
            "registry_url": "https://dsvh.gov.vn/x-1", "source_status": "registry_only",
            "coverage_snapshot": "20260925T034421Z", "retrieved_at": "2026-09-25T03:44:21Z", "registry_fields": {}}
    (raw / "registry_records.jsonl").write_text(json.dumps(base, ensure_ascii=False) + "\n", encoding="utf-8")
    (raw / "pages.jsonl").write_text(json.dumps({"page_id": 1, "title": "X", "registry_ids": ["registry-aaaaaaaaaaaa"]}) + "\n",
                                     encoding="utf-8")
    summary = wl.collect_wikipedia_lists(raw_dir=raw, fetcher=fake, retrieved_at="2026-10-04T00:00:00Z")
    records = [json.loads(l) for l in (raw / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()]
    pages = [json.loads(l) for l in (raw / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    return raw, summary, records, pages


def test_documentary_list_keeps_only_recognized_and_merges_levels(tmp_path):
    raw, summary, records, pages = _run(tmp_path, FakeWiki(SECTION_HTML_LISTS))
    docs = [r for r in records if r["registry_category"] == "documentary_heritage"]
    labels = [r["label_vi"] for r in docs]
    assert labels == ["Mộc bản triều Nguyễn", "Bia Tiến sĩ tại Văn Miếu - Quốc Tử Giám", "Châu bản triều Nguyễn",
                      "Bộ sưu tập tài liệu của nhạc sĩ Hoàng Vân", "Mộc bản chùa Vĩnh Nghiêm", "Hoàng hoa sứ trình đồ"]
    chau_ban = docs[2]["registry_fields"]
    assert chau_ban["recognition_text"] == "2014 (Khu vực Châu Á - Thái Bình Dương); 2017 (Thế giới)"
    assert chau_ban["type"] == "Thế giới"
    assert docs[3]["registry_fields"]["recognition_text"] == "2025 (Thế giới)"   # bỏ năm sinh–mất của nhạc sĩ
    assert docs[0]["coverage_snapshot"] == "20260925T034421Z"           # giữ snapshot registry hiện có
    assert docs[0]["registry_url"].startswith("https://vi.wikipedia.org/wiki/Di_s%E1%BA%A3n")
    assert docs[0]["registry_fields"]["location"] == "Đà Lạt, Lâm Đồng"   # từ infobox bài Mộc bản
    excluded = [json.loads(l) for l in (raw / wl.EXCLUDED_FILE).read_text(encoding="utf-8").splitlines()]
    assert [e["reason"] for e in excluded] == ["NOT_RECOGNIZED"]
    assert records[0]["registry_id"] == "registry-aaaaaaaaaaaa" and pages[0]["title"] == "X"   # raw cũ giữ nguyên
    report = summary["sources"][0]
    assert report["mode"] == "sections" and report["sections"] == ["Việt Nam"]
    assert "Thơ văn trên kiến trúc cung đình Huế" in report["reference_missing"]


def test_hoang_van_override_is_related_subject_without_identity(tmp_path):
    _, _, records, pages = _run(tmp_path, FakeWiki(SECTION_HTML_LISTS))
    hv = next(r for r in records if "Hoàng Vân" in r["label_vi"])
    page = next(p for p in pages if p["title"] == "Hoàng Vân (nhạc sĩ)")
    assert hv["registry_fields"]["page_role"] == "related_subject"
    assert page["registry_ids"] == [hv["registry_id"]]
    assert page["wikidata_id"] is None and page["subject_wikidata_id"] == "Q999"
    record = map_record({**hv, "_entity_id": hv["registry_id"]}, TYPES, PageIndex(pages), derived=DerivedRegistry())
    assert "wikidata" not in record.get("external_ids", {})
    assert "description_vi" not in record
    assert record["source_title"] == "Hoàng Vân (nhạc sĩ)"
    assert record["provenance"] == {"source": hv["registry_url"], "method": "mediawiki-api", "license": "CC BY-SA 4.0"}
    assert record["aliases_vi"] == []


def test_list_record_without_article_uses_list_page_metadata(tmp_path):
    _, _, records, pages = _run(tmp_path, FakeWiki(SECTION_HTML_LISTS))
    red = next(r for r in records if r["label_vi"] == "Hoàng hoa sứ trình đồ")
    record = map_record({**red, "_entity_id": red["registry_id"]}, TYPES, PageIndex(pages))
    assert record["source_status"] == "registry+wikipedia"
    assert record["source_title"] == "Di sản tư liệu thế giới" and record["source_page_id"] > 0
    assert record["recognition_year"] == 2018


def test_documentary_table_with_rowspan_and_holder_area(tmp_path):
    _, _, records, pages = _run(tmp_path, FakeWiki(SECTION_HTML_TABLE))
    docs = {r["label_vi"]: r for r in records if r["registry_category"] == "documentary_heritage"}
    assert list(docs) == ["Mộc bản triều Nguyễn", "Bộ sưu tập tài liệu của nhạc sĩ Hoàng Vân",
                          "Thơ văn trên kiến trúc cung đình Huế"]
    assert docs["Bộ sưu tập tài liệu của nhạc sĩ Hoàng Vân"]["registry_fields"]["type"] == "Thế giới"   # rowspan
    assert docs["Thơ văn trên kiến trúc cung đình Huế"]["registry_fields"]["type"] == "Khu vực Châu Á - Thái Bình Dương"
    derived = DerivedRegistry()
    moc = docs["Mộc bản triều Nguyễn"]
    record = map_record({**moc, "_entity_id": moc["registry_id"]}, TYPES, PageIndex(pages), derived=derived)
    assert record["custodian"].startswith("Trung tâm Lưu trữ quốc gia IV")
    assert [a["label_vi"] for a in derived.records() if a["level"] == "tỉnh"] == ["Lâm Đồng"]
    assert record["external_ids"] == {"wikidata": "Q101"}


def test_holder_text_guard_for_person_name():
    resolver = default_resolver()
    assert [a.label for a in hl.text_areas("Bảo tàng Hồ Chí Minh", resolver)] == []
    assert [a.label for a in hl.text_areas("Bảo tàng Lịch sử thành phố Hồ Chí Minh", resolver)] == ["Thành phố Hồ Chí Minh"]
    assert [a.label for a in hl.text_areas("Bảo tàng tỉnh Bắc Ninh", resolver)] == ["Bắc Ninh"]


def test_resolve_holders_text_wikipedia_manual():
    resolver = default_resolver()
    holders = {hl.holder_key(h): {"holder": h, "categories": {"national_treasures"}, "count": 1} for h in [
        "Bảo tàng tỉnh Bắc Ninh", "Bảo tàng Lịch sử quốc gia", "Bảo tàng Hồ Chí Minh", "Bảo tàng Quân khu 7",
        "Bảo tàng Hải quân", "Bảo tàng Mơ hồ", "Bảo tàng Không có bài"]}
    manual = hl.load_manual()
    rows = {r["holder"]: r for r in hl.resolve_holders(holders, resolver, FakeWiki(""), "x", {}, manual,
                                                         retrieved_at="2026-10-04T00:00:00Z")}
    assert rows["Bảo tàng tỉnh Bắc Ninh"]["method"] == "registry_text"
    assert rows["Bảo tàng Lịch sử quốc gia"]["area_labels"] == ["Hà Nội"]
    assert rows["Bảo tàng Lịch sử quốc gia"]["method"].startswith("wikipedia:infobox")
    assert rows["Bảo tàng Hồ Chí Minh"]["area_labels"] == ["Hà Nội"]
    assert rows["Bảo tàng Quân khu 7"]["area_labels"] == ["Thành phố Hồ Chí Minh"]
    assert rows["Bảo tàng Hải quân"]["wikipedia_title"] == "Bảo tàng Hải quân (Việt Nam)"
    assert rows["Bảo tàng Hải quân"]["area_labels"] == ["Hải Phòng"]
    assert rows["Bảo tàng Mơ hồ"]["area_labels"] == [] and rows["Bảo tàng Mơ hồ"]["wikipedia_reason"].startswith("ambiguous")
    assert rows["Bảo tàng Không có bài"]["method"] == "unresolved"


def test_mapper_treasure_located_in_from_holder_index():
    resolver = default_resolver()
    entity = {"_entity_id": "registry-b54471e322bd", "registry_id": "registry-b54471e322bd",
              "registry_category": "national_treasures", "label_vi": "Trống đồng Ngọc Lũ",
              "registry_url": "https://dsvh.gov.vn/bao-vat-quoc-gia-1758", "coverage_snapshot": "s",
              "retrieved_at": "2026-09-25T03:44:21Z", "source_status": "registry_only",
              "registry_fields": {"label_vi": "Trống đồng Ngọc Lũ", "location": "Bảo tàng Lịch sử quốc gia"}}
    derived = DerivedRegistry()
    index = {hl.holder_key("Bảo tàng Lịch sử quốc gia"): ["Hà Nội"]}
    record = map_record(entity, TYPES, derived=derived, area_resolver=resolver, holder_index=index)
    assert record["current_holder"] == "Bảo tàng Lịch sử quốc gia" and "address" not in record
    areas = [a for a in derived.records() if a["level"] not in ("miền", "quốc gia")]
    assert [a["label_vi"] for a in areas] == ["Hà Nội"]
    assert record["relations"]["located_in"] == [areas[0]["entity_id"]]
    # Nơi lưu giữ ghi tỉnh cũ -> công bố theo tỉnh sau sắp xếp 2025.
    entity["registry_fields"]["location"] = "Bảo tàng tỉnh Bạc Liêu"
    derived = DerivedRegistry()
    map_record(entity, TYPES, derived=derived, area_resolver=resolver, holder_index=index)
    assert [a["label_vi"] for a in derived.records() if a["level"] == "tỉnh"] == ["Cà Mau"]


def test_real_manual_holder_config_uses_known_areas():
    resolver = default_resolver()
    labels = {a.label for a in resolver.areas}
    manual = hl.load_manual()
    assert manual and all(item["area"] in labels for item in manual.values())
