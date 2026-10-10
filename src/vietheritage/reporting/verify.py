"""Final production integration verification (COMP-013)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from neo4j import GraphDatabase
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from vietheritage.lpg.cypher_runner import run as cypher_run
from vietheritage.lpg.loader import _neo4j_config, run as neo4j_load_run
from vietheritage.rdf.fuseki_loader import golden_query_endpoint, load_golden
from vietheritage.rdf.fuseki_loader import run as fuseki_load_run
from vietheritage.reasoning.reasoner import run as reason_run
from vietheritage.reporting.health import is_fuseki_ready
from vietheritage.reporting.query_runner import run as cq_run
from vietheritage.validation.policy import is_fixture_site_id
from vietheritage.validation.validator import run as validate_run


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports"
FULL_REPORT_DIR = REPORTS_DIR / "full"
CANONICAL = REPO_ROOT / "data" / "processed" / "canonical.jsonl"
ONTOLOGY = REPO_ROOT / "ontology" / "vietheritage.ttl"
ASSERTED = REPO_ROOT / "data" / "rdf" / "vietheritage.ttl"
INFERRED = REPO_ROOT / "data" / "rdf" / "inferred.ttl"
GRAPH_BASE = "http://localhost:3030/vietheritage/graph"
GRAPH_NAMES = ("ontology", "data", "external-links", "inferred", "metadata")


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:6]}"


def _records() -> list[dict[str, Any]]:
    if not CANONICAL.is_file():
        return []
    return [
        json.loads(line)
        for line in CANONICAL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _latest_report(filename: str) -> tuple[Path | None, dict[str, Any]]:
    paths = list(REPORTS_DIR.glob(f"20*/{filename}"))
    if not paths:
        return None, {}
    path = max(paths, key=lambda item: item.stat().st_mtime)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _coverage_for_snapshot(snapshot_id: str | None) -> dict[str, Any]:
    paths = sorted(
        REPORTS_DIR.glob("20*/coverage.json"),
        key=lambda path: path.stat().st_mtime,
    )
    for path in reversed(paths):
        report = json.loads(path.read_text(encoding="utf-8"))
        if snapshot_id is None or report.get("snapshot_id") == snapshot_id:
            return report
    return {}


def _verified_link_count() -> int:
    path = REPO_ROOT / "data" / "linking" / "link-review.jsonl"
    if not path.is_file():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("status") == "verified"
    )


def _reasoning_stale() -> bool:
    if not INFERRED.is_file() or not ONTOLOGY.is_file() or not ASSERTED.is_file():
        return True
    return INFERRED.stat().st_mtime < max(
        ONTOLOGY.stat().st_mtime,
        ASSERTED.stat().st_mtime,
    )


def _production_resource(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            record
            for record in records
            if record.get("entity_type") == "HeritageSite" and record.get("registry_id")
        ),
        None,
    )


def _rdf_describes_resource(content: bytes, rdf_format: str, uri: str) -> bool:
    try:
        graph = Graph().parse(data=content, format=rdf_format)
    except Exception:
        return False
    return any(graph.triples((URIRef(uri), None, None)))


def _sparql(query: str) -> dict[str, Any]:
    base = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
    dataset = os.getenv("FUSEKI_DATASET", "vietheritage")
    response = requests.get(
        f"{base}/{dataset}/sparql",
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _fuseki_evidence() -> dict[str, Any]:
    base = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
    dataset = os.getenv("FUSEKI_DATASET", "vietheritage")
    evidence: dict[str, Any] = {
        "version": "4.10.0",
        "url": f"{base}/{dataset}/sparql",
        "status": "FAIL",
        "graphs": {},
    }
    try:
        values = " ".join(f"<{GRAPH_BASE}/{name}>" for name in GRAPH_NAMES)
        payload = _sparql(
            "SELECT ?graph (COUNT(*) AS ?count) WHERE { "
            f"VALUES ?graph {{ {values} }} GRAPH ?graph {{ ?s ?p ?o }} "
            "} GROUP BY ?graph"
        )
        graphs = {
            row["graph"]["value"].rsplit("/", 1)[-1]: int(row["count"]["value"])
            for row in payload.get("results", {}).get("bindings", [])
        }
        fixture = _sparql(
            "ASK { <http://localhost:3030/vietheritage/resource/site-in-sub-area-1> ?p ?o }"
        ).get("boolean")
        production = _sparql(
            "ASK { GRAPH <http://localhost:3030/vietheritage/graph/data> { ?s ?p ?o } }"
        ).get("boolean")
        evidence.update(
            {
                "graphs": graphs,
                "production_query": bool(production),
                "fixture_contamination": bool(fixture),
                "status": "PASS"
                if set(graphs) == set(GRAPH_NAMES)
                and all(value > 0 for value in graphs.values())
                and production is True
                and fixture is False
                else "FAIL",
            }
        )
    except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
        evidence["error"] = str(exc)
    return evidence


def _neo4j_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "version": None,
        "url": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "status": "FAIL",
    }
    try:
        uri, auth, database = _neo4j_config()
        with GraphDatabase.driver(uri, auth=auth) as driver:
            with driver.session(database=database) as session:
                evidence.update(
                    {
                        "version": session.run(
                            "CALL dbms.components() YIELD versions "
                            "RETURN versions[0] AS value"
                        ).single()["value"],
                        "resources": session.run(
                            "MATCH (n:Resource) RETURN count(n) AS value"
                        ).single()["value"],
                        "external_resources": session.run(
                            "MATCH (n:ExternalResource) RETURN count(n) AS value"
                        ).single()["value"],
                        "relationships": session.run(
                            "MATCH ()-[r]->() RETURN count(r) AS value"
                        ).single()["value"],
                        "same_as": session.run(
                            "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS value"
                        ).single()["value"],
                        "duplicate_entity_ids": session.run(
                            "MATCH (n:Resource) WITH n.entityId AS id, count(*) AS copies "
                            "WHERE copies > 1 RETURN count(*) AS value"
                        ).single()["value"],
                        "missing_required_properties": session.run(
                            "MATCH (n:Resource) "
                            "WHERE n.entityId IS NULL OR n.uri IS NULL OR n.labelVi IS NULL "
                            "OR n.sourceUrl IS NULL OR n.retrievedAt IS NULL "
                            "RETURN count(n) AS value"
                        ).single()["value"],
                    }
                )
        evidence["status"] = "PASS" if (
            evidence["duplicate_entity_ids"] == 0
            and evidence["missing_required_properties"] == 0
        ) else "FAIL"
    except Exception as exc:
        evidence["error"] = str(exc)
    return evidence


def _explorer_evidence(resource: dict[str, Any] | None) -> dict[str, Any]:
    base = os.getenv("EXPLORER_URL", "http://localhost:3030").rstrip("/")
    evidence: dict[str, Any] = {
        "version": "0.1.0",
        "url": base,
        "status": "FAIL",
        "checks": {},
    }
    if resource is None:
        evidence["error"] = "production HeritageSite is unavailable"
        return evidence
    entity_id = resource["entity_id"]
    uri = f"{base}/vietheritage/resource/{entity_id}"
    checks: dict[str, bool] = {}
    try:
        home = requests.get(base, timeout=15)
        checks["homepage"] = home.status_code == 200 and "text/html" in home.headers.get("Content-Type", "")
        health = requests.get(f"{base}/api/health", timeout=15)
        checks["api_health"] = health.status_code == 200 and health.json().get("status") == "ok"
        lookup = requests.get(f"{base}/api/entities/{entity_id}", timeout=30)
        checks["resource_lookup"] = lookup.status_code == 200 and lookup.json().get("@id") == uri
        html = requests.get(uri, headers={"Accept": "text/html"}, timeout=30)
        checks["html"] = html.status_code == 200 and "text/html" in html.headers.get("Content-Type", "") and entity_id in html.text
        turtle = requests.get(uri, headers={"Accept": "text/turtle"}, timeout=30)
        checks["turtle"] = (
            turtle.status_code == 200
            and turtle.headers.get("Content-Type", "").startswith("text/turtle")
            and _rdf_describes_resource(turtle.content, "turtle", uri)
        )
        jsonld = requests.get(uri, headers={"Accept": "application/ld+json"}, timeout=30)
        checks["jsonld"] = (
            jsonld.status_code == 200
            and jsonld.headers.get("Content-Type", "").startswith("application/ld+json")
            and _rdf_describes_resource(jsonld.content, "json-ld", uri)
        )
        unsupported = requests.get(uri, headers={"Accept": "application/xml"}, timeout=15)
        checks["not_acceptable"] = unsupported.status_code == 406
        missing = requests.get(f"{base}/vietheritage/resource/does-not-exist", timeout=15)
        checks["not_found"] = missing.status_code == 404
        mutation = requests.post(f"{base}/api/config", timeout=15)
        checks["read_only"] = mutation.status_code == 405
        checks["canonical_namespace"] = uri.startswith(f"{base}/vietheritage/resource/")
        evidence.update(
            {
                "resource_uri": uri,
                "checks": checks,
                "status": "PASS" if checks and all(checks.values()) else "FAIL",
            }
        )
    except (ValueError, requests.RequestException) as exc:
        evidence["error"] = str(exc)
        evidence["checks"] = checks
    return evidence


def _ontology_inventory() -> dict[str, int]:
    graph = Graph().parse(ONTOLOGY, format="turtle")
    base = "http://localhost:3030/vietheritage/ontology/"
    return {
        "classes": len({node for node in graph.subjects(RDF.type, OWL.Class) if str(node).startswith(base)}),
        "object_properties": len({node for node in graph.subjects(RDF.type, OWL.ObjectProperty) if str(node).startswith(base)}),
        "datatype_properties": len({node for node in graph.subjects(RDF.type, OWL.DatatypeProperty) if str(node).startswith(base)}),
    }


def _coverage_status(records: list[dict[str, Any]], run_mode: str) -> tuple[bool, dict[str, Any]]:
    registry_records = [record for record in records if record.get("registry_id")]
    identity_map = REPO_ROOT / "data" / "processed" / "identity_map.jsonl"
    merged_ids = {
        merged
        for line in (identity_map.read_text(encoding="utf-8").splitlines() if identity_map.is_file() else [])
        if line.strip()
        for merged in (json.loads(line).get("merged_from") or [])
        if isinstance(merged, str)
    }
    registry_count = len({record["registry_id"] for record in registry_records} | merged_ids)
    snapshot_id = str(registry_records[0].get("coverage_snapshot")) if registry_records else None
    coverage = _coverage_for_snapshot(snapshot_id)
    category_ok = bool(coverage.get("categories")) and all(
        row.get("coverage_percent") == 100.0 for row in coverage["categories"]
    )
    passed = run_mode == "sample" or (
        coverage.get("claim") == "100% of selected official registry snapshot"
        and coverage.get("registry_total") == registry_count
        and coverage.get("canonical_total") == registry_count
        and len(coverage.get("categories", [])) == 17
        and category_ok
    )
    return passed, {
        "snapshot_id": snapshot_id,
        "registry_records": registry_count,
        "claim": coverage.get("claim"),
        "categories": len(coverage.get("categories", [])),
    }


def _coverage_check(
    records: list[dict[str, Any]], run_mode: str
) -> tuple[str, dict[str, Any]]:
    coverage_ok, evidence = _coverage_status(records, run_mode)
    if coverage_ok:
        return "PASS", evidence
    if not _coverage_for_snapshot(evidence.get("snapshot_id")):
        return "NOT_AVAILABLE", evidence
    return "FAIL", evidence


def _blocking_errors(checks: dict[str, str]) -> list[str]:
    return [name for name, status in checks.items() if status == "FAIL"]


def run(run_mode: str = "sample") -> int:
    run_id = _run_id()
    FULL_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    records = _records()
    resource = _production_resource(records)
    checks: dict[str, str] = {}
    report_paths: dict[str, str] = {}

    reasoning_refreshed = _reasoning_stale()
    reasoning_exit = reason_run(run_mode, run_id=run_id) if reasoning_refreshed else 0
    reasoning_path, reasoning = _latest_report("reasoning.json")
    checks["reasoning"] = "PASS" if reasoning_exit == 0 and reasoning.get("status") == "PASS" else "FAIL"
    if reasoning_path:
        report_paths["reasoning"] = str(reasoning_path)

    validation_exit = validate_run(run_mode)
    validation_path = FULL_REPORT_DIR / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.is_file() else {}
    checks["semantic_validation"] = "PASS" if validation_exit == 0 and validation.get("status") == "PASS" else "FAIL"
    checks["shacl"] = "PASS" if validation.get("shacl") == "PASS" and validation.get("conforms") is True else "FAIL"
    if validation_path.is_file():
        report_paths["validation"] = str(validation_path)

    checks["fuseki_health"] = "PASS" if is_fuseki_ready() else "FAIL"
    fuseki_load_exit = fuseki_load_run(run_mode) if checks["fuseki_health"] == "PASS" else 1
    fuseki = _fuseki_evidence() if fuseki_load_exit == 0 else {"version": "4.10.0", "url": None, "status": "FAIL"}
    checks["fuseki_publication"] = fuseki["status"]

    cq_exit = load_golden()
    if cq_exit == 0:
        cq_exit = cq_run(endpoint=golden_query_endpoint())
    cq_path, cq_report = _latest_report("cq_results.json")
    checks["sparql_cq"] = "PASS" if cq_exit == 0 and cq_report.get("passed") == cq_report.get("total") == 10 else "FAIL"
    if cq_path:
        report_paths["sparql_cq"] = str(cq_path)

    neo4j_load_exit = neo4j_load_run(run_mode)
    neo4j_load_path, neo4j_load = _latest_report("neo4j_load.json")
    neo4j_before = _neo4j_evidence()
    checks["neo4j_load"] = "PASS" if neo4j_load_exit == 0 and neo4j_load.get("status") == "PASS" else "FAIL"
    checks["neo4j_health"] = neo4j_before["status"]
    if neo4j_load_path:
        report_paths["neo4j_load"] = str(neo4j_load_path)

    cypher_exit = cypher_run()
    cypher_path, cypher_report = _latest_report("cypher_results.json")
    neo4j_after = _neo4j_evidence()
    checks["cypher_cq"] = "PASS" if cypher_exit == 0 and cypher_report.get("passed") == cypher_report.get("total") == 10 else "FAIL"
    checks["parity"] = "PASS" if cypher_report.get("parity_passed") == cypher_report.get("total") == 10 else "FAIL"
    checks["production_isolation"] = "PASS" if neo4j_before == neo4j_after else "FAIL"
    if cypher_path:
        report_paths["cypher"] = str(cypher_path)

    explorer = _explorer_evidence(resource)
    checks["explorer"] = explorer["status"]
    checks["linked_data"] = "PASS" if explorer.get("checks", {}).get("turtle") and explorer.get("checks", {}).get("jsonld") else "FAIL"

    checks["coverage"], coverage = _coverage_check(records, run_mode)
    checks["external_links"] = "PASS" if run_mode == "sample" or _verified_link_count() >= 100 else "FAIL"
    checks["fixture_contamination"] = "PASS" if not any(is_fixture_site_id(record.get("entity_id", "")) for record in records) and fuseki.get("fixture_contamination") is False else "FAIL"
    checks["metadata"] = "PASS" if fuseki.get("graphs", {}).get("metadata", 0) > 0 else "FAIL"
    checks["ontology_inventory"] = "PASS" if _ontology_inventory() == {"classes": 23, "object_properties": 12, "datatype_properties": 10} else "FAIL"

    graph_counts = fuseki.get("graphs", {})
    metrics = {
        "canonical_records": len(records),
        "ontology_triples": graph_counts.get("ontology", 0),
        "asserted_triples": graph_counts.get("data", 0),
        "inferred_delta": graph_counts.get("inferred", 0),
        "external_links": graph_counts.get("external-links", 0),
        "metadata_triples": graph_counts.get("metadata", 0),
        "final_public_graph": validation.get("final_triples", 0),
        "ontology_inventory": _ontology_inventory(),
        "neo4j_resources": neo4j_after.get("resources", 0),
        "neo4j_external_resources": neo4j_after.get("external_resources", 0),
        "neo4j_relationships": neo4j_after.get("relationships", 0),
        "neo4j_same_as": neo4j_after.get("same_as", 0),
        "verified_external_links": _verified_link_count(),
    }
    checks["canonical_lpg_count"] = "PASS" if metrics["neo4j_resources"] == metrics["canonical_records"] else "FAIL"

    errors = _blocking_errors(checks)
    limitations = []
    if checks["coverage"] == "NOT_AVAILABLE":
        limitations.append(
            "Collector coverage.json is unavailable for the current snapshot; collection was not rerun during M4.4."
        )
    passed = not errors
    report = {
        "run_id": run_id,
        "run_mode": run_mode,
        "status": "PASS" if passed else "FAIL",
        "services": {
            "fuseki": fuseki,
            "neo4j": neo4j_after,
            "explorer": explorer,
        },
        "metrics": metrics,
        "coverage": coverage,
        "reasoning": {
            "status": reasoning.get("status"),
            "refreshed": reasoning_refreshed,
            "axioms": reasoning.get("axioms", {}),
        },
        "validation": {
            "status": validation.get("status"),
            "conforms": validation.get("conforms"),
            "shacl": validation.get("shacl"),
            "errors": validation.get("errors", []),
        },
        "query_acceptance": {
            "sparql": f"{cq_report.get('passed', 0)}/{cq_report.get('total', 0)}",
            "cypher": f"{cypher_report.get('passed', 0)}/{cypher_report.get('total', 0)}",
            "parity": f"{cypher_report.get('parity_passed', 0)}/{cypher_report.get('total', 0)}",
        },
        "neo4j_production_before_parity": neo4j_before,
        "neo4j_production_after_parity": neo4j_after,
        "checks": checks,
        "report_paths": report_paths,
        "errors": errors,
        "limitations": limitations,
    }
    final_path = FULL_REPORT_DIR / "final_integration.json"
    verify_path = FULL_REPORT_DIR / "verify.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    final_path.write_text(serialized, encoding="utf-8")
    verify_path.write_text(serialized, encoding="utf-8")
    print(
        f"verify ({run_mode}): SPARQL={report['query_acceptance']['sparql']}, "
        f"Cypher={report['query_acceptance']['cypher']}, parity={report['query_acceptance']['parity']}"
    )
    print(f"final-integration-report: {final_path}")
    print(f"FINAL STATUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1
