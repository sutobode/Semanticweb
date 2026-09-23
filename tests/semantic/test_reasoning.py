"""AX-001–AX-007 acceptance checks using real Jena and authoritative fixtures.

These tests fail (rather than silently skip or substitute an engine) if the
required local Apache Jena runtime is unavailable.
"""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from vietheritage.reasoning import reasoner

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology/vietheritage.ttl"
FIXTURES = ROOT / "data/fixtures"
VH = Namespace("http://localhost:3030/vietheritage/ontology/")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")


@pytest.fixture(scope="module")
def inputs() -> tuple[Graph, Graph, Graph]:
    return (
        Graph().parse(ONTOLOGY, format="turtle"),
        Graph().parse(FIXTURES / "semantic/axioms-valid.ttl", format="turtle"),
        Graph().parse(FIXTURES / "expected/inferred.ttl", format="turtle"),
    )


@pytest.fixture(scope="module")
def actual(inputs) -> tuple[Graph, int]:
    ontology, fixture, _ = inputs
    return reasoner.reason([ontology, fixture])


@pytest.mark.parametrize(("axiom", "subject"), [
    ("AX-001", VHR["site-ax001"]),
    ("AX-002", VHR["complex-ax002-inner"]),
    ("AX-003", VHR["site-ax002"]),
    ("AX-005", VHR["site-ax005"]),
    ("AX-006", VHR["site-ax006-b"]),
    ("AX-007", VHR["site-ax007"]),
], ids=["AX-001", "AX-002", "AX-003", "AX-005", "AX-006", "AX-007"])
def test_axiom_entailments(axiom, subject, inputs, actual) -> None:
    ontology, fixture, expected = inputs
    inferred, _ = actual
    required = set(expected.triples((subject, None, None)))
    assert required, f"No authoritative expectation found for {axiom}"
    assert required.isdisjoint(set(ontology) | set(fixture)), "Entailment was already asserted"
    assert required <= set(inferred), f"{axiom}: missing {required - set(inferred)}"


def test_complete_expected_subset_and_delta(inputs, actual) -> None:
    ontology, fixture, expected = inputs
    inferred, count = actual
    assert set(expected) <= set(inferred), f"Missing: {set(expected) - set(inferred)}"
    assert set(inferred).isdisjoint(set(ontology) | set(fixture))
    assert count == len(inferred)
    assert (VHR["site-ax005"], RDF.type, VH.UNESCOHeritageSite) not in fixture
    assert (VHR["person-ax007"], RDF.type, VH.HistoricalPerson) in fixture


def test_ax004_inconsistent_fixture_rejected(inputs) -> None:
    ontology, _, _ = inputs
    invalid = Graph().parse(FIXTURES / "semantic/ax004-inconsistent.ttl", format="turtle")
    with pytest.raises(reasoner.OntologyInconsistent) as caught:
        reasoner.reason([ontology, invalid])
    assert caught.value.code == "ONTOLOGY_INCONSISTENT"
    assert str(caught.value), "Preserve Jena's consistency diagnostics"


def test_ax004_all_disjoint_checks_inferred_types(inputs) -> None:
    # Small extra case needed to exercise OWL 2 -> OWL 1 disjointness expansion.
    ontology, fixture, _ = inputs
    invalid = fixture + Graph()
    invalid.add((VHR["site-ax001"], RDF.type, VH.Museum))
    with pytest.raises(reasoner.OntologyInconsistent):
        reasoner.reason([ontology, invalid])


@pytest.mark.parametrize("valid", [True, False], ids=["valid-output", "AX-004-report"])
def test_reason_stage_artifact_and_status(valid, inputs, monkeypatch, tmp_path: Path) -> None:
    ontology, fixture, expected = inputs
    monkeypatch.setattr(reasoner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reasoner, "ASSERTED", FIXTURES / "semantic" / (
        "axioms-valid.ttl" if valid else "ax004-inconsistent.ttl"
    ))
    monkeypatch.setattr(reasoner, "INFERRED", tmp_path / "rdf/inferred.ttl")
    monkeypatch.setattr(reasoner, "REPORT", tmp_path / "rdf/reasoning-report.json")
    monkeypatch.setattr("vietheritage.rdf.generator.refresh_dataset_metadata_metrics", lambda: None)
    run_id = "20260922T000000Z-abc123"
    result = reasoner.run(run_id=run_id)
    report = json.loads((tmp_path / "reports" / run_id / "reasoning.json").read_text())
    assert report["engine"] == "http://jena.hpl.hp.com/2003/OWLMiniFBRuleReasoner"
    assert report["scope"] == [f"AX-{i:03d}" for i in range(1, 8)]
    assert report["aggregate_scope"] == [f"AX-{i:03d}" for i in range(1, 10)]
    assert set(report["axioms"]) == set(report["aggregate_scope"])
    if valid:
        assert result == 0, report
        assert report["status"] == "PASS"
        assert set(report["axioms"].values()) == {"PASS"}
        inferred = Graph().parse(reasoner.INFERRED, format="turtle")
        assert set(expected) <= set(inferred)
        assert set(inferred).isdisjoint(set(ontology) | set(fixture))
        assert report["inferred_triples"] == len(inferred)
    else:
        assert result != 0
        assert report["status"] == "ONTOLOGY_INCONSISTENT", report
        assert report["axioms"]["AX-004"] == "ONTOLOGY_INCONSISTENT"
        assert not reasoner.INFERRED.exists()
