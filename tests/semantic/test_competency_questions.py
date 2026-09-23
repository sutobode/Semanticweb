"""PROJECT_SPEC 1.6.2 CQ acceptance on a small, offline public-graph fixture.

Uses the existing Jena runtime (JENA_HOME/JENA_CLASSPATH and JAVA_HOME), with no
Fuseki, external endpoint, generator, or substitute reasoning implementation.
The committed expected bindings are hand-derived, never recorded query output.
"""
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Dataset, Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

from vietheritage.reasoning import reasoner
from vietheritage.reporting import query_runner
from vietheritage.validation.semantic import DEFAULT_BASE, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data/fixtures"
VH = Namespace(DEFAULT_BASE + "/ontology/")
VHR = Namespace(DEFAULT_BASE + "/resource/")
QUERIES = {name[:4]: name for name in query_runner.CQ_CONTRACT}


def expected(cq):
    return json.loads((FIXTURES / "expected" / f"{cq}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def specification_queries():
    spec = (ROOT / "PROJECT_SPEC.md").read_text(encoding="utf-8")
    section = spec.split("# 24. Competency Questions", 1)[1].split("# 25. SPARQL Specification", 1)[0]
    return {"CQ" + number: text for number, text in re.findall(
        r"## CQ-(\d{2}).*?```sparql\n(.*?)```", section, flags=re.DOTALL,
    )}


@pytest.fixture(scope="module")
def components():
    ontology = Graph().parse(ROOT / "ontology/vietheritage.ttl", format="turtle")
    data = Graph().parse(FIXTURES / "cq-data.ttl", format="turtle")
    inferred, _ = reasoner.reason([ontology, data])
    return {
        "ontology": ontology,
        "data": data,
        "inferred": inferred,
        "verified": Graph().parse(FIXTURES / "cq-verified-links.ttl", format="turtle"),
        "snapshot": Graph().parse(FIXTURES / "external_snapshot.ttl", format="turtle"),
    }


def execute_local(components, cqs, work):
    dataset = Dataset()
    for name, graph in components.items():
        name = "external-links" if name in {"verified", "snapshot"} else name
        target = dataset.graph(URIRef(DEFAULT_BASE + "/graph/" + name))
        target += graph
    dataset_path = work / "public.trig"
    dataset.serialize(destination=dataset_path, format="trig")
    # Reuse the configured local Java/Jena launcher, replacing only its main.
    command = reasoner._jena_command()[:-1] + [
        str(Path(__file__).with_name("CqFixtureQuery.java")), str(dataset_path), str(work),
        *(str(ROOT / "sparql" / QUERIES[cq]) for cq in cqs),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return {cq: json.loads((work / f"{cq}.json").read_text(encoding="utf-8")) for cq in cqs}


@pytest.fixture(scope="module")
def actual(components, tmp_path_factory):
    return execute_local(components, QUERIES, tmp_path_factory.mktemp("cq-local"))


@pytest.mark.parametrize("cq", QUERIES)
def test_cq_contract_and_expected_bindings(cq, specification_queries, actual):
    text = (ROOT / "sparql" / QUERIES[cq]).read_text(encoding="utf-8")
    authoritative = specification_queries[cq]
    if cq in {"CQ09", "CQ10"}:
        # Approved Phase 4 clarification: exclude OWL Mini's reflexive identities
        # while preserving every other part of the Section 24 query templates.
        guard = "FILTER(?site != ?externalResource)"
        assert text.count(guard) == 1
        text = text.replace(guard, "")
    # Anchored in the normative specification, including constants, filters,
    # graph scope, projection, UNION/paths, aggregate ordering and limits.
    assert " ".join(text.split()) == " ".join(authoritative.split())
    variables = [str(var) for var in translateQuery(parseQuery(authoritative)).algebra.PV]
    wanted = expected(cq)  # Missing files fail, not skip.
    assert wanted["head"]["vars"] == query_runner.CQ_CONTRACT[QUERIES[cq]] == variables
    assert wanted["results"]["bindings"], "Every CQ fixture must exercise non-empty results"
    assert actual[cq]["head"]["vars"] == variables
    assert actual[cq]["results"]["bindings"] == wanted["results"]["bindings"]


def test_cq_fixture_validates_and_uses_existing_inference(components):
    ontology, data, inferred = (components[name] for name in ("ontology", "data", "inferred"))
    public = sum(components.values(), Graph())
    validation = validate_semantics(public, ontology, base=DEFAULT_BASE)
    assert validation["status"] == "PASS", validation
    for triple in (
        (VHR["site-unesco-1"], RDF.type, VH.UNESCOHeritageSite),
        (VHR["site-person-linked-2"], VH.associatedWithPerson, VHR["person-ly-thuong-kiet"]),
    ):
        assert triple not in data
        assert triple in inferred
    # CQ01 traverses the hierarchy; CQ06 must still count only direct locations.
    assert (VHR["site-in-sub-area-1"], VH.locatedIn, VHR["area-hanoi"]) not in public
    site = VHR["registry-dsvh-national-monument-000001"]
    assert (site, OWL.sameAs, site) in inferred  # The CQ09/10 guard must handle real closure.
    external_links = {triple for triple in public.triples((None, OWL.sameAs, None)) if triple[0] != triple[2]}
    assert external_links == set(components["verified"])


@pytest.mark.parametrize(("omitted", "cqs"), [
    ("inferred", ("CQ02", "CQ04", "CQ07")),
    ("verified", ("CQ09", "CQ10")),
    ("snapshot", ("CQ10",)),
])
def test_cq_graph_dependencies(components, omitted, cqs, tmp_path):
    graphs = {name: graph for name, graph in components.items() if name != omitted}
    results = execute_local(graphs, cqs, tmp_path)
    for cq in cqs:
        wanted = expected(cq)
        if cq == "CQ04":
            wanted["results"]["bindings"] = wanted["results"]["bindings"][1:]
        elif cq == "CQ07":
            wanted["results"]["bindings"][0]["siteCount"]["value"] = "2"
        else:
            wanted["results"]["bindings"] = []
        assert results[cq]["head"]["vars"] == wanted["head"]["vars"]
        assert results[cq]["results"]["bindings"] == wanted["results"]["bindings"]


def test_all_ten_local_cqs_pass_expected_binding_runner(actual, tmp_path):
    by_query = {(ROOT / "sparql" / name).read_text(encoding="utf-8"): actual[cq]
                for cq, name in QUERIES.items()}

    def local_response(url, **kwargs):
        result = by_query[kwargs["params"]["query"]]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: result)

    assert query_runner.run(endpoint="local-jena-fixture", request_get=local_response, reports_dir=tmp_path) == 0
    report = json.loads(next(tmp_path.glob("*/cq_results.json")).read_text(encoding="utf-8"))
    assert report["passed"] == report["total"] == 10
    assert all(row["status"] == "PASS" and row["expected_checked"] and row["row_count"] > 0
               for row in report["queries"])
