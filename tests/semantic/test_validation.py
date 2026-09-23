"""Focused acceptance checks for the semantic-validation axiom contract."""
import json
from pathlib import Path

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from vietheritage.validation.semantic import DEFAULT_BASE, validate_axioms

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
