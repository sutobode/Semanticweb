"""Chính sách bằng chứng cho di sản phi vật thể (``matching.intangible_evidence``, review Kaggle 2026-09-24).

Chạy toàn bộ 860 record thật trên MediaWiki giả lập ``tests/fixtures/fake_viwiki.py``. Các bài giả lập
mô phỏng đúng những trường hợp bị loại oan ở lần chạy Kaggle (xem ``m2_wiki_unmatched.json``) và các bẫy
tương ứng; kết quả thật vẫn phụ thuộc nội dung bài trên vi.wikipedia.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from vietheritage.collector import wikipedia as wiki
from vietheritage.normalization.areas import AreaResolver

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "registry_records.jsonl"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    if not RAW.exists():
        pytest.skip("registry snapshot not present")
    spec = importlib.util.spec_from_file_location("fake_viwiki", ROOT / "tests" / "fixtures" / "fake_viwiki.py")
    fake_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fake_module)
    records = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = tmp_path_factory.mktemp("wiki")
    items = [{"registry_id": r["registry_id"], "label_vi": r["label_vi"], "registry_category": r["registry_category"],
              "location": (r.get("registry_fields") or {}).get("location")} for r in records]
    wiki.enrich_many(items, fetcher=fake_module.FakeWiki(), output_dir=out, sleeper=lambda _s: None)
    pages = [json.loads(l) for l in (out / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    failures = [json.loads(l) for l in (out / "enrichment_failures.jsonl").read_text(encoding="utf-8").splitlines()]
    links: dict[str, set[str]] = {}
    for page in pages:
        for link in page["registry_links"]:
            links.setdefault(link["label_vi"], set()).add(page["title"])
    reasons: dict[str, list[str]] = {}
    for failure in failures:
        reasons.setdefault(failure["label_vi"], []).append(failure["reason"])
    counts: dict[str, int] = {}
    for page in pages:
        counts[page["title"]] = len(page["registry_ids"])
    return {"pages": pages, "links": links, "reasons": reasons, "counts": counts}


RECOVERED = {
    "Nghệ thuật Xòe Thái": "Xòe Thái",                          # chỉ bỏ "Nghệ thuật" -> không cần bằng chứng tỉnh
    "Nghệ thuật Bài Chòi": "Bài chòi",
    "Nghệ thuật múa rối nước": "Múa rối nước",                  # cùng di sản với record "Múa rối nước" (bỏ "Nghệ thuật")
    "Nghệ thuật Đờn ca tài tử Nam bộ": "Đờn ca tài tử Nam Bộ",  # bỏ "Nam bộ" -> page nhắc "Nam Bộ" (bằng chứng vùng)
    "Đờn ca Tài tử Nam Bộ": "Đờn ca tài tử Nam Bộ",            # page nhắc >= 2 nhóm tỉnh khác -> không xung đột
    "Lễ hội Nghinh Ông": "Lễ hội nghinh Ông",
    "Hát Sli của người Nùng": "Hát sli",                        # bằng chứng dân tộc "người Nùng"
    "Mo Mường ở Hòa Bình": "Mo Mường",                          # cùng di sản sau khi bỏ địa danh -> không "mơ hồ"
    "Mo Mường (Hà Nội)": "Mo Mường",
    "Mo Mường": "Mo Mường",
    "Nghi lễ Then của người Tày": "Nghi lễ Then",               # override
    "Nghi lễ Then của người Tày, người Nùng": "Nghi lễ Then",   # override
    "Hát Ca trù": "Ca trù",                                     # trực tiếp thắng "Hát nhà tơ" (redirect)
}


@pytest.mark.parametrize("label, title", sorted(RECOVERED.items()))
def test_intangible_records_recovered(run, label, title):
    assert run["links"].get(label) == {title}, run["reasons"].get(label)


def test_all_province_inscriptions_share_the_practice_page(run):
    assert run["counts"]["Xòe Thái"] == 4 and run["counts"]["Lễ hội nghinh Ông"] == 4
    assert run["counts"]["Mo Mường"] == 5


REJECTED = {
    "Dân ca của người Bố Y": "without ethnic evidence",         # bài "Dân ca" chung chung
    "Nghề rèn của người Nùng An": "without ethnic evidence",
    "Lễ hội Cầu mùa của người Sán Chay": "without ethnic evidence",  # bài của người Dao
    "Nghi lễ Then của người Giáy": "without ethnic evidence",
    "Dân ca Cao Lan": "ambiguous shared page",
    "Dân ca Sán Chí": "ambiguous shared page",
    "Hát Sình ca của người Cao Lan": "ambiguous shared page",  # 2 nhãn khác nhau redirect thẳng vào "Sình ca"
    "Hát nhà tơ (Hát cửa đình)": "ambiguous shared page",
    "Lễ Cấp sắc của người Tày": "ambiguous shared page",       # nhiều dân tộc khác nhau -> bài khái niệm chung
}


@pytest.mark.parametrize("label, reason", sorted(REJECTED.items()))
def test_intangible_traps_rejected(run, label, reason):
    assert label not in run["links"]
    assert any(reason in r for r in run["reasons"][label]), run["reasons"][label]


def test_generic_pages_never_linked(run):
    linked = {t for titles in run["links"].values() for t in titles}
    assert not linked & {"Dân ca", "Rèn", "Lễ hội Cầu mùa (người Dao)", "Cao Lan", "Lễ cấp sắc"}


def test_ethnic_names_parsing():
    assert wiki.ethnic_names("Kéo co của người Tày, người Giáy") == ["Tày", "Giáy"]
    assert wiki.ethnic_names("Lễ Cấp sắc (Tủ cải) của người Dao Quần chẹt") == ["Dao Quần chẹt"]
    assert wiki.ethnic_names("Hát ru của người Việt ở Cần Thơ") == ["Việt"]
    assert wiki.ethnic_names("Nghệ thuật Xòe Thái") == []


def test_site_categories_keep_strict_province_rules():
    """Di tích không đổi: alias vẫn bắt buộc bằng chứng tỉnh, xung đột tỉnh vẫn loại."""
    cfg = wiki.load_config()
    page = {"pageid": 9, "title": "Chùa Keo", "categories": [{"title": "Thể loại:Chùa tại Thái Bình"}],
            "extract": "Chùa ở Thái Bình và có bản sao ở Hà Nội.", "revisions": []}
    target = {"registry_id": "r", "label_vi": "DTKTNT Chùa Keo", "location": "Tỉnh Nam Định",
              "registry_category": "national_special_monuments"}
    pages, failures = wiki.match_registry_labels_to_pages([target], {"query": {"pages": [page]}}, "t", cfg,
                                                          AreaResolver.from_config())
    assert pages == [] and "province conflict" in failures[0]["reason"]


def test_api_client_caches_responses(tmp_path):
    calls = []

    def fetch(url, params, cfg, session=None):
        calls.append(params)
        return {"ok": len(calls)}

    client = wiki.ApiClient(cache_dir=tmp_path, log_progress=False, fetch=fetch)
    first = client("https://x/api.php", {"action": "query", "titles": "A|B"}, {})
    again = client("https://x/api.php", {"titles": "A|B", "action": "query"}, {})   # thứ tự khóa không quan trọng
    other = client("https://x/api.php", {"action": "query", "titles": "C"}, {})
    assert first == again == {"ok": 1} and other == {"ok": 2} and len(calls) == 2
    assert client.summary()["cache_hits"] == 1 and client.summary()["http_requests"] == 2
    fresh = wiki.ApiClient(cache_dir=tmp_path, log_progress=False, fetch=fetch)       # lần chạy sau
    assert fresh("https://x/api.php", {"action": "query", "titles": "C"}, {}) == {"ok": 2} and len(calls) == 2


def test_user_agent_contact(monkeypatch):
    monkeypatch.setenv("VIETHERITAGE_CONTACT", "m2@example.com")
    assert wiki.user_agent({"user_agent": "Tool/1.0 (capstone)"}) == "Tool/1.0 (capstone; m2@example.com)"
    monkeypatch.delenv("VIETHERITAGE_CONTACT")
    assert wiki.user_agent({"user_agent": "Tool/1.0 (capstone)"}) == "Tool/1.0 (capstone)"
