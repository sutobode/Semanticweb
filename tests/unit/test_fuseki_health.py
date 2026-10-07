from types import SimpleNamespace

import pytest
import requests

from vietheritage.reporting.health import ASK_QUERY, is_fuseki_ready


def response(status=200, payload=None):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def test_fuseki_readiness_uses_sparql_ask() -> None:
    calls = []

    def mock_get(url, **kwargs):
        calls.append((url, kwargs))
        return response(payload={"head": {}, "boolean": True})

    assert is_fuseki_ready("http://example.test/vietheritage/sparql", request_get=mock_get)
    assert calls[0][1]["params"] == {"query": ASK_QUERY}
    assert calls[0][1]["timeout"] == 3


@pytest.mark.parametrize(
    "mock_response",
    [
        response(status=503, payload={"boolean": True}),
        response(payload={"results": {"bindings": []}}),
        response(payload={"boolean": False}),
        response(payload={"boolean": "true"}),
    ],
)
def test_fuseki_readiness_rejects_http_and_payload_failures(mock_response) -> None:
    assert not is_fuseki_ready(request_get=lambda *args, **kwargs: mock_response)


def test_fuseki_readiness_rejects_malformed_json_and_network_errors() -> None:
    malformed = SimpleNamespace(status_code=200, json=lambda: (_ for _ in ()).throw(ValueError("bad json")))
    assert not is_fuseki_ready(request_get=lambda *args, **kwargs: malformed)

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    assert not is_fuseki_ready(request_get=unavailable)
