"""RDF Generator (COMP-005, Section 20) — canonical.jsonl -> Turtle.

Input: ``data/processed/canonical.jsonl`` (đúng ``canonical-record.schema.json``).
Output: ``data/rdf/vietheritage.ttl``, ``data/rdf/dataset-metadata.ttl``.

Dùng RDFLib 7.1.3, sort triple theo (subject, predicate, object) trước khi
serialize để output deterministic (Section 20.1).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, XSD

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RDF_DIR = REPO_ROOT / "data" / "rdf"

VH = Namespace("http://localhost:3030/vietheritage/ontology/")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")

_ENTITY_TYPE_TO_CLASS = {
    "HeritageSite": VH.HeritageSite,
    "AdministrativeArea": VH.AdministrativeArea,
    "HistoricalPerson": VH.HistoricalPerson,
    "HistoricalEvent": VH.HistoricalEvent,
    "HistoricalPeriod": VH.HistoricalPeriod,
    "HeritageComplex": VH.HeritageComplex,
    "Organization": VH.Organization,
    "ArchitecturalStyle": VH.ArchitecturalStyle,
    "Museum": VH.Museum,
    "IntangibleHeritage": VH.IntangibleHeritage,
    "NationalTreasure": VH.NationalTreasure,
    "DocumentaryHeritage": VH.DocumentaryHeritage,
    "Artisan": VH.Artisan,
    "CulturalObject": VH.CulturalObject,
}

_SITE_TYPE_TOKENS = {
    "lịch sử": VH.HistoricalSite,
    "tôn giáo": VH.ReligiousSite,
    "khảo cổ": VH.ArchaeologicalSite,
    "kiến trúc": VH.ArchitecturalSite,
}

_RELATION_PREDICATES = {
    "located_in": VH.locatedIn,
    "parent_area": VH.locatedIn,
    "associated_persons": VH.associatedWithPerson,
    "associated_events": VH.associatedWithEvent,
    "periods": VH.belongsToPeriod,
    "part_of": VH.partOf,
    "member_sites": VH.hasMember,
    "recognized_by": VH.recognizedBy,
    "architectural_styles": VH.hasArchitecturalStyle,
}


def entity_uri(entity_id: str) -> URIRef:
    return VHR[entity_id]


def add_entity_type_triples(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    """entity_type -> rdf:type + site_types -> subtype (Section 19)."""
    subject = entity_uri(entity_id)
    entity_type = record.get("entity_type")
    cls = _ENTITY_TYPE_TO_CLASS.get(entity_type)
    if cls is not None:
        g.add((subject, RDF.type, cls))

    for site_type in record.get("site_types", []) or []:
        normalized = site_type.strip().lower()
        for token, subtype_cls in _SITE_TYPE_TOKENS.items():
            if token in normalized:
                g.add((subject, RDF.type, subtype_cls))


def add_label_and_literals(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    subject = entity_uri(entity_id)
    if record.get("label_vi"):
        g.add((subject, RDFS.label, Literal(record["label_vi"], lang="vi")))
    if record.get("description_vi"):
        g.add((subject, RDFS.comment, Literal(record["description_vi"], lang="vi")))

    if record.get("construction_year"):
        g.add((subject, VH.constructionYear, Literal(str(record["construction_year"]), datatype=XSD.gYear)))
    if record.get("recognition_year"):
        g.add((subject, VH.recognitionYear, Literal(str(record["recognition_year"]), datatype=XSD.gYear)))
    if record.get("birth_year"):
        g.add((subject, VH.birthYear, Literal(str(record["birth_year"]), datatype=XSD.gYear)))
    if record.get("death_year"):
        g.add((subject, VH.deathYear, Literal(str(record["death_year"]), datatype=XSD.gYear)))
    if record.get("address"):
        g.add((subject, VH.address, Literal(record["address"])))

    coords = record.get("coordinates")
    if coords and coords.get("lat") is not None and coords.get("lon") is not None:
        g.add((subject, GEO.lat, Literal(str(coords["lat"]), datatype=XSD.decimal)))
        g.add((subject, GEO.long, Literal(str(coords["lon"]), datatype=XSD.decimal)))

    if record.get("source_page_id"):
        g.add((subject, VH.sourcePageId, Literal(record["source_page_id"], datatype=XSD.integer)))
    if record.get("title"):
        g.add((subject, VH.sourceTitle, Literal(record["title"])))


def add_relations(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    """Section 19 mapping table — relation field -> object property, omit khi thiếu."""
    subject = entity_uri(entity_id)
    relations = record.get("relations", {}) or {}

    for field_name, predicate in _RELATION_PREDICATES.items():
        target_ids = relations.get(field_name)
        if not target_ids:
            continue
        if isinstance(target_ids, str):
            target_ids = [target_ids]
        for target_id in target_ids:
            g.add((subject, predicate, entity_uri(target_id)))

    built_by = relations.get("built_by")
    if built_by:
        built_by_type = relations.get("built_by_type", "HistoricalPerson")
        # Section 16 AX-007 baseline (A): builtBy CHỈ sinh khi target là HistoricalPerson.
        if built_by_type == "HistoricalPerson":
            targets = built_by if isinstance(built_by, list) else [built_by]
            for target_id in targets:
                g.add((subject, VH.builtBy, entity_uri(target_id)))
        else:
            targets = built_by if isinstance(built_by, list) else [built_by]
            for target_id in targets:
                g.add((subject, VH.recognizedBy, entity_uri(target_id)))


def add_provenance(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    """Section 21.1 — mọi source-derived entity MUST có dcterms:source + prov:wasDerivedFrom."""
    subject = entity_uri(entity_id)
    provenance = record.get("provenance", {}) or {}
    source = provenance.get("source") or record.get("source_url") or record.get("registry_url")
    if source:
        g.add((subject, DCTERMS.source, URIRef(source)))
        g.add((subject, PROV.wasDerivedFrom, URIRef(source)))
    license_value = provenance.get("license")
    if license_value:
        g.add((subject, DCTERMS.license, Literal(license_value)))

    wikidata_id = record.get("external_ids", {}).get("wikidata") if record.get("external_ids") else None
    if wikidata_id:
        g.add((subject, OWL.sameAs, URIRef(f"https://www.wikidata.org/entity/{wikidata_id}")))


def record_to_triples(g: Graph, record: dict[str, Any]) -> None:
    entity_id = record["entity_id"]
    add_entity_type_triples(g, entity_id, record)
    add_label_and_literals(g, entity_id, record)
    add_relations(g, entity_id, record)
    add_provenance(g, entity_id, record)


def build_graph(records: list[dict[str, Any]]) -> Graph:
    g = Graph()
    g.bind("vh", VH)
    g.bind("vhr", VHR)
    g.bind("geo", GEO)
    for record in records:
        record_to_triples(g, record)
    return g


def serialize_deterministic(g: Graph) -> str:
    """Section 20.1 — sort triple theo (subject, predicate, object) trước serialize."""
    triples = sorted(g, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))
    sorted_graph = Graph()
    sorted_graph.bind("vh", VH)
    sorted_graph.bind("vhr", VHR)
    sorted_graph.bind("geo", GEO)
    for triple in triples:
        sorted_graph.add(triple)
    return sorted_graph.serialize(format="turtle")


def run(run_mode: str = "sample") -> int:
    """`make generate-rdf` — canonical.jsonl -> vietheritage.ttl."""
    canonical_path = PROCESSED_DIR / "canonical.jsonl"
    if not canonical_path.exists():
        print(f"generate-rdf: {canonical_path} not found; run map first")
        return 1

    records: list[dict[str, Any]] = []
    with canonical_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    g = build_graph(records)
    turtle_output = serialize_deterministic(g)

    RDF_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RDF_DIR / "vietheritage.ttl"
    output_path.write_text(turtle_output, encoding="utf-8")

    # Round-trip validate: parse lại để xác nhận Turtle hợp lệ (Section 20 failure rule).
    validation_graph = Graph()
    validation_graph.parse(data=turtle_output, format="turtle")

    print(f"generate-rdf ({run_mode}): {len(records)} entities, {len(g)} triples -> {output_path}")
    return 0
