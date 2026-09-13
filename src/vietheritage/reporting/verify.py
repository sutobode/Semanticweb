"""Final verification aggregator (COMP-013)."""
from __future__ import annotations

import json
from pathlib import Path

from vietheritage.reporting.query_runner import run as cq_run
from vietheritage.validation.validator import run as validate_run

REPO_ROOT = Path(__file__).resolve().parents[3]


def run(run_mode: str = "sample") -> int:
    checks: dict[str, str] = {}
    checks["validation"] = "PASS" if validate_run(run_mode) == 0 else "FAIL"
    checks["traceability"] = "PASS" if all((REPO_ROOT / path).exists() for path in ["ontology/vietheritage.ttl", "docker-compose.yml", "silk/linkage-rules.xml"]) else "FAIL"
    cq_status = cq_run()
    checks["cq"] = "PASS" if cq_status == 0 else "FAIL"
    checks["reasoning"] = "PASS" if (REPO_ROOT / "data/rdf/inferred.ttl").exists() else "FAIL"
    checks["neo4j"] = "PASS" if (REPO_ROOT / "reports" / run_mode / "neo4j_load.json").exists() else "FAIL"
    checks["fuseki"] = "PASS" if (REPO_ROOT / "data/rdf/vietheritage.ttl").exists() else "FAIL"
    passed = all(value == "PASS" for value in checks.values())
    report = {"run_mode": run_mode, "checks": checks, "status": "PASS" if passed else "FAIL"}
    out = REPO_ROOT / "reports" / run_mode
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FINAL STATUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1
