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
    assert set(report["axioms"].values()) == {"NOT_RUN"}
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
