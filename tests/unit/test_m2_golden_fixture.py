"""M2-19 — golden canonical fixture (Section 35) -> RDF -> CQ expected bindings.

Fixture ``data/fixtures/canonical.jsonl`` là input chung của cả nhóm; test này
khẳng định nó hợp lệ theo schema/mapping và sinh ra đúng ``expected/CQ*.json``
khi đi qua RDF generator thật (không dùng file TTL viết tay).

CQ02 (cần AX-005 hasValue), CQ09 (link review) và CQ10 (DBpedia snapshot) phụ
thuộc reasoner/linker nên không kiểm ở đây. CQ04/CQ07 cần một entailment RDFS
(``vh:builtBy rdfs:subPropertyOf vh:associatedWithPerson``) được áp tường minh.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from rdflib import Graph, Namespace

from vietheritage.mapping.mapper import load_mapping, validate_canonical
from vietheritage.rdf import generator

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "canonical.jsonl"
EXPECTED = ROOT / "data" / "fixtures" / "expected"
VH = Namespace("http://localhost:3030/vietheritage/ontology/")
CANONICAL_TYPES = {
    "HeritageSite", "AdministrativeArea", "HistoricalPerson", "HistoricalEvent", "HistoricalPeriod",
    "HeritageComplex", "Organization", "ArchitecturalStyle", "Museum", "IntangibleHeritage",
    "NationalTreasure", "DocumentaryHeritage", "Artisan", "CulturalObject",
}


@pytest.fixture(scope="module")
def records():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def graph(records):
    g = generator.build_graph(records) + Graph().parse(ROOT / "ontology" / "vietheritage.ttl")
    for subject, obj in list(g.subject_objects(VH.builtBy)):
        g.add((subject, VH.associatedWithPerson, obj))
    return g


def test_golden_fixture_size_and_types(records):
    assert 20 <= len(records) <= 30
    assert {record["entity_type"] for record in records} == CANONICAL_TYPES
    ids = [record["entity_id"] for record in records]
    assert len(ids) == len(set(ids))
    for required in ("registry-dsvh-national-monument-000001", "site-unesco-1", "site-archaeological-1",
                     "site-religious-1", "site-person-linked-2", "site-duplicate-1", "complex-thang-long",
                     "area-hanoi", "area-ba-dinh", "area-quang-ninh", "person-ly-thuong-kiet", "person-2",
                     "event-example", "period-example", "organization-unesco", "style-example"):
        assert required in ids


def test_golden_fixture_is_schema_and_mapping_valid(records):
    schema = json.loads((ROOT / "schema" / "canonical-record.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    mapping = load_mapping()
    for record in records:
        assert validate_canonical(record, mapping, validator) == [], record["entity_id"]


def test_golden_fixture_relations_point_to_fixture_entities(records):
    ids = {record["entity_id"] for record in records}
    for record in records:
        for targets in (record.get("relations") or {}).values():
            assert set(targets) <= ids
        if record.get("parent_area"):
            assert record["parent_area"] in ids


def _rows(result, variables):
    return {tuple(str(row[var]) for var in variables) for row in result}


@pytest.mark.parametrize("cq", ["CQ01", "CQ03", "CQ04", "CQ05", "CQ06", "CQ07", "CQ08"])
def test_golden_fixture_reproduces_expected_cq(graph, cq):
    query_path = next((ROOT / "sparql").glob(f"{cq}-*.rq"))
    expected = json.loads((EXPECTED / f"{cq}.json").read_text(encoding="utf-8"))
    variables = expected["head"]["vars"]
    expected_rows = {tuple(binding[var]["value"] for var in variables) for binding in expected["results"]["bindings"]}
    actual = graph.query(query_path.read_text(encoding="utf-8"))
    assert _rows(actual, variables) == expected_rows
