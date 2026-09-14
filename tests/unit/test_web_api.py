from __future__ import annotations

import json
from typing import Any

import pytest
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS

from vietheritage.web.api import APIError, FusekiClient, SemanticAPI


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeTransport:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def get(self, _url: str, **kwargs: Any) -> FakeResponse:
        query = kwargs["params"]["query"]
        self.queries.append(query)
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
                                "category": {"type": "uri", "value": "http://localhost:3030/vietheritage/resource/category/world_heritage"},
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
                            self.row("http://localhost:3030/vietheritage/graph/data", DCTERMS.subject, "http://localhost:3030/vietheritage/resource/category/world_heritage"),
                            self.row("http://localhost:3030/vietheritage/graph/data", SKOS.altLabel, "Huế cổ", lang="vi"),
                        ]
                    }
                }
            )
        if "ASK WHERE" in query:
            return FakeResponse({"boolean": True})
        return FakeResponse({"results": {"bindings": []}})

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


def test_search_rejects_page_size_over_limit() -> None:
    with pytest.raises(APIError) as error:
        make_api(FakeTransport()).search({"page_size": "101"})
    assert error.value.status == 400
    assert error.value.code == "INVALID_PAGINATION"


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



def test_config_exposes_canonical_read_only_endpoints() -> None:
    result = make_api(FakeTransport()).config()
    assert result["@id"].endswith("/resource/dataset/vietheritage")
    assert result["resource_template"].endswith("/resource/{entity_id}")
    assert result["sparql_endpoint"].endswith("/vietheritage/sparql")
    assert result["read_only"] is True
