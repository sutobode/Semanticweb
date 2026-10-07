"""SPARQL CQ runner (COMP-010)."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
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
    response = request_get(
        url,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
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


def _term_key(term: Any) -> tuple[str, str, str, str]:
    if not isinstance(term, dict) or not isinstance(term.get("type"), str) or not isinstance(term.get("value"), str):
        raise ValueError("CQ_BINDINGS_INVALID")
    term_type = term["type"]
    if term_type not in {"uri", "literal", "bnode"}:
        raise ValueError("CQ_BINDINGS_INVALID")
    datatype = term.get("datatype", "")
    language = term.get("xml:lang", "")
    if not isinstance(datatype, str) or not isinstance(language, str):
        raise ValueError("CQ_BINDINGS_INVALID")
    if term_type != "literal" and (datatype or language):
        raise ValueError("CQ_BINDINGS_INVALID")
    return term_type, term["value"], datatype, language


def _binding_key(binding: dict[str, Any], variables: list[str]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(_term_key(binding[variable]) for variable in variables)


def _matches(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    variables: list[str],
    ordered: bool,
) -> bool:
    actual_keys = [_binding_key(binding, variables) for binding in actual]
    expected_keys = [_binding_key(binding, variables) for binding in expected]
    return actual_keys == expected_keys if ordered else Counter(actual_keys) == Counter(expected_keys)


def _term_tsv(term: dict[str, Any]) -> str:
    term_type, value, datatype, language = _term_key(term)
    if term_type == "uri":
        return f"<{value}>"
    if term_type == "bnode":
        return f"_:{value}"
    rendered = json.dumps(value, ensure_ascii=False)
    if language:
        return f"{rendered}@{language}"
    if datatype:
        return f"{rendered}^^<{datatype}>"
    return rendered


def _write_tsv(path: Path, variables: list[str], bindings: list[dict[str, Any]]) -> None:
    lines = ["\t".join(f"?{variable}" for variable in variables)]
    lines.extend("\t".join(_term_tsv(binding[variable]) for variable in variables) for binding in bindings)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    endpoint_url = endpoint or (
        f"{os.getenv('FUSEKI_URL', 'http://localhost:3031').rstrip('/')}"
        f"/{os.getenv('FUSEKI_CQ_DATASET', 'vietheritage-cq')}/sparql"
    )
    run_started = datetime.now(UTC)
    run_id = _run_id()
    report_dir = reports_dir / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    all_pass = True
    for path in queries:
        text = path.read_text(encoding="utf-8")
        cq_id = path.stem[:4]
        variables = CQ_CONTRACT[path.name]
        started = datetime.now(UTC)
        actual_result: dict[str, Any] | None = None
        actual: list[dict[str, Any]] = []
        row: dict[str, Any] = {
            "cq_id": cq_id,
            "query": path.name,
            "endpoint": endpoint_url,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "status": "PASS",
            "comparison": "NOT_RUN",
            "http_status": None,
            "started_at": started.isoformat(),
            "finished_at": None,
            "duration_seconds": 0.0,
            "actual_row_count": 0,
            "expected_row_count": 0,
            "expected_checked": False,
            "row_count": 0,
        }
        try:
            expected_path = expected_dir / f"{cq_id}.json"
            if not expected_path.is_file():
                raise ValueError("CQ_EXPECTED_MISSING")
            expected = _bindings(json.loads(expected_path.read_text(encoding="utf-8")), variables)
            row["expected_row_count"] = len(expected)
            if not expected:
                raise ValueError("CQ_EXPECTED_EMPTY")

            parsed = parseQuery(text)
            ordered = "orderby" in parsed[1]
            if [str(var) for var in translateQuery(parsed).algebra.PV] != variables:
                raise ValueError("CQ_VARIABLES_MISMATCH")

            response = request_get(
                endpoint_url,
                params={"query": text},
                headers={"Accept": "application/sparql-results+json"},
                timeout=30,
            )
            row["http_status"] = getattr(response, "status_code", 200)
            response.raise_for_status()
            actual_result = response.json()
            actual = _bindings(actual_result, variables)
            row["actual_row_count"] = row["row_count"] = len(actual)
            row["expected_checked"] = True
            if not _matches(actual, expected, variables, ordered):
                row["comparison"] = "MISMATCH"
                raise ValueError("CQ_EXPECTED_MISMATCH")
            row["comparison"] = "MATCH"
        except (OSError, ValueError, TypeError, AttributeError, ParseBaseException, requests.RequestException) as exc:
            row["status"] = "FAIL"
            row["error"] = str(exc)
        finally:
            finished = datetime.now(UTC)
            row["finished_at"] = finished.isoformat()
            row["duration_seconds"] = round((finished - started).total_seconds(), 6)
            json_artifact = report_dir / f"{cq_id}.json"
            tsv_artifact = report_dir / f"{cq_id}.tsv"
            artifact_payload = actual_result or {
                "cq_id": cq_id,
                "status": row["status"],
                "error": row.get("error", "CQ_RESULT_UNAVAILABLE"),
            }
            json_artifact.write_text(
                json.dumps(artifact_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                _write_tsv(tsv_artifact, variables, actual)
            except ValueError:
                _write_tsv(tsv_artifact, variables, [])
            row["artifacts"] = [str(json_artifact), str(tsv_artifact)]
        if row["status"] != "PASS":
            all_pass = False
        rows.append(row)

    run_finished = datetime.now(UTC)
    report = {
        "run_id": run_id,
        "endpoint": endpoint_url,
        "started_at": run_started.isoformat(),
        "finished_at": run_finished.isoformat(),
        "duration_seconds": round((run_finished - run_started).total_seconds(), 6),
        "status": "PASS" if all_pass else "FAIL",
        "queries": rows,
        "passed": sum(r["status"] == "PASS" for r in rows),
        "total": len(rows),
    }
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
