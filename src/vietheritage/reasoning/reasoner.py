"""AX-001–AX-007/010/011/012 via local Apache Jena 4.10.0 OWL Mini (COMP-008).

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

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from vietheritage.validation.semantic import report, validate_axioms

REPO_ROOT = Path(__file__).resolve().parents[3]
RDF_DIR = REPO_ROOT / "data" / "rdf"
ONTOLOGY = REPO_ROOT / "ontology" / "vietheritage.ttl"
ASSERTED = RDF_DIR / "vietheritage.ttl"
INFERRED = RDF_DIR / "inferred.ttl"
REPORT = RDF_DIR / "reasoning-report.json"
FIXTURES = REPO_ROOT / "data" / "fixtures"
VALID_FIXTURE = FIXTURES / "semantic" / "axioms-valid.ttl"
AX011_FIXTURE = FIXTURES / "semantic" / "ax011-owa-no-location.ttl"
EXPECTED = FIXTURES / "expected" / "inferred.ttl"
JAVA_SOURCE = Path(__file__).with_name("OwlMiniReasoner.java")
ENGINE = "http://jena.hpl.hp.com/2003/OWLMiniFBRuleReasoner"
JENA_VERSION = "4.10.0"
AXIOMS = tuple(f"AX-{number:03d}" for number in range(1, 8)) + ("AX-010", "AX-011", "AX-012")
SEMANTIC_AXIOMS = ("AX-008", "AX-009", "AX-017")
AGGREGATE_AXIOMS = tuple(sorted(AXIOMS + SEMANTIC_AXIOMS))
VH = Namespace("http://localhost:3030/vietheritage/ontology/")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")
# Subjects identify each case in the authoritative expected subset.
EXPECTED_SUBJECTS = {
    "AX-001": VHR["site-ax001"],
    "AX-002": VHR["complex-ax002-inner"],
    "AX-003": VHR["site-ax002"],
    "AX-005": VHR["site-ax005"],
    "AX-006": VHR["site-ax006-b"],
    "AX-007": VHR["site-ax007"],
    "AX-010": VHR["site-ax010"],
    "AX-012": VHR["site-ax012"],
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
    axioms = {axiom: result["axioms"].get(axiom, "NOT_RUN") for axiom in SEMANTIC_AXIOMS}
    errors = [error for error in result["errors"] if error.get("axiom") in SEMANTIC_AXIOMS]
    successor_count = sum(1 for _ in data.triples((None, VH.hasHistoricalSuccessor, None)))
    payload["semantic_validation"] = report(
        errors, axioms=axioms,
        coverage={"AX-017": {"relation_triples": successor_count, "vacuous": successor_count == 0}},
    )
    payload["axioms"].update(axioms)
    if errors:
        raise ReasoningError(errors[0]["code"], "; ".join(error["message"] for error in errors))
    if any(status != "PASS" for status in axioms.values()):
        payload["semantic_validation"]["status"] = "NOT_RUN"
        raise ReasoningError("SEMANTIC_AXIOM_NOT_RUN", "Required semantic axioms were not all evaluated successfully.")


def _check_ax011(ontology: Graph, fixture: Graph, payload: dict) -> None:
    restrictions = {
        restriction
        for restriction in ontology.objects(VH.HeritageSite, RDFS.subClassOf)
        if (restriction, RDF.type, OWL.Restriction) in ontology
        and (restriction, OWL.onProperty, VH.locatedIn) in ontology
    }
    expected = Literal(1, datatype=XSD.nonNegativeInteger)
    valid = len(restrictions) == 1
    if valid:
        restriction = next(iter(restrictions))
        valid = (
            set(ontology.objects(restriction, OWL.minCardinality)) == {expected}
            and not list(ontology.objects(restriction, OWL.onClass))
            and not list(ontology.objects(restriction, OWL.onDataRange))
        )
    if not valid:
        payload["axioms"]["AX-011"] = "FAIL"
        raise ReasoningError("AXIOM_DECLARATION_MISSING", "AX-011 exact minCardinality restriction is missing.")

    site = VHR["site-ax011-owa"]
    inferred, inferred_count = reason([ontology, fixture])
    named_locations = {
        value for value in (fixture + inferred).objects(site, VH.locatedIn)
        if isinstance(value, URIRef)
    }
    payload["fixture_verification"]["AX-011"] = {
        "input": str(AX011_FIXTURE),
        "source_triples": len(ontology + fixture),
        "inferred_triples": inferred_count,
        "named_locations": len(named_locations),
        "status": "PASS" if not named_locations else "FAIL",
        "owa": True,
    }
    payload["axioms"]["AX-011"] = "PASS" if not named_locations else "FAIL"
    if named_locations:
        raise ReasoningError("INFERENCE_UNEXPECTED", "AX-011 materialized a named locatedIn value.")


def run(
    run_mode: str = "sample", *, run_id: str | None = None,
    refresh_metadata: bool = True,
) -> int:
    run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
    report_payload = {
        "run_id": run_id, "run_mode": run_mode, "engine": ENGINE,
        "jena_version": JENA_VERSION, "scope": list(AXIOMS), "status": "FAIL",
        "aggregate_scope": list(AGGREGATE_AXIOMS),
        "axioms": dict.fromkeys(AGGREGATE_AXIOMS, "NOT_RUN"),
        "source_triples": 0, "inferred_triples": 0, "closure_triples": 0,
    }
    try:
        for path in (ONTOLOGY, ASSERTED, VALID_FIXTURE, AX011_FIXTURE, EXPECTED):
            if not path.is_file():
                raise ReasoningError("REASONING_INPUT_MISSING", f"Turtle input missing: {path}")
        ontology = Graph().parse(ONTOLOGY, format="turtle")
        asserted = Graph().parse(ASSERTED, format="turtle")
        source = ontology + asserted
        fixture = Graph().parse(VALID_FIXTURE, format="turtle")
        ax011_fixture = Graph().parse(AX011_FIXTURE, format="turtle")
        expected = Graph().parse(EXPECTED, format="turtle")
        report_payload["ontology_triples"] = len(ontology)
        report_payload["ontology_version"] = str(next(ontology.objects(None, OWL.versionInfo), "unknown"))
        report_payload["asserted_triples"] = len(asserted)
        report_payload["production_inputs"] = [str(ONTOLOGY), str(ASSERTED)]
        report_payload["source_triples"] = len(source)
        _check_semantic_axioms(source, ontology, report_payload)
        inferred, inferred_count = reason([source])
        # Acceptance fixtures have their own Jena model and never enter the
        # production source, delta, closure counts, or serialized artifact.
        fixture_inferred, fixture_count = reason([ontology, fixture])
        report_payload["fixture_verification"] = {
            "inputs": [str(ONTOLOGY), str(VALID_FIXTURE)],
            "source_triples": len(ontology + fixture),
            "inferred_triples": fixture_count,
        }
        _check_semantic_axioms(ontology + fixture + fixture_inferred, ontology, report_payload)
        report_payload["fixture_verification"]["semantic_validation"] = report_payload["semantic_validation"]
        report_payload["axioms"]["AX-004"] = "PASS"
        for axiom, subject in EXPECTED_SUBJECTS.items():
            triples = list(expected.triples((subject, None, None)))
            report_payload["axioms"][axiom] = (
                "PASS" if triples and all(triple in fixture_inferred for triple in triples) else "FAIL"
            )
        missing = sorted(" ".join(term.n3() for term in triple) + " ."
                         for triple in expected if triple not in fixture_inferred)
        report_payload["expected_triples"] = len(expected)
        report_payload["missing_triples"] = missing
        control = (VHR["site-ax010-control"], RDF.type, VH.HeritageSiteWithHistoricalBuilder)
        unexpected = [" ".join(term.n3() for term in control) + " ."] if control in fixture_inferred else []
        report_payload["unexpected_triples"] = unexpected
        if unexpected:
            report_payload["axioms"]["AX-010"] = "FAIL"
            raise ReasoningError("INFERENCE_UNEXPECTED", "AX-010 was inferred for the associatedWithPerson-only control.")
        _check_ax011(ontology, ax011_fixture, report_payload)
        if missing or any(status != "PASS" for status in report_payload["axioms"].values()):
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
    if refresh_metadata:
        from vietheritage.rdf.generator import refresh_dataset_metadata_metrics
        refresh_dataset_metadata_metrics()
    print(f"reason ({run_mode}): {inferred_count} inferred triples -> {INFERRED}; report: {report_dir}")
    return 0
