"""Cypher CQ runner with RDF/LPG binding-set parity (COMP-011)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[3]
CYPHER_DIR = REPO_ROOT / "cypher"
SPARQL_DIR = REPO_ROOT / "sparql"
REPORTS_DIR = REPO_ROOT / "reports"

_CYPHER_TO_SPARQL_ALIASES = {
    "CQ01-sites-by-location": {"entity": "site"},
    "CQ03-unesco-sites": {"entity": "site"},
}


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, float):
        # Neo4j returns coordinates as binary floats; preserve their decimal
        # lexical value instead of format(..., "g"), which truncates precision.
        text = format(Decimal(str(value)).normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        normalized = format(Decimal(text).normalize(), "f")
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
    for marker in ("/vietheritage/resource/", "/vietheritage/ontology/"):
        if marker in text:
            return text.split(marker, 1)[1]
    return text


def _normalize_rows(rows: list[dict[str, Any]], aliases: dict[str, str]) -> set[tuple[tuple[str, str], ...]]:
    normalized = []
    for row in rows:
        mapped = {
            aliases.get(key, key): _normalize_value(value)
            for key, value in row.items()
        }
        normalized.append(tuple(sorted(mapped.items())))
    return set(normalized)


def _query_fuseki(query: str) -> dict[str, Any]:
    base = os.getenv("FUSEKI_URL", "http://localhost:3030").rstrip("/")
    dataset = os.getenv("FUSEKI_DATASET", "vietheritage")
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    response = requests.get(
        f"{base}/{dataset}/sparql",
        params={"query": query, "format": "json"},
        auth=auth,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def run() -> int:
    queries = sorted(CYPHER_DIR.glob("CQ*.cypher"))
    if len(queries) != 10:
        print(f"cypher-test: expected 10 queries, found {len(queries)}")
        return 1
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "change-me-local-only"))
    rows: list[dict[str, Any]] = []
    try:
        driver = GraphDatabase.driver(uri, auth=auth)
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            for path in queries:
                row: dict[str, Any] = {"query": path.name, "status": "PASS"}
                try:
                    cypher_rows = session.run(path.read_text(encoding="utf-8")).data()
                    sparql_path = SPARQL_DIR / f"{path.stem}.rq"
                    rdf_bindings = _query_fuseki(sparql_path.read_text(encoding="utf-8"))[
                        "results"
                    ]["bindings"]
                    aliases = _CYPHER_TO_SPARQL_ALIASES.get(path.stem, {})
                    lpg_set = _normalize_rows(cypher_rows, {})
                    rdf_set = _normalize_rows(rdf_bindings, aliases)
                    row["lpg_row_count"] = len(cypher_rows)
                    row["rdf_row_count"] = len(rdf_bindings)
                    if lpg_set != rdf_set:
                        row["status"] = "FAIL"
                        row["error"] = "LPG_RDF_MISMATCH"
                        row["lpg_only"] = len(lpg_set - rdf_set)
                        row["rdf_only"] = len(rdf_set - lpg_set)
                except (OSError, KeyError, ValueError, requests.RequestException) as exc:
                    row["status"] = "FAIL"
                    row["error"] = str(exc)
                rows.append(row)
        driver.close()
    except Exception as exc:
        print(f"cypher-test: FAIL - {exc}")
        return 1

    passed = sum(row["status"] == "PASS" for row in rows)
    report_dir = REPORTS_DIR / _run_id()
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"queries": rows, "passed": passed, "total": len(rows), "status": "PASS" if passed == len(rows) else "FAIL"}
    (report_dir / "cypher_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cypher-test: {passed}/{len(rows)} PASS -> {report_dir / 'cypher_results.json'}")
    return 0 if passed == len(rows) else 1
