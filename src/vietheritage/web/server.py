"""Local HTTP server for the VietHeritageLOD explorer and linked-data API."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rdflib import Graph

from .api import APIError, CANONICAL_PATH, DEFAULT_BASE_URI, JSONLD_CONTEXT, SemanticAPI, render_entity_html

STATIC_DIR = Path(__file__).with_name("static")
ONTOLOGY_PATH = Path(__file__).resolve().parents[3] / "ontology" / "vietheritage.ttl"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _content_type(path: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(Path(path).suffix, "application/octet-stream")


class Router:
    def __init__(self, api: SemanticAPI | None = None) -> None:
        self.api = api or SemanticAPI()

    def _static(self, path: str) -> tuple[int, dict[str, str], bytes]:
        relative = "index.html" if path == "/" else path.lstrip("/")
        if relative in {"", "."} or ".." in Path(relative).parts:
            relative = "index.html"
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            raise APIError(404, "NOT_FOUND", "resource was not found")
        if not target.is_file():
            raise APIError(404, "NOT_FOUND", "resource was not found")
        return 200, {"Content-Type": _content_type(str(target))}, target.read_bytes()

    def _ontology(self, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        if not ONTOLOGY_PATH.is_file():
            raise APIError(404, "NOT_FOUND", "ontology was not found")
        canonical = f"{DEFAULT_BASE_URI}/ontology/"
        accept = headers.get("accept", "text/html").lower()
        common = {"Vary": "Accept", "Link": f'<{canonical}>; rel="canonical"'}
        graph = Graph().parse(ONTOLOGY_PATH, format="turtle")
        if "application/ld+json" in accept:
            body = graph.serialize(format="json-ld", context=JSONLD_CONTEXT, auto_compact=True).encode("utf-8")
            common["Content-Type"] = "application/ld+json; charset=utf-8"
            return 200, common, body
        if "text/turtle" in accept:
            common["Content-Type"] = "text/turtle; charset=utf-8"
            return 200, common, ONTOLOGY_PATH.read_bytes()
        if "text/html" in accept or accept in {"", "*/*"}:
            body = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>VietHeritageLOD Ontology</title><link rel="canonical" href="{canonical}"></head><body><main><h1>VietHeritageLOD Ontology</h1><p><a href="{canonical}">{canonical}</a></p></main></body></html>'.encode("utf-8")
            common["Content-Type"] = "text/html; charset=utf-8"
            return 200, common, body
        raise APIError(406, "NOT_ACCEPTABLE", "supported representations are text/html, text/turtle, and application/ld+json")

    def handle(self, path: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        parsed = urlparse(path)
        route = parsed.path.rstrip("/") or "/"
        if CANONICAL_PATH != "/":
            if route == CANONICAL_PATH:
                route = "/"
            elif route.startswith(f"{CANONICAL_PATH}/"):
                route = route[len(CANONICAL_PATH):] or "/"
        params = {key: values[-1] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}

        if route in {"/", "/app.js", "/styles.css"}:
            return self._static(route)
        if route in {"/ontology", "/ontology/"}:
            return self._ontology(headers)
        if route == "/docs":
            body = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>VietHeritageLOD API</title><link rel=\"stylesheet\" href=\"/styles.css\"></head><body><main class=\"container\"><h1>VietHeritageLOD Read-only API</h1><p><a href=\"/openapi.json\">OpenAPI JSON</a></p><p>SPARQL endpoint: <a href=\"http://localhost:3031/vietheritage/sparql\">Fuseki</a></p><ul><li><code>GET /api/health</code></li><li><code>GET /api/stats</code></li><li><code>GET /api/search?q=Huế</code></li><li><code>GET /vietheritage/resource/&lt;entity_id&gt;</code> with Turtle or JSON-LD Accept</li></ul></main></body></html>"""
            return 200, {"Content-Type": "text/html; charset=utf-8"}, body.encode("utf-8")
        if route == "/openapi.json":
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(self.api.openapi())

        if route == "/api/health":
            payload = self.api.health()
            status = 200 if payload["status"] == "ok" else 503
            return status, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(payload)
        if route == "/api/stats":
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(self.api.stats())
        if route == "/api/search":
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(self.api.search(params))
        if route == "/api/queries":
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes({"items": self.api.queries()})
        if route.startswith("/api/queries/") and route.endswith("/run"):
            query_id = route.split("/")[3]
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(self.api.run_query(query_id))
        if route.startswith("/api/entities/"):
            entity_id = route.removeprefix("/api/entities/")
            return 200, {"Content-Type": "application/json; charset=utf-8"}, _json_bytes(self.api.entity(entity_id))
        if route.startswith("/resource/"):
            entity_id = route.removeprefix("/resource/")
            detail = self.api.entity(entity_id)
            accept = headers.get("accept", "text/html").lower()
            format_hint = params.get("format", "").lower()
            if format_hint == "turtle":
                accept = "text/turtle"
            elif format_hint in {"jsonld", "json-ld"}:
                accept = "application/ld+json"
            common = {"Vary": "Accept", "Link": f'<{detail["@id"]}>; rel="canonical"'}
            if "text/html" in accept or accept in {"", "*/*"}:
                common["Content-Type"] = "text/html; charset=utf-8"
                return 200, common, render_entity_html(detail, entity_id)
            if "text/turtle" in accept:
                common["Content-Type"] = "text/turtle; charset=utf-8"
                return 200, common, self.api.resource_turtle(entity_id)
            if "application/ld+json" in accept:
                common["Content-Type"] = "application/ld+json; charset=utf-8"
                return 200, common, self.api.resource_jsonld(entity_id)
            if "application/json" in accept:
                common["Content-Type"] = "application/json; charset=utf-8"
                return 200, common, _json_bytes(detail)
            raise APIError(406, "NOT_ACCEPTABLE", "supported representations are text/html, text/turtle, application/ld+json, and application/json")

        raise APIError(404, "NOT_FOUND", "route was not found")


class RequestHandler(BaseHTTPRequestHandler):
    router: Router

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        try:
            status, headers, body = self.router.handle(self.path, {key.lower(): value for key, value in self.headers.items()})
        except APIError as exc:
            status = exc.status
            headers = {"Content-Type": "application/json; charset=utf-8"}
            body = _json_bytes({"error": {"code": exc.code, "message": exc.message}})
        except Exception:
            status = 500
            headers = {"Content-Type": "application/json; charset=utf-8"}
            body = _json_bytes({"error": {"code": "INTERNAL_ERROR", "message": "internal server error"}})
        self._send(status, headers, body)

    def do_POST(self) -> None:  # noqa: N802
        self._send(405, {"Content-Type": "application/json; charset=utf-8", "Allow": "GET"}, _json_bytes({"error": {"code": "METHOD_NOT_ALLOWED", "message": "read-only API accepts GET only"}}))

    def log_message(self, format: str, *args: Any) -> None:
        # Keep request logging, but never log query bodies or credentials.
        print(f"[explorer] {self.address_string()} - {format % args}")


def main() -> int:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    router = Router()

    class BoundHandler(RequestHandler):
        pass

    BoundHandler.router = router
    server = ThreadingHTTPServer((host, port), BoundHandler)
    print(f"VietHeritageLOD explorer listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
