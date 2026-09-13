"""G6 unit tests — RDF Generator (COMP-005, TEST-021..027).

Kiểm tra parse Turtle, datatype, language tag, deterministic sort, provenance.
"""
import json
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, XSD

from vietheritage.rdf.generator import (
    VH,
    VHR,
    GEO,
    add_entity_type_triples,
    add_label_and_literals,
    add_provenance,
    add_relations,
    build_graph,
    record_to_triples,
    run,
    serialize_deterministic,
)

SAMPLE_HERITAGE_SITE = {
    "entity_id": "registry-dsvh-national-monument-000001",
    "entity_type": "HeritageSite",
    "label_vi": "Văn Miếu – Quốc Tử Giám",
    "source_status": "registry_only",
    "retrieved_at": "2026-09-13T00:00:00Z",
    "site_types": ["di tích lịch sử"],
    "coordinates": {"lat": 21.0278, "lon": 105.8357},
    "construction_year": 1070,
    "relations": {"located_in": ["area-hanoi"]},
    "provenance": {
        "source": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753",
        "method": "registry",
        "license": "CC BY-SA 4.0",
    },
}


def test_add_entity_type_triples_creates_rdf_type() -> None:
    g = Graph()
    add_entity_type_triples(g, "registry-x", SAMPLE_HERITAGE_SITE)
    assert (VHR["registry-x"], RDF.type, VH.HeritageSite) in g


def test_add_entity_type_triples_adds_site_subtype_from_site_types() -> None:
    g = Graph()
    add_entity_type_triples(g, "registry-x", SAMPLE_HERITAGE_SITE)
    assert (VHR["registry-x"], RDF.type, VH.HistoricalSite) in g


def test_add_label_and_literals_creates_vi_language_tag() -> None:
    g = Graph()
    add_label_and_literals(g, "registry-x", SAMPLE_HERITAGE_SITE)
    labels = list(g.objects(VHR["registry-x"], RDFS.label))
    assert any(label.language == "vi" for label in labels)


def test_add_label_and_literals_construction_year_has_gyear_datatype() -> None:
    g = Graph()
    add_label_and_literals(g, "registry-x", SAMPLE_HERITAGE_SITE)
    years = list(g.objects(VHR["registry-x"], VH.constructionYear))
    assert len(years) == 1
    assert years[0].datatype == XSD.gYear


def test_add_label_and_literals_coordinates_have_decimal_datatype() -> None:
    g = Graph()
    add_label_and_literals(g, "registry-x", SAMPLE_HERITAGE_SITE)
    lats = list(g.objects(VHR["registry-x"], GEO.lat))
    assert lats[0].datatype == XSD.decimal


def test_add_relations_creates_located_in_triple() -> None:
    g = Graph()
    add_relations(g, "registry-x", SAMPLE_HERITAGE_SITE)
    assert (VHR["registry-x"], VH.locatedIn, VHR["area-hanoi"]) in g


def test_add_relations_built_by_person_creates_builtby_triple() -> None:
    g = Graph()
    record = {"relations": {"built_by": "person-kien-truc-su", "built_by_type": "HistoricalPerson"}}
    add_relations(g, "registry-x", record)
    assert (VHR["registry-x"], VH.builtBy, VHR["person-kien-truc-su"]) in g


def test_add_relations_built_by_organization_uses_recognizedby_not_builtby() -> None:
    """AX-007 baseline (A): builtBy CHỈ sinh khi target là HistoricalPerson."""
    g = Graph()
    record = {"relations": {"built_by": "organization-x", "built_by_type": "Organization"}}
    add_relations(g, "registry-x", record)
    assert (VHR["registry-x"], VH.builtBy, VHR["organization-x"]) not in g
    assert (VHR["registry-x"], VH.recognizedBy, VHR["organization-x"]) in g


def test_add_provenance_creates_dcterms_source_and_prov_wasderivedfrom() -> None:
    g = Graph()
    add_provenance(g, "registry-x", SAMPLE_HERITAGE_SITE)
    source_uri = URIRef("https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753")
    assert (VHR["registry-x"], DCTERMS.source, source_uri) in g
    assert (VHR["registry-x"], PROV.wasDerivedFrom, source_uri) in g


def test_add_provenance_creates_owl_sameas_when_wikidata_id_present() -> None:
    g = Graph()
    record = dict(SAMPLE_HERITAGE_SITE)
    record["external_ids"] = {"wikidata": "Q123456"}
    add_provenance(g, "registry-x", record)
    assert (VHR["registry-x"], OWL.sameAs, URIRef("https://www.wikidata.org/entity/Q123456")) in g


def test_build_graph_produces_parseable_turtle() -> None:
    g = build_graph([SAMPLE_HERITAGE_SITE])
    turtle_text = serialize_deterministic(g)
    reparsed = Graph()
    reparsed.parse(data=turtle_text, format="turtle")
    assert len(reparsed) == len(g)


def test_serialize_deterministic_produces_stable_output_across_calls() -> None:
    g1 = build_graph([SAMPLE_HERITAGE_SITE])
    g2 = build_graph([SAMPLE_HERITAGE_SITE])
    assert serialize_deterministic(g1) == serialize_deterministic(g2)


def test_no_null_literal_triples_generated() -> None:
    record = {"entity_id": "registry-x", "entity_type": "HeritageSite", "label_vi": "X", "construction_year": None}
    g = Graph()
    record_to_triples(g, record)
    for triple in g:
        assert triple[2] is not None
        assert str(triple[2]) != "None"


def test_run_writes_turtle_file_and_parses_successfully(tmp_path: Path, monkeypatch) -> None:
    import vietheritage.rdf.generator as generator_module

    processed_dir = tmp_path / "processed"
    rdf_dir = tmp_path / "rdf"
    processed_dir.mkdir()
    canonical_path = processed_dir / "canonical.jsonl"
    canonical_path.write_text(json.dumps(SAMPLE_HERITAGE_SITE, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(generator_module, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(generator_module, "RDF_DIR", rdf_dir)

    exit_code = run(run_mode="sample")
    assert exit_code == 0
    output_path = rdf_dir / "vietheritage.ttl"
    assert output_path.exists()

    g = Graph()
    g.parse(output_path, format="turtle")
    assert len(g) > 0
    assert (VHR["registry-dsvh-national-monument-000001"], RDF.type, VH.HeritageSite) in g



def test_world_heritage_record_creates_unesco_type() -> None:
    g = Graph()
    record = dict(SAMPLE_HERITAGE_SITE, registry_category="world_heritage")
    add_entity_type_triples(g, "registry-world", record)
    assert (VHR["registry-world"], RDF.type, VH.UNESCOHeritageSite) in g
