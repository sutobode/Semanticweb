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
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RDF_DIR = REPO_ROOT / "data" / "rdf"

VH = Namespace("http://localhost:3030/vietheritage/ontology/")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")

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
    if record.get("registry_category") == "world_heritage":
        g.add((subject, RDF.type, VH.UNESCOHeritageSite))

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
        description = Literal(record["description_vi"], lang="vi")
        g.add((subject, RDFS.comment, description))
        g.add((subject, DCTERMS.description, description))

    for alias in record.get("aliases_vi", []) or []:
        if alias and alias != record.get("label_vi"):
            g.add((subject, SKOS.altLabel, Literal(alias, lang="vi")))

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


def add_registry_semantics(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    """Emit standard vocabulary metadata needed by semantic API projections."""
    subject = entity_uri(entity_id)
    category = record.get("registry_category")
    if category:
        category_slug = str(category).strip().lower().replace(" ", "-")
        category_uri = URIRef(f"{VHR}category/{category_slug}")
        g.add((subject, DCTERMS.subject, category_uri))
        g.add((category_uri, RDF.type, SKOS.Concept))
        g.add((category_uri, SKOS.prefLabel, Literal(str(category), lang="en")))


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
    sources: list[str] = []
    for candidate in (
        provenance.get("source"),
        record.get("registry_url"),
        record.get("source_url"),
    ):
        if candidate and candidate not in sources:
            sources.append(str(candidate))
    for source in sources:
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
    add_registry_semantics(g, entity_id, record)
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


def _latest_coverage() -> dict[str, Any]:
    reports = sorted((REPO_ROOT / "reports").glob("20*/coverage.json"), key=lambda path: path.stat().st_mtime)
    if not reports:
        return {}
    return json.loads(reports[-1].read_text(encoding="utf-8"))


def _verified_link_count() -> int:
    path = REPO_ROOT / "data" / "linking" / "link-review.jsonl"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("status") == "verified")


def _metadata_counts(asserted_count: int, records: list[dict[str, Any]]) -> dict[str, int]:
    inferred_path = RDF_DIR / "inferred.ttl"
    reasoning_path = RDF_DIR / "reasoning-report.json"
    inferred_count = len(Graph().parse(inferred_path, format="turtle")) if inferred_path.exists() else 0
    reasoning = json.loads(reasoning_path.read_text(encoding="utf-8")) if reasoning_path.exists() else {}
    return {
        "registry_records": len(records),
        "canonical_records": len(records),
        "asserted_triples": asserted_count,
        "inferred_closure_triples": inferred_count,
        "inferred_delta_triples": int(reasoning.get("inferred_triples", 0)),
        "verified_external_links": _verified_link_count(),
    }


def build_dataset_metadata(records: list[dict[str, Any]], asserted_count: int) -> Graph:
    coverage = _latest_coverage()
    snapshot = str((records[0] if records else {}).get("coverage_snapshot") or coverage.get("snapshot_id") or "unknown")
    dataset = URIRef(f"{VHR}dataset/vietheritage")
    activity = URIRef(f"{VHR}activity/{snapshot}")
    manifest = URIRef(f"{VHR}manifest/{snapshot}")
    graph = Graph()
    graph.bind("vhr", VHR)
    graph.bind("dcat", DCAT)
    graph.bind("dcterms", DCTERMS)
    graph.bind("prov", PROV)
    graph.bind("xsd", XSD)
    graph.add((dataset, RDF.type, DCAT.Dataset))
    graph.add((dataset, DCTERMS.title, Literal("VietHeritageLOD dataset", lang="en")))
    graph.add((dataset, DCTERMS.title, Literal("Bộ dữ liệu VietHeritageLOD", lang="vi")))
    graph.add((dataset, DCTERMS.description, Literal("Snapshot Linked Open Data về di sản văn hóa Việt Nam trong phạm vi registry chính thức đã cấu hình.", lang="vi")))
    graph.add((dataset, DCTERMS.identifier, Literal(snapshot)))
    graph.add((dataset, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by-sa/4.0/")))
    graph.add((dataset, PROV.wasGeneratedBy, activity))
    graph.add((dataset, PROV.wasDerivedFrom, manifest))
    graph.add((activity, RDF.type, PROV.Activity))
    graph.add((activity, DCTERMS.identifier, Literal(snapshot)))
    graph.add((manifest, RDF.type, PROV.Entity))
    graph.add((manifest, DCTERMS.identifier, Literal(snapshot)))
    timestamps = [str(record.get("retrieved_at")) for record in records if record.get("retrieved_at")]
    if timestamps:
        graph.add((activity, PROV.startedAtTime, Literal(min(timestamps), datatype=XSD.dateTime)))
        graph.add((activity, PROV.endedAtTime, Literal(max(timestamps), datatype=XSD.dateTime)))
        graph.add((dataset, DCTERMS.modified, Literal(max(timestamps), datatype=XSD.dateTime)))
    graph.add((dataset, DCTERMS.issued, Literal(snapshot, datatype=XSD.string)))
    source_urls = set(coverage.get("source_urls", []))
    source_urls.update(str(record.get("registry_url")) for record in records if record.get("registry_url"))
    source_urls.update(str(record.get("source_url")) for record in records if record.get("source_url"))
    for source in sorted(source_urls):
        source_uri = URIRef(source)
        graph.add((dataset, DCTERMS.source, source_uri))
        checksum = coverage.get("source_checksums", {}).get(source)
        if checksum:
            graph.add((manifest, DCTERMS.description, Literal(f"{source} sha256={checksum}")))
    for key, value in _metadata_counts(asserted_count, records).items():
        graph.add((dataset, DCTERMS.extent, Literal(f"{key}={value}")))
    distributions = {
        "ontology": ("text/turtle", "http://localhost:3030/vietheritage/graph/ontology"),
        "asserted": ("text/turtle", "http://localhost:3030/vietheritage/graph/data"),
        "external-links": ("text/turtle", "http://localhost:3030/vietheritage/graph/external-links"),
        "inferred": ("text/turtle", "http://localhost:3030/vietheritage/graph/inferred"),
        "metadata": ("text/turtle", "http://localhost:3030/vietheritage/graph/metadata"),
    }
    for name, (media_type, graph_uri) in distributions.items():
        distribution = URIRef(f"{dataset}/distribution/{name}")
        graph.add((dataset, DCAT.distribution, distribution))
        graph.add((distribution, RDF.type, DCAT.Distribution))
        graph.add((distribution, DCAT.mediaType, Literal(media_type)))
        graph.add((distribution, DCTERMS.identifier, URIRef(graph_uri)))
        graph.add((distribution, DCAT.accessURL, URIRef(f"http://localhost:3031/vietheritage/data?graph={graph_uri}")))
    return graph


def refresh_dataset_metadata_metrics() -> None:
    path = RDF_DIR / "dataset-metadata.ttl"
    asserted_path = RDF_DIR / "vietheritage.ttl"
    canonical_path = PROCESSED_DIR / "canonical.jsonl"
    if not path.exists() or not asserted_path.exists() or not canonical_path.exists():
        return
    records = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    graph = Graph().parse(path, format="turtle")
    dataset = URIRef(f"{VHR}dataset/vietheritage")
    for triple in list(graph.triples((dataset, DCTERMS.extent, None))):
        graph.remove(triple)
    for key, value in _metadata_counts(len(Graph().parse(asserted_path, format="turtle")), records).items():
        graph.add((dataset, DCTERMS.extent, Literal(f"{key}={value}")))
    graph.serialize(destination=path, format="turtle")


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

    metadata_graph = build_dataset_metadata(records, len(g))
    metadata_output = serialize_deterministic(metadata_graph)
    metadata_path = RDF_DIR / "dataset-metadata.ttl"
    metadata_path.write_text(metadata_output, encoding="utf-8")
    Graph().parse(data=metadata_output, format="turtle")

    print(f"generate-rdf ({run_mode}): {len(records)} entities, {len(g)} triples -> {output_path}; metadata -> {metadata_path}")
    return 0
