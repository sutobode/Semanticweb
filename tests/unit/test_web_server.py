from __future__ import annotations

from typing import Any

import pytest
from rdflib.namespace import RDF, RDFS

from vietheritage.web.api import FusekiClient, SemanticAPI
from vietheritage.web.server import Router


class Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        query = getattr(self, "query", "")
        if "GRAPH ?graph" in query:
            return {"results": {"bindings": [
                {"graph": {"type": "uri", "value": "http://localhost:3030/vietheritage/graph/data"}, "predicate": {"type": "uri", "value": str(RDFS.label)}, "object": {"type": "literal", "xml:lang": "vi", "value": "Huế"}},
                {"graph": {"type": "uri", "value": "http://localhost:3030/vietheritage/graph/data"}, "predicate": {"type": "uri", "value": str(RDF.type)}, "object": {"type": "uri", "value": "http://localhost:3030/vietheritage/ontology/HeritageSite"}},
            ]}}
        return {"results": {"bindings": []}}


def fake_get(_url: str, **kwargs: Any) -> Response:
    response = Response()
    response.query = kwargs["params"]["query"]
    return response


def router() -> Router:
    return Router(SemanticAPI(FusekiClient(request_get=fake_get)))


def test_resource_turtle_content_negotiation() -> None:
    status, headers, body = router().handle("/resource/site-a", {"accept": "text/turtle"})
    assert status == 200
    assert headers["Content-Type"].startswith("text/turtle")
    assert headers["Vary"] == "Accept"
    assert b"Hu" in body


def test_resource_jsonld_content_negotiation() -> None:
    status, headers, body = router().handle("/resource/site-a", {"accept": "application/ld+json"})
    assert status == 200
    assert headers["Content-Type"].startswith("application/ld+json")
    assert b"@id" in body


def test_resource_format_hint_supports_browser_links() -> None:
    status, headers, body = router().handle("/resource/site-a?format=turtle", {"accept": "text/html"})
    assert status == 200
    assert headers["Content-Type"].startswith("text/turtle")
    assert b"Hu" in body




def test_docs_and_openapi_are_available() -> None:
    docs_status, docs_headers, docs_body = router().handle("/docs", {})
    openapi_status, openapi_headers, openapi_body = router().handle("/openapi.json", {})
    assert docs_status == 200 and docs_headers["Content-Type"].startswith("text/html")
    assert b"VietHeritageLOD" in docs_body
    assert openapi_status == 200 and openapi_headers["Content-Type"].startswith("application/json")
    assert b"openapi" in openapi_body


def test_unknown_route_is_api_error() -> None:
    with pytest.raises(Exception):
        router().handle("/resource/not found", {"accept": "text/turtle"})



def test_canonical_resource_path_is_dereferenceable() -> None:
    status, headers, body = router().handle("/vietheritage/resource/site-a", {"accept": "text/turtle"})
    assert status == 200
    assert headers["Content-Type"].startswith("text/turtle")
    assert b"Hu" in body


def test_canonical_ontology_path_is_dereferenceable() -> None:
    status, headers, body = router().handle("/vietheritage/ontology/", {"accept": "text/turtle"})
    assert status == 200
    assert headers["Content-Type"].startswith("text/turtle")
    assert b"VietHeritageLOD" in body
