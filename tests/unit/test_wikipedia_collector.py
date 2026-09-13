"""G3 unit tests — Vietnamese Wikipedia Enrichment Collector (COMP-001, TEST-001..004).

Toàn bộ test dùng mock MediaWiki API JSON response, KHÔNG gọi network thật.
"""
import json
from pathlib import Path

import pytest

from vietheritage.collector.wikipedia import (
    build_query_params,
    enrich,
    enrich_many,
    load_config,
    match_registry_labels_to_pages,
    normalize_title,
    page_from_api_response,
    parse_first_infobox,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "collector.yaml"


def test_load_config_has_correct_api_url() -> None:
    cfg = load_config(CONFIG_PATH)
    assert cfg["api_url"] == "https://vi.wikipedia.org/w/api.php"


def test_load_config_matching_disallows_fuzzy() -> None:
    cfg = load_config(CONFIG_PATH)
    assert cfg["matching"]["allow_fuzzy"] is False


def test_build_query_params_uses_action_query_and_formatversion_2() -> None:
    cfg = load_config(CONFIG_PATH)
    params = build_query_params(["Văn Miếu"], cfg["query"])
    assert params["action"] == "query"
    assert params["format"] == "json"
    assert params["formatversion"] == 2
    assert "pageprops" in params["prop"]
    assert "revisions" in params["prop"]


def test_normalize_title_is_case_and_whitespace_insensitive() -> None:
    assert normalize_title("  Văn   Miếu  ") == normalize_title("văn miếu")


def test_parse_first_infobox_extracts_key_value_pairs() -> None:
    wikitext = (
        "{{Infobox di tích\n"
        "| ten = Văn Miếu\n"
        "| dia_diem = Hà Nội\n"
        "| nam_xay = 1070\n"
        "}}\n"
        "'''Văn Miếu''' là một di tích."
    )
    infobox = parse_first_infobox(wikitext)
    assert infobox["ten"] == "Văn Miếu"
    assert infobox["dia_diem"] == "Hà Nội"
    assert infobox["nam_xay"] == "1070"


def test_parse_first_infobox_returns_empty_dict_when_no_template() -> None:
    assert parse_first_infobox("Không có template nào ở đây.") == {}


def test_page_from_api_response_extracts_all_fields() -> None:
    page_json = {
        "pageid": 12345,
        "title": "Văn Miếu – Quốc Tử Giám",
        "pageprops": {"wikibase_item": "Q123456"},
        "coordinates": [{"lat": 21.0278, "lon": 105.8355}],
        "categories": [{"title": "Category:Di tích lịch sử"}],
        "links": [{"title": "Hà Nội"}],
        "extract": "Văn Miếu là quần thể di tích.",
        "revisions": [
            {
                "revid": 999,
                "slots": {"main": {"content": "{{Infobox\n|ten=X\n}}"}},
            }
        ],
    }
    page = page_from_api_response(page_json, "2026-09-13T00:00:00Z")
    assert page is not None
    assert page.page_id == 12345
    assert page.wikidata_id == "Q123456"
    assert page.coordinates == {"lat": 21.0278, "lon": 105.8355}
    assert page.categories == ["Category:Di tích lịch sử"]
    assert page.revision_id == 999
    assert page.infobox == {"ten": "X"}


def test_page_from_api_response_returns_none_when_missing() -> None:
    assert page_from_api_response({"missing": True, "title": "X"}, "2026-09-13T00:00:00Z") is None


def test_match_registry_labels_exact_normalized_title() -> None:
    api_response = {
        "query": {
            "pages": [
                {"pageid": 1, "title": "Văn Miếu – Quốc Tử Giám", "revisions": []},
            ]
        }
    }
    pages, failures = match_registry_labels_to_pages(
        ["Văn Miếu – Quốc Tử Giám"], api_response, "2026-09-13T00:00:00Z"
    )
    assert len(pages) == 1
    assert not failures


def test_match_registry_labels_missing_match_keeps_registry_only() -> None:
    """Không tìm được match -> ENRICHMENT_MISSING, KHÔNG raise, registry entity
    vẫn giữ được (chỉ mất enrichment, không mất record).
    """
    api_response = {"query": {"pages": [{"missing": True, "title": "Không Tồn Tại"}]}}
    pages, failures = match_registry_labels_to_pages(
        ["Không Tồn Tại"], api_response, "2026-09-13T00:00:00Z"
    )
    assert pages == []
    assert len(failures) == 1
    assert failures[0]["error_code"] == "ENRICHMENT_MISSING"


def test_match_registry_labels_deduplicates_by_page_id() -> None:
    api_response = {
        "query": {
            "pages": [
                {"pageid": 1, "title": "Alias A", "revisions": []},
                {"pageid": 1, "title": "Alias A", "revisions": []},
            ]
        }
    }
    pages, _ = match_registry_labels_to_pages(["Alias A", "Alias A"], api_response, "2026-09-13T00:00:00Z")
    assert len(pages) == 1


def test_enrich_writes_pages_and_failures_jsonl(tmp_path: Path) -> None:
    def mock_fetcher(api_url: str, params: dict, request_cfg: dict) -> dict:  # noqa: ARG001
        return {
            "query": {
                "pages": [
                    {"pageid": 1, "title": "Văn Miếu", "revisions": []},
                    {"missing": True, "title": "Không rõ"},
                ]
            }
        }

    result = enrich(["Văn Miếu", "Không rõ"], fetcher=mock_fetcher, output_dir=tmp_path)
    assert result["matched"] == 1
    assert result["missing"] == 1
    pages_path = tmp_path / "pages.jsonl"
    failures_path = tmp_path / "enrichment_failures.jsonl"
    assert pages_path.exists()
    assert failures_path.exists()
    page_record = json.loads(pages_path.read_text(encoding="utf-8").strip())
    for required_field in ["page_id", "title", "source_url", "retrieved_at"]:
        assert required_field in page_record



def test_enrich_many_batches_titles_and_reports_qids(tmp_path: Path) -> None:
    calls: list[int] = []

    def mock_fetcher(api_url: str, params: dict, request_cfg: dict) -> dict:  # noqa: ARG001
        titles = params["titles"].split("|")
        calls.append(len(titles))
        return {"query": {"pages": [
            {"pageid": len(calls), "title": titles[0], "pageprops": {"wikibase_item": "Q1"}, "revisions": []}
        ]}}

    result = enrich_many(["A", "B", "C"], fetcher=mock_fetcher, output_dir=tmp_path, chunk_size=2)
    assert calls == [2, 1]
    assert result["matched"] == 2
    assert result["wikidata_linked"] == 2



def test_build_query_params_follows_redirects() -> None:
    cfg = load_config(CONFIG_PATH)
    assert build_query_params(["Tranh dân gian Đông Hồ"], cfg["query"])["redirects"] == 1


def test_match_registry_labels_resolves_redirect_target_qid() -> None:
    api_response = {
        "query": {
            "redirects": [{"from": "Alias di sản", "to": "Trang đích"}],
            "pages": [{
                "pageid": 99,
                "title": "Trang đích",
                "pageprops": {"wikibase_item": "Q999"},
                "revisions": [],
            }],
        }
    }
    pages, failures = match_registry_labels_to_pages(
        ["Alias di sản"], api_response, "2026-09-13T00:00:00Z"
    )
    assert not failures
    assert pages[0].title == "Alias di sản"
    assert pages[0].page_id == 99
    assert pages[0].wikidata_id == "Q999"
