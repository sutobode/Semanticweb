"""HTTP smoke checks for the local explorer service."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("EXPLORER_URL", "http://localhost:8000").rstrip("/")


def _entity_id() -> str:
    path = ROOT / "data" / "processed" / "canonical.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return json.loads(line)["entity_id"]
    return "registry-b043193f37c5"


def _get(path: str, **kwargs: object) -> requests.Response:
    response = requests.get(f"{BASE}{path}", timeout=10, **kwargs)
    response.raise_for_status()
    return response


def main() -> int:
    entity_id = _entity_id()
    checks: list[tuple[str, bool]] = []
    checks.append(("home", _get("/").headers.get("content-type", "").startswith("text/html")))
    health = _get("/api/health").json()
    checks.append(("health", health.get("status") == "ok" and health.get("fuseki") == "ok"))
    stats = _get("/api/stats").json()
    checks.append(("stats", stats.get("total_entities", 0) > 0))
    search = _get("/api/search", params={"q": "Huế", "page": 1, "page_size": 5}).json()
    checks.append(("search", isinstance(search.get("items"), list) and "@context" in search))
    detail = _get(f"/api/entities/{entity_id}").json()
    checks.append(("entity", detail.get("@id", "").endswith(entity_id) and "@type" in detail))
    turtle = _get(f"/resource/{entity_id}", headers={"Accept": "text/turtle"})
    checks.append(("turtle", turtle.headers.get("content-type", "").startswith("text/turtle") and len(turtle.content) > 0))
    jsonld = _get(f"/resource/{entity_id}", headers={"Accept": "application/ld+json"})
    jsonld_payload = jsonld.json()
    checks.append(("jsonld", jsonld.headers.get("content-type", "").startswith("application/ld+json") and bool(jsonld_payload)))
    format_hint = _get(f"/resource/{entity_id}?format=turtle")
    checks.append(("format_hint", format_hint.headers.get("content-type", "").startswith("text/turtle") and len(format_hint.content) > 0))
    queries = _get("/api/queries").json()
    checks.append(("query_catalogue", len(queries.get("items", [])) == 10))
    query_result = _get("/api/queries/CQ01/run").json()
    checks.append(("allowlisted_cq", query_result.get("id") == "CQ01" and "results" in query_result))
    missing = requests.get(f"{BASE}/api/entities/does-not-exist", timeout=10)
    checks.append(("404", missing.status_code == 404 and missing.json().get("error", {}).get("code") == "ENTITY_NOT_FOUND"))
    failed = [name for name, passed in checks if not passed]
    print(f"app-smoke: {len(checks) - len(failed)}/{len(checks)} PASS")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
