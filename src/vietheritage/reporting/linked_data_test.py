"""Linked Data resource dereference check (COMP-012)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from rdflib import Graph

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
    uri = f"{os.getenv('VH_BASE_URI', 'http://localhost:3030/vietheritage').rstrip('/')}/resource/{first['entity_id']}"
    try:
        response = requests.get(uri, headers={"Accept": "text/turtle"}, timeout=30)
        response.raise_for_status()
        graph = Graph().parse(data=response.content, format="turtle")
    except Exception as exc:
        print(f"linked-data-test: FAIL - {exc}")
        return 1
    if len(graph) == 0:
        print(f"linked-data-test: FAIL - empty RDF response for {uri}")
        return 1
    print(f"linked-data-test: PASS ({response.status_code}, {len(graph)} triples) {uri}")
    return 0
