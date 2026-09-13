"""Vietnamese Wikipedia enrichment collector (COMP-001, Section 7).

Bổ sung mô tả và structured field cho registry entity đã tồn tại, qua
MediaWiki API (``action=query``). Registry entity không tìm được page khớp
MUST giữ ``source_status=registry_only`` — enrichment KHÔNG BAO GIỜ loại một
entity khỏi canonical dataset (Section 12.4.1).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config" / "collector.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"


class EnrichmentMissingError(RuntimeError):
    """ENRICHMENT_MISSING — không tìm được Wikipedia page khớp registry entity."""


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFC", title)
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass
class WikipediaPage:
    page_id: int
    title: str
    source_url: str
    retrieved_at: str
    wikidata_id: str | None = None
    coordinates: dict[str, float] | None = None
    infobox: dict[str, Any] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    abstract: str | None = None
    links: list[str] = field(default_factory=list)
    revision_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "wikidata_id": self.wikidata_id,
            "coordinates": self.coordinates,
            "infobox": self.infobox,
            "categories": self.categories,
            "abstract": self.abstract,
            "links": self.links,
            "revision_id": self.revision_id,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def build_query_params(titles: list[str], query_cfg: dict[str, Any]) -> dict[str, Any]:
    """Section 7 COMP-001 request contract — action=query, prop list cố định."""
    return {
        "action": "query",
        "format": "json",
        "formatversion": query_cfg.get("formatversion", 2),
        "titles": "|".join(titles),
        "prop": query_cfg.get("prop", "pageprops|revisions|coordinates|categories|extracts|links"),
        "rvprop": query_cfg.get("rvprop", "ids|timestamp|content"),
        "rvslots": query_cfg.get("rvslots", "main"),
        "exintro": query_cfg.get("exintro", 1),
        "explaintext": query_cfg.get("explaintext", 1),
        "cllimit": query_cfg.get("cllimit", "max"),
        "pllimit": query_cfg.get("pllimit", "max"),
    }


_TEMPLATE_RE = re.compile(r"\{\{([^{}|]+)((?:\|[^{}]*)*)\}\}", re.DOTALL)
_KV_RE = re.compile(r"^\s*([a-zA-Z0-9_\- ]+?)\s*=\s*(.*)$", re.DOTALL)


def parse_first_infobox(wikitext: str) -> dict[str, str]:
    """Lấy infobox template đầu tiên, chuyển thành raw key/value đã normalize.

    Không suy luận ontology class từ một key đơn lẻ (Section 7 COMP-001).
    """
    match = _TEMPLATE_RE.search(wikitext)
    if not match or "infobox" not in match.group(1).strip().lower():
        # Tìm template đầu tiên có chữ "infobox" trong tên (không phân biệt hoa thường)
        for m in _TEMPLATE_RE.finditer(wikitext):
            if "infobox" in m.group(1).strip().lower():
                match = m
                break
        else:
            return {}
    params_blob = match.group(2)
    fields: dict[str, str] = {}
    for part in params_blob.split("|"):
        part = part.strip()
        if not part:
            continue
        kv = _KV_RE.match(part)
        if kv:
            key = kv.group(1).strip().lower().replace(" ", "_")
            value = re.sub(r"\s+", " ", kv.group(2)).strip()
            fields[key] = value
    return fields


def fetch_query(api_url: str, params: dict[str, Any], request_cfg: dict[str, Any], session: requests.Session | None = None) -> dict[str, Any]:
    """Điểm duy nhất gọi HTTP thật tới MediaWiki API."""
    sess = session or requests.Session()
    timeout = request_cfg.get("timeout_seconds", 30)
    retries = request_cfg.get("retries", 3)
    backoffs = request_cfg.get("backoff_seconds", [2, 4, 8])

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(api_url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
    raise EnrichmentMissingError(f"failed to query {api_url}: {last_exc}") from last_exc


def page_from_api_response(page_json: dict[str, Any], retrieved_at: str) -> WikipediaPage | None:
    if page_json.get("missing"):
        return None

    wikidata_id = None
    pageprops = page_json.get("pageprops", {})
    if isinstance(pageprops, dict):
        wikidata_id = pageprops.get("wikibase_item")

    coordinates = None
    coords = page_json.get("coordinates")
    if coords:
        coordinates = {"lat": coords[0]["lat"], "lon": coords[0]["lon"]}

    categories = [c["title"] for c in page_json.get("categories", [])]
    links = [link["title"] for link in page_json.get("links", [])]
    abstract = page_json.get("extract")

    revisions = page_json.get("revisions", [])
    revision_id = None
    infobox: dict[str, Any] = {}
    if revisions:
        rev = revisions[0]
        revision_id = rev.get("revid")
        slots = rev.get("slots", {})
        content = ""
        if "main" in slots:
            content = slots["main"].get("content", "")
        elif "content" in rev:
            content = rev["content"]
        if content:
            infobox = parse_first_infobox(content)

    title = page_json.get("title", "")
    page_id = page_json.get("pageid")
    source_url = f"https://vi.wikipedia.org/wiki/{title.replace(' ', '_')}"

    return WikipediaPage(
        page_id=page_id,
        title=title,
        source_url=source_url,
        retrieved_at=retrieved_at,
        wikidata_id=wikidata_id,
        coordinates=coordinates,
        infobox=infobox,
        categories=categories,
        abstract=abstract,
        links=links,
        revision_id=revision_id,
    )


def match_registry_labels_to_pages(
    registry_labels: list[str],
    api_response: dict[str, Any],
    retrieved_at: str,
) -> tuple[list[WikipediaPage], list[dict[str, Any]]]:
    """Matching: exact normalized title/alias trước; QID xác nhận thứ hai.

    Trả (pages, failures). Nhãn không match được ghi ENRICHMENT_MISSING
    nhưng KHÔNG raise — registry entity vẫn giữ registry_only.
    """
    pages_json = api_response.get("query", {}).get("pages", [])
    normalized_lookup = {normalize_title(p.get("title", "")): p for p in pages_json if not p.get("missing")}

    pages: list[WikipediaPage] = []
    failures: list[dict[str, Any]] = []
    seen_page_ids: set[int] = set()

    for label in registry_labels:
        norm = normalize_title(label)
        page_json = normalized_lookup.get(norm)
        if page_json is None:
            failures.append({"label_vi": label, "error_code": "ENRICHMENT_MISSING", "reason": "no exact title match"})
            continue
        page = page_from_api_response(page_json, retrieved_at)
        if page is None:
            failures.append({"label_vi": label, "error_code": "ENRICHMENT_MISSING", "reason": "page missing"})
            continue
        if page.page_id in seen_page_ids:
            continue
        seen_page_ids.add(page.page_id)
        pages.append(page)

    return pages, failures


def enrich(
    registry_labels: list[str],
    config_path: Path = CONFIG_PATH,
    fetcher=fetch_query,
    output_dir: Path = RAW_DIR,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    retrieved_at = utc_now_iso()
    params = build_query_params(registry_labels, cfg.get("query", {}))
    api_response = fetcher(cfg["api_url"], params, cfg.get("request", {}))
    pages, failures = match_registry_labels_to_pages(registry_labels, api_response, retrieved_at)

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_path = output_dir / "pages.jsonl"
    failures_path = output_dir / "enrichment_failures.jsonl"
    with pages_path.open("w", encoding="utf-8") as fh:
        for page in pages:
            fh.write(json.dumps(page.to_dict(), ensure_ascii=False) + "\n")
    with failures_path.open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(failure, ensure_ascii=False) + "\n")

    return {
        "matched": len(pages),
        "missing": len(failures),
        "total": len(registry_labels),
        "pages_path": str(pages_path),
        "failures_path": str(failures_path),
    }
