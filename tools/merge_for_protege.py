"""Merge ontology + asserted data + verified links into one Protégé-ready Turtle file.

HermiT (Protégé's default reasoner) supports only the OWL 2 datatype map, which
excludes ``xsd:gYear`` and ``xsd:date``. The export therefore rewrites year
literals to ``xsd:integer`` and dates to ``xsd:dateTime`` (also in
``rdfs:range``); the canonical artifacts under ``data/rdf`` are not touched.
Inferred triples are deliberately excluded so the reasoner in Protégé derives them.
"""
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef, XSD

root = Path.cwd()

inputs = [
    root / "ontology/vietheritage.ttl",
    root / "data/rdf/vietheritage.ttl",
    root / "data/rdf/external-links.ttl",
]

DATATYPE_MAP = {XSD.gYear: XSD.integer, XSD.date: XSD.dateTime}


def protege_safe(term):
    if term in DATATYPE_MAP:
        return DATATYPE_MAP[term]
    if isinstance(term, Literal) and term.datatype in DATATYPE_MAP:
        value = str(term)
        if term.datatype == XSD.gYear:
            value = str(int(value))
        else:
            value = f"{value}T00:00:00"
        return Literal(value, datatype=DATATYPE_MAP[term.datatype])
    return term


g = Graph()
for path in inputs:
    print("Loading:", path)
    g.parse(path, format="turtle")

out = Graph()
for prefix, namespace in g.namespaces():
    out.bind(prefix, namespace)
for s, p, o in g:
    out.add((s, p, protege_safe(o)))

# OWL 2 DL requires every entity to be declared. External vocabularies
# (dcterms, prov, skos, geo, foaf) are declared as annotation properties so the
# reasoner ignores them, and foaf:Person as a class.
BUILTIN = (str(RDF), str(RDFS), str(OWL), str(XSD))
declared = {s for s, o in out.subject_objects(RDF.type)
            if o in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)}
# A super-property of a project property inherits its kind (e.g. dcterms:title).
for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
    for child, parent in out.subject_objects(RDFS.subPropertyOf):
        if (child, RDF.type, kind) in out and parent not in declared and not str(parent).startswith(BUILTIN):
            out.add((parent, RDF.type, kind))
            declared.add(parent)
for p in set(out.predicates()):
    if not str(p).startswith(BUILTIN) and p not in declared:
        out.add((p, RDF.type, OWL.AnnotationProperty))
for parent in set(out.objects(None, RDFS.subClassOf)):
    if isinstance(parent, URIRef) and (parent, RDF.type, OWL.Class) not in out and not str(parent).startswith(BUILTIN):
        out.add((parent, RDF.type, OWL.Class))

output = root / "vietheritage-protege-asserted.ttl"
out.serialize(output, format="turtle")
# RDF/XML parses in every OWL API version; older Turtle parsers reject long
# strings ending in an escaped quote (e.g. `...về\""""`).
output_owl = output.with_suffix(".owl")
out.serialize(output_owl, format="xml")

print("Triples:", len(out))
print("Output:", output, output_owl)
