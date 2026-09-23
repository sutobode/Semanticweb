from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, PROV, RDF, RDFS, XSD

from vietheritage.validation.shacl import validate_graph

EX = Namespace("http://example/")


def _write_graph(path: Path, with_source: bool) -> None:
    graph = Graph()
    graph.add((EX.entity, RDF.type, EX.HeritageSite))
    graph.add((EX.entity, RDFS.label, Literal("Huế", lang="vi")))
    graph.add((EX.entity, DCTERMS.modified, Literal("2026-09-23", datatype=XSD.date)))
    graph.add((EX.entity, PROV.wasGeneratedBy, EX.activity))
    graph.add((EX.activity, RDF.type, PROV.Activity))
    graph.add((EX.activity, PROV.startedAtTime, Literal("2026-09-23T00:00:00Z", datatype=XSD.dateTime)))
    if with_source:
        graph.add((EX.entity, DCTERMS.source, URIRef("https://dsvh.gov.vn/hue")))
        graph.add((EX.entity, PROV.wasDerivedFrom, URIRef("https://dsvh.gov.vn/hue")))
    graph.serialize(path, format="turtle")


def test_shacl_accepts_entity_with_identity_and_provenance(tmp_path: Path) -> None:
    data = tmp_path / "valid.ttl"
    _write_graph(data, with_source=True)
    conforms, _text, _results = validate_graph(data)
    assert conforms is True


def test_shacl_rejects_entity_without_provenance(tmp_path: Path) -> None:
    data = tmp_path / "invalid.ttl"
    _write_graph(data, with_source=False)
    conforms, text, _results = validate_graph(data)
    assert conforms is False
    assert "source URI" in text or "provenance" in text



def _write_dataset(path: Path, with_license: bool) -> None:
    dcat = Namespace("http://www.w3.org/ns/dcat#")
    graph = Graph()
    dataset = EX.dataset
    activity = EX.activity
    graph.add((dataset, RDF.type, dcat.Dataset))
    graph.add((dataset, DCTERMS.identifier, Literal("snapshot-1")))
    graph.add((dataset, DCTERMS.title, Literal("Dataset", lang="en")))
    graph.add((dataset, DCTERMS.description, Literal("Validation test dataset", lang="en")))
    graph.add((dataset, DCTERMS.creator, Literal("Team")))
    graph.add((dataset, DCTERMS.created, Literal("2026-09-14", datatype=XSD.date)))
    graph.add((dataset, DCTERMS.modified, Literal("2026-09-14", datatype=XSD.date)))
    graph.add((dataset, dcat.accessURL, EX.sparql))
    graph.add((dataset, dcat.downloadURL, EX["data.ttl"]))
    if with_license:
        graph.add((dataset, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by-sa/4.0/")))
    graph.add((dataset, PROV.wasGeneratedBy, activity))
    graph.add((activity, RDF.type, PROV.Activity))
    graph.add((activity, PROV.startedAtTime, Literal("2026-09-14T00:00:00Z", datatype=XSD.dateTime)))
    for index in range(5):
        distribution = EX[f"distribution-{index}"]
        graph.add((dataset, dcat.distribution, distribution))
        graph.add((distribution, RDF.type, dcat.Distribution))
    graph.serialize(path, format="turtle")


def test_shacl_accepts_dataset_metadata(tmp_path: Path) -> None:
    data = tmp_path / "dataset-valid.ttl"
    _write_dataset(data, with_license=True)
    conforms, _text, _results = validate_graph(data)
    assert conforms is True


def test_shacl_rejects_dataset_without_license(tmp_path: Path) -> None:
    data = tmp_path / "dataset-invalid.ttl"
    _write_dataset(data, with_license=False)
    conforms, text, _results = validate_graph(data)
    assert conforms is False
    assert "license" in text.lower()
