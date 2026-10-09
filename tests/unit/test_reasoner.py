"""Reasoning adapter failure/report contracts, independent of Jena availability."""
import json
import os
import re
from pathlib import Path

import pytest
from rdflib import Graph

from vietheritage.reasoning import reasoner


@pytest.fixture
def output_paths(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(reasoner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reasoner, "INFERRED", tmp_path / "rdf" / "inferred.ttl")
    monkeypatch.setattr(reasoner, "REPORT", tmp_path / "rdf" / "reasoning-report.json")
    monkeypatch.setattr(reasoner, "ASSERTED", reasoner.VALID_FIXTURE)
    return tmp_path


def test_missing_jena_fails_without_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("JENA_CLASSPATH", raising=False)
    monkeypatch.setenv("JENA_HOME", str(tmp_path / "missing-jena"))
    fixture = Graph().parse(reasoner.VALID_FIXTURE, format="turtle")
    with pytest.raises(reasoner.ReasoningError, match="Apache Jena 4.10.0") as caught:
        reasoner.reason([fixture])
    assert caught.value.code == "JENA_UNAVAILABLE"


def test_java_home_resolves_executable_with_spaces(monkeypatch, tmp_path: Path) -> None:
    java_home = tmp_path / "local jdk"
    java = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    java.parent.mkdir(parents=True)
    java.touch()
    java.chmod(0o755)
    monkeypatch.setenv("JAVA_HOME", str(java_home))
    monkeypatch.setenv("JENA_CLASSPATH", "local-jena.jar")
    monkeypatch.setenv("PATH", "")
    assert reasoner._jena_command()[0] == str(java)


def test_unavailable_jena_reports_failure(monkeypatch, output_paths: Path) -> None:
    monkeypatch.delenv("JENA_CLASSPATH", raising=False)
    monkeypatch.setenv("JENA_HOME", str(output_paths / "missing-jena"))
    assert reasoner.run() == 1
    reports = list((output_paths / "reports").glob("*/reasoning.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9]{6}", report["run_id"])
    assert reports[0].parent.name == report["run_id"]
    assert report["status"] == "FAIL"
    assert report["error_code"] == "JENA_UNAVAILABLE"
    assert {report["axioms"][axiom] for axiom in reasoner.AXIOMS} == {"NOT_RUN"}
    assert {report["axioms"][axiom] for axiom in reasoner.SEMANTIC_AXIOMS} == {"PASS"}
    assert not reasoner.INFERRED.exists()


def test_missing_entailment_fails_subset_gate(monkeypatch, output_paths: Path) -> None:
    # Exercise the output gate, not inference: take its data from the expected file.
    incomplete = Graph().parse(reasoner.EXPECTED, format="turtle")
    incomplete.remove((reasoner.EXPECTED_SUBJECTS["AX-005"], None, None))
    monkeypatch.setattr(reasoner, "reason", lambda graphs: (incomplete, len(incomplete)))
    assert reasoner.run(run_id="20260922T000000Z-abc123") == 1
    report = json.loads(reasoner.REPORT.read_text())
    assert report["status"] == "FAIL"
    assert report["error_code"] == "INFERENCE_MISSING"
    assert report["axioms"]["AX-005"] == "FAIL"
    assert len(report["missing_triples"]) == 1
    assert not reasoner.INFERRED.exists()


def test_inconsistency_propagates_to_report(monkeypatch, output_paths: Path) -> None:
    # The actual contradictory fixture is tested against Jena in test_reasoning.py.
    def inconsistent(graphs):
        raise reasoner.OntologyInconsistent("Jena consistency diagnostic")

    monkeypatch.setattr(reasoner, "reason", inconsistent)
    reasoner.INFERRED.parent.mkdir(parents=True)
    reasoner.INFERRED.write_text(reasoner.EXPECTED.read_text(encoding="utf-8"), encoding="utf-8")
    assert reasoner.run(run_id="20260922T000000Z-abc123") == 1
    report = json.loads(reasoner.REPORT.read_text())
    assert report["status"] == "ONTOLOGY_INCONSISTENT"
    assert report["error_code"] == "ONTOLOGY_INCONSISTENT"
    assert report["axioms"]["AX-004"] == "ONTOLOGY_INCONSISTENT"
    assert "Jena consistency diagnostic" in report["message"]
    assert not reasoner.INFERRED.exists()


@pytest.mark.parametrize("axiom", ["AX-008", "AX-009", "AX-017"])
def test_semantic_failure_blocks_aggregate_with_specific_code(axiom, monkeypatch, output_paths):
    expected = json.loads((reasoner.FIXTURES / "expected/semantic-validation.json").read_text())[axiom]
    monkeypatch.setattr(reasoner, "ASSERTED", reasoner.FIXTURES.parents[1] / expected["invalid_input"])
    # No inference substitute: invalid semantic input is rejected before Jena.
    def unexpected_reason(graphs):
        pytest.fail("Jena must not adjudicate AX-008/009/017 validation failures")

    monkeypatch.setattr(reasoner, "reason", unexpected_reason)
    assert reasoner.run(run_id="semantic-failure") == 1
    result = json.loads((output_paths / "reports/semantic-failure/reasoning.json").read_text())
    assert result["aggregate_scope"] == [f"AX-{i:03d}" for i in range(1, 13)] + ["AX-017"]
    assert set(result["axioms"]) == set(result["aggregate_scope"])
    assert result["status"] == result["axioms"][axiom] == "FAIL"
    assert result["error_code"] == expected["expected_error_code"]
    assert result["semantic_validation"]["errors"][0]["code"] == expected["expected_error_code"]
    assert result["axioms"]["AX-004"] == "NOT_RUN"
    assert not reasoner.INFERRED.exists()


def test_ax010_unexpected_control_entailment_blocks_aggregate(monkeypatch, output_paths):
    from rdflib.namespace import RDF

    inferred = Graph().parse(reasoner.EXPECTED, format="turtle")
    inferred.add((reasoner.VHR["site-ax010-control"], RDF.type, reasoner.VH.HeritageSiteWithHistoricalBuilder))
    monkeypatch.setattr(reasoner, "reason", lambda graphs: (inferred, len(inferred)))
    assert reasoner.run(run_id="unexpected-ax010") == 1
    result = json.loads(reasoner.REPORT.read_text())
    assert result["axioms"]["AX-010"] == "FAIL"
    assert result["error_code"] == "INFERENCE_UNEXPECTED"
    assert len(result["unexpected_triples"]) == 1
    assert not reasoner.INFERRED.exists()


def test_semantic_not_run_is_not_promoted_to_pass(monkeypatch, output_paths):
    monkeypatch.setattr(reasoner, "validate_axioms", lambda *args: {
        "errors": [], "axioms": {"AX-008": "PASS", "AX-009": "PASS", "AX-017": "NOT_RUN"},
    })
    monkeypatch.setattr(reasoner, "reason", lambda graphs: pytest.fail("Unvalidated semantics must block Jena"))
    assert reasoner.run(run_id="semantic-not-run") == 1
    result = json.loads(reasoner.REPORT.read_text())
    assert result["status"] == "FAIL"
    assert result["error_code"] == "SEMANTIC_AXIOM_NOT_RUN"
    assert result["axioms"]["AX-017"] == "NOT_RUN"
    assert result["axioms"]["AX-010"] == "NOT_RUN"
    assert result["axioms"]["AX-011"] == "NOT_RUN"
    assert result["semantic_validation"]["status"] == "NOT_RUN"
    assert not reasoner.INFERRED.exists()
