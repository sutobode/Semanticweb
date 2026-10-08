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


def test_heritage_complex_emits_asserted_has_member_only() -> None:
    records = [
        {
            "entity_id": "complex-x", "entity_type": "HeritageComplex", "label_vi": "Quần thể X",
            "source_status": "derived", "source_url": "https://example.org/complex", "retrieved_at": "2026-10-05T00:00:00Z",
            "relations": {"member_sites": ["site-x"]},
            "provenance": {"source": "https://example.org/complex", "method": "derived", "license": "Official source"},
        },
        {
            "entity_id": "site-x", "entity_type": "HeritageSite", "label_vi": "Di tích X",
            "source_status": "derived", "source_url": "https://example.org/site", "retrieved_at": "2026-10-05T00:00:00Z",
            "provenance": {"source": "https://example.org/site", "method": "derived", "license": "Official source"},
        },
    ]
    g = build_graph(records)

    assert (VHR["complex-x"], VH.hasMember, VHR["site-x"]) in g
    assert (VHR["complex-x"], VH.hasPart, VHR["site-x"]) not in g
    assert (VHR["site-x"], VH.partOf, VHR["complex-x"]) not in g


def test_reconciled_complex_emits_one_subject_selected_year_and_all_source_provenance() -> None:
    record = {
        "entity_id": "complex-thanh-nha-ho", "entity_type": "HeritageComplex",
        "label_vi": "Di sản Văn hóa Thế giới Thành Nhà Hồ", "source_status": "registry_only",
        "registry_id": "registry-world", "registry_category": "world_heritage",
        "registry_url": "https://dsvh.gov.vn/thanh-nha-ho", "coverage_snapshot": "snapshot",
        "source_url": "https://whc.unesco.org/en/list/1358/", "retrieved_at": "2026-10-05T00:00:00Z",
        "recognition_year": 2011, "relations": {"recognized_by": ["organization-unesco"]},
        "source_records": [
            {
                "source_namespace": "dsvh", "source_record_id": "registry-world",
                "source_url": "https://dsvh.gov.vn/thanh-nha-ho", "recognition_year": 2011,
                "retrieved_at": "2026-10-05T00:00:00Z",
                "provenance": {"source": "https://dsvh.gov.vn/thanh-nha-ho",
                               "method": "registry", "license": "Official source"},
            },
            {
                "source_namespace": "dsvh", "source_record_id": "registry-national",
                "source_url": "https://dsvh.gov.vn/national-special", "recognition_year": 2012,
                "retrieved_at": "2026-10-05T00:00:00Z",
                "provenance": {"source": "https://dsvh.gov.vn/national-special",
                               "method": "registry", "license": "Official source"},
            },
        ],
        "provenance": {"source": "https://dsvh.gov.vn/thanh-nha-ho",
                       "method": "registry", "license": "Official source"},
    }
    graph = build_graph([record])
    subject = VHR[record["entity_id"]]

    assert set(graph.subjects(RDF.type, VH.HeritageComplex)) == {subject}
    assert set(graph.objects(subject, VH.recognitionYear)) == {Literal("2011", datatype=XSD.gYear)}
    assert (subject, VH.recognizedBy, VHR["organization-unesco"]) in graph
    assert URIRef("https://dsvh.gov.vn/national-special") in set(graph.objects(subject, DCTERMS.source))
    assert set(graph.objects(subject, DCTERMS.source)) == set(graph.objects(subject, PROV.wasDerivedFrom))


def test_heritage_site_emits_multiple_architectural_styles() -> None:
    source = "https://dsvh.gov.vn/thap-nhan-3238"
    records = [
        {
            "entity_id": "registry-thap-nhan", "entity_type": "HeritageSite", "label_vi": "Tháp Nhạn",
            "source_status": "derived", "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
            "relations": {"architectural_styles": ["style-my-son-a1", "style-binh-dinh"]},
            "provenance": {"source": source, "method": "derived", "license": "Official source"},
        },
        *(
            {
                "entity_id": entity_id, "entity_type": "ArchitecturalStyle", "label_vi": label,
                "source_status": "derived", "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
                "provenance": {"source": source, "method": "derived", "license": "Official source"},
            }
            for entity_id, label in (("style-my-son-a1", "Mỹ Sơn A1"), ("style-binh-dinh", "Bình Định"))
        ),
    ]
    graph = build_graph(records)

    assert set(graph.objects(VHR["registry-thap-nhan"], VH.hasArchitecturalStyle)) == {
        VHR["style-my-son-a1"], VHR["style-binh-dinh"],
    }


def test_heritage_site_emits_historical_period() -> None:
    source = "https://dsvh.gov.vn/thap-nhan-3238"
    period_id = "period-957be01571dd"
    records = [
        {
            "entity_id": "registry-thap-nhan", "entity_type": "HeritageSite", "label_vi": "Tháp Nhạn",
            "source_status": "derived", "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
            "relations": {"periods": [period_id]},
            "provenance": {"source": source, "method": "derived", "license": "Official source"},
        },
        {
            "entity_id": period_id, "entity_type": "HistoricalPeriod",
            "label_vi": "Cuối thế kỷ XI - đầu thế kỷ XII", "source_status": "derived",
            "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
            "provenance": {"source": source, "method": "derived", "license": "Official source"},
        },
    ]
    graph = build_graph(records)

    assert (VHR["registry-thap-nhan"], VH.belongsToPeriod, VHR[period_id]) in graph
    assert (VHR[period_id], RDF.type, VH.HistoricalPeriod) in graph


def test_heritage_site_emits_overlapping_religious_and_architectural_types() -> None:
    record = {
        **SAMPLE_HERITAGE_SITE,
        "entity_id": "registry-thap-nhan",
        "label_vi": "Tháp Nhạn",
        "site_types": ["di tích tôn giáo", "di tích kiến trúc nghệ thuật"],
    }
    graph = build_graph([record])
    types = set(graph.objects(VHR["registry-thap-nhan"], RDF.type))

    assert types == {VH.HeritageSite, VH.ReligiousSite, VH.ArchitecturalSite}


def test_historical_successor_is_directed_without_reverse_or_self_edge() -> None:
    source = "https://baotanglichsu.vn/vi/Articles/2002/67980/example.html"
    first = "event-dien-bien-phu-dot-i"
    second = "event-dien-bien-phu-dot-ii"
    records = [
        {
            "entity_id": first, "entity_type": "HistoricalEvent", "label_vi": "Đợt I",
            "source_status": "derived", "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
            "relations": {"historical_successors": [second]},
            "provenance": {"source": source, "method": "derived", "license": "Official source"},
        },
        {
            "entity_id": second, "entity_type": "HistoricalEvent", "label_vi": "Đợt II",
            "source_status": "derived", "source_url": source, "retrieved_at": "2026-10-05T00:00:00Z",
            "provenance": {"source": source, "method": "derived", "license": "Official source"},
        },
    ]
    graph = build_graph(records)
    predicate = VH.hasHistoricalSuccessor

    assert (VHR[first], predicate, VHR[second]) in graph
    assert (VHR[second], predicate, VHR[first]) not in graph
    assert (VHR[first], predicate, VHR[first]) not in graph
    assert (VHR[second], predicate, VHR[second]) not in graph


def test_related_site_is_asserted_once_without_reverse_or_self_edge() -> None:
    first = "registry-den-phu-dong"
    second = "registry-den-soc"
    records = [
        {
            "entity_id": first, "entity_type": "HeritageSite", "label_vi": "Đền Phù Đổng",
            "source_status": "derived", "source_url": "https://example.org/phu-dong",
            "retrieved_at": "2026-10-06T00:00:00Z", "relations": {"related_sites": [second]},
            "provenance": {"source": "https://example.org/phu-dong", "method": "derived", "license": "Official source"},
        },
        {
            "entity_id": second, "entity_type": "HeritageSite", "label_vi": "Đền Sóc",
            "source_status": "derived", "source_url": "https://example.org/den-soc",
            "retrieved_at": "2026-10-06T00:00:00Z",
            "provenance": {"source": "https://example.org/den-soc", "method": "derived", "license": "Official source"},
        },
    ]
    graph = build_graph(records)
    predicate = VH.hasRelatedSite

    assert list(graph.triples((VHR[first], predicate, VHR[second]))) == [
        (VHR[first], predicate, VHR[second])
    ]
    assert (VHR[second], predicate, VHR[first]) not in graph
    assert (VHR[first], predicate, VHR[first]) not in graph
    assert (VHR[second], predicate, VHR[second]) not in graph


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
