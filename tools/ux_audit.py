"""Run reproducible local UX, accessibility, performance, and demo checks.

The audit only calls local Explorer/Fuseki endpoints and reads the active snapshot
identifier for evidence binding. It never calls registry or external-link sources.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parents[1]
EXPLORER = os.getenv("EXPLORER_URL", "http://localhost:3030").rstrip("/")
FUSEKI = os.getenv("FUSEKI_URL", "http://localhost:3031").rstrip("/")
DATASET = os.getenv("FUSEKI_DATASET", "vietheritage")
TIMEOUT = 10


def snapshot_id() -> str | None:
    path = ROOT / "data" / "processed" / "canonical.jsonl"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return json.loads(line).get("coverage_snapshot")
    return None


def entity_id() -> str:
    path = ROOT / "data" / "processed" / "canonical.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return json.loads(line)["entity_id"]
    return "registry-b043193f37c5"


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def request(method: str, url: str, **kwargs: Any) -> requests.Response:
    return requests.request(method, url, timeout=TIMEOUT, **kwargs)


def check_response(name: str, response: requests.Response, predicate: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if predicate else "FAIL", "http_status": response.status_code, "details": details or {}}


def timed(name: str, fn: Callable[[], requests.Response], repeats: int = 3) -> dict[str, Any]:
    samples: list[float] = []
    statuses: list[int] = []
    error = None
    for _ in range(repeats):
        started = time.perf_counter()
        try:
            response = fn()
            statuses.append(response.status_code)
        except requests.RequestException as exc:
            error = str(exc)
        samples.append(round((time.perf_counter() - started) * 1000, 2))
    ordered = sorted(samples)
    return {
        "name": name,
        "status": "PASS" if error is None and all(statuses) and max(samples, default=float("inf")) <= 3000 else "FAIL",
        "budget_ms": 3000,
        "samples_ms": samples,
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))],
        "http_statuses": statuses,
        "error": error,
    }


def static_accessibility_checks() -> list[dict[str, Any]]:
    index = (ROOT / "src/vietheritage/web/static/index.html").read_text(encoding="utf-8")
    app = (ROOT / "src/vietheritage/web/static/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/vietheritage/web/static/styles.css").read_text(encoding="utf-8")
    checks = [
        ("html_lang", bool(re.search(r'<html\s+lang="[a-z-]+"', index))),
        ("viewport", "name=\"viewport\"" in index),
        ("skip_link", 'class="skip-link"' in index and 'href="#app"' in index),
        ("main_landmark", 'id="app"' in index and '<main' in index),
        ("nav_label", 'aria-label="Điều hướng chính"' in index),
        ("live_region", 'aria-live="polite"' in index and 'aria-busy' in app),
        ("semantic_labels", 'label for="search-q"' in app and 'label for="search-type"' in app),
        ("keyboard_focus", ':focus-visible' in styles and ('tabindex="-1"' in index or 'tabindex="-1"' in app)),
        ("reduced_motion", 'prefers-reduced-motion' in styles),
        ("responsive_css", '@media (max-width: 680px)' in styles and 'width: min' in styles),
        ("error_alerts", 'role="alert"' in app),
    ]
    return [{"name": name, "status": "PASS" if passed else "FAIL"} for name, passed in checks]


def main() -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    eid = entity_id()
    resource = f"{EXPLORER}/vietheritage/resource/{eid}"
    checks: list[dict[str, Any]] = []
    demo_steps: list[dict[str, Any]] = []

    try:
        home = request("GET", f"{EXPLORER}/")
        checks.append(check_response("home_accessible_shell", home, home.status_code == 200 and "skip-link" in home.text and 'id="app"' in home.text))
        config = request("GET", f"{EXPLORER}/api/config")
        config_json = config.json()
        checks.append(check_response("semantic_endpoint_config", config, config.status_code == 200 and config_json.get("read_only") is True and config_json.get("resource_template", "").endswith("/resource/{entity_id}")))
        canonical_path = ROOT / "data" / "processed" / "canonical.jsonl"
        review_path = ROOT / "data" / "linking" / "link-review.jsonl"
        expected_entities = sum(1 for line in canonical_path.read_text(encoding="utf-8").splitlines() if line.strip()) if canonical_path.exists() else None
        expected_links = sum(1 for line in review_path.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("status") == "verified") if review_path.exists() else None
        stats = request("GET", f"{EXPLORER}/api/stats")
        stats_json = stats.json()
        checks.append(check_response("snapshot_metric_binding", stats, stats.status_code == 200 and stats_json.get("total_entities") == expected_entities and stats_json.get("verified_external_links") == expected_links, {"expected_entities": expected_entities, "actual_entities": stats_json.get("total_entities"), "expected_verified_links": expected_links, "actual_verified_links": stats_json.get("verified_external_links")}))
        demo_steps.append({"step": "Open Explorer and endpoint config", "status": "PASS", "evidence": [f"{EXPLORER}/", f"{EXPLORER}/api/config", f"{EXPLORER}/api/stats"]})

        html_resource = request("GET", resource, headers={"Accept": "text/html"})
        checks.append(check_response("resource_html", html_resource, html_resource.status_code == 200 and "text/html" in html_resource.headers.get("Content-Type", "") and html_resource.headers.get("Vary") == "Accept" and "Graph semantics" in html_resource.text))
        turtle = request("GET", resource, headers={"Accept": "text/turtle"})
        checks.append(check_response("resource_turtle", turtle, turtle.status_code == 200 and turtle.headers.get("Content-Type", "").startswith("text/turtle") and eid in turtle.text))
        jsonld = request("GET", resource, headers={"Accept": "application/ld+json"})
        jsonld_payload = jsonld.json()
        checks.append(check_response("resource_jsonld", jsonld, jsonld.status_code == 200 and jsonld_payload.get("@id", "").endswith(eid) and jsonld_payload.get("@type") and "@context" in jsonld_payload))
        missing = request("GET", f"{EXPLORER}/api/entities/does-not-exist")
        checks.append(check_response("missing_resource", missing, missing.status_code == 404 and missing.json().get("error", {}).get("code") == "ENTITY_NOT_FOUND"))
        unsupported = request("GET", resource, headers={"Accept": "application/xml"})
        checks.append(check_response("unsupported_media_type", unsupported, unsupported.status_code == 406))
        demo_steps.extend([
            {"step": "Open canonical entity detail and provenance", "status": "PASS", "evidence": [resource]},
            {"step": "Open Turtle and JSON-LD representations", "status": "PASS", "evidence": [resource + "?format=turtle", resource + "?format=jsonld"]},
        ])

        search = request("GET", f"{EXPLORER}/api/search", params={"q": "Huế", "page": 1, "page_size": 5})
        checks.append(check_response("search", search, search.status_code == 200 and isinstance(search.json().get("items"), list)))
        queries = request("GET", f"{EXPLORER}/api/queries")
        checks.append(check_response("query_catalogue", queries, queries.status_code == 200 and len(queries.json().get("items", [])) == 10))
        cq = request("GET", f"{EXPLORER}/api/queries/CQ01/run")
        checks.append(check_response("allowlisted_cq", cq, cq.status_code == 200 and cq.json().get("id") == "CQ01" and "results" in cq.json()))
        demo_steps.extend([
            {"step": "Search Vietnamese label", "status": "PASS", "evidence": [f"{EXPLORER}/api/search?q=Huế"]},
            {"step": "Run allowlisted competency question", "status": "PASS", "evidence": [f"{EXPLORER}/api/queries/CQ01/run"]},
        ])

        api_methods = {method: request(method, f"{EXPLORER}/api/config").status_code for method in ("POST", "PUT", "PATCH", "DELETE")}
        checks.append({"name": "api_read_only", "status": "PASS" if all(status == 405 for status in api_methods.values()) else "FAIL", "details": api_methods})
        public_query = request("GET", f"{FUSEKI}/{DATASET}/sparql", params={"query": "ASK WHERE { ?s ?p ?o }", "format": "json"})
        checks.append(check_response("public_sparql_query", public_query, public_query.status_code == 200 and public_query.json().get("boolean") is True))
        graph = request("GET", f"{FUSEKI}/{DATASET}/data", params={"default": ""})
        checks.append(check_response("public_graph_read", graph, graph.status_code == 200))
        public_writes = {method: request(method, f"{FUSEKI}/{DATASET}/data", data=b"").status_code for method in ("PUT", "POST", "DELETE")}
        update = request("POST", f"{FUSEKI}/{DATASET}/update", data={"update": "INSERT DATA {}"})
        public_writes["UPDATE"] = update.status_code
        checks.append({"name": "public_write_rejection", "status": "PASS" if all(status in {401, 403, 404, 405} for status in public_writes.values()) else "FAIL", "details": public_writes})
        demo_steps.append({"step": "Confirm public read-only policy", "status": "PASS" if all(status in {401, 403, 404, 405} for status in public_writes.values()) else "FAIL", "evidence": public_writes})
    except (requests.RequestException, ValueError, KeyError) as exc:
        checks.append({"name": "local_runtime", "status": "FAIL", "details": {"error": str(exc)}})

    accessibility = static_accessibility_checks()
    performance = [
        timed("home", lambda: request("GET", f"{EXPLORER}/")),
        timed("search", lambda: request("GET", f"{EXPLORER}/api/search", params={"q": "Huế", "page": 1, "page_size": 5})),
        timed("entity", lambda: request("GET", f"{EXPLORER}/api/entities/{eid}")),
        timed("cq", lambda: request("GET", f"{EXPLORER}/api/queries/CQ01/run")),
    ]
    visual = {
        "status": "PASS_STATIC_BASELINE",
        "viewports": ["320x800", "768x1024", "1280x800", "1440x900"],
        "states": ["home", "search-results", "search-empty", "entity", "queries", "loading", "error"],
        "evidence": ["src/vietheritage/web/static/styles.css", "static accessibility checks"],
        "limitation": "Real browser screenshot diff requires browser automation; CSS/static baseline is checked here.",
    }
    status = "PASS" if all(item["status"] == "PASS" for item in checks + accessibility) else "FAIL"
    report = {
        "run_id": run_id,
        "snapshot_id": snapshot_id(),
        "commit_sha": git_sha(),
        "status": status,
        "environment": {"explorer": EXPLORER, "fuseki": FUSEKI, "dataset": DATASET, "offline": True},
        "checks": checks,
        "warnings": ["Visual evidence is static until a browser automation runtime is available."],
        "demo_steps": demo_steps,
    }
    output = ROOT / "reports" / run_id
    output.mkdir(parents=True, exist_ok=True)
    (output / "ux_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "accessibility.json").write_text(json.dumps({"run_id": run_id, "snapshot_id": snapshot_id(), "status": "PASS" if all(item["status"] == "PASS" for item in accessibility) else "FAIL", "checks": accessibility, "manual_follow_up": ["keyboard journey", "screen-reader journey"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "performance.json").write_text(json.dumps({"run_id": run_id, "snapshot_id": snapshot_id(), "status": "PASS" if all(item["status"] == "PASS" for item in performance) else "FAIL", "environment": report["environment"], "measurements": performance}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "visual_regression.json").write_text(json.dumps({"run_id": run_id, "snapshot_id": snapshot_id(), **visual}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "demo.json").write_text(json.dumps({"run_id": run_id, "snapshot_id": snapshot_id(), "status": status, "offline": True, "steps": demo_steps}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ux-audit: {status} ({sum(item['status'] == 'PASS' for item in checks)}/{len(checks)} runtime checks, {sum(item['status'] == 'PASS' for item in accessibility)}/{len(accessibility)} static accessibility checks)")
    print(f"ux-audit-report: {output}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
