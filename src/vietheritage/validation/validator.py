"""RDF and canonical validation (COMP-006)."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from rdflib import Graph

from .shacl import run as shacl_run

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"
RDF_DIR = REPO_ROOT / "data" / "rdf"
SCHEMA = REPO_ROOT / "schema" / "canonical-record.schema.json"


def run(run_mode: str = "sample") -> int:
    canonical = PROCESSED / "canonical.jsonl"
    asserted = RDF_DIR / "vietheritage.ttl"
    ontology = REPO_ROOT / "ontology" / "vietheritage.ttl"
    if not canonical.exists() or not asserted.exists() or not ontology.exists():
        print("validate: required artifact missing")
        return 1
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors: list[str] = []
    count = 0
    for line in canonical.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        errors.extend(error.message for error in Draft202012Validator(schema).iter_errors(json.loads(line)))
    for path in (asserted, ontology):
        try:
            Graph().parse(path, format="turtle")
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    shacl_status = shacl_run(run_mode, asserted)
    if shacl_status != 0:
        errors.append("SHACL_VALIDATION_FAILED")
    report = {
        "status": "PASS" if not errors else "FAIL",
        "canonical_records": count,
        "shacl": "PASS" if shacl_status == 0 else "FAIL",
        "errors": errors,
    }
    out = REPO_ROOT / "reports" / run_mode
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"validate ({run_mode}): {report['status']} ({count} canonical records)")
    return 0 if not errors else 1
