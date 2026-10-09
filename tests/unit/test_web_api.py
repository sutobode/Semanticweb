from __future__ import annotations

import json
from typing import Any

import pytest
import requests
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS

from vietheritage.web.api import APIError, FusekiClient, SemanticAPI


class FakeResponse:
    def __init__(self, payload: dict[str, Any], text: str = "") -> None:
        self.payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeTransport:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.calls: list[dict[str, Any]] = []

    def get(self, _url: str, **kwargs: Any) -> FakeResponse:
        query = kwargs["params"]["query"]
        self.queries.append(query)
        self.calls.append(kwargs)
        if "CONSTRUCT " in query.upper() or "DESCRIBE " in query.upper():
            return FakeResponse({}, "@prefix vh: <http://localhost:3030/vietheritage/ontology/> .")
        if "COUNT(DISTINCT ?entity)" in query:
            return FakeResponse({"results": {"bindings": [{"total": {"type": "literal", "value": "1"}}]}})
        if "SELECT DISTINCT ?entity" in query:
            return FakeResponse(
                {
                    "results": {
                        "bindings": [
                            {
                                "entity": {"type": "uri", "value": "http://localhost:3030/vietheritage/resource/site-a"},
                                "label": {"type": "literal", "xml:lang": "vi", "value": "Huế"},
                                "type": {"type": "uri", "value": "http://localhost:3030/vietheritage/ontology/HeritageSite"},
                                "category": {"type": "literal", "value": "world_heritage"},
                                "source": {"type": "uri", "value": "https://vi.wikipedia.org/wiki/Hue"},
                            }
                        ]
                    }
                }
            )
        if "GRAPH ?graph" in query:
            return FakeResponse(
                {
                    "results": {
                        "bindings": [
                            self.row("http://localhost:3030/vietheritage/graph/data", RDFS.label, "Huế", lang="vi"),
                            self.row("http://localhost:3030/vietheritage/graph/data", RDF.type, "http://localhost:3030/vietheritage/ontology/HeritageSite"),
                            self.row("http://localhost:3030/vietheritage/graph/data", DCTERMS.source, "https://dsvh.gov.vn/hue"),
                            self.row("http://localhost:3030/vietheritage/graph/data", PROV.wasDerivedFrom, "https://vi.wikipedia.org/wiki/Hue"),
                            self.row("http://localhost:3030/vietheritage/graph/external-links", OWL.sameAs, "https://www.wikidata.org/entity/Q1"),
                            self.row("http://localhost:3030/vietheritage/graph/data", DCTERMS.subject, "world_heritage"),
                            self.row("http://localhost:3030/vietheritage/graph/data", SKOS.altLabel, "Huế cổ", lang="vi"),
                        ]
                    }
                }
            )
        if "ASK" in query.upper():
            return FakeResponse({"boolean": True})
        return FakeResponse({"head": {"vars": []}, "results": {"bindings": []}})

    @staticmethod
    def row(graph: str, predicate: Any, value: str, lang: str | None = None) -> dict[str, Any]:
        object_type = "uri" if value.startswith(("http://", "https://")) else "literal"
        obj: dict[str, Any] = {"type": object_type, "value": value}
        if lang:
            obj["xml:lang"] = lang
        return {"graph": {"type": "uri", "value": graph}, "predicate": {"type": "uri", "value": str(predicate)}, "object": obj}


def make_api(transport: FakeTransport) -> SemanticAPI:
    return SemanticAPI(FusekiClient(endpoint="http://fake/sparql", request_get=transport.get))


def test_search_returns_jsonld_ids_categories_and_pagination() -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"q": "Huế", "page": "1", "page_size": "10"})
    assert result["total"] == 1
    assert result["has_next"] is False
    assert result["items"][0]["@id"].endswith("site-a")
    assert result["items"][0]["source_status"] == "registry+wikipedia"
    assert result["items"][0]["category"]
    assert any("Huế" in query for query in transport.queries)


def test_search_registry_category_matches_stored_literal() -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"registry_category": "world_heritage"})
    search_queries = [query for query in transport.queries if "?entity" in query]
    assert result["total"] == 1
    assert result["items"]
    assert all('dcterms:subject "world_heritage"' in query for query in search_queries)
    assert all("/resource/category/world_heritage" not in query for query in search_queries)


def test_search_rejects_page_size_over_limit() -> None:
    with pytest.raises(APIError) as error:
        make_api(FakeTransport()).search({"page_size": "101"})
    assert error.value.status == 400
    assert error.value.code == "INVALID_PAGINATION"


@pytest.mark.parametrize(
    ("query", "query_form"),
    [
        ("SELECT * WHERE { GRAPH ?g { ?s ?p ?o } } LIMIT 1", "SELECT"),
        ("PREFIX vh: <http://example.test/> SELECT * WHERE { ?s a vh:Thing }", "SELECT"),
        ("# demo\nASK WHERE { ?s ?p ?o }", "ASK"),
        ("CONSTRUCT { ?s ?p ?o } WHERE { GRAPH ?g { ?s ?p ?o } } LIMIT 1", "CONSTRUCT"),
        ("BASE <http://example.test/> DESCRIBE <resource/a>", "DESCRIBE"),
    ],
)
def test_execute_sparql_accepts_read_only_query_forms(query: str, query_form: str) -> None:
    transport = FakeTransport()
    result = make_api(transport).execute_sparql(query)
    assert result["query_form"] == query_form
    assert "auth" not in transport.calls[-1]
    assert transport.calls[-1]["timeout"] == 10.0


@pytest.mark.parametrize("query", ["INSERT DATA { <x:a> <x:b> <x:c> }", "DELETE WHERE { ?s ?p ?o }"])
def test_execute_sparql_rejects_updates(query: str) -> None:
    transport = FakeTransport()
    with pytest.raises(APIError) as error:
        make_api(transport).execute_sparql(query)
    assert error.value.status == 400
    assert error.value.code == "INVALID_SPARQL"
    assert transport.calls == []


@pytest.mark.parametrize("query", ["", "SELECT WHERE { ?s ?p ?o }"])
def test_execute_sparql_rejects_empty_or_malformed_query(query: str) -> None:
    with pytest.raises(APIError) as error:
        make_api(FakeTransport()).execute_sparql(query)
    assert error.value.status == 400
    assert error.value.code == "INVALID_SPARQL"


def test_execute_sparql_enforces_query_size_limit() -> None:
    query = "SELECT * WHERE { ?s ?p ?o } #" + ("x" * 50_000)
    with pytest.raises(APIError) as error:
        make_api(FakeTransport()).execute_sparql(query)
    assert error.value.status == 413
    assert error.value.code == "QUERY_TOO_LARGE"


def test_execute_sparql_sanitizes_upstream_error() -> None:
    def unavailable(_url: str, **_kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("private upstream detail")

    api = SemanticAPI(FusekiClient(endpoint="http://fake/sparql", request_get=unavailable))
    with pytest.raises(APIError) as error:
        api.execute_sparql("SELECT * WHERE { ?s ?p ?o }")
    assert error.value.status == 503
    assert error.value.code == "SPARQL_UNAVAILABLE"
    assert "private upstream detail" not in error.value.message


def test_entity_preserves_provenance_external_links_and_asserted_inferred_split() -> None:
    result = make_api(FakeTransport()).entity("site-a")
    assert result["@id"].endswith("site-a")
    assert result["source_status"] == "registry+wikipedia"
    assert "https://dsvh.gov.vn/hue" in result["sources"]
    assert result["external_links"][0]["verified"] is True
    assert result["asserted_triples"]
    assert "inferred_triples" in result
    assert "closure_triples" in result


def test_resource_serializations_are_parseable() -> None:
    api = make_api(FakeTransport())
    turtle = api.resource_turtle("site-a").decode("utf-8")
    jsonld = api.resource_jsonld("site-a").decode("utf-8")
    assert "Huế" in turtle
    parsed = json.loads(jsonld)
    assert parsed
    assert "@context" in parsed
    assert parsed.get("@id", "").endswith("site-a")
    assert parsed.get("@type")


def test_allowlist_rejects_arbitrary_query_id() -> None:
    with pytest.raises(APIError) as error:
        make_api(FakeTransport()).run_query("UPDATE")
    assert error.value.status == 404
    assert error.value.code == "QUERY_NOT_FOUND"


def test_query_catalog_exposes_allowlisted_sparql_and_presentation_metadata() -> None:
    items = make_api(FakeTransport()).queries()
    assert [item["id"] for item in items] == [f"CQ{number:02d}" for number in range(1, 11)]
    cq08 = next(item for item in items if item["id"] == "CQ08")
    assert cq08["display_title"] == "Các địa điểm thuộc quần thể di sản"
    assert "hasMember+" in cq08["sparql"]
    assert cq08["question"]
    assert cq08["semantic_note"]
    assert cq08["read_only"] is True
    assert len(cq08["sha256"]) == 64



def test_config_exposes_canonical_read_only_endpoints() -> None:
    result = make_api(FakeTransport()).config()
    assert result["@id"].endswith("/resource/dataset/vietheritage")
    assert result["resource_template"].endswith("/resource/{entity_id}")
    assert result["sparql_endpoint"].endswith("/vietheritage/sparql")
    assert result["read_only"] is True


def test_stats_query_matches_verified_snapshot_metrics() -> None:
    transport = FakeTransport()
    result = make_api(transport).stats()
    assert result["@id"].endswith("/resource/dataset/vietheritage")
    assert any("VALUES ?type" in query and "HeritageSite" in query for query in transport.queries)
    assert any("COUNT(*)" in query for query in transport.queries)
    assert any("graph/external-links" in query for query in transport.queries)
