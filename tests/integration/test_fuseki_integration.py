import json
import os
import subprocess
from pathlib import Path

import pytest
import requests

from vietheritage.rdf import fuseki_loader
from vietheritage.reporting import query_runner
from vietheritage.reporting.health import is_fuseki_ready

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FUSEKI_INTEGRATION") != "1",
    reason="set RUN_FUSEKI_INTEGRATION=1 for the live Fuseki acceptance test",
)

BASE = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
PRODUCTION_QUERY = f"{BASE}/{os.getenv('FUSEKI_DATASET', 'vietheritage')}/sparql"
GOLDEN_QUERY = f"{BASE}/{os.getenv('FUSEKI_CQ_DATASET', 'vietheritage-cq')}/sparql"
GRAPH_BASE = "http://localhost:3030/vietheritage/graph"
SYNTHETIC_SITE = "http://localhost:3030/vietheritage/resource/site-in-sub-area-1"


def sparql(endpoint: str, query: str) -> dict:
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


@pytest.fixture(scope="module", autouse=True)
def loaded_datasets():
    assert is_fuseki_ready(PRODUCTION_QUERY)
    assert fuseki_loader.run("full") == 0
    assert fuseki_loader.load_golden() == 0


def test_runtime_is_official_fuseki_4_10_0_image() -> None:
    container = subprocess.run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", "vietheritage-fuseki"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert container.stdout.strip() == "vietheritage/fuseki:4.10.0"
    image = subprocess.run(
        [
            "docker", "image", "inspect", "vietheritage/fuseki:4.10.0",
            "--format", '{{index .Config.Labels "org.opencontainers.image.version"}}',
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert image.stdout.strip() == "4.10.0"


def test_all_production_graphs_are_loaded_and_union_default_is_queryable() -> None:
    graph_names = ["ontology", "data", "external-links", "inferred", "metadata"]
    values = " ".join(f"<{GRAPH_BASE}/{name}>" for name in graph_names)
    result = sparql(
        PRODUCTION_QUERY,
        f"SELECT ?graph (COUNT(*) AS ?count) WHERE {{ VALUES ?graph {{ {values} }} GRAPH ?graph {{ ?s ?p ?o }} }} GROUP BY ?graph",
    )
    counts = {
        binding["graph"]["value"]: int(binding["count"]["value"])
        for binding in result["results"]["bindings"]
    }
    assert set(counts) == {f"{GRAPH_BASE}/{name}" for name in graph_names}
    assert all(count > 0 for count in counts.values())

    union = sparql(
        PRODUCTION_QUERY,
        "ASK { <http://localhost:3030/vietheritage/ontology/HeritageSite> a <http://www.w3.org/2002/07/owl#Class> }",
    )
    assert union["boolean"] is True


def test_public_graph_store_rejects_unauthenticated_write() -> None:
    response = requests.put(
        f"{BASE}/vietheritage/data",
        params={"graph": "urn:vietheritage:test:public-write"},
        data=b"<urn:test:s> <urn:test:p> <urn:test:o> .",
        headers={"Content-Type": "text/turtle"},
        timeout=30,
    )
    assert response.status_code in {401, 403, 404, 405}


def test_golden_graph_is_isolated_and_contains_cq10_snapshot() -> None:
    fixture_query = f"ASK {{ <{SYNTHETIC_SITE}> ?p ?o }}"
    assert sparql(PRODUCTION_QUERY, fixture_query)["boolean"] is False
    assert sparql(GOLDEN_QUERY, fixture_query)["boolean"] is True

    snapshot = sparql(
        GOLDEN_QUERY,
        'ASK { <http://dbpedia.org/resource/Example_Site> <http://www.w3.org/2000/01/rdf-schema#label> "Example Site"@en }',
    )
    assert snapshot["boolean"] is True


def test_all_ten_cqs_match_deterministic_expected_results(tmp_path: Path) -> None:
    assert query_runner.run(endpoint=GOLDEN_QUERY, reports_dir=tmp_path) == 0
    report_path = next(tmp_path.glob("*/cq_results.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] == report["total"] == 10
    assert all(row["http_status"] == 200 and row["comparison"] == "MATCH" for row in report["queries"])
