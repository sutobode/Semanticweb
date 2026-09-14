"""Final verification aggregator (COMP-013)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from vietheritage.reporting.query_runner import run as cq_run
from vietheritage.validation.validator import run as validate_run

REPO_ROOT = Path(__file__).resolve().parents[3]


def _coverage_for_snapshot(snapshot_id: str | None) -> dict:
    reports = sorted((REPO_ROOT / "reports").glob("20*/coverage.json"), key=lambda path: path.stat().st_mtime)
    if snapshot_id:
        for path in reversed(reports):
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("snapshot_id") == snapshot_id:
                return report
        return {}
    if not reports:
        return {}
    return json.loads(reports[-1].read_text(encoding="utf-8"))


def _verified_link_count() -> int:
    path = REPO_ROOT / "data" / "linking" / "link-review.jsonl"
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("status") == "verified"
    )


def _health(url: str) -> bool:
    try:
        return requests.get(url, timeout=5).status_code < 500
    except requests.RequestException:
        return False



def _resource_health() -> bool:
    base = os.getenv("VH_BASE_URI", "http://localhost:3030/vietheritage").rstrip("/")
    canonical = REPO_ROOT / "data" / "processed" / "canonical.jsonl"
    try:
        first = next(line for line in canonical.read_text(encoding="utf-8").splitlines() if line.strip())
        entity_id = json.loads(first)["entity_id"]
        response = requests.get(f"{base}/resource/{entity_id}", headers={"Accept": "text/turtle"}, timeout=10)
        return response.status_code == 200 and bool(response.content)
    except (OSError, StopIteration, KeyError, json.JSONDecodeError, requests.RequestException):
        return False



def _latest_cypher_report() -> dict:
    reports = list((REPO_ROOT / "reports").glob("20*/cypher_results.json"))
    if not reports:
        return {}
    latest = max(reports, key=lambda path: path.stat().st_mtime)
    return json.loads(latest.read_text(encoding="utf-8"))


def run(run_mode: str = "sample") -> int:
    checks: dict[str, str] = {}
    checks["validation"] = "PASS" if validate_run(run_mode) == 0 else "FAIL"
    checks["traceability"] = "PASS" if all(
        (REPO_ROOT / path).exists()
        for path in ["ontology/vietheritage.ttl", "docker-compose.yml", "silk/linkage-rules.xml"]
    ) else "FAIL"
    cq_status = cq_run()
    checks["cq"] = "PASS" if cq_status == 0 else "FAIL"
    cypher_report = _latest_cypher_report()
    checks["cypher_parity"] = "PASS" if cypher_report.get("status") == "PASS" else "FAIL"
    checks["reasoning"] = "PASS" if (REPO_ROOT / "data/rdf/inferred.ttl").exists() else "FAIL"
    checks["neo4j"] = "PASS" if (REPO_ROOT / "reports" / run_mode / "neo4j_load.json").exists() else "FAIL"
    checks["fuseki"] = "PASS" if (REPO_ROOT / "data/rdf/vietheritage.ttl").exists() else "FAIL"
    checks["metadata"] = "PASS" if (REPO_ROOT / "data/rdf/dataset-metadata.ttl").exists() else "FAIL"
    checks["canonical_resource"] = "PASS" if _resource_health() else "FAIL"
    checks["fuseki_health"] = "PASS" if _health("http://localhost:3031/$/ping") else "FAIL"
    checks["neo4j_health"] = "PASS" if _health("http://localhost:7474") else "FAIL"

    coverage_path = REPO_ROOT / "data" / "processed" / "canonical.jsonl"
    canonical_records = [json.loads(line) for line in coverage_path.read_text(encoding="utf-8").splitlines() if line.strip()] if coverage_path.exists() else []
    canonical_count = len(canonical_records)
    snapshot_id = str(canonical_records[0].get("coverage_snapshot")) if canonical_records else None
    coverage = _coverage_for_snapshot(snapshot_id)
    category_coverage_ok = bool(coverage.get("categories")) and all(
        item.get("coverage_percent") == 100.0 for item in coverage["categories"]
    )
    coverage_ok = (
        run_mode == "sample"
        or coverage.get("claim") == "100% of selected official registry snapshot"
        and coverage.get("registry_total") == canonical_count
        and coverage.get("canonical_total") == canonical_count
        and len(coverage.get("categories", [])) == 17
        and category_coverage_ok
    )
    checks["coverage"] = "PASS" if coverage_ok else "FAIL"

    pages_ok = run_mode == "sample" or (REPO_ROOT / "data/raw/pages.jsonl").exists()
    checks["wikipedia_enrichment"] = "PASS" if pages_ok else "FAIL"
    verified_links = _verified_link_count()
    checks["external_links"] = "PASS" if run_mode == "sample" or verified_links >= 100 else "FAIL"

    passed = all(value == "PASS" for value in checks.values())
    report = {
        "run_mode": run_mode,
        "checks": checks,
        "metrics": {
            "snapshot_id": snapshot_id,
            "canonical_records": canonical_count,
            "verified_external_links": verified_links,
            "coverage_claim": coverage.get("claim"),
            "registry_total": coverage.get("registry_total"),
            "cypher_passed": cypher_report.get("passed", 0),
            "cypher_total": cypher_report.get("total", 0),
        },
        "status": "PASS" if passed else "FAIL",
    }
    out = REPO_ROOT / "reports" / run_mode
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"verify ({run_mode}): coverage={checks['coverage']}, external_links={verified_links}, services={checks['fuseki_health']}/{checks['neo4j_health']}")
    print(f"FINAL STATUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1
