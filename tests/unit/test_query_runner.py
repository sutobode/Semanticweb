import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vietheritage.reporting.query_runner import (
    CQ_CONTRACT,
    EXPECTED_DIR,
    QUERY_DIR,
    run,
)


def test_cq_runner_requires_exactly_ten_queries(tmp_path: Path) -> None:
    (tmp_path / "CQ01.rq").write_text("SELECT * WHERE {}", encoding="utf-8")
    assert run(query_dir=tmp_path, expected_dir=tmp_path, reports_dir=tmp_path) == 1


@pytest.fixture
def cq_run(tmp_path: Path):
    query_dir = tmp_path / "queries"
    expected_dir = tmp_path / "expected"
    reports_dir = tmp_path / "reports"
    query_dir.mkdir()
    expected_dir.mkdir()
    responses = {}
    for name in CQ_CONTRACT:
        (query_dir / name).write_text((QUERY_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
        expected_name = name[:4] + ".json"
        text = (EXPECTED_DIR / expected_name).read_text(encoding="utf-8")
        (expected_dir / expected_name).write_text(text, encoding="utf-8")
        responses[name[:4]] = json.loads(text)

    def mock_get(url, **kwargs):
        name = next(name for name in CQ_CONTRACT
                    if (query_dir / name).read_text(encoding="utf-8") == kwargs["params"]["query"])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: responses[name[:4]])

    def execute():
        code = run(request_get=mock_get, query_dir=query_dir, expected_dir=expected_dir, reports_dir=reports_dir)
        report = next(reports_dir.glob("*/cq_results.json"))
        return code, json.loads(report.read_text(encoding="utf-8"))

    return query_dir, expected_dir, responses, execute


def test_cq_runner_enforces_ten_expectations_and_ignores_demo(cq_run) -> None:
    query_dir, _, _, execute = cq_run
    (query_dir / "CQ10-federated-demo.rq").write_text("INVALID demo query", encoding="utf-8")
    code, report = execute()
    assert code == 0
    assert report["passed"] == report["total"] == 10
    assert [item["query"] for item in report["queries"]] == list(CQ_CONTRACT)
    assert all(item["expected_checked"] and item["row_count"] > 0 for item in report["queries"])
    assert all(len(item["sha256"]) == 64 for item in report["queries"])


@pytest.mark.parametrize(("case", "error"), [
    ("missing-expected", "CQ_EXPECTED_MISSING"),
    ("empty-result", "CQ_EXPECTED_MISMATCH"),
    ("wrong-variables", "CQ_VARIABLES_MISMATCH"),
    ("missing-variables", "CQ_VARIABLES_MISMATCH"),
    ("extra-variables", "CQ_VARIABLES_MISMATCH"),
    ("wrong-binding", "CQ_EXPECTED_MISMATCH"),
    ("missing-binding-variable", "CQ_BINDINGS_INVALID"),
    ("extra-binding-variable", "CQ_BINDINGS_INVALID"),
    ("wrong-language", "CQ_EXPECTED_MISMATCH"),
    ("wrong-term-type", "CQ_EXPECTED_MISMATCH"),
    ("wrong-order", "CQ_EXPECTED_MISMATCH"),
    ("duplicate-binding", "CQ_EXPECTED_MISMATCH"),
    ("empty-expected", "CQ_EXPECTED_EMPTY"),
    ("wrong-expected-variables", "CQ_VARIABLES_MISMATCH"),
    ("missing-results", "CQ_BINDINGS_INVALID"),
])
def test_cq_runner_rejects_false_success(cq_run, case, error) -> None:
    _, expected_dir, responses, execute = cq_run
    expected_path = expected_dir / "CQ01.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = responses["CQ01"]
    bindings = actual["results"]["bindings"]
    if case == "missing-expected":
        expected_path.unlink()
    elif case == "empty-result":
        bindings.clear()
    elif case == "wrong-variables":
        actual["head"]["vars"][0] = "entity"
    elif case == "missing-variables":
        actual["head"]["vars"].pop()
    elif case == "extra-variables":
        actual["head"]["vars"].append("extra")
    elif case == "wrong-binding":
        bindings[0]["site"]["value"] += "-wrong"
    elif case == "missing-binding-variable":
        bindings[0].pop("site")
    elif case == "extra-binding-variable":
        bindings[0]["extra"] = bindings[0]["site"]
    elif case == "wrong-language":
        bindings[0]["label"]["xml:lang"] = "en"
    elif case == "wrong-term-type":
        bindings[0]["site"]["type"] = "literal"
    elif case == "wrong-order":
        bindings.reverse()
    elif case == "duplicate-binding":
        bindings.append(bindings[0])
    elif case == "empty-expected":
        expected["results"]["bindings"].clear()
        bindings.clear()  # Even matching empty/empty must not turn the gate green.
    elif case == "wrong-expected-variables":
        expected["head"]["vars"] = actual["head"]["vars"] = ["entity", "label"]
    elif case == "missing-results":
        actual.pop("results")
    if case != "missing-expected":
        expected_path.write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")

    code, report = execute()
    assert code == 1
    assert report["passed"] == 9
    assert report["queries"][0]["status"] == "FAIL"
    assert report["queries"][0]["error"] == error


@pytest.mark.parametrize("text", ["INVALID SPARQL", "SELECT ?wrong WHERE { BIND(1 AS ?wrong) }"])
def test_cq_runner_checks_query_syntax_and_projection_before_request(cq_run, text) -> None:
    query_dir, _, _, execute = cq_run
    (query_dir / "CQ01-sites-by-location.rq").write_text(text, encoding="utf-8")
    code, report = execute()
    assert code == 1
    assert report["passed"] == 9
    assert report["queries"][0]["status"] == "FAIL"
    assert not report["queries"][0]["expected_checked"]


def test_cq_runner_compares_sets_only_without_order_by(cq_run) -> None:
    query_dir, _, responses, execute = cq_run
    path = query_dir / "CQ01-sites-by-location.rq"
    path.write_text(path.read_text(encoding="utf-8").replace("ORDER BY ?label", ""), encoding="utf-8")
    responses["CQ01"]["results"]["bindings"].reverse()
    code, report = execute()
    assert code == 0
    assert report["passed"] == 10
