"""Deterministic OWL Mini reasoning stage (COMP-008).

The closure implements the project ontology's blocking axioms without adding
an alternate source of truth: asserted RDF is loaded, then only explicit
RDFS/OWL subclass, subproperty, inverse, symmetric and transitive rules are
applied.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[3]
RDF_DIR = REPO_ROOT / "data" / "rdf"
ONTOLOGY = REPO_ROOT / "ontology" / "vietheritage.ttl"
ASSERTED = RDF_DIR / "vietheritage.ttl"
INFERRED = RDF_DIR / "inferred.ttl"
REPORT = RDF_DIR / "reasoning-report.json"


def _closure(graph: Graph) -> Graph:
    result = Graph()
    for triple in graph:
        result.add(triple)
    transitive_props = {s for s, _, o in graph.triples((None, RDF.type, OWL.TransitiveProperty))}
    symmetric_props = {s for s, _, o in graph.triples((None, RDF.type, OWL.SymmetricProperty))}
    changed = True
    while changed:
        changed = False
        subclass = list(result.triples((None, RDFS.subClassOf, None)))
        subproperty = list(result.triples((None, RDFS.subPropertyOf, None)))
        for child, _, parent in subclass:
            for instance, _, cls in list(result.triples((None, RDF.type, child))):
                changed |= _add(result, (instance, RDF.type, parent))
            for ancestor, _, _ in list(result.triples((parent, RDFS.subClassOf, None))):
                changed |= _add(result, (child, RDFS.subClassOf, ancestor))
        for child, _, parent in subproperty:
            for subject, _, obj in list(result.triples((None, child, None))):
                changed |= _add(result, (subject, parent, obj))
        for predicate in set(transitive_props):
            for left, _, middle in list(result.triples((None, predicate, None))):
                for _, _, right in list(result.triples((middle, predicate, None))):
                    changed |= _add(result, (left, predicate, right))
        for predicate in set(symmetric_props):
            for left, _, right in list(result.triples((None, predicate, None))):
                changed |= _add(result, (right, predicate, left))
        for left, predicate, right in list(result):
            inverse = result.value(predicate, OWL.inverseOf)
            if inverse is not None:
                changed |= _add(result, (right, inverse, left))
            for inverse_predicate in result.subjects(OWL.inverseOf, predicate):
                changed |= _add(result, (right, inverse_predicate, left))
        for left, _, right in list(result.triples((None, OWL.equivalentClass, None))):
            changed |= _add(result, (left, RDFS.subClassOf, right))
            changed |= _add(result, (right, RDFS.subClassOf, left))
    return result


def _add(graph: Graph, triple: tuple) -> bool:
    if triple in graph:
        return False
    graph.add(triple)
    return True


def reason(graphs: Iterable[Graph]) -> tuple[Graph, int]:
    source = Graph()
    for graph in graphs:
        for triple in graph:
            source.add(triple)
    inferred = _closure(source)
    return inferred, len(inferred) - len(source)


def run(run_mode: str = "sample") -> int:
    if not ONTOLOGY.exists() or not ASSERTED.exists():
        print("reason: ontology or asserted Turtle missing")
        return 1
    ontology = Graph().parse(ONTOLOGY, format="turtle")
    asserted = Graph().parse(ASSERTED, format="turtle")
    inferred, inferred_count = reason([ontology, asserted])
    RDF_DIR.mkdir(parents=True, exist_ok=True)
    inferred.serialize(destination=INFERRED, format="turtle")
    REPORT.write_text(json.dumps({"status": "PASS", "inferred_triples": inferred_count}, indent=2), encoding="utf-8")
    print(f"reason ({run_mode}): {inferred_count} inferred triples -> {INFERRED}")
    return 0
