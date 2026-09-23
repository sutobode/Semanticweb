"""G6 unit tests — RDF Generator (COMP-005, TEST-021..027).

Kiểm tra parse Turtle, datatype, language tag, deterministic sort, provenance.
"""
import json
from pathlib import Path

import pytest
import yaml
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from vietheritage.rdf.generator import (
    GEO,
    VH,
    VHR,
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
    "registry_id": "dsvh-national-monument-000001",
    "registry_category": "national_monuments",
    "registry_url": "https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753",
    "coverage_snapshot": "20260913T000000Z",
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
    g.add((VHR["area-hanoi"], RDF.type, VH.AdministrativeArea))
    add_relations(g, "registry-x", SAMPLE_HERITAGE_SITE)
    assert (VHR["registry-x"], VH.locatedIn, VHR["area-hanoi"]) in g


def test_add_relations_built_by_person_creates_builtby_triple() -> None:
    g = Graph()
    g.add((VHR["person-kien-truc-su"], RDF.type, VH.HistoricalPerson))
    record = {"entity_type": "HeritageSite", "relations": {"built_by": ["person-kien-truc-su"]}}
    add_relations(g, "registry-x", record)
    assert (VHR["registry-x"], VH.builtBy, VHR["person-kien-truc-su"]) in g


@pytest.mark.parametrize("target_type", [VH.Organization, None], ids=["organization", "unknown"])
def test_built_by_unsupported_target_is_omitted_without_reinterpretation(target_type) -> None:
    """DEC-041: neither a default Person type nor a made-up recognition relation."""
    g = Graph()
    if target_type:
        g.add((VHR["organization-x"], RDF.type, target_type))
    record = {"entity_type": "HeritageSite", "relations": {
        "built_by": ["organization-x"], "built_by_type": "HistoricalPerson",
    }}
    add_relations(g, "registry-x", record)
    assert (VHR["registry-x"], VH.builtBy, VHR["organization-x"]) not in g
    assert (VHR["registry-x"], VH.recognizedBy, VHR["organization-x"]) not in g


def test_record_emits_standard_category_alias_and_all_sources() -> None:
    record = dict(
        SAMPLE_HERITAGE_SITE,
        registry_category="world_heritage",
        aliases_vi=["Văn Miếu Quốc Tử Giám"],
        source_status="registry+wikipedia",
        source_page_id=123,
        source_title="Văn Miếu",
        source_url="https://vi.wikipedia.org/wiki/Van_Mieu",
    )
    g = build_graph([record])
    subject = VHR[record["entity_id"]]
    assert (subject, DCTERMS.subject, Literal("world_heritage")) in g
    assert any(str(value) == "Văn Miếu Quốc Tử Giám" for value in g.objects(subject, SKOS.altLabel))
    assert (subject, PROV.wasDerivedFrom, URIRef(record["source_url"])) in g


def test_add_provenance_creates_dcterms_source_and_prov_wasderivedfrom() -> None:
    g = Graph()
    add_provenance(g, "registry-x", SAMPLE_HERITAGE_SITE)
    source_uri = URIRef("https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753")
    assert (VHR["registry-x"], DCTERMS.source, source_uri) in g
    assert (VHR["registry-x"], PROV.wasDerivedFrom, source_uri) in g
    assert (VHR["registry-x"], DCTERMS.modified, Literal("2026-09-13", datatype=XSD.date)) in g
    assert (VHR["registry-x"], DCTERMS.license, URIRef("https://creativecommons.org/licenses/by-sa/4.0/")) in g
    assert len(list(g.objects(VHR["registry-x"], PROV.wasGeneratedBy))) == 1


@pytest.mark.parametrize("qid", ["Q123456", "not-a-qid"])
def test_asserted_generator_leaves_identity_publication_to_linker(qid) -> None:
    g = Graph()
    record = dict(SAMPLE_HERITAGE_SITE)
    record["external_ids"] = {"wikidata": qid, "dbpedia": "http://dbpedia.org/resource/Test"}
    add_provenance(g, "registry-x", record)
    assert not list(g.triples((None, OWL.sameAs, None)))


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



def test_world_heritage_record_asserts_ax005_inputs_only() -> None:
    g = Graph()
    record = dict(SAMPLE_HERITAGE_SITE, registry_category="world_heritage")
    add_entity_type_triples(g, "registry-world", record)
    assert (VHR["registry-world"], RDF.type, VH.HeritageSite) in g
    assert (VHR["registry-world"], VH.recognizedBy, VHR["organization-unesco"]) in g
    assert (VHR["registry-world"], RDF.type, VH.UNESCOHeritageSite) not in g


@pytest.mark.parametrize(("category", "subclass"), [
    ("intangible_representative", VH.RepresentativeIntangibleHeritage),
    ("intangible_urgent", VH.UrgentSafeguardingIntangibleHeritage),
    ("national_intangible", VH.NationalIntangibleHeritage),
])
def test_intangible_category_uses_authoritative_subclass(category, subclass):
    record = dict(SAMPLE_HERITAGE_SITE, entity_type="IntangibleHeritage", registry_category=category)
    graph = build_graph([record])
    assert set(graph.objects(VHR[record["entity_id"]], RDF.type)) == {VH.IntangibleHeritage, subclass}


def test_mapping_covers_registry_types_and_matches_subclass_hints():
    from vietheritage.rdf.generator import MAPPING_PATH, load_mapping

    mapping = load_mapping()
    registry = yaml.safe_load((MAPPING_PATH.parent / "registry_sources.yaml").read_text(encoding="utf-8"))
    for category in registry["categories"]:
        assert category["entity_type"] in mapping["entity_types"]
        assert category.get("ontology_subclass") == mapping["registry_category_subclass"].get(category["key"])


def test_admin_parent_and_relations_resolve_against_all_canonical_types():
    child = {"entity_id": "area-child", "entity_type": "AdministrativeArea", "parent_area": "area-parent"}
    parent = {"entity_id": "area-parent", "entity_type": "AdministrativeArea"}
    graph = build_graph([child, parent])
    assert (VHR["area-child"], VH.locatedIn, VHR["area-parent"]) in graph
    assert not list(build_graph([child]).objects(VHR["area-child"], VH.locatedIn))


@pytest.mark.parametrize("status", ["registry_only", "registry+wikipedia", "registry+enriched"])
def test_wikipedia_metadata_is_conditional_and_preserves_page_title(status):
    record = dict(SAMPLE_HERITAGE_SITE, source_status=status, source_page_id=123, source_title="Tên trang Wikipedia")
    graph = build_graph([record])
    subject = VHR[record["entity_id"]]
    expected = status != "registry_only"
    assert ((subject, VH.sourcePageId, Literal(123)) in graph) == expected
    assert ((subject, VH.sourceTitle, Literal("Tên trang Wikipedia", datatype=XSD.string)) in graph) == expected


def test_out_of_domain_enrichment_does_not_change_entity_type():
    record = dict(SAMPLE_HERITAGE_SITE, entity_type="Artisan", registry_category="artisans",
                  recognition_year=2000, address="Hà Nội", relations={"recognized_by": ["organization-unesco"]})
    graph = build_graph([record])
    subject = VHR[record["entity_id"]]
    assert set(graph.objects(subject, RDF.type)) == {VH.Artisan}
    for predicate in (VH.recognizedBy, VH.recognitionYear, VH.constructionYear, VH.address):
        assert not list(graph.objects(subject, predicate))
