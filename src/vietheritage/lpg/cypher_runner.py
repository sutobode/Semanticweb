"""Cypher CQ runner (COMP-011 parity smoke)."""
from __future__ import annotations

import os
from pathlib import Path

from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[3]
CYPHER_DIR = REPO_ROOT / "cypher"


def run() -> int:
    queries = sorted(CYPHER_DIR.glob("CQ*.cypher"))
    if len(queries) != 10:
        print(f"cypher-test: expected 10 queries, found {len(queries)}")
        return 1
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "change-me-local-only"))
    try:
        driver = GraphDatabase.driver(uri, auth=auth)
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            for path in queries:
                session.run(path.read_text(encoding="utf-8")).consume()
        driver.close()
    except Exception as exc:
        print(f"cypher-test: FAIL - {exc}")
        return 1
    print("cypher-test: 10/10 PASS")
    return 0
