"""Compact offline final demo acceptance using existing service runners."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from rdflib import Graph, URIRef

from vietheritage.lpg.cypher_runner import run as cypher_run
from vietheritage.rdf.fuseki_loader import golden_query_endpoint, load_golden
from vietheritage.reporting.health import is_fuseki_ready
from vietheritage.reporting.query_runner import run as cq_run
from vietheritage.reporting.verify import (
    REPORTS_DIR,
    _latest_report,
    _neo4j_evidence,
    _production_resource,
    _records,
    _sparql,
)


def _step(name: str, passed: bool, evidence: Any = None) -> dict[str, Any]:
    return {
        "step": name,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
    }


def run() -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid4().hex[:6]}"
    output = REPORTS_DIR / run_id
    output.mkdir(parents=True, exist_ok=True)
    explorer = os.getenv("EXPLORER_URL", "http://localhost:3030").rstrip("/")
    resource = _production_resource(_records())
    steps: list[dict[str, Any]] = []

    try:
        home = requests.get(explorer, timeout=15)
        steps.append(_step("Explorer reachable", home.status_code == 200, explorer))
        if resource is None:
            raise ValueError("production HeritageSite is unavailable")
        uri = f"{explorer}/vietheritage/resource/{resource['entity_id']}"
        turtle = requests.get(uri, headers={"Accept": "text/turtle"}, timeout=30)
        graph = Graph().parse(data=turtle.content, format="turtle") if turtle.status_code == 200 else Graph()
        steps.append(
            _step(
                "Production resource dereference",
                turtle.status_code == 200 and any(graph.triples((URIRef(uri), None, None))),
                uri,
            )
        )
    except (ValueError, requests.RequestException) as exc:
        steps.extend(
            [
                _step("Explorer reachable", False, str(exc)),
                _step("Production resource dereference", False, str(exc)),
            ][len(steps):]
        )

    steps.append(_step("Fuseki SPARQL reachable", is_fuseki_ready()))
    try:
        production_query = _sparql(
            "ASK { GRAPH <http://localhost:3030/vietheritage/graph/data> { ?s ?p ?o } }"
        )
        steps.append(_step("Production graph query", production_query.get("boolean") is True))
    except requests.RequestException as exc:
        steps.append(_step("Production graph query", False, str(exc)))

    sparql_exit = load_golden()
    if sparql_exit == 0:
        sparql_exit = cq_run(endpoint=golden_query_endpoint())
    _, sparql_report = _latest_report("cq_results.json")
    steps.append(
        _step(
            "Deterministic SPARQL CQs",
            sparql_exit == 0 and sparql_report.get("passed") == sparql_report.get("total") == 10,
            f"{sparql_report.get('passed', 0)}/{sparql_report.get('total', 0)}",
        )
    )

    neo4j = _neo4j_evidence()
    steps.append(_step("Neo4j reachable", neo4j.get("status") == "PASS", neo4j))
    cypher_exit = cypher_run()
    cypher_path, cypher_report = _latest_report("cypher_results.json")
    steps.append(
        _step(
            "Deterministic Cypher CQs",
            cypher_exit == 0 and cypher_report.get("passed") == cypher_report.get("total") == 10,
            str(cypher_path) if cypher_path else None,
        )
    )
    steps.append(
        _step(
            "SPARQL/Cypher parity",
            cypher_report.get("parity_passed") == cypher_report.get("total") == 10,
            f"{cypher_report.get('parity_passed', 0)}/{cypher_report.get('total', 0)}",
        )
    )

    passed = len(steps) == 8 and all(step["status"] == "PASS" for step in steps)
    report = {
        "run_id": run_id,
        "offline": True,
        "status": "PASS" if passed else "FAIL",
        "steps": steps,
    }
    path = output / "demo_smoke.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"demo-smoke: {sum(step['status'] == 'PASS' for step in steps)}/8 PASS -> {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
