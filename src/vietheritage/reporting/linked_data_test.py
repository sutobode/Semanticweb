"""Linked Data resource dereference check (COMP-012)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]


def run() -> int:
    path = REPO_ROOT / "data" / "processed" / "canonical.jsonl"
    if not path.exists():
        print("linked-data-test: canonical data missing")
        return 1
    first = next((json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), None)
    if not first:
        print("linked-data-test: no entity")
        return 1
    uri = f"http://localhost:3030/vietheritage/resource/{first['entity_id']}"
    endpoint = f"{os.getenv('FUSEKI_URL', 'http://localhost:3030').rstrip('/')}/{os.getenv('FUSEKI_DATASET', 'vietheritage')}/sparql"
    query = f"DESCRIBE <{uri}>"
    try:
        response = requests.get(endpoint, params={"query": query}, headers={"Accept": "text/turtle"}, auth=("admin", os.getenv("FUSEKI_ADMIN_PASSWORD", "change-me-local-only")), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"linked-data-test: FAIL - {exc}")
        return 1
    print(f"linked-data-test: PASS ({response.status_code}) {uri}")
    return 0
