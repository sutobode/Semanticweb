"""RDF and canonical validation (COMP-006)."""
from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator
from rdflib import Graph
from rdflib.exceptions import ParserError
from rdflib.namespace import OWL

from .policy import validate_public_graph
from .semantic import issue, report, validate_semantics

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"
RDF_DIR = REPO_ROOT / "data" / "rdf"
SCHEMA = REPO_ROOT / "schema" / "canonical-record.schema.json"


def run(
    run_mode: str = "sample", *, run_id: str | None = None,
    data_path: Path | None = None, metadata_path: Path | None = None,
) -> int:
    run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
    canonical = PROCESSED / "canonical.jsonl"
    paths = {
        "ontology": REPO_ROOT / "ontology" / "vietheritage.ttl",
        "asserted": data_path or RDF_DIR / "vietheritage.ttl",
        "external-links": RDF_DIR / "external-links.ttl",
        "inferred": RDF_DIR / "inferred.ttl",
        "metadata": metadata_path or RDF_DIR / "dataset-metadata.ttl",
    }
    errors: list[dict] = []
    graphs = {}
    records = []
    count = 0
    for name, path in {"canonical": canonical, "schema": SCHEMA, **paths}.items():
        if not path.is_file():
            errors.append(issue("VALIDATION_INPUT_MISSING", message=f"Required artifact missing: {name}.", artifact=name))
    if canonical.is_file() and SCHEMA.is_file():
        try:
            schema = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
            for number, line in enumerate(canonical.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                count += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(issue("CANONICAL_INVALID", message=str(exc), line=number))
                    continue
                problems = list(schema.iter_errors(record))
                errors.extend(issue("CANONICAL_INVALID", message=error.message,
                                    line=number, field=error.json_path) for error in problems)
                if not problems:
                    records.append(record)
        except (OSError, ValueError) as exc:
            errors.append(issue("CANONICAL_INVALID", message=str(exc)))
    for name, path in paths.items():
        if not path.is_file():
            continue
        try:
            graphs[name] = Graph().parse(path, format="turtle")
        except (OSError, SyntaxError, ValueError, ParserError) as exc:
            errors.append(issue("RDF_PARSE_ERROR", message=str(exc), artifact=name))
    axioms = dict.fromkeys(("AX-004", "AX-008", "AX-009"), "NOT_RUN")
    shacl_status = "NOT_RUN"
    final = Graph()
    if len(graphs) == len(paths):
        assertions = Graph()
        for name, graph in graphs.items():
            final += graph
            if name != "inferred":
                assertions += graph
        # Check assertions first: domain/range entailments cannot repair bad input.
        before = validate_semantics(assertions, graphs["ontology"])
        reviews = []
        review_path = REPO_ROOT / "data" / "linking" / "link_review.csv"
        if any(assertions.triples((None, OWL.sameAs, None))) and review_path.is_file():
            try:
                with review_path.open(encoding="utf-8", newline="") as handle:
                    reviews = list(csv.DictReader(handle))
            except (OSError, csv.Error) as exc:
                errors.append(issue("LINK_EVIDENCE_INVALID", message=str(exc)))
        result = validate_public_graph(
            final, graphs["ontology"], assertions=assertions, canonical_records=records,
            link_reviews=reviews, run_mode=run_mode, require_dataset=True,
        )
        errors.extend(before["errors"])
        errors.extend(result["errors"])
        for axiom in axioms:
            statuses = (before["axioms"][axiom], result.get("axioms", {}).get(axiom, "NOT_RUN"))
            axioms[axiom] = "FAIL" if "FAIL" in statuses else statuses[1]
        if "conforms" in result:
            shacl_status = "PASS" if result["conforms"] else "FAIL"
    payload = report(
        errors, run_id=run_id, run_mode=run_mode, canonical_records=count,
        shacl=shacl_status, conforms=shacl_status == "PASS", axioms=axioms, final_triples=len(final),
        graphs={name: {"path": str(path), "triples": len(graphs[name]) if name in graphs else None}
                for name, path in paths.items()},
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # Keep the previous run-mode aliases for existing report consumers.
    for directory in {run_id, run_mode}:
        out = REPO_ROOT / "reports" / directory
        out.mkdir(parents=True, exist_ok=True)
        for filename in ("validation.json", "rdf_validation.json", "shacl.json"):
            (out / filename).write_text(text, encoding="utf-8")
    print(f"validate ({run_mode}): {payload['status']} ({count} canonical records); reports/{run_id}/rdf_validation.json")
    return 0 if not errors else 1
