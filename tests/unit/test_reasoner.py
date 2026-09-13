from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from vietheritage.reasoning.reasoner import reason

EX = Namespace("http://example/")


def test_reasoner_applies_subclass_and_subproperty_rules() -> None:
    graph = Graph()
    graph.add((EX.Child, RDFS.subClassOf, EX.Parent))
    graph.add((EX.child, RDF.type, EX.Child))
    graph.add((EX.p1, RDFS.subPropertyOf, EX.p2))
    graph.add((EX.a, EX.p1, EX.b))
    inferred, count = reason([graph])
    assert count >= 2
    assert (EX.child, RDF.type, EX.Parent) in inferred
    assert (EX.a, EX.p2, EX.b) in inferred


def test_reasoner_applies_inverse_symmetric_and_transitive_rules() -> None:
    graph = Graph()
    graph.add((EX.p, OWL.inverseOf, EX.q))
    graph.add((EX.sym, RDF.type, OWL.SymmetricProperty))
    graph.add((EX.trans, RDF.type, OWL.TransitiveProperty))
    graph.add((EX.a, EX.p, EX.b))
    graph.add((EX.x, EX.sym, EX.y))
    graph.add((EX.a, EX.trans, EX.b))
    graph.add((EX.b, EX.trans, EX.c))
    inferred, _ = reason([graph])
    assert (EX.b, EX.q, EX.a) in inferred
    assert (EX.y, EX.sym, EX.x) in inferred
    assert (EX.a, EX.trans, EX.c) in inferred
