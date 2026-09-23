"""RDF Generator (COMP-005, Section 20) — canonical.jsonl -> Turtle.

Input: ``data/processed/canonical.jsonl`` (đúng ``canonical-record.schema.json``).
Output: ``data/rdf/vietheritage.ttl``, ``data/rdf/dataset-metadata.ttl``.

Dùng RDFLib 7.1.3, sort triple theo (subject, predicate, object) trước khi
serialize để output deterministic (Section 20.1).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, PROV, RDF, RDFS, SKOS, XSD

from vietheritage.validation.policy import ENTITY_ID
from vietheritage.validation.semantic import DEFAULT_BASE, Contract, base_uri

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RDF_DIR = REPO_ROOT / "data" / "rdf"
MAPPING_PATH = REPO_ROOT / "config" / "mapping.yaml"
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "vietheritage.ttl"
SCHEMA_PATH = REPO_ROOT / "schema" / "canonical-record.schema.json"

VH = Namespace(DEFAULT_BASE + "/ontology/")
VHR = Namespace(DEFAULT_BASE + "/resource/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
LICENSE = URIRef("https://creativecommons.org/licenses/by-sa/4.0/")


def _base() -> str:
    base = base_uri()
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or base.endswith("/") or parsed.query or parsed.fragment:
        raise ValueError("CONFIG_INVALID: invalid VH_BASE_URI")
    return base


def _term(name: str) -> URIRef:
    prefix, local = name.split(":", 1)
    namespaces = {
        "vh": Namespace(_base() + "/ontology/"), "vhr": Namespace(_base() + "/resource/"),
        "rdf": RDF, "rdfs": RDFS, "xsd": XSD, "dcterms": DCTERMS, "prov": PROV, "geo": GEO,
    }
    return namespaces[prefix][local]


def load_mapping() -> dict:
    return yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))


def load_ontology() -> Graph:
    """Use the authoritative schema at the configured namespace, in memory only."""
    graph = Graph().parse(ONTOLOGY_PATH, format="turtle")
    base = _base()
    if base == DEFAULT_BASE:
        return graph
    rebased = Graph()
    for triple in graph:
        rebased.add(tuple(
            URIRef(base + str(node)[len(DEFAULT_BASE):])
            if isinstance(node, URIRef) and str(node).startswith(DEFAULT_BASE + "/") else node
            for node in triple
        ))
    return rebased


def entity_uri(entity_id: str) -> URIRef:
    if not ENTITY_ID.fullmatch(entity_id):
        raise ValueError(f"INVALID_URI: invalid entity ID {entity_id!r}")
    return URIRef(f"{_base()}/resource/{entity_id}")


def add_entity_type_triples(g: Graph, entity_id: str, record: dict[str, Any], *, mapping=None) -> None:
    """entity_type -> rdf:type + site_types -> subtype (Section 19)."""
    subject = entity_uri(entity_id)
    mapping = mapping if mapping is not None else load_mapping()
    entity_type = record.get("entity_type")
    cls = mapping["entity_types"].get(entity_type, {}).get("class")
    if cls is not None:
        g.add((subject, RDF.type, _term(cls)))
    category = record.get("registry_category")
    subclass = mapping["registry_category_subclass"].get(category)
    if subclass:
        if entity_type != "IntangibleHeritage":
            raise ValueError(f"MAPPING_TYPE_MISMATCH: {category} requires IntangibleHeritage")
        g.add((subject, RDF.type, _term(subclass)))
    if entity_type != "HeritageSite":
        return
    if category == "world_heritage":
        g.add((subject, _term("vh:recognizedBy"), entity_uri("organization-unesco")))

    for site_type in record.get("site_types", []) or []:
        normalized = site_type.strip().lower()
        for token, subtype_cls in mapping["site_type_tokens"].items():
            if token in normalized:
                g.add((subject, RDF.type, _term(subtype_cls)))


def _record_contract(g: Graph, entity_id: str, record: dict, mapping: dict) -> Contract:
    typed = g + Graph()
    add_entity_type_triples(typed, entity_id, record, mapping=mapping)
    return Contract(typed, load_ontology())


def _domain_matches(contract: Contract, subject: URIRef, predicate: URIRef) -> bool:
    return all(contract.matches(subject, domain) for domain in contract.ontology.objects(predicate, RDFS.domain))


def add_label_and_literals(g: Graph, entity_id: str, record: dict[str, Any], *, mapping=None, contract=None) -> None:
    subject = entity_uri(entity_id)
    mapping = mapping if mapping is not None else load_mapping()
    contract = contract or _record_contract(g, entity_id, record, mapping)
    for field, rule in mapping["literal_properties"].items():
        value = record.get(field)
        if value is None or value == "":
            continue
        if rule.get("required_when") == "wikipedia_enriched" and record.get("source_status") == "registry_only":
            continue
        predicate = _term(rule["predicate"])
        if not _domain_matches(contract, subject, predicate):
            continue
        datatype = _term(rule["datatype"]) if "datatype" in rule else None
        if datatype == XSD.gYear:
            value = f"{value:04d}"
        literal = Literal(value, lang=rule.get("lang"), datatype=datatype)
        g.add((subject, predicate, literal))
        if field == "description_vi":
            g.add((subject, DCTERMS.description, literal))

    for alias in record.get("aliases_vi", []) or []:
        if alias and alias != record.get("label_vi"):
            g.add((subject, SKOS.altLabel, Literal(alias, lang="vi")))

    coords = record.get("coordinates")
    if coords and coords.get("lat") is not None and coords.get("lon") is not None:
        for field, rule in mapping["coordinate_properties"].items():
            g.add((subject, _term(rule["predicate"]), Literal(str(coords[field]), datatype=_term(rule["datatype"]))))


def add_registry_semantics(g: Graph, entity_id: str, record: dict[str, Any]) -> None:
    """Retain the source category without minting noncanonical entity URIs."""
    subject = entity_uri(entity_id)
    category = record.get("registry_category")
    if category:
        g.add((subject, DCTERMS.subject, Literal(str(category))))


def add_relations(g: Graph, entity_id: str, record: dict[str, Any], *, mapping=None, contract=None) -> None:
    """Section 19 mapping table — relation field -> object property, omit khi thiếu."""
    subject = entity_uri(entity_id)
    mapping = mapping if mapping is not None else load_mapping()
    contract = contract or _record_contract(g, entity_id, record, mapping)
    relations = record.get("relations", {}) or {}

    for field_name, rule in mapping["relation_properties"].items():
        predicate = _term(rule["predicate"])
        if not _domain_matches(contract, subject, predicate):
            continue
        target_ids = record.get("parent_area") if field_name == "parent_area" else relations.get(field_name)
        target_ids = target_ids or relations.get(field_name)
        if not target_ids:
            continue
        if isinstance(target_ids, str):
            target_ids = [target_ids]
        for target_id in target_ids:
            if not ENTITY_ID.fullmatch(target_id):
                continue
            target = entity_uri(target_id)
            required = list(contract.ontology.objects(predicate, RDFS.range))
            if rule.get("object_must_be"):
                required.append(_term(rule["object_must_be"]))
            if not contract.types(target) or not all(contract.matches(target, cls) for cls in required):
                continue
            g.add((subject, predicate, target))


def _snapshot(records: list[dict]) -> str:
    snapshots = [str(record["coverage_snapshot"]) for record in records if record.get("coverage_snapshot")]
    timestamps = [str(record["retrieved_at"]) for record in records if record.get("retrieved_at")]
    return max(snapshots or timestamps or ["unknown"])


def _activity_uri(records: list[dict]) -> URIRef:
    identifier = sha256(_snapshot(records).encode("utf-8")).hexdigest()[:12]
    return URIRef(f"{_base()}/resource/activity-run-{identifier}")


def add_provenance(g: Graph, entity_id: str, record: dict[str, Any], *, mapping=None, activity=None) -> None:
    """Section 21.1 — mọi source-derived entity MUST có dcterms:source + prov:wasDerivedFrom."""
    subject = entity_uri(entity_id)
    mapping = mapping if mapping is not None else load_mapping()
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
        for predicate in mapping["provenance_properties"]["source_url"]["predicates"]:
            g.add((subject, _term(predicate), URIRef(source)))
    g.add((subject, DCTERMS.license, LICENSE))
    if record.get("retrieved_at"):
        retrieved = datetime.fromisoformat(record["retrieved_at"])
        g.add((subject, DCTERMS.modified, Literal(retrieved.date(), datatype=XSD.date)))
    g.add((subject, PROV.wasGeneratedBy, activity or _activity_uri([record])))


def record_to_triples(g: Graph, record: dict[str, Any], *, mapping=None, contract=None, activity=None) -> None:
    entity_id = record["entity_id"]
    mapping = mapping if mapping is not None else load_mapping()
    add_entity_type_triples(g, entity_id, record, mapping=mapping)
    contract = contract or Contract(g, load_ontology())
    add_label_and_literals(g, entity_id, record, mapping=mapping, contract=contract)
    add_registry_semantics(g, entity_id, record)
    add_relations(g, entity_id, record, mapping=mapping, contract=contract)
    add_provenance(g, entity_id, record, mapping=mapping, activity=activity)


def build_graph(records: list[dict[str, Any]]) -> Graph:
    g = Graph()
    g.bind("vh", Namespace(_base() + "/ontology/"))
    g.bind("vhr", Namespace(_base() + "/resource/"))
    g.bind("geo", GEO)
    mapping = load_mapping()
    # Resolve references against all explicit canonical types, independent of row order.
    for record in records:
        add_entity_type_triples(g, record["entity_id"], record, mapping=mapping)
    contract = Contract(g, load_ontology())
    activity = _activity_uri(records)
    for record in records:
        record_to_triples(g, record, mapping=mapping, contract=contract, activity=activity)
    return g


def serialize_deterministic(g: Graph) -> str:
    """Section 20.1 — sort triple theo (subject, predicate, object) trước serialize."""
    triples = sorted(g, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))
    sorted_graph = Graph()
    sorted_graph.bind("vh", Namespace(_base() + "/ontology/"))
    sorted_graph.bind("vhr", Namespace(_base() + "/resource/"))
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
    snapshot = _snapshot(records)
    if coverage.get("snapshot_id") != snapshot:
        coverage = {}
    timestamps = [datetime.fromisoformat(record["retrieved_at"]) for record in records if record.get("retrieved_at")]
    if not timestamps:
        raise ValueError("RDF_METADATA_MISSING: no source retrieval timestamps")
    base = _base()
    dataset = URIRef(f"{base}/dataset/vietheritage")
    activity = _activity_uri(records)
    graph = Graph()
    graph.bind("vhr", Namespace(base + "/resource/"))
    graph.bind("dcat", DCAT)
    graph.bind("dcterms", DCTERMS)
    graph.bind("prov", PROV)
    graph.bind("xsd", XSD)
    graph.add((dataset, RDF.type, DCAT.Dataset))
    graph.add((dataset, DCTERMS.title, Literal("VietHeritageLOD dataset", lang="en")))
    graph.add((dataset, DCTERMS.title, Literal("Bộ dữ liệu VietHeritageLOD", lang="vi")))
    graph.add((dataset, DCTERMS.description, Literal("Snapshot Linked Open Data về di sản văn hóa Việt Nam trong phạm vi registry chính thức đã cấu hình.", lang="vi")))
    graph.add((dataset, DCTERMS.creator, Literal("VietHeritageLOD Team")))
    graph.add((dataset, DCTERMS.identifier, Literal(snapshot)))
    graph.add((dataset, DCTERMS.license, LICENSE))
    graph.add((dataset, PROV.wasGeneratedBy, activity))
    graph.add((activity, RDF.type, PROV.Activity))
    graph.add((activity, DCTERMS.identifier, Literal(snapshot)))
    graph.add((activity, PROV.startedAtTime, Literal(min(timestamps), datatype=XSD.dateTime)))
    graph.add((activity, PROV.endedAtTime, Literal(max(timestamps), datatype=XSD.dateTime)))
    graph.add((dataset, DCTERMS.created, Literal(min(timestamps).date(), datatype=XSD.date)))
    graph.add((dataset, DCTERMS.modified, Literal(max(timestamps).date(), datatype=XSD.date)))
    graph.add((dataset, DCTERMS.issued, Literal(snapshot, datatype=XSD.string)))
    source_urls = set(coverage.get("source_urls", []))
    source_urls.update(str(record.get("registry_url")) for record in records if record.get("registry_url"))
    source_urls.update(str(record.get("source_url")) for record in records if record.get("source_url"))
    source_urls.update(record["provenance"]["source"] for record in records if record.get("provenance", {}).get("source"))
    for source in sorted(source_urls):
        source_uri = URIRef(source)
        graph.add((dataset, DCTERMS.source, source_uri))
        graph.add((dataset, PROV.wasDerivedFrom, source_uri))
        graph.add((activity, PROV.used, source_uri))
        checksum = coverage.get("source_checksums", {}).get(source)
        if checksum:
            graph.add((activity, DCTERMS.description, Literal(f"{source} sha256={checksum}")))
    for key, value in _metadata_counts(asserted_count, records).items():
        graph.add((dataset, DCTERMS.extent, Literal(f"{key}={value}")))
    # Service URLs are the existing public Fuseki settings, not entity identities.
    endpoint = os.environ.get("FUSEKI_URL", "http://localhost:3031").rstrip("/")
    endpoint += "/" + os.environ.get("FUSEKI_DATASET", "vietheritage")
    graph.add((dataset, DCAT.accessURL, URIRef(endpoint + "/sparql")))
    graph.add((dataset, DCAT.downloadURL, URIRef(endpoint + "/data")))
    distributions = {"ontology": "ontology", "asserted": "data", "external-links": "external-links",
                     "inferred": "inferred", "metadata": "metadata"}
    for name, graph_name in distributions.items():
        graph_uri = URIRef(f"{base}/graph/{graph_name}")
        distribution = URIRef(f"{dataset}/distribution/{name}")
        graph.add((dataset, DCAT.distribution, distribution))
        graph.add((distribution, RDF.type, DCAT.Distribution))
        graph.add((distribution, DCAT.mediaType, Literal("text/turtle")))
        graph.add((distribution, DCTERMS.identifier, graph_uri))
        download = URIRef(endpoint + "/data?" + urlencode({"graph": str(graph_uri)}))
        graph.add((distribution, DCAT.accessURL, download))
        graph.add((distribution, DCAT.downloadURL, download))
    return graph


def refresh_dataset_metadata_metrics() -> None:
    path = RDF_DIR / "dataset-metadata.ttl"
    asserted_path = RDF_DIR / "vietheritage.ttl"
    canonical_path = PROCESSED_DIR / "canonical.jsonl"
    if not path.exists() or not asserted_path.exists() or not canonical_path.exists():
        return
    records = [json.loads(line) for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    graph = Graph().parse(path, format="turtle")
    dataset = URIRef(f"{_base()}/dataset/vietheritage")
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

    try:
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker())
        records: list[dict[str, Any]] = []
        with canonical_path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                validator.validate(record)
                if run_mode == "full" and record["entity_id"].startswith("site-"):
                    raise ValueError("FIXTURE_ID_IN_PRODUCTION: site- IDs are fixture-only")
                records.append(record)
        g = build_graph(records)
        turtle_output = serialize_deterministic(g)
        metadata_graph = build_dataset_metadata(records, len(g))
        metadata_output = serialize_deterministic(metadata_graph)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"generate-rdf: {exc}")
        return 1

    RDF_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RDF_DIR / "vietheritage.ttl"
    output_path.write_text(turtle_output, encoding="utf-8")

    # Round-trip validate: parse lại để xác nhận Turtle hợp lệ (Section 20 failure rule).
    validation_graph = Graph()
    validation_graph.parse(data=turtle_output, format="turtle")

    metadata_path = RDF_DIR / "dataset-metadata.ttl"
    metadata_path.write_text(metadata_output, encoding="utf-8")
    Graph().parse(data=metadata_output, format="turtle")

    print(f"generate-rdf ({run_mode}): {len(records)} entities, {len(g)} triples -> {output_path}; metadata -> {metadata_path}")
    return 0
