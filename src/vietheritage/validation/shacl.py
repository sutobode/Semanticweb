"""Reusable SHACL checks for public RDF, including a final graph union."""
from __future__ import annotations

from pathlib import Path

from pyshacl import validate
from rdflib import Graph, URIRef
from rdflib.namespace import DCAT, OWL, PROV, RDF, RDFS, SH

from .semantic import DEFAULT_BASE

REPO_ROOT = Path(__file__).resolve().parents[3]
SHAPES_PATH = REPO_ROOT / "shapes" / "vietheritage.shacl.ttl"


def validate_graph(
    data_path: Path | Graph, shapes_path: Path = SHAPES_PATH, *,
    ontology: Graph | None = None, base: str = DEFAULT_BASE,
    entities=None, source_entities=None,
) -> tuple[bool, str, Graph]:
    data_graph = data_path if isinstance(data_path, Graph) else Graph().parse(data_path, format="turtle")
    shapes_graph = Graph().parse(shapes_path, format="turtle")
    if entities is None:
        schema_and_metadata = {
            OWL.Class, RDFS.Class, RDF.Property, OWL.ObjectProperty, OWL.DatatypeProperty,
            OWL.Ontology, DCAT.Dataset, DCAT.Distribution, PROV.Activity,
        }
        candidates = set(data_graph.subjects(RDFS.label, None)) | {
            node for node, kind in data_graph.subject_objects(RDF.type)
            if str(kind).startswith(base + "/ontology/")
        }
        entities = {node for node in candidates
                    if not set(data_graph.objects(node, RDF.type)) & schema_and_metadata}
    if source_entities is None:
        source_entities = {node for node in entities
                           if ontology is None or not any(ontology.triples((node, None, None)))}
    if base != DEFAULT_BASE:
        rebased = Graph()
        for triple in shapes_graph:
            rebased.add(tuple(
                URIRef(base + str(node)[len(DEFAULT_BASE):])
                if isinstance(node, URIRef) and str(node).startswith(DEFAULT_BASE + "/") else node
                for node in triple
            ))
        shapes_graph = rebased
    for name, targets in (("PublicEntityShape", entities), ("SourceEntityShape", source_entities)):
        for target in targets:
            shapes_graph.add((URIRef(f"{base}/shapes/{name}"), SH.targetNode, target))
    conforms, results_graph, results_text = validate(
        data_graph=data_graph,
        shacl_graph=shapes_graph,
        ont_graph=ontology,
        inference="none",
        do_owl_imports=False,
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
        advanced=True,
    )
    return bool(conforms), str(results_text), results_graph


def run(
    run_mode: str = "sample", data_path: Path | None = None, metadata_path: Path | None = None,
    *, run_id: str | None = None,
) -> int:
    """Use the same final-graph validation/report path as the CLI."""
    from .validator import run as validate_run

    return validate_run(run_mode, run_id=run_id, data_path=data_path, metadata_path=metadata_path)
