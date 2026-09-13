"""Fuseki Graph Store Protocol loader (COMP-009)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
RDF_DIR = REPO_ROOT / "data" / "rdf"
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "vietheritage.ttl"
FUSEKI_URL = os.getenv("FUSEKI_URL", "http://localhost:3030").rstrip("/")
DATASET = os.getenv("FUSEKI_DATASET", "vietheritage")


def load_plan() -> list[tuple[str, Path, str | None]]:
    """Return the mandatory PUT order; absent optional artifacts are skipped by run."""
    return [
        ("ontology", ONTOLOGY_PATH, "http://localhost:3030/vietheritage/graph/ontology"),
        ("data", RDF_DIR / "vietheritage.ttl", None),
        ("external-links", RDF_DIR / "external-links.ttl", "http://localhost:3030/vietheritage/graph/external-links"),
        ("inferred", RDF_DIR / "inferred.ttl", "http://localhost:3030/vietheritage/graph/inferred"),
        ("metadata", RDF_DIR / "dataset-metadata.ttl", "http://localhost:3030/vietheritage/graph/metadata"),
    ]


def put_turtle(
    endpoint: str,
    content: bytes,
    graph: str | None,
    request_put: Callable[..., Any] = requests.put,
    auth: tuple[str, str] | None = None,
) -> None:
    params = {"default": ""} if graph is None else {"graph": graph}
    kwargs: dict[str, Any] = {
        "params": params,
        "data": content,
        "headers": {"Content-Type": "text/turtle; charset=utf-8"},
        "timeout": 30,
    }
    if auth:
        kwargs["auth"] = auth
    response = request_put(endpoint, **kwargs)
    response.raise_for_status()


def run(run_mode: str = "sample") -> int:
    endpoint = f"{FUSEKI_URL}/{DATASET}/data"
    auth = (os.getenv("FUSEKI_USER", "admin"), os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only"))
    loaded: list[str] = []
    for name, path, graph in load_plan():
        if not path.exists():
            if name in {"inferred", "metadata", "external-links"}:
                continue
            print(f"fuseki-load: required artifact missing: {path}")
            return 1
        try:
            put_turtle(endpoint, path.read_bytes(), graph, auth=auth)
        except requests.RequestException as exc:
            print(f"fuseki-load: {name} failed: {exc}")
            return 1
        loaded.append(name)
    print(f"fuseki-load ({run_mode}): loaded {','.join(loaded)}")
    return 0
