"""Reasoning delta/closure metrics must not be confused by metadata refresh."""
import json

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF

from vietheritage.rdf import generator


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(generator, "RDF_DIR", tmp_path / "rdf")
    monkeypatch.setattr(generator, "PROCESSED_DIR", tmp_path / "processed")
    generator.RDF_DIR.mkdir()
    generator.PROCESSED_DIR.mkdir()
    (generator.PROCESSED_DIR / "canonical.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    site = generator.VHR["registry-metrics"]
    Graph().add((site, RDF.type, generator.VH.HeritageSite)).serialize(
        generator.RDF_DIR / "vietheritage.ttl", format="turtle",
    )
    Graph().add((site, RDF.type, generator.VH.HeritageSiteWithHistoricalBuilder)).serialize(
        generator.RDF_DIR / "inferred.ttl", format="turtle",
    )
    dataset = URIRef(generator._base() + "/dataset/vietheritage")
    metadata = generator.RDF_DIR / "dataset-metadata.ttl"
    Graph().add((dataset, DCTERMS.extent, Literal("registry_records=2"))).serialize(metadata, format="turtle")
    payload = {"status": "PASS", "source_triples": 10, "inferred_triples": 1, "closure_triples": 11}
    report_path = generator.RDF_DIR / "reasoning-report.json"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    return dataset, metadata, report_path, payload


def test_refresh_uses_verified_closure_not_delta_and_is_repeatable(workspace):
    dataset, metadata, _, _ = workspace
    generator.refresh_dataset_metadata_metrics()
    values = set(Graph().parse(metadata, format="turtle").objects(dataset, DCTERMS.extent))
    assert values >= {
        Literal("registry_records=2"), Literal("canonical_records=2"),
        Literal("inferred_delta_triples=1"), Literal("inferred_closure_triples=11"),
    }
    first = metadata.read_bytes()
    generator.refresh_dataset_metadata_metrics()
    assert metadata.read_bytes() == first


@pytest.mark.parametrize("field", ["status", "inferred_triples", "closure_triples"])
def test_inconsistent_reasoning_metrics_do_not_overwrite_metadata(workspace, field):
    _, metadata, report_path, payload = workspace
    payload[field] = "FAIL" if field == "status" else 99
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    before = metadata.read_bytes()
    with pytest.raises(ValueError, match="REASONING_METRICS_MISMATCH"):
        generator.refresh_dataset_metadata_metrics()
    assert metadata.read_bytes() == before
