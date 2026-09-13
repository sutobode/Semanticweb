import json
from pathlib import Path

from vietheritage.reporting.query_runner import run


def test_cq_runner_requires_exactly_ten_queries(tmp_path: Path) -> None:
    (tmp_path / "CQ01.rq").write_text("SELECT * WHERE {}", encoding="utf-8")
    assert run(query_dir=tmp_path, expected_dir=tmp_path, reports_dir=tmp_path) == 1


def test_cq_runner_executes_ten_queries_and_writes_report(tmp_path: Path) -> None:
    query_dir = tmp_path / "queries"
    query_dir.mkdir()
    for i in range(1, 11):
        (query_dir / f"CQ{i:02d}.rq").write_text(f"SELECT * WHERE {{ BIND({i} AS ?n) }}", encoding="utf-8")

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"results": {"bindings": []}}

    def mock_get(url, **kwargs):  # noqa: ARG001
        return Response()

    report_root = tmp_path / "reports"
    assert run(request_get=mock_get, query_dir=query_dir, expected_dir=tmp_path / "expected", reports_dir=report_root) == 0
    report = next(report_root.glob("*/cq_results.json"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] == 10
    assert all(len(item["sha256"]) == 64 for item in payload["queries"])
