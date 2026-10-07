from pathlib import Path

from vietheritage.rdf import fuseki_loader
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
    assert calls[0][1]["timeout"] == 180


def test_production_load_fails_before_put_when_any_artifact_is_missing(
    tmp_path: Path, monkeypatch,
) -> None:
    present = tmp_path / "present.ttl"
    present.write_text("@prefix : <urn:test:> .", encoding="utf-8")
    missing = tmp_path / "missing.ttl"
    puts = []
    monkeypatch.setattr(
        fuseki_loader,
        "load_plan",
        lambda: [
            ("ontology", present, "urn:graph:ontology"),
            ("inferred", missing, "urn:graph:inferred"),
        ],
    )
    monkeypatch.setattr(fuseki_loader, "put_turtle", lambda *args, **kwargs: puts.append(args))

    assert fuseki_loader.run("full") == 1
    assert puts == []
