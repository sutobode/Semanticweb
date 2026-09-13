"""SPARQL CQ runner (COMP-010)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
QUERY_DIR = REPO_ROOT / "sparql"
EXPECTED_DIR = REPO_ROOT / "data" / "fixtures" / "expected"
REPORTS_DIR = REPO_ROOT / "reports"


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def query_fuseki(
    query: str,
    endpoint: str | None = None,
    request_get: Callable[..., Any] = requests.get,
) -> dict[str, Any]:
    url = endpoint or f"{os.getenv('FUSEKI_URL', 'http://localhost:3030').rstrip('/')}/{os.getenv('FUSEKI_DATASET', 'vietheritage')}/sparql"
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    response = request_get(url, params={"query": query, "format": "json"}, auth=auth, timeout=30)
    response.raise_for_status()
    return response.json()


def _bindings(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result.get("results", {}).get("bindings", [])


def run(
    endpoint: str | None = None,
    request_get: Callable[..., Any] = requests.get,
    query_dir: Path = QUERY_DIR,
    expected_dir: Path = EXPECTED_DIR,
    reports_dir: Path = REPORTS_DIR,
) -> int:
    queries = sorted(query_dir.glob("CQ*.rq"))
    if len(queries) != 10:
        print(f"cq-test: expected 10 queries, found {len(queries)}")
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
            result = query_fuseki(text, endpoint=endpoint, request_get=request_get)
            row["row_count"] = len(_bindings(result))
            expected_path = expected_dir / f"{path.stem[:4]}.json"
            if expected_path.exists():
                expected = json.loads(expected_path.read_text(encoding="utf-8"))
                row["expected_checked"] = True
                if _bindings(result) != _bindings(expected):
                    row["status"] = "FAIL"
                    row["error"] = "CQ_EXPECTED_MISMATCH"
        except (OSError, ValueError, requests.RequestException) as exc:
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
