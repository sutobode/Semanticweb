"""AX-001–AX-007 via local Apache Jena 4.10.0 OWL Mini (COMP-008).

Set JENA_HOME to an unpacked Jena distribution, or JENA_CLASSPATH to its local
jars. A JDK (Java source-file launcher, Java 11+) is required; JAVA_HOME is
honoured when set. No dependencies or RDF imports are fetched at runtime.
RDFLib handles RDF I/O only; inference and consistency checking belong to Jena.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from rdflib import Graph, Namespace

from vietheritage.validation.semantic import report, validate_axioms

REPO_ROOT = Path(__file__).resolve().parents[3]
RDF_DIR = REPO_ROOT / "data" / "rdf"
ONTOLOGY = REPO_ROOT / "ontology" / "vietheritage.ttl"
ASSERTED = RDF_DIR / "vietheritage.ttl"
INFERRED = RDF_DIR / "inferred.ttl"
REPORT = RDF_DIR / "reasoning-report.json"
FIXTURES = REPO_ROOT / "data" / "fixtures"
VALID_FIXTURE = FIXTURES / "semantic" / "axioms-valid.ttl"
EXPECTED = FIXTURES / "expected" / "inferred.ttl"
JAVA_SOURCE = Path(__file__).with_name("OwlMiniReasoner.java")
ENGINE = "http://jena.hpl.hp.com/2003/OWLMiniFBRuleReasoner"
JENA_VERSION = "4.10.0"
AXIOMS = tuple(f"AX-{number:03d}" for number in range(1, 8))
SEMANTIC_AXIOMS = ("AX-008", "AX-009")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")
# Subjects identify each case in the authoritative expected subset.
EXPECTED_SUBJECTS = {
    "AX-001": VHR["site-ax001"],
    "AX-002": VHR["complex-ax002-inner"],
    "AX-003": VHR["site-ax002"],
    "AX-005": VHR["site-ax005"],
    "AX-006": VHR["site-ax006-b"],
    "AX-007": VHR["site-ax007"],
}


class ReasoningError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class OntologyInconsistent(ReasoningError):
    def __init__(self, message: str) -> None:
        super().__init__("ONTOLOGY_INCONSISTENT", message)


def _jena_command() -> list[str]:
    classpath = os.environ.get("JENA_CLASSPATH")
    if not classpath:
        home = os.environ.get("JENA_HOME")
        if not home or not list((Path(home) / "lib").glob("jena-core-*.jar")):
            raise ReasoningError(
                "JENA_UNAVAILABLE",
                "Apache Jena 4.10.0 is required: set JENA_HOME to a local Jena "
                "distribution or JENA_CLASSPATH to its local jars.",
            )
        classpath = str(Path(home).resolve() / "lib" / "*")

    java_home = os.environ.get("JAVA_HOME")
    java_name = "java.exe" if os.name == "nt" else "java"
    java = (
        shutil.which(str(Path(java_home) / "bin" / java_name))
        if java_home else shutil.which(java_name)
    )
    if not java:
        raise ReasoningError(
            "JENA_UNAVAILABLE", "A local JDK is required; set JAVA_HOME or add java to PATH."
        )
    return [java, "--class-path", classpath, str(JAVA_SOURCE)]


def reason(graphs: Iterable[Graph]) -> tuple[Graph, int]:
    """Return only novel entailments and their count; reject inconsistent input.

    The delta is computed inside Jena, before blank nodes are serialized, so
    asserted triples cannot be mistaken for deductions after a parser relabels
    their blank nodes. There is deliberately no fallback reasoning engine.
    """
    command = _jena_command()
    source = Graph()
    for graph in graphs:
        source += graph
        for prefix, namespace in graph.namespaces():
            source.bind(prefix, namespace)
    with TemporaryDirectory(prefix="vietheritage-owl-mini-") as directory:
        work = Path(directory)
        source_path = work / "source.ttl"
        inferred_path = work / "inferred.ttl"
        status_path = work / "status.txt"
        source.serialize(destination=source_path, format="turtle")
        try:
            result = subprocess.run(
                command + [str(source_path), str(inferred_path), str(status_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=300, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReasoningError("JENA_EXECUTION_FAILED", str(error)) from error
        status = status_path.read_text(encoding="utf-8").splitlines() if status_path.exists() else []
        if status and status[0] == "ONTOLOGY_INCONSISTENT":
            raise OntologyInconsistent("\n".join(status[1:]))
        if result.returncode != 0 or not status or status[0] != "PASS":
            detail = "\n".join(status) or result.stderr.strip() or result.stdout.strip()
            raise ReasoningError("JENA_EXECUTION_FAILED", detail or "Jena returned no status.")
        if not inferred_path.exists():
            raise ReasoningError("JENA_EXECUTION_FAILED", "Jena returned no inferred Turtle.")
        inferred = Graph().parse(inferred_path, format="turtle")
    return inferred, len(inferred)


def _check_semantic_axioms(data: Graph, ontology: Graph, payload: dict) -> None:
    result = validate_axioms(data, ontology)
    axioms = {axiom: result["axioms"][axiom] for axiom in SEMANTIC_AXIOMS}
    errors = [error for error in result["errors"] if error.get("axiom") in SEMANTIC_AXIOMS]
    payload["semantic_validation"] = report(errors, axioms=axioms)
    payload["axioms"].update(axioms)
    if errors:
        raise ReasoningError(errors[0]["code"], "; ".join(error["message"] for error in errors))


def run(run_mode: str = "sample", *, run_id: str | None = None) -> int:
    run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
    report_payload = {
        "run_id": run_id, "run_mode": run_mode, "engine": ENGINE,
        "jena_version": JENA_VERSION, "scope": list(AXIOMS), "status": "FAIL",
        "aggregate_scope": list(AXIOMS + SEMANTIC_AXIOMS),
        "axioms": dict.fromkeys(AXIOMS + SEMANTIC_AXIOMS, "NOT_RUN"),
        "source_triples": 0, "inferred_triples": 0, "closure_triples": 0,
    }
    try:
        for path in (ONTOLOGY, ASSERTED, VALID_FIXTURE, EXPECTED):
            if not path.is_file():
                raise ReasoningError("REASONING_INPUT_MISSING", f"Turtle input missing: {path}")
        ontology = Graph().parse(ONTOLOGY, format="turtle")
        source = ontology + Graph()
        for path in (ASSERTED, VALID_FIXTURE):
            source += Graph().parse(path, format="turtle")
        expected = Graph().parse(EXPECTED, format="turtle")
        report_payload["source_triples"] = len(source)
        _check_semantic_axioms(source, ontology, report_payload)
        inferred, inferred_count = reason([source])
        report_payload["axioms"]["AX-004"] = "PASS"
        for axiom, subject in EXPECTED_SUBJECTS.items():
            triples = list(expected.triples((subject, None, None)))
            report_payload["axioms"][axiom] = (
                "PASS" if triples and all(triple in inferred for triple in triples) else "FAIL"
            )
        missing = sorted(" ".join(term.n3() for term in triple) + " ."
                         for triple in expected if triple not in inferred)
        report_payload["expected_triples"] = len(expected)
        report_payload["missing_triples"] = missing
        if missing or "FAIL" in report_payload["axioms"].values():
            raise ReasoningError("INFERENCE_MISSING", "Required fixture entailments are missing.")
        _check_semantic_axioms(source + inferred, ontology, report_payload)
        INFERRED.parent.mkdir(parents=True, exist_ok=True)
        inferred.serialize(destination=INFERRED, format="turtle")
        report_payload.update(
            status="PASS", inferred_triples=inferred_count,
            closure_triples=len(source) + inferred_count,
        )
    except ReasoningError as error:
        INFERRED.unlink(missing_ok=True)
        report_payload["error_code"] = error.code
        report_payload["message"] = str(error)
        if isinstance(error, OntologyInconsistent):
            report_payload["status"] = error.code
            report_payload["axioms"]["AX-004"] = error.code

    report_dir = REPO_ROOT / "reports" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_text = json.dumps(report_payload, indent=2)
    (report_dir / "reasoning.json").write_text(report_text, encoding="utf-8")
    # Preserve the existing metrics consumer's report location.
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report_text, encoding="utf-8")
    if report_payload["status"] != "PASS":
        print(f"reason ({run_mode}): {report_payload['error_code']}: {report_payload['message']}")
        return 1
    from vietheritage.rdf.generator import refresh_dataset_metadata_metrics
    refresh_dataset_metadata_metrics()
    print(f"reason ({run_mode}): {inferred_count} inferred triples -> {INFERRED}; report: {report_dir}")
    return 0
