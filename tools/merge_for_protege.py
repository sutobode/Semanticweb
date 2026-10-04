from pathlib import Path
from rdflib import Graph

root = Path.cwd()

inputs = [
    root / "ontology/vietheritage.ttl",
    root / "data/rdf/vietheritage.ttl",
]

g = Graph()

for path in inputs:
    print("Loading:", path)
    g.parse(path, format="turtle")

output = root / "vietheritage-protege-asserted.ttl"
g.serialize(output, format="turtle")

print("Triples:", len(g))
print("Output:", output)
