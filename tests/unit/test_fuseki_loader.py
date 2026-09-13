from pathlib import Path

from vietheritage.rdf.fuseki_loader import load_plan, put_turtle


def test_fuseki_load_plan_has_required_five_stage_order() -> None:
    assert [item[0] for item in load_plan()] == ["ontology", "data", "external-links", "inferred", "metadata"]


def test_put_turtle_uses_graph_store_params_and_content_type() -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            pass

    def mock_put(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    put_turtle("http://localhost:3030/vietheritage/data", b"@prefix : <x:> .", "http://example/graph", mock_put)
    assert calls[0][0].endswith("/vietheritage/data")
    assert calls[0][1]["params"] == {"graph": "http://example/graph"}
    assert calls[0][1]["headers"]["Content-Type"].startswith("text/turtle")
