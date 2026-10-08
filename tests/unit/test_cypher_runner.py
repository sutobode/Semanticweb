from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from vietheritage.lpg import cypher_runner
from vietheritage.lpg.cypher_runner import (
    CQ_CONTRACT,
    _entity_ids,
    _normalize_rows,
    _normalize_value,
    _sparql_entity_ids,
)


ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def consume(self) -> Any:
        return None

    def data(self) -> list[dict[str, Any]]:
        return self._rows


class _Transaction:
    def __init__(self, rows_by_query: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_query = rows_by_query
        self.rolled_back = False

    def run(self, query: str, **params: Any) -> _Result:
        return _Result(self.rows_by_query.get(query, []))

    def rollback(self) -> None:
        self.rolled_back = True


class _Session:
    def __init__(self, transaction: _Transaction) -> None:
        self.transaction = transaction

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def run(self, query: str, **params: Any) -> _Result:
        return _Result()

    def begin_transaction(self) -> _Transaction:
        return self.transaction


class _Driver:
    def __init__(self, transaction: _Transaction) -> None:
        self.transaction = transaction

    def __enter__(self) -> _Driver:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def session(self, **kwargs: Any) -> _Session:
        return _Session(self.transaction)


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_normalize_float_preserves_coordinate_precision() -> None:
    assert _normalize_value(21.3682242) == "21.3682242"
    assert _normalize_value(105.3214424) == "105.3214424"


def test_normalize_decimal_lexical_form_is_stable() -> None:
    assert _normalize_value({"value": "20.9000"}) == "20.9"
    assert _normalize_value(Decimal("105.32144240")) == "105.3214424"


def test_entity_and_row_normalization_is_order_independent() -> None:
    rows = [{"entityId": "site-b"}, {"entityId": "site-a"}, {"entityId": "site-a"}]
    assert _entity_ids(rows) == ["site-a", "site-b"]
    assert _normalize_rows([{"site": "site-a"}, {"site": "site-b"}], {}) == _normalize_rows(
        [{"site": "site-b"}, {"site": "site-a"}], {}
    )


def test_exact_query_and_expected_file_contract() -> None:
    query_names = sorted(path.name for path in (ROOT / "cypher").glob("CQ*.cypher"))
    assert query_names == sorted(CQ_CONTRACT)
    assert len(query_names) == 10
    for cq_id in (f"CQ{number:02d}" for number in range(1, 11)):
        assert (ROOT / "data" / "fixtures" / "expected" / f"cypher_{cq_id}.json").is_file()


def test_cypher_expected_ids_are_derived_from_sparql_fixture() -> None:
    expected_dir = ROOT / "data" / "fixtures" / "expected"
    for cypher_name, (_sparql_name, primary_variable) in CQ_CONTRACT.items():
        cq_id = cypher_name[:4]
        sparql_expected = json.loads((expected_dir / f"{cq_id}.json").read_text(encoding="utf-8"))
        cypher_expected = json.loads(
            (expected_dir / f"cypher_{cq_id}.json").read_text(encoding="utf-8")
        )
        assert sorted(cypher_expected) == _sparql_entity_ids(sparql_expected, primary_variable)


def test_queries_use_appendix_c_semantics() -> None:
    texts = {
        name[:4]: (ROOT / "cypher" / name).read_text(encoding="utf-8")
        for name in CQ_CONTRACT
    }
    assert "[:LOCATED_IN*1..]" in texts["CQ01"]
    assert "[:RECOGNIZED_BY]" in texts["CQ02"] and "organization-unesco" in texts["CQ02"]
    assert ":UNESCOHeritageSite" not in texts["CQ02"] and "recognitionYear < 2000" in texts["CQ02"]
    assert ":ArchaeologicalSite" in texts["CQ03"]
    assert "ASSOCIATED_WITH_PERSON|BUILT_BY" in texts["CQ04"]
    assert "ASSOCIATED_WITH_EVENT|BELONGS_TO_PERIOD" in texts["CQ05"]
    assert "count(DISTINCT site)" in texts["CQ06"]
    assert "ASSOCIATED_WITH_PERSON|BUILT_BY" in texts["CQ07"] and "siteCount > 1" in texts["CQ07"]
    assert "[:PART_OF*1..]" in texts["CQ08"]
    assert ":SAME_AS" in texts["CQ09"] and "site.uri <> external.uri" in texts["CQ09"]
    assert ":SAME_AS" in texts["CQ10"] and "external.labelEn" in texts["CQ10"]
    assert all("entityId AS entityId" in text for text in texts.values())
    assert all(":Entity" not in text and ".label AS" not in text for text in texts.values())


def test_runner_reports_ten_of_ten_acceptance_and_parity(
    monkeypatch: Any, tmp_path: Path
) -> None:
    expected_dir = ROOT / "data" / "fixtures" / "expected"
    rows_by_query: dict[str, list[dict[str, Any]]] = {}
    sparql_by_query: dict[str, dict[str, Any]] = {}
    for cypher_name, (sparql_name, primary_variable) in CQ_CONTRACT.items():
        cypher_text = (ROOT / "cypher" / cypher_name).read_text(encoding="utf-8")
        sparql_text = (ROOT / "sparql" / sparql_name).read_text(encoding="utf-8")
        sparql_payload = json.loads(
            (expected_dir / f"{cypher_name[:4]}.json").read_text(encoding="utf-8")
        )
        rows_by_query[cypher_text] = [
            {"entityId": _normalize_value(binding[primary_variable])}
            for binding in sparql_payload["results"]["bindings"]
        ]
        sparql_by_query[sparql_text] = sparql_payload

    transaction = _Transaction(rows_by_query)
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setattr(
        cypher_runner,
        "load_records",
        lambda *args, **kwargs: {"status": "PASS", "skipped_dangling": 0},
    )
    monkeypatch.setattr(
        cypher_runner,
        "_check_invariants",
        lambda *args, **kwargs: [
            {"name": "fixture", "value": 1, "expected": 1, "status": "PASS"}
        ],
    )

    result = cypher_runner.run(
        request_get=lambda _url, **kwargs: _Response(sparql_by_query[kwargs["params"]["query"]]),
        driver_factory=lambda *args, **kwargs: _Driver(transaction),
        reports_dir=tmp_path,
    )

    report = json.loads(next(tmp_path.glob("*/cypher_results.json")).read_text(encoding="utf-8"))
    assert result == 0
    assert report["status"] == "PASS"
    assert report["passed"] == report["parity_passed"] == report["total"] == 10
    assert all(row["status"] == "PASS" and row["acceptance"] and row["parity"] for row in report["queries"])
    assert all(row["actual_row_count"] == row["expected_row_count"] for row in report["queries"])
    assert transaction.rolled_back is True
