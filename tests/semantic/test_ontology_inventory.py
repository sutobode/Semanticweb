"""G2 semantic tests — ontology inventory và consistency cơ bản (AC-014, TEST-033).

Đếm class/property project-owned bằng RDFLib để không lệ thuộc vào việc đếm
dòng trong file .ttl bằng tay (Section 15.0 P2-1: MET-001 phải đếm owl:Class
trong ontology thật, không đếm dòng markdown).
"""
from pathlib import Path

import pytest
from rdflib import OWL, RDF, RDFS, XSD, Literal, Namespace
from rdflib.graph import Graph

ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "ontology" / "vietheritage.ttl"
VH = Namespace("http://localhost:3030/vietheritage/ontology/")

EXPECTED_CLASSES = {
    "CulturalHeritageEntity", "HeritageSite", "UNESCOHeritageSite", "HistoricalSite",
    "ReligiousSite", "ArchaeologicalSite", "ArchitecturalSite", "HeritageComplex",
    "Museum", "HistoricalPerson", "HistoricalEvent", "HistoricalPeriod",
    "ArchitecturalStyle", "AdministrativeArea", "Organization", "IntangibleHeritage",
    "RepresentativeIntangibleHeritage", "UrgentSafeguardingIntangibleHeritage",
    "NationalIntangibleHeritage", "NationalTreasure", "DocumentaryHeritage",
    "Artisan", "CulturalObject", "HeritageSiteWithHistoricalBuilder",
}

EXPECTED_OBJECT_PROPERTIES = {
    "locatedIn", "partOf", "hasPart", "associatedWithPerson", "associatedWithEvent",
    "belongsToPeriod", "builtBy", "recognizedBy", "hasArchitecturalStyle",
    "hasMember", "hasRelatedSite", "hasHistoricalSuccessor",
}

EXPECTED_DATATYPE_PROPERTIES = {
    "constructionYear", "recognitionYear", "address", "sourcePageId", "sourceTitle",
    "shortDescription", "alternativeName", "birthYear", "deathYear", "areaLevel",
}


@pytest.fixture(scope="module")
def graph() -> Graph:
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")
    return g


def test_ontology_file_parses_as_valid_turtle(graph: Graph) -> None:
    assert len(graph) > 0


def test_ontology_has_owl_ontology_header(graph: Graph) -> None:
    subjects = list(graph.subjects(RDF.type, OWL.Ontology))
    assert len(subjects) == 1
    assert str(subjects[0]) == "http://localhost:3030/vietheritage/ontology/"


def test_ontology_has_exactly_24_project_owned_classes(graph: Graph) -> None:
    classes = {
        str(s).replace(str(VH), "")
        for s in graph.subjects(RDF.type, OWL.Class)
        if str(s).startswith(str(VH))
    }
    assert classes == EXPECTED_CLASSES
    assert len(classes) == 24


def test_ontology_has_exactly_12_object_properties(graph: Graph) -> None:
    props = {
        str(s).replace(str(VH), "")
        for s in graph.subjects(RDF.type, OWL.ObjectProperty)
        if str(s).startswith(str(VH))
    }
    assert props == EXPECTED_OBJECT_PROPERTIES
    assert len(props) == 12


def test_ontology_has_exactly_10_datatype_properties(graph: Graph) -> None:
    props = {
        str(s).replace(str(VH), "")
        for s in graph.subjects(RDF.type, OWL.DatatypeProperty)
        if str(s).startswith(str(VH))
    }
    assert props == EXPECTED_DATATYPE_PROPERTIES
    assert len(props) == 10


def test_every_class_has_bilingual_labels(graph: Graph) -> None:
    for cls_name in EXPECTED_CLASSES:
        cls = VH[cls_name]
        labels = list(graph.objects(cls, RDFS.label))
        langs = {label.language for label in labels}
        assert "vi" in langs, f"{cls_name} missing @vi label"
        assert "en" in langs, f"{cls_name} missing @en label"


def test_every_property_has_bilingual_labels(graph: Graph) -> None:
    for prop_name in EXPECTED_OBJECT_PROPERTIES | EXPECTED_DATATYPE_PROPERTIES:
        prop = VH[prop_name]
        labels = list(graph.objects(prop, RDFS.label))
        langs = {label.language for label in labels}
        assert "vi" in langs, f"{prop_name} missing @vi label"
        assert "en" in langs, f"{prop_name} missing @en label"


def test_ax001_unesco_subclass_asserted(graph: Graph) -> None:
    assert (VH.UNESCOHeritageSite, RDFS.subClassOf, VH.HeritageSite) in graph


def test_ax002_inverse_part_relation_asserted(graph: Graph) -> None:
    assert (VH.partOf, OWL.inverseOf, VH.hasPart) in graph


def test_ax003_transitive_part_relation_asserted(graph: Graph) -> None:
    assert (VH.partOf, RDF.type, OWL.TransitiveProperty) in graph


def test_ax004_disjoint_classes_asserted(graph: Graph) -> None:
    assert (VH.HistoricalPerson, OWL.disjointWith, VH.HeritageSite) in graph
    assert (VH.HistoricalPerson, OWL.disjointWith, VH.AdministrativeArea) in graph
    assert (VH.Artisan, OWL.disjointWith, VH.HeritageSite) in graph
    assert (VH.HeritageSite, OWL.disjointWith, VH.AdministrativeArea) in graph


def test_ax004_all_disjoint_classes_present(graph: Graph) -> None:
    assert list(graph.subjects(RDF.type, OWL.AllDisjointClasses))


def test_ax005_unesco_named_individual_and_equivalent_class(graph: Graph) -> None:
    assert (VH.hasRelatedSite, RDF.type, OWL.SymmetricProperty) is not None
    unesco = graph.value(subject=None, predicate=RDFS.label, object=None)  # noqa: F841
    orgs = list(graph.subjects(RDF.type, VH.Organization))
    assert any("organization-unesco" in str(o) for o in orgs)
    assert list(graph.objects(VH.UNESCOHeritageSite, OWL.equivalentClass))


def test_ax006_symmetric_property_asserted(graph: Graph) -> None:
    assert (VH.hasRelatedSite, RDF.type, OWL.SymmetricProperty) in graph


def test_ax007_subproperty_of_associated_with_person(graph: Graph) -> None:
    assert (VH.builtBy, RDFS.subPropertyOf, VH.associatedWithPerson) in graph


def test_ax008_disjoint_union_of_intangible_heritage(graph: Graph) -> None:
    values = list(graph.objects(VH.IntangibleHeritage, OWL.disjointUnionOf))
    assert values, "AX-008 owl:disjointUnionOf missing"


def test_ax009_functional_properties_for_8_datatype_properties(graph: Graph) -> None:
    functional_expected = {
        "constructionYear", "recognitionYear", "address", "sourcePageId",
        "sourceTitle", "birthYear", "deathYear", "areaLevel",
    }
    for name in functional_expected:
        assert (VH[name], RDF.type, OWL.FunctionalProperty) in graph, f"{name} not FunctionalProperty"

    non_functional = {"shortDescription", "alternativeName"}
    for name in non_functional:
        assert (VH[name], RDF.type, OWL.FunctionalProperty) not in graph, f"{name} must NOT be FunctionalProperty"


def test_recognition_properties_apply_to_all_cultural_heritage_entities(graph: Graph) -> None:
    assert set(graph.objects(VH.recognizedBy, RDFS.domain)) == {VH.CulturalHeritageEntity}
    assert set(graph.objects(VH.recognitionYear, RDFS.domain)) == {VH.CulturalHeritageEntity}
    assert (VH.recognitionYear, RDF.type, OWL.FunctionalProperty) in graph


def test_ontology_version_and_ax010_exact_definition(graph: Graph) -> None:
    assert set(graph.objects(VH[""], OWL.versionInfo)) == {Literal("1.9.0")}
    cls = VH.HeritageSiteWithHistoricalBuilder
    assert set(graph.objects(cls, RDFS.subClassOf)) == {VH.HeritageSite}
    equivalents = list(graph.objects(cls, OWL.equivalentClass))
    assert len(equivalents) == 1
    definition = equivalents[0]
    assert (definition, RDF.type, OWL.Class) in graph
    lists = list(graph.objects(definition, OWL.intersectionOf))
    assert len(lists) == 1
    members = list(graph.items(lists[0]))
    assert len(members) == 2 and members[0] == VH.HeritageSite
    restriction = members[1]
    assert (restriction, RDF.type, OWL.Restriction) in graph
    assert set(graph.objects(restriction, OWL.onProperty)) == {VH.builtBy}
    assert set(graph.objects(restriction, OWL.someValuesFrom)) == {VH.HistoricalPerson}
    assert {value.language for value in graph.objects(cls, RDFS.comment)} == {"vi", "en"}


def test_ax010_does_not_add_a_disjoint_main_branch(graph: Graph) -> None:
    groups = list(graph.subjects(RDF.type, OWL.AllDisjointClasses))
    assert len(groups) == 1
    assert set(graph.items(graph.value(groups[0], OWL.members))) == {
        VH.HeritageSite, VH.HeritageComplex, VH.Museum, VH.IntangibleHeritage,
        VH.NationalTreasure, VH.DocumentaryHeritage, VH.CulturalObject,
    }
    assert not list(graph.objects(VH.HeritageSiteWithHistoricalBuilder, OWL.disjointWith))
    assert not list(graph.subjects(OWL.disjointWith, VH.HeritageSiteWithHistoricalBuilder))


def test_ax011_exact_minimum_location_restriction(graph: Graph) -> None:
    restrictions = {
        restriction
        for restriction in graph.objects(VH.HeritageSite, RDFS.subClassOf)
        if (restriction, RDF.type, OWL.Restriction) in graph
        and (restriction, OWL.onProperty, VH.locatedIn) in graph
    }
    assert len(restrictions) == 1
    restriction = restrictions.pop()
    assert set(graph.objects(restriction, OWL.minCardinality)) == {
        Literal(1, datatype=XSD.nonNegativeInteger)
    }
    assert not list(graph.objects(restriction, OWL.onClass))
    assert not list(graph.objects(restriction, OWL.onDataRange))


def test_ax017_is_only_asymmetric_and_keeps_event_domain_range(graph: Graph) -> None:
    prop = VH.hasHistoricalSuccessor
    assert set(graph.objects(prop, RDF.type)) == {OWL.ObjectProperty, RDF.Property, OWL.AsymmetricProperty}
    assert set(graph.objects(prop, RDFS.domain)) == {VH.HistoricalEvent}
    assert set(graph.objects(prop, RDFS.range)) == {VH.HistoricalEvent}
    for characteristic in (OWL.TransitiveProperty, OWL.SymmetricProperty, OWL.IrreflexiveProperty):
        assert (prop, RDF.type, characteristic) not in graph


def test_has_member_range_is_exactly_site_or_complex(graph: Graph) -> None:
    prop = VH.hasMember
    assert set(graph.objects(prop, RDFS.domain)) == {VH.HeritageComplex}
    assert set(graph.objects(prop, RDFS.subPropertyOf)) == {VH.hasPart}
    ranges = list(graph.objects(prop, RDFS.range))
    assert len(ranges) == 1 and VH.CulturalHeritageEntity not in ranges
    union = ranges[0]
    assert (union, RDF.type, OWL.Class) in graph
    lists = list(graph.objects(union, OWL.unionOf))
    assert len(lists) == 1
    assert list(graph.items(lists[0])) == [VH.HeritageSite, VH.HeritageComplex]
    assert (VH.partOf, OWL.inverseOf, VH.hasPart) in graph
    assert (VH.partOf, RDF.type, OWL.TransitiveProperty) in graph
