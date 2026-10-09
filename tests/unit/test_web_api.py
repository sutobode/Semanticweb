from __future__ import annotations

import json
import re
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
        self.search_bindings: list[dict[str, Any]] | None = None
        self.search_entities = [("http://localhost:3030/vietheritage/resource/site-a", "Huế")]

    def get(self, _url: str, **kwargs: Any) -> FakeResponse:
        query = kwargs["params"]["query"]
        self.queries.append(query)
        self.calls.append(kwargs)
        if "CONSTRUCT " in query.upper() or "DESCRIBE " in query.upper():
            return FakeResponse({}, "@prefix vh: <http://localhost:3030/vietheritage/ontology/> .")
        if "COUNT(DISTINCT ?entity)" in query:
            return FakeResponse({"results": {"bindings": [{"total": {"type": "literal", "value": str(len(self.search_entities))}}]}})
        if "SELECT ?entity (MIN(" in query:
            limit = int(re.search(r"LIMIT (\d+)", query).group(1))
            offset = int(re.search(r"OFFSET (\d+)", query).group(1))
            bindings = [
                {
                    "entity": {"type": "uri", "value": entity},
                    "sortLabel": {"type": "literal", "value": label.lower()},
                }
                for entity, label in self.search_entities[offset:offset + limit]
            ]
            return FakeResponse({"results": {"bindings": bindings}})
        if "SELECT DISTINCT ?entity" in query:
            bindings = self.search_bindings if self.search_bindings is not None else [self.search_row()]
            bindings = [
                row for row in bindings
                if f'<{row.get("entity", {}).get("value", "")}>' in query
            ]
            return FakeResponse(
                {
                    "results": {
                        "bindings": bindings
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

    @staticmethod
    def search_row(entity_id: str = "site-a", label: str = "Huế", **extra: Any) -> dict[str, Any]:
        return {
            "entity": {"type": "uri", "value": f"http://localhost:3030/vietheritage/resource/{entity_id}"},
            "label": {"type": "literal", "xml:lang": "vi", "value": label},
            "type": {"type": "uri", "value": "http://localhost:3030/vietheritage/ontology/HeritageSite"},
            "category": {"type": "literal", "value": "world_heritage"},
            "source": {"type": "uri", "value": "https://vi.wikipedia.org/wiki/Hue"},
            **extra,
        }


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
    assert result["items"][0]["match_reasons"] == [{"filter": "keyword", "value": "Huế"}]
    assert any("Huế" in query for query in transport.queries)


def test_search_registry_category_matches_stored_literal() -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"registry_category": "world_heritage"})
    search_queries = [
        query for query in transport.queries
        if "COUNT(DISTINCT ?entity)" in query or "SELECT ?entity (MIN(" in query
    ]
    assert result["total"] == 1
    assert result["items"]
    assert all('dcterms:subject "world_heritage"' in query for query in search_queries)
    assert all("/resource/category/world_heritage" not in query for query in search_queries)
    assert result["items"][0]["match_reasons"] == [
        {"filter": "registry_category", "value": "world_heritage"}
    ]


def test_search_canonical_type_filter_still_uses_rdf_type() -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"entity_type": "HeritageSite"})
    assert any(
        "FILTER EXISTS { ?entity a <http://localhost:3030/vietheritage/ontology/HeritageSite> . }" in query
        for query in transport.queries
    )
    assert result["items"][0]["match_reasons"] == [
        {"filter": "entity_type", "value": "HeritageSite"}
    ]


def test_search_marks_inferred_only_unesco_semantic_match() -> None:
    transport = FakeTransport()
    transport.search_bindings = [
        transport.search_row(
            semanticInferred={"type": "literal", "value": "true"},
            semanticAsserted={"type": "literal", "value": "false"},
        )
    ]
    result = make_api(transport).search({"semantic_type": "UNESCOHeritageSite"})
    page_query = next(query for query in transport.queries if "SELECT ?entity (MIN(" in query)
    detail_query = next(query for query in transport.queries if "SELECT DISTINCT ?entity" in query)
    assert "FILTER EXISTS { ?entity a <http://localhost:3030/vietheritage/ontology/UNESCOHeritageSite> . }" in page_query
    assert "GRAPH <http://localhost:3030/vietheritage/graph/inferred>" in detail_query
    assert "GRAPH <http://localhost:3030/vietheritage/graph/data>" in detail_query
    assert result["items"][0]["match_reasons"] == [
        {"filter": "semantic_type", "value": "UNESCOHeritageSite", "inferred": True}
    ]


def test_search_does_not_mark_asserted_semantic_type_as_inferred_only() -> None:
    transport = FakeTransport()
    transport.search_bindings = [
        transport.search_row(
            semanticInferred={"type": "literal", "value": "true"},
            semanticAsserted={"type": "literal", "value": "true"},
        )
    ]
    result = make_api(transport).search({"semantic_type": "HistoricalSite"})
    assert result["items"][0]["match_reasons"][0]["inferred"] is False


@pytest.mark.parametrize("relation", ["associatedWithPerson", "builtBy"])
def test_search_relation_filter_uses_union_default_graph(relation: str) -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"relation": relation})
    query = next(query for query in transport.queries if "SELECT ?entity (MIN(" in query)
    assert f"?entity <http://localhost:3030/vietheritage/ontology/{relation}> ?relatedResource" in query
    assert "GRAPH" not in query.split("?relatedResource", 1)[0].rsplit("FILTER EXISTS", 1)[-1]
    assert result["items"][0]["match_reasons"] == [{"filter": "relation", "value": relation}]


def test_materialized_built_by_inference_can_match_associated_person_relation() -> None:
    transport = FakeTransport()
    result = make_api(transport).search({"relation": "associatedWithPerson"})
    query = next(query for query in transport.queries if "SELECT ?entity (MIN(" in query)
    assert "FILTER EXISTS { ?entity <http://localhost:3030/vietheritage/ontology/associatedWithPerson>" in query
    assert result["items"]


def test_search_combines_filters_with_and_reasons_and_deduplicates_results() -> None:
    transport = FakeTransport()
    row = transport.search_row(
        semanticInferred={"type": "literal", "value": "true"},
        semanticAsserted={"type": "literal", "value": "false"},
    )
    transport.search_bindings = [row, dict(row)]
    params = {
        "q": "Huế",
        "entity_type": "HeritageSite",
        "semantic_type": "UNESCOHeritageSite",
        "relation": "associatedWithPerson",
        "registry_category": "world_heritage",
        "location": "Huế",
        "year": "1993",
    }
    result = make_api(transport).search(params)
    count_query = next(query for query in transport.queries if "COUNT(DISTINCT ?entity)" in query)
    assert "HeritageSite" in count_query and "UNESCOHeritageSite" in count_query
    assert "associatedWithPerson" in count_query
    assert 'dcterms:subject "world_heritage"' in count_query
    assert "1993" in count_query and "Huế" in count_query
    assert len(result["items"]) == 1
    assert [reason["filter"] for reason in result["items"][0]["match_reasons"]] == [
        "keyword",
        "entity_type",
        "semantic_type",
        "relation",
        "registry_category",
        "location",
        "year",
    ]


def test_search_paginates_distinct_resources_before_hydrating_many_bindings() -> None:
    transport = FakeTransport()
    transport.search_entities = [
        (f"http://localhost:3030/vietheritage/resource/site-{index}", f"Di tích {index}")
        for index in range(8)
    ]
    transport.search_bindings = [
        transport.search_row(
            entity_id=f"site-{index}",
            label=f"Di tích {index}",
            type={"type": "uri", "value": f"http://localhost:3030/vietheritage/ontology/Type{type_index}"},
        )
        for index in range(8)
        for type_index in range(12 if index == 0 else 1)
    ]
    result = make_api(transport).search({"semantic_type": "UNESCOHeritageSite", "page_size": "10"})
    assert result["total"] == 8
    assert len(result["items"]) == 8
    assert len({item["@id"] for item in result["items"]}) == 8
    assert result["has_next"] is False
    page_query = next(query for query in transport.queries if "SELECT ?entity (MIN(" in query)
    detail_query = next(query for query in transport.queries if "SELECT DISTINCT ?entity" in query)
    assert "GROUP BY ?entity ORDER BY ?sortLabel STR(?entity) LIMIT 10 OFFSET 0" in page_query
    assert "VALUES ?entity" in detail_query
    assert "LIMIT" not in detail_query and "OFFSET" not in detail_query


def test_search_second_page_uses_stable_distinct_resource_slice() -> None:
    transport = FakeTransport()
    transport.search_entities = [
        (f"http://localhost:3030/vietheritage/resource/site-{index}", f"Di tích {index}")
        for index in range(5)
    ]
    transport.search_bindings = [
        transport.search_row(entity_id=f"site-{index}", label=f"Di tích {index}")
        for index in range(5)
    ]
    result = make_api(transport).search({"page": "2", "page_size": "2"})
    assert result["total"] == 5
    assert [item["@id"].rsplit("/", 1)[-1] for item in result["items"]] == ["site-2", "site-3"]
    assert result["has_next"] is True
    page_query = next(query for query in transport.queries if "SELECT ?entity (MIN(" in query)
    assert "ORDER BY ?sortLabel STR(?entity) LIMIT 2 OFFSET 2" in page_query


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
    assert any("VALUES ?relation" in query and "associatedWithPerson" in query for query in transport.queries)
    assert any("COUNT(*)" in query for query in transport.queries)
    assert any("graph/external-links" in query for query in transport.queries)
