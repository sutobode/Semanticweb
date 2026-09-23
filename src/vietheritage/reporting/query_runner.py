"""SPARQL CQ runner (COMP-010)."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from pyparsing import ParseBaseException
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

REPO_ROOT = Path(__file__).resolve().parents[3]
QUERY_DIR = REPO_ROOT / "sparql"
EXPECTED_DIR = REPO_ROOT / "data" / "fixtures" / "expected"
REPORTS_DIR = REPO_ROOT / "reports"

# PROJECT_SPEC 1.6.2 Section 25: exactly these ten blocking queries/columns.
CQ_CONTRACT = {
    "CQ01-sites-by-location.rq": ["site", "label"],
    "CQ02-unesco-before-year.rq": ["site", "label", "year"],
    "CQ03-sites-by-type.rq": ["site", "label"],
    "CQ04-sites-by-person.rq": ["site", "siteLabel"],
    "CQ05-sites-by-event-or-period.rq": ["site", "label"],
    "CQ06-top-areas.rq": ["area", "areaLabel", "siteCount"],
    "CQ07-persons-with-many-sites.rq": ["person", "name", "siteCount"],
    "CQ08-sites-in-complex.rq": ["site", "label"],
    "CQ09-external-links.rq": ["site", "label", "externalResource"],
    "CQ10-english-label-from-snapshot.rq": ["site", "viLabel", "externalResource", "enLabel"],
}


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def query_fuseki(
    query: str,
    endpoint: str | None = None,
    request_get: Callable[..., Any] = requests.get,
) -> dict[str, Any]:
    url = endpoint or f"{os.getenv('FUSEKI_URL', 'http://localhost:3031').rstrip('/')}/{os.getenv('FUSEKI_DATASET', 'vietheritage')}/sparql"
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    response = request_get(url, params={"query": query, "format": "json"}, auth=auth, timeout=30)
    response.raise_for_status()
    return response.json()


def _bindings(result: dict[str, Any], variables: list[str]) -> list[dict[str, Any]]:
    if result.get("head", {}).get("vars") != variables:
        raise ValueError("CQ_VARIABLES_MISMATCH")
    bindings = result.get("results", {}).get("bindings")
    if not isinstance(bindings, list) or any(
        not isinstance(binding, dict) or set(binding) != set(variables) for binding in bindings
    ):
        raise ValueError("CQ_BINDINGS_INVALID")
    return bindings


def run(
    endpoint: str | None = None,
    request_get: Callable[..., Any] = requests.get,
    query_dir: Path = QUERY_DIR,
    expected_dir: Path = EXPECTED_DIR,
    reports_dir: Path = REPORTS_DIR,
) -> int:
    queries = [query_dir / name for name in CQ_CONTRACT]
    missing = [path.name for path in queries if not path.is_file()]
    if missing:
        print(f"cq-test: missing required queries: {', '.join(missing)}")
        return 1
    rows: list[dict[str, Any]] = []
    all_pass = True
    for path in queries:
        text = path.read_text(encoding="utf-8")
        row: dict[str, Any] = {
            "query": path.name,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "status": "PASS",
            "expected_checked": False,
            "row_count": 0,
        }
        try:
            variables = CQ_CONTRACT[path.name]
            parsed = parseQuery(text)
            ordered = "orderby" in parsed[1]
            if [str(var) for var in translateQuery(parsed).algebra.PV] != variables:
                raise ValueError("CQ_VARIABLES_MISMATCH")
            expected_path = expected_dir / f"{path.stem[:4]}.json"
            if not expected_path.is_file():
                raise ValueError("CQ_EXPECTED_MISSING")
            expected = _bindings(json.loads(expected_path.read_text(encoding="utf-8")), variables)
            if not expected:
                raise ValueError("CQ_EXPECTED_EMPTY")
            result = query_fuseki(text, endpoint=endpoint, request_get=request_get)
            actual = _bindings(result, variables)
            row["row_count"] = len(actual)
            row["expected_checked"] = True
            if ordered:
                matches = actual == expected
            else:
                matches = {json.dumps(b, sort_keys=True) for b in actual} == {
                    json.dumps(b, sort_keys=True) for b in expected
                }
            if not matches:
                raise ValueError("CQ_EXPECTED_MISMATCH")
        except (OSError, ValueError, TypeError, AttributeError, ParseBaseException, requests.RequestException) as exc:
            row["status"] = "FAIL"
            row["error"] = str(exc)
        if row["status"] != "PASS":
            all_pass = False
        rows.append(row)

    report = {"run_id": _run_id(), "endpoint": endpoint or "fuseki", "queries": rows, "passed": sum(r["status"] == "PASS" for r in rows), "total": len(rows)}
    report_dir = reports_dir / report["run_id"]
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "cq_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cq-test: {report['passed']}/{report['total']} PASS -> {report_dir / 'cq_results.json'}")
    return 0 if all_pass else 1


def run_single(query: str) -> int:
    try:
        result = query_fuseki(query)
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"query: FAIL - {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
