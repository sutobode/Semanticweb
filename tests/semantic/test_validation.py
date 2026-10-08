"""Focused acceptance checks for the semantic-validation axiom contract."""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, XSD

from vietheritage.validation.semantic import (
    DEFAULT_BASE,
    validate_axioms,
    validate_semantics,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = json.loads((ROOT / "data/fixtures/expected/semantic-validation.json").read_text())


@pytest.fixture(scope="module")
def ontology() -> Graph:
    return Graph().parse(ROOT / "ontology/vietheritage.ttl", format="turtle")


def test_valid_axiom_fixture(ontology) -> None:
    expected = EXPECTED["AX-008"]
    data = Graph().parse(ROOT / expected["valid_input"], format="turtle")
    result = validate_axioms(data, ontology)
    assert result["status"] == expected["valid_status"]
    assert result["errors"] == []
    assert result["axioms"]["AX-008"] == result["axioms"]["AX-009"] == "PASS"
    assert result["axioms"]["AX-017"] == "PASS"


@pytest.mark.parametrize("axiom", ["AX-008", "AX-009"])
def test_invalid_axiom_fixture(axiom, ontology) -> None:
    expected = EXPECTED[axiom]
    data = Graph().parse(ROOT / expected["invalid_input"], format="turtle")
    result = validate_axioms(data, ontology)
    assert result["status"] == expected["invalid_status"]
    assert result["axioms"][axiom] == "FAIL"
    assert {error["code"] for error in result["errors"]} == {expected["expected_error_code"]}
    assert {error["axiom"] for error in result["errors"]} == {axiom}
    if "property" in expected:
        assert {error["property"] for error in result["errors"]} == {expected["property"]}


def test_missing_disjoint_union_branch_is_not_inconsistent_under_owa(ontology) -> None:
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    data = Graph().add((vh.example, RDF.type, vh.IntangibleHeritage))
    assert validate_axioms(data, ontology)["status"] == "PASS"


def test_recognition_properties_accept_heritage_complex(ontology) -> None:
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    data = Graph()
    data.add((vhr["complex-unesco-1358"], RDF.type, vh.HeritageComplex))
    data.add((vhr["organization-unesco"], RDF.type, vh.Organization))
    data.add((vhr["complex-unesco-1358"], vh.recognizedBy, vhr["organization-unesco"]))
    data.add((vhr["complex-unesco-1358"], vh.recognitionYear, Literal("2011", datatype=XSD.gYear)))

    assert validate_semantics(data, ontology)["status"] == "PASS"


def test_ax011_does_not_add_closed_world_location_validation(ontology) -> None:
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    data = Graph().add((vhr.site_without_asserted_location, RDF.type, vh.HeritageSite))
    result = validate_semantics(data, ontology)
    assert result["status"] == "PASS"
    assert "AX-011" not in result["axioms"]


@pytest.mark.parametrize("path", EXPECTED["AX-017"]["invalid_inputs"])
def test_ax017_invalid_fixtures_are_identity_aware(path, ontology):
    data = Graph().parse(ROOT / path, format="turtle")
    result = validate_semantics(data, ontology)
    assert result["status"] == result["axioms"]["AX-017"] == "FAIL"
    assert {error["code"] for error in result["errors"]} == {"ONTOLOGY_INCONSISTENT"}
    assert {error["axiom"] for error in result["errors"]} == {"AX-017"}
    assert {error["property"] for error in result["errors"]} == {EXPECTED["AX-017"]["property"]}


@pytest.mark.parametrize("edges", [[], [(0, 1)], [(0, 1), (1, 2), (2, 0)]],
                         ids=["no-successor", "directed-edge", "three-node-cycle"])
def test_ax017_does_not_require_successors_or_general_acyclicity(edges, ontology):
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    nodes = [vhr[f"event-ax017-{i}"] for i in range(3)]
    data = Graph()
    for node in nodes:
        data.add((node, RDF.type, vh.HistoricalEvent))
    for left, right in edges:
        data.add((nodes[left], vh.hasHistoricalSuccessor, nodes[right]))
    result = validate_semantics(data, ontology)
    assert result["status"] == result["axioms"]["AX-017"] == "PASS"
    assert result["errors"] == []


@pytest.mark.parametrize(("endpoint", "code"), [("source", "DOMAIN_VIOLATION"), ("target", "RANGE_VIOLATION")])
def test_ax017_wrong_types_keep_existing_domain_range_errors(endpoint, code, ontology):
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    left, right = vhr["event-ax017-left"], vhr["event-ax017-right"]
    data = Graph().add((left, vh.hasHistoricalSuccessor, right))
    data.add((left, RDF.type, vh.HeritageSite if endpoint == "source" else vh.HistoricalEvent))
    data.add((right, RDF.type, vh.HeritageSite if endpoint == "target" else vh.HistoricalEvent))
    result = validate_semantics(data, ontology)
    assert result["status"] == "FAIL"
    assert result["axioms"]["AX-017"] == "PASS"
    assert {error["code"] for error in result["errors"]} == {code}


def test_ax017_without_asymmetric_declaration_is_not_run(ontology):
    legacy = ontology + Graph()
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    legacy.remove((vh.hasHistoricalSuccessor, RDF.type, OWL.AsymmetricProperty))
    assert validate_axioms(Graph(), legacy)["axioms"]["AX-017"] == "NOT_RUN"


@pytest.mark.parametrize("member_type", ["HeritageSite", "HeritageComplex"])
def test_has_member_accepts_site_or_nested_complex(member_type, ontology):
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    data = Graph()
    data.add((vhr["complex-member-parent"], RDF.type, vh.HeritageComplex))
    data.add((vhr["member-target"], RDF.type, vh[member_type]))
    data.add((vhr["complex-member-parent"], vh.hasMember, vhr["member-target"]))
    result = validate_semantics(data, ontology)
    assert result["status"] == "PASS"
    assert result["errors"] == []


def test_has_member_rejects_other_heritage_branch(ontology):
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    vhr = Namespace(DEFAULT_BASE + "/resource/")
    data = Graph()
    data.add((vhr["complex-member-parent"], RDF.type, vh.HeritageComplex))
    data.add((vhr["museum-target"], RDF.type, vh.Museum))
    data.add((vhr["complex-member-parent"], vh.hasMember, vhr["museum-target"]))
    result = validate_semantics(data, ontology)
    assert result["status"] == "FAIL"
    assert [(error["code"], error["property"]) for error in result["errors"]] == [
        ("RANGE_VIOLATION", str(vh.hasMember)),
    ]


def test_production_has_member_hierarchy_meets_refined_range(ontology):
    vh = Namespace(DEFAULT_BASE + "/ontology/")
    production = Graph().parse(ROOT / "data/rdf/vietheritage.ttl", format="turtle")
    edges = set(production.subject_objects(vh.hasMember))
    data = Graph()
    for parent, member in edges:
        data.add((parent, vh.hasMember, member))
        for node in (parent, member):
            for cls in production.objects(node, RDF.type):
                data.add((node, RDF.type, cls))
    member_types = [
        "HeritageComplex" if (member, RDF.type, vh.HeritageComplex) in production else "HeritageSite"
        for _, member in edges
    ]
    assert len(edges) == 16
    assert sorted(member_types).count("HeritageSite") == 15
    assert member_types.count("HeritageComplex") == 1
    nested = next(member for _, member in edges if (member, RDF.type, vh.HeritageComplex) in production)
    assert (nested, RDF.type, vh.HeritageSite) not in production
    result = validate_semantics(data, ontology)
    assert result["status"] == "PASS", result["errors"]
