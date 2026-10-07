"""AX-001–AX-007/010/011 acceptance using real Jena and authoritative fixtures.

These tests fail (rather than silently skip or substitute an engine) if the
required local Apache Jena runtime is unavailable.
"""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF

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
    ("AX-010", VHR["site-ax010"]),
], ids=["AX-001", "AX-002", "AX-003", "AX-005", "AX-006", "AX-007", "AX-010"])
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


@pytest.mark.parametrize("identity", ["direct", "reverse", "transitive"])
def test_same_and_different_identity_is_still_rejected(identity) -> None:
    # Untyped individuals exercise Jena's identity-conflict rule itself,
    # independently of its separate disjoint-class validation rules.
    left, right, middle = VHR["registry-left"], VHR["registry-right"], VHR["registry-middle"]
    invalid = Graph().add((left, OWL.differentFrom, right))
    if identity == "transitive":
        invalid.add((left, OWL.sameAs, middle))
        invalid.add((middle, OWL.sameAs, right))
    elif identity == "reverse":
        invalid.add((right, OWL.sameAs, left))
    else:
        invalid.add((left, OWL.sameAs, right))
    with pytest.raises(reasoner.OntologyInconsistent, match="both same and different"):
        reasoner.reason([invalid])


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
    assert report["scope"] == [f"AX-{i:03d}" for i in range(1, 8)] + ["AX-010", "AX-011"]
    assert report["aggregate_scope"] == [f"AX-{i:03d}" for i in range(1, 12)] + ["AX-017"]
    assert set(report["axioms"]) == set(report["aggregate_scope"])
    if valid:
        assert result == 0, report
        assert report["status"] == "PASS"
        assert set(report["axioms"].values()) == {"PASS"}
        assert report["fixture_verification"]["AX-011"]["status"] == "PASS"
        assert report["fixture_verification"]["AX-011"]["named_locations"] == 0
        inferred = Graph().parse(reasoner.INFERRED, format="turtle")
        assert set(expected) <= set(inferred)
        assert set(inferred).isdisjoint(set(ontology) | set(fixture))
        assert report["inferred_triples"] == len(inferred)
    else:
        assert result != 0
        assert report["status"] == "ONTOLOGY_INCONSISTENT", report
        assert report["axioms"]["AX-004"] == "ONTOLOGY_INCONSISTENT"
        assert not reasoner.INFERRED.exists()


def test_production_artifact_isolated_from_fixture_acceptance(inputs, monkeypatch, tmp_path):
    ontology, fixture, expected = inputs
    asserted = Graph()
    site, person = VHR["registry-production"], VHR["person-production"]
    asserted.add((site, RDF.type, VH.HeritageSite))
    asserted.add((site, VH.recognizedBy, VHR["organization-unesco"]))
    asserted.add((site, VH.builtBy, person))
    asserted.add((person, RDF.type, VH.HistoricalPerson))
    asserted_path = tmp_path / "asserted.ttl"
    asserted.serialize(asserted_path, format="turtle")
    monkeypatch.setattr(reasoner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reasoner, "ASSERTED", asserted_path)
    monkeypatch.setattr(reasoner, "INFERRED", tmp_path / "rdf/inferred.ttl")
    monkeypatch.setattr(reasoner, "REPORT", tmp_path / "rdf/reasoning-report.json")

    def unexpected_refresh():
        pytest.fail("Metadata refresh must be deferred until final validation passes")

    monkeypatch.setattr("vietheritage.rdf.generator.refresh_dataset_metadata_metrics", unexpected_refresh)
    assert reasoner.run("full", run_id="production-isolation", refresh_metadata=False) == 0
    result = json.loads(reasoner.REPORT.read_text())
    inferred = Graph().parse(reasoner.INFERRED, format="turtle")
    fixture_resources = {term for triple in fixture for term in triple
                         if isinstance(term, URIRef) and str(term).startswith(str(VHR))}
    fixture_resources -= {term for triple in ontology for term in triple}
    assert fixture_resources.isdisjoint(term for triple in inferred for term in triple)
    assert set(expected).isdisjoint(inferred)
    assert (site, RDF.type, VH.UNESCOHeritageSite) in inferred
    assert (site, VH.associatedWithPerson, person) in inferred
    assert (site, RDF.type, VH.HeritageSiteWithHistoricalBuilder) in inferred
    assert result["ontology_triples"] == len(ontology)
    assert result["asserted_triples"] == len(asserted)
    assert result["source_triples"] == len(ontology + asserted)
    assert result["inferred_triples"] == len(inferred)
    assert result["closure_triples"] == len(ontology + asserted) + len(inferred)
    assert result["fixture_verification"]["source_triples"] == len(ontology + fixture)
    assert set(result["axioms"].values()) == {"PASS"}
    assert result["semantic_validation"]["coverage"]["AX-017"] == {"relation_triples": 0, "vacuous": True}
    assert result["fixture_verification"]["semantic_validation"]["coverage"]["AX-017"] == {
        "relation_triples": 1, "vacuous": False,
    }


def test_ax010_association_only_control_is_not_classified(inputs, actual):
    ontology, fixture, _ = inputs
    inferred, _ = actual
    cls = VH.HeritageSiteWithHistoricalBuilder
    assert not list((ontology + fixture).subjects(RDF.type, cls))
    control = VHR["site-ax010-control"]
    assert (control, VH.associatedWithPerson, VHR["person-ax010-control"]) in fixture
    assert not list(fixture.objects(control, VH.builtBy))
    assert not list(inferred.objects(control, VH.builtBy))
    assert (control, RDF.type, cls) not in inferred


def test_ax010_range_driven_inference_with_current_ontology(inputs):
    ontology, _, _ = inputs
    site, person = VHR["site-ax010-range"], VHR["person-ax010-range"]
    data = Graph().add((site, VH.builtBy, person))
    expected = {
        (site, RDF.type, VH.HeritageSite),
        (person, RDF.type, VH.HistoricalPerson),
        (site, RDF.type, VH.HeritageSiteWithHistoricalBuilder),
    }
    assert expected.isdisjoint(ontology + data)
    inferred, _ = reasoner.reason([ontology, data])
    assert expected <= set(inferred)


def test_ax010_can_overlap_existing_site_subclasses(inputs):
    ontology, _, _ = inputs
    site, person = VHR["site-ax010-overlap"], VHR["person-ax010-overlap"]
    data = Graph().add((site, VH.builtBy, person)).add((person, RDF.type, VH.HistoricalPerson))
    for cls in (VH.HistoricalSite, VH.ReligiousSite, VH.ArchaeologicalSite,
                VH.ArchitecturalSite, VH.UNESCOHeritageSite):
        data.add((site, RDF.type, cls))
    inferred, _ = reasoner.reason([ontology, data])
    assert (site, RDF.type, VH.HeritageSiteWithHistoricalBuilder) in inferred


def test_ax011_owa_fixture_is_consistent_without_a_named_location(inputs):
    ontology, _, _ = inputs
    fixture = Graph().parse(
        FIXTURES / "semantic/ax011-owa-no-location.ttl", format="turtle"
    )
    site = VHR["site-ax011-owa"]
    assert (site, RDF.type, VH.HeritageSite) in fixture
    assert not list(fixture.objects(site, VH.locatedIn))

    inferred, _ = reasoner.reason([ontology, fixture])

    assert not any(isinstance(value, URIRef) for value in inferred.objects(site, VH.locatedIn))


def test_nested_has_member_entails_part_chain_without_retyping(inputs) -> None:
    ontology = inputs[0]
    outer, inner, site = VHR["complex-member-outer"], VHR["complex-member-inner"], VHR["site-member"]
    data = Graph()
    data.add((outer, RDF.type, VH.HeritageComplex))
    data.add((inner, RDF.type, VH.HeritageComplex))
    data.add((site, RDF.type, VH.HeritageSite))
    data.add((outer, VH.hasMember, inner))
    data.add((inner, VH.hasMember, site))

    inferred, _ = reasoner.reason([ontology, data])

    for triple in (
        (inner, VH.partOf, outer), (site, VH.partOf, inner), (site, VH.partOf, outer),
        (outer, VH.hasPart, inner), (inner, VH.hasPart, site),
    ):
        assert triple in inferred
    assert (inner, RDF.type, VH.HeritageSite) not in inferred
    assert (site, RDF.type, VH.HeritageComplex) not in inferred
