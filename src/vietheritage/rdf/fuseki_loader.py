"""Fuseki Graph Store Protocol loader (COMP-009)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import requests
from rdflib import Graph
from rdflib.exceptions import ParserError

from vietheritage.reasoning.reasoner import ReasoningError, reason

REPO_ROOT = Path(__file__).resolve().parents[3]
RDF_DIR = REPO_ROOT / "data" / "rdf"
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "vietheritage.ttl"
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"
FUSEKI_URL = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
DATASET = os.getenv("FUSEKI_LOAD_DATASET", "vietheritage-admin")
CQ_DATASET = os.getenv("FUSEKI_CQ_LOAD_DATASET", "vietheritage-cq-admin")

GRAPH_BASE = "http://localhost:3030/vietheritage/graph"


def load_plan() -> list[tuple[str, Path, str | None]]:
    """Return the five mandatory production graph inputs in PUT order."""
    return [
        ("ontology", ONTOLOGY_PATH, f"{GRAPH_BASE}/ontology"),
        ("data", RDF_DIR / "vietheritage.ttl", f"{GRAPH_BASE}/data"),
        ("external-links", RDF_DIR / "external-links.ttl", f"{GRAPH_BASE}/external-links"),
        ("inferred", RDF_DIR / "inferred.ttl", f"{GRAPH_BASE}/inferred"),
        ("metadata", RDF_DIR / "dataset-metadata.ttl", f"{GRAPH_BASE}/metadata"),
    ]


def put_turtle(
    endpoint: str,
    content: bytes,
    graph: str | None,
    request_put: Callable[..., Any] = requests.put,
    auth: tuple[str, str] | None = None,
    timeout: float | None = None,
) -> None:
    params = {"default": ""} if graph is None else {"graph": graph}
    kwargs: dict[str, Any] = {
        "params": params,
        "data": content,
        "headers": {"Content-Type": "text/turtle; charset=utf-8"},
        "timeout": timeout or float(os.getenv("FUSEKI_LOAD_TIMEOUT_SECONDS", "180")),
    }
    if auth:
        kwargs["auth"] = auth
    response = request_put(endpoint, **kwargs)
    response.raise_for_status()


def run(run_mode: str = "sample") -> int:
    endpoint = f"{FUSEKI_URL}/{DATASET}/data"
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    plan = load_plan()
    missing = [path for _, path, _ in plan if not path.is_file()]
    if missing:
        for path in missing:
            print(f"fuseki-load: required artifact missing: {path}")
        return 1

    loaded: list[str] = []
    for name, path, graph in plan:
        try:
            put_turtle(endpoint, path.read_bytes(), graph, auth=auth)
        except requests.RequestException as exc:
            print(f"fuseki-load: {name} failed: {exc}")
            return 1
        loaded.append(name)
    print(f"fuseki-load ({run_mode}): loaded {','.join(loaded)}")
    return 0


def golden_query_endpoint() -> str:
    dataset = os.getenv("FUSEKI_CQ_DATASET", "vietheritage-cq")
    return f"{FUSEKI_URL}/{dataset}/sparql"


def golden_load_plan() -> list[tuple[str, bytes, str]]:
    """Build the isolated CQ graph exactly as the semantic acceptance test does."""
    ontology = Graph().parse(ONTOLOGY_PATH, format="turtle")
    data = Graph().parse(FIXTURES_DIR / "cq-data.ttl", format="turtle")
    inferred, _ = reason([ontology, data])
    external = Graph().parse(FIXTURES_DIR / "cq-verified-links.ttl", format="turtle")
    external.parse(FIXTURES_DIR / "external_snapshot.ttl", format="turtle")

    def turtle(graph: Graph) -> bytes:
        content = graph.serialize(format="turtle", encoding="utf-8")
        return content if isinstance(content, bytes) else content.encode("utf-8")

    return [
        ("ontology", ONTOLOGY_PATH.read_bytes(), f"{GRAPH_BASE}/ontology"),
        ("data", (FIXTURES_DIR / "cq-data.ttl").read_bytes(), f"{GRAPH_BASE}/data"),
        ("external-links", turtle(external), f"{GRAPH_BASE}/external-links"),
        ("inferred", turtle(inferred), f"{GRAPH_BASE}/inferred"),
    ]


def load_golden() -> int:
    endpoint = f"{FUSEKI_URL}/{CQ_DATASET}/data"
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    try:
        plan = golden_load_plan()
        for name, content, graph in plan:
            put_turtle(endpoint, content, graph, auth=auth)
    except (OSError, ParserError, ReasoningError, requests.RequestException) as exc:
        print(f"cq-load: FAIL: {exc}")
        return 1
    print(f"cq-load: loaded isolated {','.join(name for name, _, _ in plan)}")
    return 0
