"""Service health checks for Docker-backed Fuseki and Neo4j."""
from __future__ import annotations

import os
import time

import requests

ASK_QUERY = "ASK WHERE {}"


def fuseki_query_endpoint() -> str:
    base = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
    dataset = os.getenv("FUSEKI_DATASET", "vietheritage")
    return f"{base}/{dataset}/sparql"


def is_fuseki_ready(
    endpoint: str | None = None,
    request_get=requests.get,
    request_timeout: float = 3,
) -> bool:
    """Return true only for a valid successful SPARQL boolean response."""
    try:
        response = request_get(
            endpoint or fuseki_query_endpoint(),
            params={"query": ASK_QUERY},
            headers={"Accept": "application/sparql-results+json"},
            timeout=request_timeout,
        )
        if not 200 <= response.status_code < 300:
            return False
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("boolean") is True


def wait_fuseki(
    timeout_seconds: int = 60,
    request_get=requests.get,
    retry_interval: float = 1,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    endpoint = fuseki_query_endpoint()
    while time.monotonic() < deadline:
        if is_fuseki_ready(endpoint, request_get=request_get):
            print(f"fuseki health: PASS ({ASK_QUERY})")
            return 0
        time.sleep(retry_interval)
    print(f"fuseki health: FAIL ({endpoint}, {ASK_QUERY})")
    return 1


def wait_neo4j(timeout_seconds: int = 60) -> int:
    url = os.getenv("NEO4J_HTTP_URL", "http://localhost:7474").rstrip("/")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code < 500:
                print(f"neo4j health: PASS ({response.status_code})")
                return 0
        except requests.RequestException:
            pass
        time.sleep(1)
    print(f"neo4j health: FAIL ({url})")
    return 1
