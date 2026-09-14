from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, PROV, RDF, RDFS

from vietheritage.validation.shacl import validate_graph

EX = Namespace("http://example/")


def _write_graph(path: Path, with_source: bool) -> None:
    graph = Graph()
    graph.add((EX.entity, RDF.type, EX.HeritageSite))
    graph.add((EX.entity, RDFS.label, Literal("Huế", lang="vi")))
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
