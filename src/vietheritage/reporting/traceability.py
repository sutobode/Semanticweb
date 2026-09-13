"""Minimal MUST artifact traceability check."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def run() -> int:
    required = [
        "ontology/vietheritage.ttl", "schema/canonical-record.schema.json",
        "schema/coverage.schema.json", "docker-compose.yml", "silk/linkage-rules.xml",
    ]
    required.extend(str(path.relative_to(REPO_ROOT)) for path in sorted((REPO_ROOT / "sparql").glob("CQ*.rq")))
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    print(f"traceability-check: {'PASS' if not missing else 'FAIL'}")
    if missing:
        print("missing:", ", ".join(missing))
    return 0 if not missing else 1
