"""Production canonical -> RDF output against the locked Phase 2 contracts."""
import json

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, XSD

from vietheritage.mapping.mapper import _load_category_types, map_record
from vietheritage.rdf import generator
from vietheritage.reasoning.reasoner import reason
from vietheritage.validation.policy import validate_public_graph
from vietheritage.validation.semantic import DEFAULT_BASE


@pytest.fixture
def records():
    category_types = _load_category_types()
    result = []
    for category in ("world_heritage", "intangible_representative", "intangible_urgent", "national_intangible", "artisans"):
        entity = {
            "entity_id": "registry-" + category.replace("_", "-"),
            "registry_id": category, "registry_category": category,
            "registry_url": "https://dsvh.gov.vn/" + category,
            "label_vi": "Di sản " + category, "coverage_snapshot": "20260923T000000Z-abox",
            "retrieved_at": "2026-09-23T00:00:00Z",
            "registry_fields": {"recognition_text": "2000", "location": "Hà Nội", "type": "di tích lịch sử"},
        }
        pages = {}
        if category == "world_heritage":
            pages[entity["label_vi"].casefold()] = {
                "page_id": 42, "title": entity["label_vi"].upper(),
                "source_url": "https://vi.wikipedia.org/wiki/Di_san",
            }
            entity["relations"] = {"located_in": ["area-child"],
                                   "built_by": ["person-builder", "organization-builder", "person-missing"]}
        result.append(map_record(entity, category_types, pages))
    for identifier, kind in (("area-child", "AdministrativeArea"), ("area-parent", "AdministrativeArea"),
                             ("person-builder", "HistoricalPerson"), ("organization-builder", "Organization")):
        result.append({
            "entity_id": identifier, "entity_type": kind, "label_vi": "Thực thể " + identifier,
            "source_status": "derived", "retrieved_at": "2026-09-23T00:00:00Z",
            "provenance": {"source": "https://dsvh.gov.vn/related", "method": "derived", "license": "CC BY-SA 4.0"},
        })
    result[5]["parent_area"] = "area-parent"
    result[7]["birth_year"] = 43  # Valid canonical year needs four-digit xsd:gYear lexical form.
    return result


@pytest.fixture
def generate(records, tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(generator, "PROCESSED_DIR", tmp_path / "data/processed")
    monkeypatch.setattr(generator, "RDF_DIR", tmp_path / "data/rdf")
    generator.PROCESSED_DIR.mkdir(parents=True)

    def run():
        (generator.PROCESSED_DIR / "canonical.jsonl").write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8",
        )
        return generator.run(run_mode="full")

    return run


@pytest.mark.parametrize("base", [DEFAULT_BASE, "https://heritage.example/kg"])
def test_generated_public_abox_conforms(records, generate, monkeypatch, base):
    monkeypatch.setenv("VH_BASE_URI", base)
    assert generate() == 0
    generator.refresh_dataset_metadata_metrics()
    asserted = Graph().parse(generator.RDF_DIR / "vietheritage.ttl", format="turtle")
    metadata = Graph().parse(generator.RDF_DIR / "dataset-metadata.ttl", format="turtle")
    ontology = generator.load_ontology()
    result = validate_public_graph(
        ontology + asserted + metadata, ontology, canonical_records=records,
        run_mode="full", require_dataset=True,
    )
    assert result["status"] == "PASS", result
    assert result["axioms"]["AX-008"] == result["axioms"]["AX-009"] == "PASS"
    vh, vhr = Namespace(base + "/ontology/"), Namespace(base + "/resource/")
    site = vhr[records[0]["entity_id"]]
    assert (site, RDF.type, vh.HeritageSite) in asserted
    assert (site, RDF.type, vh.UNESCOHeritageSite) not in asserted
    assert (site, vh.recognizedBy, vhr["organization-unesco"]) in asserted
    assert set(asserted.objects(site, vh.builtBy)) == {vhr["person-builder"]}
    assert (site, vh.sourceTitle, Literal(records[0]["source_title"], datatype=XSD.string)) in asserted
    assert (vhr["area-child"], vh.locatedIn, vhr["area-parent"]) in asserted
    assert not list(asserted.triples((None, OWL.sameAs, None)))
    dataset = URIRef(base + "/dataset/vietheritage")
    assert set(metadata.subjects(RDF.type, DCAT.Dataset)) == {dataset}
    assert len(list(metadata.objects(dataset, DCAT.distribution))) == 5
    assert set(metadata.objects(None, DCTERMS.identifier)) >= {
        URIRef(base + "/graph/" + name) for name in ("ontology", "data", "external-links", "inferred", "metadata")
    }
    activity = metadata.value(dataset, PROV.wasGeneratedBy)
    assert (activity, RDF.type, PROV.Activity) in metadata
    for record in records:
        node = vhr[record["entity_id"]]
        assert (node, PROV.wasGeneratedBy, activity) in asserted
        assert (node, DCTERMS.source, URIRef(record["provenance"]["source"])) in asserted
    assert generator.serialize_deterministic(asserted) == generator.serialize_deterministic(
        generator.build_graph(list(reversed(records))),
    )


def test_generated_world_heritage_ax005_is_inferred_by_jena(records, generate, monkeypatch):
    monkeypatch.setenv("VH_BASE_URI", DEFAULT_BASE)
    assert generate() == 0
    ontology = generator.load_ontology()
    asserted = Graph().parse(generator.RDF_DIR / "vietheritage.ttl", format="turtle")
    metadata = Graph().parse(generator.RDF_DIR / "dataset-metadata.ttl", format="turtle")
    expected = (generator.entity_uri(records[0]["entity_id"]), RDF.type, generator.VH.UNESCOHeritageSite)
    assert expected not in asserted
    inferred, _ = reason([ontology, asserted])
    assert expected in inferred
    assertions = ontology + asserted + metadata
    result = validate_public_graph(
        assertions + inferred, ontology, assertions=assertions, canonical_records=records,
        run_mode="full", require_dataset=True,
    )
    assert result["status"] == "PASS", result


@pytest.mark.parametrize("invalid", ["missing-title", "fixture-id", "noncanonical-id"])
def test_generation_rejects_invalid_canonical_inputs(records, generate, invalid):
    if invalid == "missing-title":
        records[0].pop("source_title")
    else:
        records[0]["entity_id"] = "site-fixture" if invalid == "fixture-id" else "unsupported-id"
    assert generate() == 1
    assert not (generator.RDF_DIR / "vietheritage.ttl").exists()
