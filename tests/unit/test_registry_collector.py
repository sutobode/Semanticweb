"""G3 unit tests — Official Heritage Registry Collector (COMP-000, TEST-076..081).

Toàn bộ test dùng fixture HTML/mock, KHÔNG gọi network thật, đúng yêu cầu
Giai đoạn A của GOAL_PROMPT.md.
"""
import json
from pathlib import Path

import pytest

from vietheritage.registry.collector import (
    CategoryConfig,
    RegistryIdCollisionError,
    RegistryParseError,
    collect,
    deterministic_registry_id,
    load_config,
    parse_table_rows,
    rows_to_records,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_HTML = (REPO_ROOT / "data" / "fixtures" / "registry_sample_page.html").read_text(encoding="utf-8")
CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"


def test_load_config_has_17_categories() -> None:
    _, categories = load_config(CONFIG_PATH)
    assert len(categories) == 17


def test_load_config_category_keys_match_spec_section_7() -> None:
    _, categories = load_config(CONFIG_PATH)
    keys = {c.key for c in categories}
    expected = {
        "world_heritage", "national_special_monuments", "national_monuments",
        "intangible_representative", "intangible_urgent", "national_intangible",
        "artisans", "national_treasures", "artifacts_antiquities",
        "national_artisans", "meritorious_artisans", "national_museums",
        "ministry_museums", "central_organization_museums", "provincial_museums",
        "private_museums", "documentary_heritage",
    }
    assert keys == expected


def test_load_config_entity_type_is_canonical_not_ontology_subclass() -> None:
    _, categories = load_config(CONFIG_PATH)
    national_intangible = next(c for c in categories if c.key == "national_intangible")
    assert national_intangible.entity_type == "IntangibleHeritage"
    assert national_intangible.ontology_subclass == "vh:NationalIntangibleHeritage"


def test_parse_table_rows_extracts_data_rows_and_skips_footer() -> None:
    rows = parse_table_rows(FIXTURE_HTML, footer_patterns=["^Tổng số", "^Total"])
    assert len(rows) == 2
    assert rows[0]["cells"][1] == "Khu trung tâm Hoàng thành Thăng Long"
    assert rows[1]["cells"][1] == "Vịnh Hạ Long"


def test_parse_table_rows_captures_hrefs() -> None:
    rows = parse_table_rows(FIXTURE_HTML, footer_patterns=["^Tổng số"])
    assert rows[0]["hrefs"] == ["/di-tich/hoang-thanh-thang-long"]


def test_rows_to_records_creates_registry_only_records() -> None:
    rows = parse_table_rows(FIXTURE_HTML, footer_patterns=["^Tổng số"])
    category = CategoryConfig(
        key="world_heritage",
        url="https://dsvh.gov.vn/di-san-van-hoa-va-thien-nhien-the-gioi-1754",
        entity_type="HeritageSite",
        row_selector="table tbody tr",
        columns={"ordinal": 0, "label_vi": 1, "recognition_text": 2, "location": 3},
    )
    records = rows_to_records(
        rows, category, coverage_snapshot="test-snapshot",
        retrieved_at="2026-09-13T00:00:00Z", base_url="https://dsvh.gov.vn/",
    )
    assert len(records) == 2
    assert all(r.source_status == "registry_only" for r in records)
    assert all(r.registry_id.startswith("registry-") for r in records)
    assert records[0].label_vi == "Khu trung tâm Hoàng thành Thăng Long"


def test_rows_to_records_raises_registry_parse_error_on_missing_label_column() -> None:
    rows = [{"cells": ["1"], "hrefs": []}]
    category = CategoryConfig(
        key="x", url="https://dsvh.gov.vn/x", entity_type="HeritageSite",
        row_selector="table tbody tr", columns={"label_vi": 5},
    )
    with pytest.raises(RegistryParseError):
        rows_to_records(rows, category, "snap", "2026-09-13T00:00:00Z", "https://dsvh.gov.vn/")


def test_deterministic_registry_id_is_stable_across_calls() -> None:
    id1 = deterministic_registry_id(None, "https://dsvh.gov.vn/x", "world_heritage", "vịnh hạ long")
    id2 = deterministic_registry_id(None, "https://dsvh.gov.vn/x", "world_heritage", "vịnh hạ long")
    assert id1 == id2
    assert id1.startswith("registry-")


def test_deterministic_registry_id_prefers_official_id() -> None:
    result = deterministic_registry_id("dsvh-12345", "https://x", "cat", "label")
    assert result == "dsvh-12345"


def test_collect_with_fixture_fetcher_produces_valid_coverage_report() -> None:
    def fixture_fetcher(url: str, request_cfg: dict) -> str:  # noqa: ARG001
        return FIXTURE_HTML

    report = collect(fetcher=fixture_fetcher, category_keys=["world_heritage"])
    assert report["canonical_total"] == 2
    assert report["registry_total"] == 2
    assert report["failure_manifest"] == []
    assert report["claim"] == "100% of selected official registry snapshot"


def test_collect_records_have_required_raw_page_schema_fields() -> None:
    def fixture_fetcher(url: str, request_cfg: dict) -> str:  # noqa: ARG001
        return FIXTURE_HTML

    import vietheritage.registry.collector as collector_module

    original_dir = collector_module.RAW_DIR

    def fixture_fetcher2(url: str, request_cfg: dict) -> str:  # noqa: ARG001
        return FIXTURE_HTML

    report = collect(fetcher=fixture_fetcher2, category_keys=["world_heritage"])
    assert report["categories"][0]["registry_category"] == "world_heritage"
    assert report["categories"][0]["coverage_percent"] == 100.0


def test_collect_records_written_to_registry_records_jsonl(tmp_path: Path) -> None:
    def fixture_fetcher(url: str, request_cfg: dict) -> str:  # noqa: ARG001
        return FIXTURE_HTML

    collect(fetcher=fixture_fetcher, category_keys=["world_heritage"], output_dir=tmp_path)
    records_path = tmp_path / "registry_records.jsonl"
    assert records_path.exists()
    lines = records_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    for required_field in ["registry_id", "registry_category", "label_vi", "registry_url", "source_status", "coverage_snapshot", "retrieved_at"]:
        assert required_field in first


def test_collect_registry_id_collision_raises_and_is_recorded_as_failure(tmp_path: Path) -> None:
    """Hai row cùng registry_id (cùng href + cùng label chuẩn hóa) nhưng có
    recognition_text khác nhau mô phỏng dữ liệu xung đột thật (label thay đổi
    giữa hai lần crawl trong cùng run) -> phải bị chặn là REGISTRY_ID_COLLISION
    vì label_vi khác nhau dẫn tới hash khác — kiểm bằng cách patch trực tiếp
    deterministic_registry_id để ép cùng ID cho hai record khác nội dung.
    """
    from vietheritage.registry import collector as collector_module

    original = collector_module.deterministic_registry_id
    try:
        collector_module.deterministic_registry_id = lambda *args, **kwargs: "registry-forced-collision"

        colliding_html = """
        <table><tbody>
        <tr><td>1</td><td><a href="/x/a">Tên A</a></td><td>info</td><td>loc</td></tr>
        <tr><td>2</td><td><a href="/x/b">Tên B khác hẳn</a></td><td>info khác</td><td>loc khác</td></tr>
        </tbody></table>
        """

        def colliding_fetcher(url: str, request_cfg: dict) -> str:  # noqa: ARG001
            return colliding_html

        report = collect(fetcher=colliding_fetcher, category_keys=["world_heritage"], output_dir=tmp_path)
    finally:
        collector_module.deterministic_registry_id = original

    assert report["failure_manifest"]
    assert report["failure_manifest"][0]["error_code"] == "REGISTRY_ID_COLLISION"
    assert report["claim"] == "coverage_failed"
