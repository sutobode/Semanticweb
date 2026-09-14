"""Service health checks for Docker-backed Fuseki and Neo4j."""
from __future__ import annotations

import os
import time

import requests


def wait_fuseki(timeout_seconds: int = 60) -> int:
    base = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
    deadline = time.monotonic() + timeout_seconds
    url = f"{base}/$/ping"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code < 500:
                print(f"fuseki health: PASS ({response.status_code})")
                return 0
        except requests.RequestException:
            pass
        time.sleep(1)
    print(f"fuseki health: FAIL ({url})")
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
