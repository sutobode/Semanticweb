"""Read-only Semantic Web API backed by the Fuseki RDF graph.

The module deliberately keeps RDF as the source of truth. JSON responses are
convenience projections and retain ``@id``/``@type``/``@context`` so clients
can follow the canonical linked-data resource.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

REPO_ROOT = Path(__file__).resolve().parents[3]
QUERY_DIR = REPO_ROOT / "sparql"
DEFAULT_BASE_URI = os.getenv("VH_BASE_URI", "http://localhost:3030/vietheritage").rstrip("/")
DEFAULT_FUSEKI_ENDPOINT = os.getenv(
    "FUSEKI_QUERY_URL",
    f"{os.getenv('FUSEKI_URL', 'http://localhost:3030').rstrip('/')}/{os.getenv('FUSEKI_DATASET', 'vietheritage')}/sparql",
)
VH = Namespace(f"{DEFAULT_BASE_URI}/ontology/")
VHR = Namespace(f"{DEFAULT_BASE_URI}/resource/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
SKOS_NS = Namespace("http://www.w3.org/2004/02/skos/core#")

JSONLD_CONTEXT: dict[str, Any] = {
    "vh": f"{DEFAULT_BASE_URI}/ontology/",
    "vhr": f"{DEFAULT_BASE_URI}/resource/",
    "rdf": str(RDF),
    "rdfs": str(RDFS),
    "owl": str(OWL),
    "dcterms": str(DCTERMS),
    "prov": str(PROV),
    "skos": str(SKOS_NS),
    "geo": str(GEO),
    "id": "@id",
    "type": "@type",
    "label": "rdfs:label",
    "description": "dcterms:description",
    "category": "dcterms:subject",
    "sameAs": "owl:sameAs",
}

ENTITY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ENTITY_TYPES = {
    "HeritageSite",
    "AdministrativeArea",
    "HistoricalPerson",
    "HistoricalEvent",
    "HistoricalPeriod",
    "HeritageComplex",
    "Organization",
    "ArchitecturalStyle",
    "Museum",
    "IntangibleHeritage",
    "NationalTreasure",
    "DocumentaryHeritage",
    "Artisan",
    "CulturalObject",
}


class APIError(Exception):
    """An expected HTTP/API error with a safe client-facing message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class QueryResult:
    status: int
    payload: dict[str, Any]



def _literal(value: str) -> str:
    return Literal(value).n3()


def _iri(value: str | URIRef) -> str:
    return URIRef(str(value)).n3()


def _entity_uri(entity_id: str) -> URIRef:
    validate_entity_id(entity_id)
    return URIRef(f"{DEFAULT_BASE_URI}/resource/{entity_id}")


def validate_entity_id(entity_id: str) -> str:
    if not entity_id or not ENTITY_ID_RE.fullmatch(entity_id):
        raise APIError(400, "INVALID_ENTITY_ID", "entity_id must contain lowercase letters, digits, and hyphens")
    return entity_id


def _validated_page(value: str | None, default: int, maximum: int | None = None) -> int:
    if value is None or value == "":
        return default
    try:
        result = int(value)
    except ValueError as exc:
        raise APIError(400, "INVALID_PAGINATION", "page and page_size must be integers") from exc
    if result < 1 or (maximum is not None and result > maximum):
        raise APIError(400, "INVALID_PAGINATION", "pagination value is outside the allowed range")
    return result


def _binding_value(binding: dict[str, Any] | None) -> str | None:
    return None if not binding else binding.get("value")


def _binding_int(binding: dict[str, Any] | None, default: int = 0) -> int:
    try:
        return int(_binding_value(binding) or default)
    except ValueError:
        return default


def _term_from_binding(binding: dict[str, Any]) -> URIRef | BNode | Literal:
    kind = binding.get("type")
    value = binding.get("value", "")
    if kind == "uri":
        return URIRef(value)
    if kind == "bnode":
        return BNode(value)
    datatype = binding.get("datatype")
    language = binding.get("xml:lang") or binding.get("lang")
    return Literal(value, datatype=URIRef(datatype) if datatype else None, lang=language)


def _json_term(binding: dict[str, Any]) -> dict[str, Any]:
    result = {"type": binding.get("type", "literal"), "value": binding.get("value", "")}
    for key in ("xml:lang", "datatype"):
        if key in binding:
            result[key] = binding[key]
    return result


class FusekiClient:
    """Small requests-based SPARQL 1.1 client with injectable transport for tests."""

    def __init__(
        self,
        endpoint: str | None = None,
        request_get: Callable[..., Any] = requests.get,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = endpoint or DEFAULT_FUSEKI_ENDPOINT
        self.request_get = request_get
        self.timeout = timeout
        self.auth = (
            os.getenv("FUSEKI_USER", "admin"),
            os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"),
        )

    def query(self, text: str) -> dict[str, Any]:
        if len(text) > 100_000:
            raise APIError(413, "QUERY_TOO_LARGE", "SPARQL query is too large")
        try:
            response = self.request_get(
                self.endpoint,
                params={"query": text, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
                auth=self.auth,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise APIError(504, "FUSEKI_TIMEOUT", "Fuseki query timed out") from exc
        except requests.RequestException as exc:
            raise APIError(503, "FUSEKI_UNAVAILABLE", "Fuseki is unavailable") from exc
        except (TypeError, ValueError) as exc:
            raise APIError(502, "FUSEKI_INVALID_RESPONSE", "Fuseki returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise APIError(502, "FUSEKI_INVALID_RESPONSE", "Fuseki response is not a JSON object")
        return payload

    def ask(self) -> bool:
        result = self.query("ASK WHERE { ?s ?p ?o }")
        return bool(result.get("boolean"))


class SemanticAPI:
    """Application services for search, resources, metadata, and allowlisted CQs."""

    def __init__(self, client: FusekiClient | None = None) -> None:
        self.client = client or FusekiClient()

    def health(self) -> dict[str, Any]:
        try:
            ok = self.client.ask()
        except APIError as exc:
            return {"status": "degraded", "fuseki": "error", "dataset": os.getenv("FUSEKI_DATASET", "vietheritage"), "error": exc.code}
        return {"status": "ok" if ok else "degraded", "fuseki": "ok" if ok else "empty", "dataset": os.getenv("FUSEKI_DATASET", "vietheritage")}

    def _where(self, params: dict[str, str]) -> str:
        clauses = [
            f"?entity a ?type ; rdfs:label ?label .",
            f"FILTER(STRSTARTS(STR(?entity), {_literal(f'{DEFAULT_BASE_URI}/resource/') }))",
            'FILTER(LANG(?label) = "vi" || LANG(?label) = "")',
            "OPTIONAL { ?entity dcterms:subject ?category . }",
            "OPTIONAL { ?entity vh:address ?location . }",
            "OPTIONAL { ?entity vh:recognitionYear ?recognitionYear . }",
            "OPTIONAL { ?entity vh:constructionYear ?constructionYear . }",
            "OPTIONAL { ?entity owl:sameAs ?external . }",
            "OPTIONAL { ?entity prov:wasDerivedFrom ?source . }",
        ]
        q = params.get("q", "").strip()
        if q:
            escaped = _literal(q)
            clauses.append(
                f"FILTER(CONTAINS(LCASE(STR(?label)), LCASE(STR({escaped}))) || "
                f"(BOUND(?location) && CONTAINS(LCASE(STR(?location)), LCASE(STR({escaped})))))"
            )
        entity_type = params.get("entity_type", "").strip()
        if entity_type:
            if entity_type not in ENTITY_TYPES:
                raise APIError(400, "INVALID_ENTITY_TYPE", "entity_type is not a known ontology class")
            clauses.append(f"?entity a <{DEFAULT_BASE_URI}/ontology/{entity_type}> .")
        category = params.get("registry_category", "").strip()
        if category:
            if not CATEGORY_RE.fullmatch(category):
                raise APIError(400, "INVALID_CATEGORY", "registry_category is invalid")
            clauses.append(f"?entity dcterms:subject <{DEFAULT_BASE_URI}/resource/category/{category}> .")
        location = params.get("location", "").strip()
        if location:
            escaped = _literal(location)
            clauses.append(f"FILTER(BOUND(?location) && CONTAINS(LCASE(STR(?location)), LCASE(STR({escaped}))))")
        year = params.get("year", "").strip()
        if year:
            if not re.fullmatch(r"[1-9][0-9]{0,3}", year):
                raise APIError(400, "INVALID_YEAR", "year must be a four-digit positive year")
            year_literal = f'"{year}"^^xsd:gYear'
            clauses.append(f"FILTER(?recognitionYear = {year_literal} || ?constructionYear = {year_literal})")
        return "\n".join(clauses)

    def search(self, params: dict[str, str]) -> dict[str, Any]:
        page = _validated_page(params.get("page"), 1)
        page_size = _validated_page(params.get("page_size"), 25, 100)
        where = self._where(params)
        total_query = f"PREFIX rdfs: <{RDFS}> PREFIX dcterms: <{DCTERMS}> PREFIX owl: <{OWL}> PREFIX prov: <{PROV}> PREFIX vh: <{VH}> SELECT (COUNT(DISTINCT ?entity) AS ?total) WHERE {{ {where} }}"
        total_result = self.client.query(total_query)
        total_bindings = total_result.get("results", {}).get("bindings", [])
        total = _binding_int(total_bindings[0].get("total") if total_bindings else None)
        offset = (page - 1) * page_size
        query = f"PREFIX rdfs: <{RDFS}> PREFIX dcterms: <{DCTERMS}> PREFIX owl: <{OWL}> PREFIX prov: <{PROV}> PREFIX vh: <{VH}> SELECT DISTINCT ?entity ?label ?type ?category ?location ?recognitionYear ?constructionYear ?external ?source WHERE {{ {where} }} ORDER BY LCASE(STR(?label)) LIMIT {page_size} OFFSET {offset}"
        result = self.client.query(query)
        items = self._group_search(result.get("results", {}).get("bindings", []))
        return {
            "@context": JSONLD_CONTEXT,
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_next": offset + page_size < total,
        }

    @staticmethod
    def _group_search(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in bindings:
            entity = _binding_value(row.get("entity"))
            if not entity:
                continue
            item = grouped.setdefault(
                entity,
                {
                    "@id": entity,
                    "@type": [],
                    "label": None,
                    "category": [],
                    "location": None,
                    "year": None,
                    "external_links": [],
                    "sources": [],
                },
            )
            for key, target in (("type", "@type"), ("category", "category"), ("external", "external_links"), ("source", "sources")):
                value = _binding_value(row.get(key))
                if value and value not in item[target]:
                    item[target].append(value)
            label = row.get("label")
            if label and item["label"] is None:
                item["label"] = {"@value": label.get("value", ""), "@language": label.get("xml:lang", "vi")}
            location = _binding_value(row.get("location"))
            if location:
                item["location"] = location
            item["year"] = item["year"] or _binding_value(row.get("recognitionYear")) or _binding_value(row.get("constructionYear"))
        for item in grouped.values():
            item["source_status"] = "registry+wikipedia" if any("wikipedia.org" in source for source in item["sources"]) else "registry_only"
        return list(grouped.values())

    def stats(self) -> dict[str, Any]:
        prefix = f"PREFIX rdfs: <{RDFS}> PREFIX rdf: <{RDF}> PREFIX owl: <{OWL}> PREFIX dcterms: <{DCTERMS}>"
        total = self.client.query(prefix + f' SELECT (COUNT(DISTINCT ?entity) AS ?total) WHERE {{ ?entity a ?type ; rdfs:label ?label . FILTER(STRSTARTS(STR(?entity), "{DEFAULT_BASE_URI}/resource/")) }}')
        classes = self.client.query(prefix + f' SELECT ?type (COUNT(DISTINCT ?entity) AS ?count) WHERE {{ ?entity a ?type ; rdfs:label ?label . FILTER(STRSTARTS(STR(?entity), "{DEFAULT_BASE_URI}/resource/")) }} GROUP BY ?type ORDER BY DESC(?count)')
        categories = self.client.query(prefix + f' SELECT ?category (COUNT(DISTINCT ?entity) AS ?count) WHERE {{ ?entity dcterms:subject ?category . FILTER(STRSTARTS(STR(?entity), "{DEFAULT_BASE_URI}/resource/")) }} GROUP BY ?category ORDER BY ?category')
        links = self.client.query(prefix + f' SELECT (COUNT(DISTINCT ?external) AS ?count) WHERE {{ ?entity owl:sameAs ?external . FILTER(STRSTARTS(STR(?entity), "{DEFAULT_BASE_URI}/resource/")) }}')
        return {
            "@context": JSONLD_CONTEXT,
            "dataset": os.getenv("FUSEKI_DATASET", "vietheritage"),
            "@id": f"{DEFAULT_BASE_URI}/dataset/vietheritage",
            "total_entities": _binding_int((total.get("results", {}).get("bindings") or [{}])[0].get("total")),
            "verified_external_links": _binding_int((links.get("results", {}).get("bindings") or [{}])[0].get("count")),
            "classes": [
                {"@id": _binding_value(row.get("type")), "count": _binding_int(row.get("count"))}
                for row in classes.get("results", {}).get("bindings", [])
            ],
            "categories": [
                {"@id": _binding_value(row.get("category")), "count": _binding_int(row.get("count"))}
                for row in categories.get("results", {}).get("bindings", [])
            ],
        }

    def _entity_rows(self, entity_id: str) -> list[dict[str, Any]]:
        uri = _entity_uri(entity_id)
        query = f"PREFIX rdfs: <{RDFS}> SELECT ?graph ?predicate ?object WHERE {{ GRAPH ?graph {{ {uri.n3()} ?predicate ?object }} }} ORDER BY STR(?graph) STR(?predicate) STR(?object)"
        result = self.client.query(query)
        return result.get("results", {}).get("bindings", [])

    def entity(self, entity_id: str) -> dict[str, Any]:
        validate_entity_id(entity_id)
        rows = self._entity_rows(entity_id)
        if not rows:
            raise APIError(404, "ENTITY_NOT_FOUND", "entity was not found in the RDF graph")
        uri = str(_entity_uri(entity_id))
        result: dict[str, Any] = {
            "@context": JSONLD_CONTEXT,
            "@id": uri,
            "@type": [],
            "label": [],
            "description": [],
            "aliases": [],
            "categories": [],
            "external_links": [],
            "sources": [],
            "coordinates": {},
            "relations": [],
            "asserted_triples": [],
            "inferred_triples": [],
        }
        for row in rows:
            predicate = _binding_value(row.get("predicate")) or ""
            object_value = _binding_value(row.get("object")) or ""
            object_binding = row.get("object", {})
            graph = _binding_value(row.get("graph")) or ""
            triple = {"predicate": predicate, "object": object_value, "object_type": object_binding.get("type", "literal"), "graph": graph}
            target = result["inferred_triples"] if "/graph/inferred" in graph else result["asserted_triples"]
            target.append(triple)
            if predicate == str(RDF.type) and object_value != str(OWL.Thing):
                if object_value not in result["@type"]:
                    result["@type"].append(object_value)
            elif predicate == str(RDFS.label):
                result["label"].append({"@value": object_value, "@language": object_binding.get("xml:lang", "")})
            elif predicate in {str(RDFS.comment), str(DCTERMS.description)}:
                if object_value not in [item["@value"] for item in result["description"]]:
                    result["description"].append({"@value": object_value, "@language": object_binding.get("xml:lang", "")})
            elif predicate == str(SKOS.altLabel):
                result["aliases"].append({"@value": object_value, "@language": object_binding.get("xml:lang", "")})
            elif predicate == str(DCTERMS.subject):
                result["categories"].append(object_value)
            elif predicate in {str(DCTERMS.source), str(PROV.wasDerivedFrom)}:
                if object_value not in result["sources"]:
                    result["sources"].append(object_value)
            elif predicate == str(OWL.sameAs):
                if object_value not in result["external_links"]:
                    result["external_links"].append({"@id": object_value, "verified": True})
            elif predicate == str(GEO.lat):
                result["coordinates"]["lat"] = object_value
            elif predicate == str(GEO.long):
                result["coordinates"]["lon"] = object_value
            elif object_binding.get("type") == "uri":
                result["relations"].append({"predicate": predicate, "object": object_value})
        result["source_status"] = "registry+wikipedia" if any("wikipedia.org" in source for source in result["sources"]) else "registry_only"
        if not result["coordinates"]:
            result.pop("coordinates")
        return result

    def entity_graph(self, entity_id: str) -> Graph:
        rows = self._entity_rows(entity_id)
        if not rows:
            raise APIError(404, "ENTITY_NOT_FOUND", "entity was not found in the RDF graph")
        graph = Graph()
        graph.bind("vh", VH)
        graph.bind("vhr", VHR)
        graph.bind("rdfs", RDFS)
        graph.bind("dcterms", DCTERMS)
        graph.bind("prov", PROV)
        graph.bind("skos", SKOS_NS)
        graph.bind("geo", GEO)
        subject = _entity_uri(entity_id)
        for row in rows:
            predicate = _term_from_binding(row["predicate"])
            obj = _term_from_binding(row["object"])
            graph.add((subject, predicate, obj))
        return graph

    def resource_turtle(self, entity_id: str) -> bytes:
        return self.entity_graph(entity_id).serialize(format="turtle").encode("utf-8")

    def resource_jsonld(self, entity_id: str) -> bytes:
        payload = self.entity_graph(entity_id).serialize(format="json-ld", context=JSONLD_CONTEXT, auto_compact=True)
        return str(payload).encode("utf-8")

    def queries(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted(QUERY_DIR.glob("CQ*.rq")):
            text = path.read_text(encoding="utf-8")
            result.append({"id": path.stem[:4], "title": path.stem, "description": path.stem.replace("-", " "), "read_only": True, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
        return result

    def run_query(self, query_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"CQ(?:0[1-9]|10)", query_id):
            raise APIError(404, "QUERY_NOT_FOUND", "only allowlisted CQ01-CQ10 queries are available")
        matches = list(QUERY_DIR.glob(f"{query_id}-*.rq"))
        if len(matches) != 1:
            raise APIError(404, "QUERY_NOT_FOUND", "competency question was not found")
        text = matches[0].read_text(encoding="utf-8")
        return {"id": query_id, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "results": self.client.query(text)}

    def openapi(self) -> dict[str, Any]:
        return {
            "openapi": "3.0.3",
            "info": {"title": "VietHeritageLOD Read-only Linked Data API", "version": "1.0.0"},
            "servers": [{"url": "http://localhost:8000"}],
            "paths": {
                "/api/health": {"get": {"responses": {"200": {"description": "Health"}}}},
                "/api/stats": {"get": {"responses": {"200": {"description": "RDF graph statistics"}}}},
                "/api/search": {"get": {"parameters": [{"name": "q", "in": "query"}, {"name": "page", "in": "query"}, {"name": "page_size", "in": "query"}], "responses": {"200": {"description": "Search results"}}}},
                "/api/entities/{entity_id}": {"get": {"responses": {"200": {"description": "Entity detail"}, "404": {"description": "Not found"}}}},
                "/resource/{entity_id}": {"get": {"responses": {"200": {"description": "Content-negotiated linked-data resource"}, "404": {"description": "Not found"}}}},
            },
        }


def render_entity_html(detail: dict[str, Any], entity_id: str) -> bytes:
    label = detail.get("label", [{"@value": entity_id}])[0].get("@value", entity_id)
    types = "".join(f"<li><a href=\"{html.escape(value)}\">{html.escape(value.rsplit('/', 1)[-1])}</a></li>" for value in detail.get("@type", []))
    sources = "".join(f"<li><a rel=\"prov:wasDerivedFrom\" href=\"{html.escape(value)}\">{html.escape(value)}</a></li>" for value in detail.get("sources", []))
    links = "".join(f"<li><a rel=\"owl:sameAs\" href=\"{html.escape(value['@id'])}\">{html.escape(value['@id'])}</a></li>" for value in detail.get("external_links", []))
    description = "<br/>".join(html.escape(item.get("@value", "")) for item in detail.get("description", []))
    turtle_url = f"/resource/{quote(entity_id)}?format=turtle"
    jsonld_url = f"/resource/{quote(entity_id)}?format=jsonld"
    body = f"""<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\"><title>{html.escape(label)} — VietHeritageLOD</title><link rel=\"canonical\" href=\"{html.escape(detail['@id'])}\"><link rel=\"alternate\" type=\"text/turtle\" href=\"{turtle_url}\"><link rel=\"alternate\" type=\"application/ld+json\" href=\"{jsonld_url}\"><link rel=\"stylesheet\" href=\"/styles.css\"></head><body><main class=\"container\"><p><a href=\"/\">← VietHeritageLOD Explorer</a></p><h1>{html.escape(label)}</h1><p class=\"uri\"><a href=\"{html.escape(detail['@id'])}\">{html.escape(detail['@id'])}</a></p><h2>Ontology types</h2><ul>{types}</ul><h2>Mô tả</h2><p>{description or 'Chưa có mô tả.'}</p><h2>Provenance</h2><ul>{sources or '<li>Chưa có source.</li>'}</ul><h2>Verified external links</h2><ul>{links or '<li>Không có verified external link.</li>'}</ul><p class=\"actions\"><a href=\"{turtle_url}\" class=\"button\">Xem Turtle</a><a href=\"{jsonld_url}\" class=\"button\">Xem JSON-LD</a></p></main></body></html>"""
    return body.encode("utf-8")
