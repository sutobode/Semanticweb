"""Small in-memory cases for the Phase 2B2 publication contract."""
import csv
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, XSD

from vietheritage.cli import main
from vietheritage.validation import validator
from vietheritage.validation.policy import validate_public_graph
from vietheritage.validation.semantic import DEFAULT_BASE, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
VH = Namespace(DEFAULT_BASE + "/ontology/")
VHR = Namespace(DEFAULT_BASE + "/resource/")
ENTITY = VHR["registry-test"]
SOURCE = URIRef("https://dsvh.gov.vn/test")
QID = URIRef("https://www.wikidata.org/entity/Q42")
DBPEDIA = URIRef("http://dbpedia.org/resource/Test")


@pytest.fixture
def publication():
    ontology = Graph().parse(ROOT / "ontology/vietheritage.ttl", format="turtle")
    asserted = Graph().parse(data=f"""
        @prefix vh: <{VH}> .
        @prefix vhr: <{VHR}> .
        @prefix rdfs: <{RDFS}> .
        @prefix dcterms: <{DCTERMS}> .
        @prefix prov: <{PROV}> .
        @prefix xsd: <{XSD}> .
        vhr:registry-test a vh:HistoricalSite ; rdfs:label "Di tích"@vi ;
            dcterms:source <{SOURCE}> ; prov:wasDerivedFrom <{SOURCE}> ;
            dcterms:modified "2026-09-23"^^xsd:date ;
            prov:wasGeneratedBy vhr:activity-test .
    """, format="turtle")
    metadata = Graph().parse(data=f"""
        @prefix dcat: <http://www.w3.org/ns/dcat#> .
        @prefix dcterms: <{DCTERMS}> .
        @prefix prov: <{PROV}> .
        @prefix xsd: <{XSD}> .
        <{DEFAULT_BASE}/dataset/vietheritage> a dcat:Dataset ;
            dcterms:identifier "test" ; dcterms:title "Di sản"@vi ;
            dcterms:description "Dữ liệu kiểm thử"@vi ; dcterms:creator "Team" ;
            dcterms:created "2026-09-23"^^xsd:date ;
            dcterms:modified "2026-09-23"^^xsd:date ;
            dcterms:license <https://creativecommons.org/licenses/by-sa/4.0/> ;
            prov:wasGeneratedBy <{VHR}activity-test> ;
            dcat:accessURL <https://example.org/sparql> ;
            dcat:downloadURL <https://example.org/data.ttl> ;
            dcat:distribution <{VHR}distribution-ontology>, <{VHR}distribution-data>,
                <{VHR}distribution-links>, <{VHR}distribution-inferred>, <{VHR}distribution-metadata> .
        <{VHR}activity-test> a prov:Activity ;
            prov:startedAtTime "2026-09-23T00:00:00Z"^^xsd:dateTime .
        <{VHR}distribution-ontology> a dcat:Distribution .
        <{VHR}distribution-data> a dcat:Distribution .
        <{VHR}distribution-links> a dcat:Distribution .
        <{VHR}distribution-inferred> a dcat:Distribution .
        <{VHR}distribution-metadata> a dcat:Distribution .
    """, format="turtle")
    record = {
        "entity_id": "registry-test", "entity_type": "HeritageSite", "label_vi": "Di tích",
        "source_status": "registry_only", "retrieved_at": "2026-09-23T00:00:00Z",
        "registry_id": "test", "registry_category": "national_monument",
        "registry_url": str(SOURCE), "coverage_snapshot": "test",
        "provenance": {"source": str(SOURCE), "method": "registry", "license": "CC BY-SA 4.0"},
        "external_ids": {"wikidata": "Q42"},
    }
    reviews = [{"source_uri": str(ENTITY), "target_uri": str(DBPEDIA),
                "target_dataset": "dbpedia", "status": "verified", "type_compatible": "True"}]
    links = Graph().add((ENTITY, OWL.sameAs, QID)).add((ENTITY, OWL.sameAs, DBPEDIA))
    inferred = Graph().add((QID, OWL.sameAs, DBPEDIA))
    return {"ontology": ontology, "asserted": asserted, "external-links": links,
            "inferred": inferred, "metadata": metadata}, [record], reviews


def check(publication, **options):
    graphs, records, reviews = publication
    assertions = Graph()
    for name, graph in graphs.items():
        if name != "inferred":
            assertions += graph
    return validate_public_graph(
        assertions + graphs["inferred"], graphs["ontology"], assertions=assertions,
        canonical_records=records, link_reviews=reviews, require_dataset=True, **options,
    )


def codes(result):
    return {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("invalid_type", [VH.Organization, None], ids=["wrong-type", "untyped"])
def test_domain_range_require_asserted_types_and_allow_subclasses(publication, invalid_type):
    ontology = publication[0]["ontology"]
    data = Graph().add((ENTITY, RDF.type, VH.HistoricalSite))
    data.add((VHR["person-test"], RDF.type, VH.HistoricalPerson))
    data.add((ENTITY, VH.builtBy, VHR["person-test"]))
    data.add((VHR["area-child"], RDF.type, VH.AdministrativeArea))
    data.add((VHR["area-parent"], RDF.type, VH.AdministrativeArea))
    data.add((VHR["area-child"], VH.locatedIn, VHR["area-parent"]))
    assert validate_semantics(data, ontology)["status"] == "PASS"
    for node in (ENTITY, VHR["person-test"]):
        data.remove((node, RDF.type, None))
        if invalid_type:
            data.add((node, RDF.type, invalid_type))
    assert codes(validate_semantics(data, ontology)) == {"DOMAIN_VIOLATION", "RANGE_VIOLATION"}


@pytest.mark.parametrize(("prop", "value"), [
    (VH.constructionYear, Literal("not-a-year", datatype=XSD.gYear)),
    (VH.sourcePageId, Literal("42")),
])
def test_invalid_datatype(publication, prop, value):
    graphs, _, _ = publication
    graphs["asserted"].add((ENTITY, prop, value))
    assert "DATATYPE_VIOLATION" in codes(check(publication))


@pytest.mark.parametrize("label", [None, Literal("Site", lang="en"), Literal("", lang="vi")])
def test_vietnamese_label_required(publication, label):
    data = publication[0]["asserted"]
    data.remove((ENTITY, RDFS.label, None))
    if label is not None:
        data.add((ENTITY, RDFS.label, label))
    assert "MISSING_LABEL" in codes(check(publication))


def test_registry_only_and_final_public_union(publication):
    result = check(publication)
    assert result["status"] == "PASS", result
    assert result["errors"] == []
    # Entity generation activity is supplied only by the metadata component.
    publication[0]["metadata"].remove((None, PROV.startedAtTime, None))
    assert "PROVENANCE_VIOLATION" in codes(check(publication))


def test_registry_requires_official_common_provenance(publication):
    data = publication[0]["asserted"]
    data.remove((ENTITY, PROV.wasDerivedFrom, None))
    data.add((ENTITY, PROV.wasDerivedFrom, URIRef("https://example.org/test")))
    assert "PROVENANCE_VIOLATION" in codes(check(publication))


@pytest.mark.parametrize("missing", [VH.sourcePageId, VH.sourceTitle])
def test_wikipedia_enrichment_requires_both_metadata_fields(publication, missing):
    graphs, records, _ = publication
    records[0]["source_status"] = "registry+wikipedia"
    graphs["asserted"].add((ENTITY, VH.sourcePageId, Literal(42)))
    graphs["asserted"].add((ENTITY, VH.sourceTitle, Literal("Di tích")))
    assert check(publication)["status"] == "PASS"
    graphs["asserted"].remove((ENTITY, missing, None))
    result = check(publication)
    assert codes(result) == {"WIKIPEDIA_METADATA_MISSING"}
    assert result["errors"][0]["property"] == str(missing)


@pytest.mark.parametrize(("identifier", "mode", "code"), [
    ("registry-bad/id", "sample", "INVALID_URI"),
    ("site-fixture", "full", "FIXTURE_ID_IN_PRODUCTION"),
])
def test_invalid_uri_and_production_fixture_id(publication, identifier, mode, code):
    publication[0]["asserted"].add((VHR[identifier], RDF.type, VH.HeritageSite))
    assert code in codes(check(publication, run_mode=mode))


def test_uri_policy_uses_environment_base(publication, monkeypatch):
    base = "https://heritage.example/vietheritage"
    monkeypatch.setenv("VH_BASE_URI", base)
    assert "INVALID_URI" in codes(check(publication))
    graphs, records, reviews = publication
    for name, graph in graphs.items():
        graphs[name] = Graph()
        for triple in graph:
            graphs[name].add(tuple(URIRef(str(node).replace(DEFAULT_BASE, base))
                                   if isinstance(node, URIRef) else node for node in triple))
    reviews[0]["source_uri"] = str(ENTITY).replace(DEFAULT_BASE, base)
    assert check((graphs, records, reviews))["status"] == "PASS"


@pytest.mark.parametrize("invalid", ["qid", "unreviewed", "incompatible", "class", "inferred"])
def test_same_as_requires_approved_local_identity(publication, invalid):
    graphs, records, reviews = publication
    if invalid == "qid":
        records[0]["external_ids"]["wikidata"] = "Q99"
    elif invalid == "unreviewed":
        reviews[0]["status"] = "auto_candidate"
    elif invalid == "incompatible":
        reviews[0]["type_compatible"] = "False"
    elif invalid == "class":
        graphs["external-links"].add((DBPEDIA, RDF.type, OWL.Class))
    else:
        graphs["inferred"].add((ENTITY, OWL.sameAs, URIRef("https://www.wikidata.org/entity/Q99")))
    assert "INVALID_SAME_AS" in codes(check(publication))


@pytest.fixture
def workspace(publication, monkeypatch, tmp_path):
    graphs, records, reviews = publication
    paths = {
        "ontology": tmp_path / "ontology/vietheritage.ttl",
        "asserted": tmp_path / "data/rdf/vietheritage.ttl",
        "external-links": tmp_path / "data/rdf/external-links.ttl",
        "inferred": tmp_path / "data/rdf/inferred.ttl",
        "metadata": tmp_path / "data/rdf/dataset-metadata.ttl",
    }
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        graphs[name].serialize(path, format="turtle")
    processed = tmp_path / "data/processed"
    processed.mkdir()
    (processed / "canonical.jsonl").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    linking = tmp_path / "data/linking"
    linking.mkdir()
    with (linking / "link_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(reviews[0]))
        writer.writeheader()
        writer.writerows(reviews)
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validator, "PROCESSED", processed)
    monkeypatch.setattr(validator, "RDF_DIR", tmp_path / "data/rdf")
    return tmp_path, paths


@pytest.mark.parametrize(("component", "expected_code"), [
    (None, None),
    ("ontology", "MISSING_LABEL"),
    ("asserted", "RANGE_VIOLATION"),
    ("external-links", "INVALID_SAME_AS"),
    ("inferred", "CARDINALITY_VIOLATION"),
    ("metadata", "METADATA_VIOLATION"),
])
def test_cli_validates_all_public_components(publication, workspace, component, expected_code):
    root, paths = workspace
    graphs, _, _ = publication
    if component == "ontology":
        graphs[component].remove((VH.HeritageSite, RDFS.label, None))
    elif component == "asserted":
        person = URIRef("https://example.org/person")
        graphs[component].add((ENTITY, VH.builtBy, person))
        # A later entailment must not mask the missing asserted range type.
        graphs["inferred"].add((person, RDF.type, VH.HistoricalPerson))
        graphs["inferred"].serialize(paths["inferred"], format="turtle")
    elif component == "external-links":
        graphs[component].add((ENTITY, OWL.sameAs, URIRef("https://www.wikidata.org/entity/Q99")))
    elif component == "inferred":
        for year in ("1070", "1080"):
            graphs[component].add((ENTITY, VH.constructionYear, Literal(year, datatype=XSD.gYear)))
    elif component == "metadata":
        graphs[component].remove((None, DCTERMS.license, None))
    if component:
        graphs[component].serialize(paths[component], format="turtle")
    args = ["validate", "--run-mode", "sample", "--run-id", "20260923T000000Z-test01"]
    assert main(args) == (1 if expected_code else 0)
    report_path = root / "reports/20260923T000000Z-test01/rdf_validation.json"
    first = report_path.read_text(encoding="utf-8")
    result = json.loads(first)
    assert set(result["graphs"]) == set(graphs)
    assert result["final_triples"] == len(set().union(*(set(graph) for graph in graphs.values())))
    if expected_code:
        assert result["status"] == "FAIL"
        assert expected_code in codes(result)
    else:
        assert result["status"] == result["shacl"] == "PASS"
        assert result["errors"] == []
        assert result["axioms"]["AX-008"] == result["axioms"]["AX-009"] == "PASS"
    assert main(args) == (1 if expected_code else 0)
    assert report_path.read_text(encoding="utf-8") == first


@pytest.mark.parametrize(("failure", "code"), [
    ("missing", "VALIDATION_INPUT_MISSING"),
    ("turtle", "RDF_PARSE_ERROR"),
    ("canonical", "CANONICAL_INVALID"),
])
def test_input_failures_still_write_specific_report(workspace, failure, code):
    root, paths = workspace
    if failure == "missing":
        paths["inferred"].unlink()
    elif failure == "turtle":
        paths["external-links"].write_text("not valid turtle", encoding="utf-8")
    else:
        (root / "data/processed/canonical.jsonl").write_text("{", encoding="utf-8")
    assert main(["validate", "--run-id", "invalid-input"]) == 1
    result = json.loads((root / "reports/invalid-input/rdf_validation.json").read_text(encoding="utf-8"))
    assert result["status"] == "FAIL"
    assert code in codes(result)
