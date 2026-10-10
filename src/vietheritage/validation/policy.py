"""Publication policy over the public graph, using local identity evidence only."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS, SH, XSD

from .semantic import (
    DEFAULT_BASE,
    Contract,
    base_uri,
    identity_component_issues,
    issue,
    literal_matches,
    report,
    reviewed_multiple_local_exception,
    same_as_components,
    validate_semantics,
)
from .shacl import validate_graph as validate_shapes

ENTITY_ID = re.compile(
    r"(?:registry|person|area|event|period|complex|organization|style|site|museum|"
    r"intangible|treasure|documentary|object)-[A-Za-z0-9._~-]+"
)
PRODUCTION_SITE_ID = re.compile(r"site-[0-9a-f]{12}(?:-[0-9a-f]{6})?")
GEO = "http://www.w3.org/2003/01/geo/wgs84_pos#"


def is_fixture_site_id(identifier: str) -> bool:
    return identifier.startswith("site-") and PRODUCTION_SITE_ID.fullmatch(identifier) is None


def _http(value) -> bool:
    parsed = urlsplit(str(value))
    return isinstance(value, URIRef) and parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _official(value) -> bool:
    host = urlsplit(str(value)).hostname or ""
    return _http(value) and (host == "dsvh.gov.vn" or host.endswith(".dsvh.gov.vn"))


def _uri_errors(data: Graph, contract: Contract, records: list[dict], mode: str) -> list[dict]:
    errors = []
    nodes = {node for triple in data for node in triple if isinstance(node, URIRef)}
    nodes.update(URIRef(f"{contract.base}/resource/{record.get('entity_id', '')}") for record in records)
    for node in nodes:
        text = str(node)
        if contract.base != DEFAULT_BASE and text.startswith(DEFAULT_BASE + "/"):
            errors.append(issue("INVALID_URI", node, message="URI uses the development base instead of VH_BASE_URI."))
        if not text.startswith(contract.base + "/"):
            continue
        path = text[len(contract.base) + 1:]
        valid = all(re.fullmatch(r"[A-Za-z0-9._~-]+", segment) for segment in path.rstrip("/").split("/"))
        if path.startswith("resource/"):
            identifier = path[len("resource/"):]
            if mode == "full" and is_fixture_site_id(identifier):
                errors.append(issue(
                    "FIXTURE_ID_IN_PRODUCTION", node,
                    message="Noncanonical site- IDs are fixture-only.",
                ))
            auxiliary = bool(contract.types(node) & {PROV.Activity, DCAT.Distribution})
            valid = valid and (auxiliary or ENTITY_ID.fullmatch(identifier) is not None)
        elif path.startswith("ontology/"):
            valid = valid and "/" not in path[len("ontology/"):].rstrip("/")
        elif path.startswith("graph/"):
            valid = valid and path[len("graph/"):] in {"ontology", "data", "external-links", "inferred", "metadata"}
        else:
            valid = valid and (path == "dataset/vietheritage" or bool(
                contract.types(node) & {PROV.Activity, DCAT.Distribution}
            ))
        if DCAT.Dataset in contract.types(node) and text != contract.base + "/dataset/vietheritage":
            valid = False
        if not valid:
            errors.append(issue("INVALID_URI", node, message="Not a canonical project URI or allowed entity ID."))
    return errors


def _identity_errors(data: Graph, assertions: Graph, contract: Contract, records: dict, reviews: list[dict]) -> list[dict]:
    errors = []
    reviewed = {(row.get("source_uri"), row.get("target_uri")) for row in reviews
                 if row.get("status") == "verified" and row.get("target_dataset") == "dbpedia"
                 and all(str(row.get(field, "")).lower() == "true" for field in (
                     "type_compatible", "same_entity", "granularity_compatible",
                     "scope_compatible", "location_compatible",
                 ))
                 and str(row.get("reviewer") or "").strip()
                 and not str(row.get("reviewer") or "").strip().casefold().startswith("automated:")
                 and str(row.get("reviewed_at") or "").strip()
                 and str(row.get("reason") or "").strip()}
    approved_pairs = []
    for source, target in assertions.subject_objects(OWL.sameAs):
        record = records.get(str(source), {})
        qid = (record.get("external_ids") or {}).get("wikidata")
        wikidata = isinstance(target, URIRef) and re.fullmatch(r"https://www\.wikidata\.org/entity/Q[1-9][0-9]*", str(target))
        dbpedia = isinstance(target, URIRef) and re.fullmatch(r"https?://dbpedia\.org/resource/[^\s<>\"{}|\\^`?#/]+", str(target))
        allowed = bool(record) and (
            (wikidata and str(target).rsplit("/", 1)[-1] == qid)
            or (dbpedia and (str(source), str(target)) in reviewed)
        )
        if dbpedia and str(target).rsplit("/", 1)[-1].startswith(("Category:", "Template:", "File:")):
            allowed = False
        if contract.types(target) & {OWL.Class, RDFS.Class}:
            allowed = False
        for left, right, _ in contract.disjoint_pairs():
            if ((contract.matches(source, left) and contract.matches(target, right))
                    or (contract.matches(source, right) and contract.matches(target, left))):
                allowed = False
        if not allowed:
            errors.append(issue("INVALID_SAME_AS", source, OWL.sameAs,
                                f"Target {target} lacks a matching source QID or verified, compatible DBpedia identity."))
        else:
            approved_pairs.append((source, target))

    components = same_as_components(approved_pairs)
    unsafe: set = set()
    seen_components: set[tuple[str, ...]] = set()
    for component in components.values():
        key = tuple(sorted(map(str, component)))
        if key in seen_components:
            continue
        seen_components.add(key)
        conflicts = identity_component_issues(component, records, contract)
        local_count = sum(str(node) in records for node in component)
        if local_count > 1 and not reviewed_multiple_local_exception(component, records, reviews):
            conflicts.append("SECOND_ACTIVE_LOCAL_ENTITY")
        if conflicts:
            unsafe.update(component)
            local = sorted((node for node in component if str(node) in records), key=str)
            errors.append(issue(
                "INVALID_SAME_AS", local[0] if local else min(component, key=str), OWL.sameAs,
                "; ".join(sorted(set(conflicts))),
            ))
    approved_pairs = [(source, target) for source, target in approved_pairs if source not in unsafe and target not in unsafe]
    components = same_as_components(approved_pairs)
    # OWL Mini may entail reflexive, reversed and transitive identities. Only
    # those justified by the approved assertion components are accepted.
    for source, target in data.subject_objects(OWL.sameAs):
        if (source, OWL.sameAs, target) in assertions or source == target:
            continue
        if target not in components.get(source, set()):
            errors.append(issue("INVALID_SAME_AS", source, OWL.sameAs,
                                f"Inferred identity {target} is not supported by approved assertions."))
    return errors


def validate_public_graph(
    data: Graph, ontology: Graph, *, assertions: Graph | None = None,
    canonical_records=(), link_reviews=(), run_mode: str = "sample",
    base: str | None = None, require_dataset: bool = False,
) -> dict:
    """Validate publication requirements, including identity links in assertions.

    `assertions` excludes only the inferred component, allowing legitimate OWL
    identity closure without treating a supplied inferred file as trusted input.
    """
    base = base_uri(base)
    parsed_base = urlsplit(base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.hostname or base.endswith("/") or parsed_base.query or parsed_base.fragment:
        return report([issue("CONFIG_INVALID", message="VH_BASE_URI must be an HTTP(S) base without a trailing slash, query or fragment.")])
    records = list(canonical_records)
    by_uri = {f"{base}/resource/{record['entity_id']}": record for record in records if "entity_id" in record}
    contract = Contract(data, ontology, base)
    result = validate_semantics(data, ontology, base=base)
    errors = result["errors"]
    errors.extend(_uri_errors(data + ontology, contract, records, run_mode))
    for node in contract.classes | contract.object_properties | contract.datatype_properties:
        languages = {value.language for value in ontology.objects(node, RDFS.label) if isinstance(value, Literal) and str(value).strip()}
        if not {"vi", "en"} <= languages:
            errors.append(issue("MISSING_LABEL", node, RDFS.label, "Project schema terms require labels in vi and en."))
    if (URIRef(base + "/ontology/"), RDF.type, OWL.Ontology) not in ontology:
        errors.append(issue("NAMESPACE_VIOLATION", message="Missing ontology declaration at the configured namespace."))

    entities = {node for triple in data for node in (triple[0], triple[2])
                if isinstance(node, URIRef) and str(node).startswith(base + "/resource/")
                and not contract.types(node) & {PROV.Activity, DCAT.Distribution, DCAT.Dataset}}
    entities.update(URIRef(node) for node in by_uri)
    source_entities = {node for node in entities if not any(ontology.triples((node, None, None))) or str(node) in by_uri}
    for node in source_entities:
        record = by_uri.get(str(node), {})
        sources = set(data.objects(node, DCTERMS.source))
        derived = set(data.objects(node, PROV.wasDerivedFrom))
        if not sources & derived:
            errors.append(issue("PROVENANCE_VIOLATION", node, message="Source and derivation must retain a common source URI."))
        registry = str(node).startswith(base + "/resource/registry-") or record.get("source_status", "").startswith("registry")
        # DEC-M2-005: category có trang dsvh rỗng được bổ sung từ trang danh sách Wikipedia; provenance
        # bắt buộc là chính trang Wikipedia đó (không giả là nguồn chính thức).
        wikipedia_list = (record.get("provenance") or {}).get("method") == "mediawiki-api"
        if registry and wikipedia_list:
            if not any((urlsplit(str(value)).hostname or "").endswith(".wikipedia.org") for value in sources & derived):
                errors.append(issue("PROVENANCE_VIOLATION", node, message="Wikipedia list provenance is required."))
        elif registry and not any(_official(value) for value in sources & derived):
            errors.append(issue("PROVENANCE_VIOLATION", node, message="Official registry provenance is required."))
        if record.get("registry_url") and URIRef(record["registry_url"]) not in sources & derived:
            errors.append(issue("PROVENANCE_VIOLATION", node, message="Canonical registry source is missing from RDF provenance."))
        expected_sources = {
            URIRef(candidate)
            for source_record in record.get("source_records") or []
            for candidate in (source_record.get("source_url"), (source_record.get("provenance") or {}).get("source"))
            if candidate
        }
        missing_sources = expected_sources - (sources & derived)
        if missing_sources:
            errors.append(issue(
                "PROVENANCE_VIOLATION", node,
                message="Source-record provenance is missing from RDF.",
                missing_sources=sorted(map(str, missing_sources)),
            ))
        wikipedia = record.get("source_status") in {"registry+wikipedia", "registry+enriched"}
        wikipedia |= any((urlsplit(str(value)).hostname or "").endswith(".wikipedia.org") for value in sources | derived)
        wikipedia |= any(data.objects(node, contract.vh.sourcePageId)) or any(data.objects(node, contract.vh.sourceTitle))
        if wikipedia:
            for prop in (contract.vh.sourcePageId, contract.vh.sourceTitle):
                if not any(data.objects(node, prop)):
                    errors.append(issue("WIKIPEDIA_METADATA_MISSING", node, prop, "Successful Wikipedia enrichment requires page ID and title."))
        for value in data.objects(node, contract.vh.sourcePageId):
            if literal_matches(value, XSD.integer) and int(value) <= 0:
                errors.append(issue("RANGE_VIOLATION", node, contract.vh.sourcePageId, "Page ID must be positive."))
    if require_dataset and (URIRef(base + "/dataset/vietheritage"), RDF.type, DCAT.Dataset) not in data:
        errors.append(issue("METADATA_VIOLATION", message="The canonical dataset description is missing."))

    conforms, _, results = validate_shapes(data, ontology=ontology, base=base,
                                          entities=entities, source_entities=source_entities)
    for entry in results.subjects(RDF.type, SH.ValidationResult):
        node, path = results.value(entry, SH.focusNode), results.value(entry, SH.resultPath)
        component = results.value(entry, SH.sourceConstraintComponent)
        if path == RDFS.label:
            code = "MISSING_LABEL"
        elif path == contract.vh.recognizedBy:
            code = "RANGE_VIOLATION"
        elif path == contract.vh.recognitionYear and component == SH.MaxCountConstraintComponent:
            code = "CARDINALITY_VIOLATION"
        elif str(path) in {GEO + "lat", GEO + "long"}:
            code = "DATATYPE_VIOLATION" if component == SH.DatatypeConstraintComponent else "INVALID_COORDINATE"
        elif component == SH.DatatypeConstraintComponent:
            code = "DATATYPE_VIOLATION"
        elif DCAT.Dataset in contract.types(node):
            code = "METADATA_VIOLATION"
        elif path == RDF.type and node in entities:
            code = "MISSING_TYPE"
        else:
            code = "PROVENANCE_VIOLATION"
        errors.append(issue(code, node, path, "; ".join(sorted(str(m) for m in results.objects(entry, SH.resultMessage)))))
    errors.extend(_identity_errors(data, data if assertions is None else assertions,
                                   contract, by_uri, list(link_reviews)))
    return report(errors, axioms=result["axioms"], conforms=conforms)
