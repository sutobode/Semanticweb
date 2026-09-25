"""Vietnamese Wikipedia enrichment collector (COMP-001, Section 7).

Bổ sung mô tả và structured field cho registry entity đã tồn tại, qua
MediaWiki API (``action=query``). Registry entity không tìm được page khớp
MUST giữ ``source_status=registry_only`` — enrichment KHÔNG BAO GIỜ loại một
entity khỏi canonical dataset (Section 12.4.1).

Quy tắc M2 (``M2_REMAINING_WORK.md`` M2-13…M2-15):

* Matching deterministic, không fuzzy (DEC-007): tiêu đề chính xác -> redirect
  -> các luật alias tường minh trong ``config/collector.yaml``. Match qua alias
  MUST có bằng chứng: tỉnh của registry xuất hiện trong categories/abstract/
  infobox/title của page. Trang định hướng bị loại.
* ``title``/``source_url`` là tiêu đề THẬT của page (sau redirect); nhãn đã
  dùng để tìm được ghi ở ``requested_labels``; ``registry_ids`` nối page với
  registry record (mapper join theo ID, không theo nhãn).
* Infobox: parser có đếm ngoặc, xử lý template lồng; giữ raw key/value
  (§11.3) và link theo từng field (``infobox_links``).
* Quan hệ (built_by, associated_persons, associated_events, periods) chỉ được
  đề xuất khi link trong infobox trỏ tới page có QID mà Wikidata P31 thuộc lớp
  đã cấu hình (ví dụ Q5 cho người). Không xác minh được -> bỏ (OWA).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config" / "collector.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"
WIKI_BASE = "https://vi.wikipedia.org/wiki/"
DEFAULT_INFOBOX_PATTERN = r"(?i)(infobox|thông tin|hộp thông tin)"
_NON_ARTICLE_PREFIXES = ("tập tin:", "file:", "hình:", "image:", "thể loại:", "category:", "wikipedia:", "bản mẫu:", "template:")


class EnrichmentMissingError(RuntimeError):
    """ENRICHMENT_MISSING — không tìm được Wikipedia page khớp registry entity."""


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFC", title)
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().casefold()


def wiki_url(title: str) -> str:
    """URL bài viết từ tiêu đề thật, percent-encoded như ví dụ ở §11.2."""
    return WIKI_BASE + quote(unicodedata.normalize("NFC", title).replace(" ", "_"), safe="()_,'!*-.:")


@dataclass
class RegistryTarget:
    label_vi: str
    registry_id: str | None = None
    registry_category: str | None = None
    location: str | None = None


def _as_targets(items: Iterable[Any]) -> list[RegistryTarget]:
    targets = []
    for item in items:
        if isinstance(item, RegistryTarget):
            targets.append(item)
        elif isinstance(item, str):
            targets.append(RegistryTarget(label_vi=item))
        else:
            targets.append(RegistryTarget(
                label_vi=item["label_vi"],
                registry_id=item.get("registry_id"),
                registry_category=item.get("registry_category"),
                location=item.get("location"),
            ))
    return targets


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
    registry_ids: list[str] = field(default_factory=list)
    requested_labels: list[str] = field(default_factory=list)
    match_method: str | None = None
    match_evidence: list[str] = field(default_factory=list)
    infobox_links: dict[str, list[str]] = field(default_factory=dict)
    relation_candidates: list[dict[str, Any]] = field(default_factory=list)
    registry_links: list[dict[str, Any]] = field(default_factory=list)
    is_disambiguation: bool = False

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
            "registry_ids": self.registry_ids,
            "requested_labels": self.requested_labels,
            "match_method": self.match_method,
            "match_evidence": self.match_evidence,
            "infobox_links": self.infobox_links,
            "relation_candidates": self.relation_candidates,
            "registry_links": self.registry_links,
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
        "redirects": 1,
        "prop": query_cfg.get("prop", "pageprops|revisions|coordinates|categories|extracts|links"),
        "rvprop": query_cfg.get("rvprop", "ids|timestamp|content"),
        "rvslots": query_cfg.get("rvslots", "main"),
        "exintro": query_cfg.get("exintro", 1),
        "explaintext": query_cfg.get("explaintext", 1),
        "exlimit": query_cfg.get("exlimit", "max"),
        "cllimit": query_cfg.get("cllimit", "max"),
        "pllimit": query_cfg.get("pllimit", "max"),
    }


# ---------------------------------------------------------------------------
# Wikitext template parsing (M2-14)
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")


def _split_top_level(text: str, separator: str) -> list[str]:
    parts, depth_t, depth_l, start, i = [], 0, 0, 0, 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair == "{{":
            depth_t += 1; i += 2; continue
        if pair == "}}" and depth_t:
            depth_t -= 1; i += 2; continue
        if pair == "[[":
            depth_l += 1; i += 2; continue
        if pair == "]]" and depth_l:
            depth_l -= 1; i += 2; continue
        if text[i] == separator and depth_t == 0 and depth_l == 0:
            parts.append(text[start:i]); start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def iter_templates(wikitext: str) -> Iterable[str]:
    """Yield nội dung (không kèm ``{{ }}``) của các template cấp ngoài cùng, đúng thứ tự."""
    i, n = 0, len(wikitext)
    while i < n:
        start = wikitext.find("{{", i)
        if start < 0:
            return
        depth, j = 0, start
        while j < n:
            if wikitext.startswith("{{", j):
                depth += 1; j += 2; continue
            if wikitext.startswith("}}", j):
                depth -= 1; j += 2
                if depth == 0:
                    break
                continue
            j += 1
        if depth != 0:
            return
        yield wikitext[start + 2:j - 2]
        i = j


def extract_link_targets(value: str) -> list[str]:
    targets = []
    for match in _LINK_RE.finditer(value or ""):
        target = re.sub(r"\s+", " ", match.group(1).replace("_", " ")).strip()
        if target and not target.casefold().startswith(_NON_ARTICLE_PREFIXES) and target not in targets:
            targets.append(target)
    return targets


def parse_first_infobox_with_links(wikitext: str, name_pattern: str = DEFAULT_INFOBOX_PATTERN) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Template infobox đầu tiên -> (raw key/value, link theo key).

    Không suy luận ontology class từ một key đơn lẻ (Section 7 COMP-001).
    """
    name_re = re.compile(name_pattern)
    for body in iter_templates(wikitext or ""):
        parts = _split_top_level(body, "|")
        name = re.sub(r"\s+", " ", parts[0]).strip()
        if not name_re.search(name):
            continue
        fields: dict[str, str] = {}
        links: dict[str, list[str]] = {}
        for part in parts[1:]:
            kv = _split_top_level(part, "=")
            if len(kv) < 2:
                continue
            key = re.sub(r"\s+", "_", kv[0].strip().lower())
            if not key:
                continue
            raw_value = "=".join(kv[1:])
            fields[key] = re.sub(r"\s+", " ", raw_value).strip()
            targets = extract_link_targets(raw_value)
            if targets:
                links[key] = targets
        return fields, links
    return {}, {}


def parse_first_infobox(wikitext: str, name_pattern: str = DEFAULT_INFOBOX_PATTERN) -> dict[str, str]:
    """Lấy infobox template đầu tiên, chuyển thành raw key/value đã normalize."""
    return parse_first_infobox_with_links(wikitext, name_pattern)[0]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def user_agent(request_cfg: dict[str, Any]) -> str:
    """User-Agent theo chính sách Wikimedia: tên tool + thông tin liên hệ.

    Liên hệ lấy từ biến môi trường ``VIETHERITAGE_CONTACT`` (ưu tiên) hoặc ``request.contact``;
    thiếu liên hệ thì request vẫn chạy nhưng dễ bị giới hạn tốc độ hơn.
    """
    base = request_cfg.get("user_agent", "VietHeritageLOD/1.0 (heritage knowledge graph collector)")
    contact = os.environ.get("VIETHERITAGE_CONTACT") or request_cfg.get("contact")
    if contact and contact not in base:
        base = f"{base[:-1]}; {contact})" if base.endswith(")") else f"{base} ({contact})"
    return base


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def fetch_query(api_url: str, params: dict[str, Any], request_cfg: dict[str, Any],
                session: requests.Session | None = None, sleeper: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Điểm duy nhất gọi HTTP thật tới MediaWiki/Wikibase API (NFR-007)."""
    sess = session or requests.Session()
    timeout = request_cfg.get("timeout_seconds", 30)
    retries = request_cfg.get("retries", 3)
    backoffs = request_cfg.get("backoff_seconds", [2, 4, 8])

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        resp: requests.Response | None = None
        try:
            resp = sess.post(
                api_url,
                data=params,
                headers={"User-Agent": user_agent(request_cfg), "Accept": "application/json"},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                retry_after = resp.headers.get("Retry-After") if resp is not None else None
                try:
                    delay = float(retry_after) if retry_after else backoffs[min(attempt, len(backoffs) - 1)]
                except (TypeError, ValueError):
                    delay = backoffs[min(attempt, len(backoffs) - 1)]
                status = resp.status_code if resp is not None else type(exc).__name__
                _log(f"[wiki] {status} -> thử lại sau {delay:g}s (lần {attempt + 1}/{retries})")
                sleeper(delay)
    raise EnrichmentMissingError(f"failed to query {api_url}: {last_exc}") from last_exc


class ApiClient:
    """Fetcher dùng chung cho cả lượt enrichment: 1 ``requests.Session``, cache đĩa, log tiến độ.

    * Cache: mỗi response thành công lưu ``<cache_dir>/<sha256[:2]>/<sha256>.json`` theo
      (api_url, params). Lần chạy sau gặp lại request y hệt -> đọc đĩa, không gọi mạng.
      Xóa thư mục cache để lấy dữ liệu Wikipedia mới. ``VIETHERITAGE_WIKI_CACHE=off`` để tắt,
      hoặc đặt đường dẫn khác.
    * Log: mỗi request mạng in 1 dòng ra stderr (flush ngay) để thấy tiến độ khi chạy lâu.
    """

    def __init__(self, cache_dir: Path | None = None, log_progress: bool = True,
                 fetch: Callable[..., dict[str, Any]] = fetch_query) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.log_progress = log_progress
        self.fetch = fetch
        self.session = requests.Session()
        self.started = time.time()
        self.stats = {"network": 0, "cache_hits": 0, "network_seconds": 0.0}

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ApiClient":
        request_cfg = cfg.get("request", {}) or {}
        setting = os.environ.get("VIETHERITAGE_WIKI_CACHE", request_cfg.get("cache_dir"))
        cache_dir = None
        if setting and str(setting).lower() not in {"off", "none", "false", "0"}:
            cache_dir = Path(setting) if Path(setting).is_absolute() else REPO_ROOT / setting
        if not (os.environ.get("VIETHERITAGE_CONTACT") or request_cfg.get("contact")):
            _log("[wiki] cảnh báo: chưa có thông tin liên hệ trong User-Agent "
                 "(đặt VIETHERITAGE_CONTACT=email) -> Wikimedia có thể giới hạn tốc độ chặt hơn")
        return cls(cache_dir, bool(request_cfg.get("log_progress", True)))

    def _path(self, api_url: str, params: dict[str, Any]) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps([api_url, sorted((k, str(v)) for k, v in params.items())], ensure_ascii=False)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def __call__(self, api_url: str, params: dict[str, Any], request_cfg: dict[str, Any]) -> dict[str, Any]:
        path = self._path(api_url, params)
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.stats["cache_hits"] += 1
                return data
            except (OSError, ValueError):
                pass  # file hỏng -> tải lại
        start = time.time()
        data = self.fetch(api_url, params, request_cfg, session=self.session)
        took = time.time() - start
        self.stats["network"] += 1
        self.stats["network_seconds"] += took
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        if self.log_progress:
            kind = params.get("list") or params.get("action", "?")
            if params.get("titles"):
                kind += f" titles={str(params['titles']).count('|') + 1}"
            if params.get("ids"):
                kind += f" ids={str(params['ids']).count('|') + 1}"
            if any(k.endswith("continue") and k != "continue" for k in params):
                kind += " +continue"
            _log(f"[wiki {time.time() - self.started:6.0f}s] #{self.stats['network']} {kind} {took:.1f}s"
                 f" (cache hit {self.stats['cache_hits']})")
        return data

    def summary(self) -> dict[str, Any]:
        return {"http_requests": self.stats["network"], "cache_hits": self.stats["cache_hits"],
                "network_seconds": round(self.stats["network_seconds"], 1),
                "wall_seconds": round(time.time() - self.started, 1)}


def _merge_page(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if key in {"links", "categories", "coordinates"} and isinstance(value, list):
            existing = target.setdefault(key, [])
            for item in value:
                if item not in existing:
                    existing.append(item)
        elif key == "pageprops" and isinstance(value, dict):
            target.setdefault("pageprops", {}).update(value)
        elif key not in target or target[key] in (None, "", [], {}):
            target[key] = value


def query_with_continuation(fetcher, api_url: str, params: dict[str, Any], request_cfg: dict[str, Any],
                            max_rounds: int = 20) -> dict[str, Any]:
    """Gộp mọi vòng ``continue`` của MediaWiki (links/categories bị cắt theo batch)."""
    merged: dict[str, Any] = {"query": {"pages": [], "redirects": [], "normalized": []}}
    by_key: dict[Any, dict[str, Any]] = {}
    current = dict(params)
    for _ in range(max_rounds):
        response = fetcher(api_url, current, request_cfg) or {}
        query = response.get("query", {}) or {}
        for listname in ("redirects", "normalized"):
            for row in query.get(listname, []) or []:
                if row not in merged["query"][listname]:
                    merged["query"][listname].append(row)
        pages = query.get("pages", []) or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        for page in pages:
            key = page.get("pageid") or ("missing", page.get("title"))
            if key in by_key:
                _merge_page(by_key[key], page)
            else:
                by_key[key] = dict(page)
                merged["query"]["pages"].append(by_key[key])
        cont = response.get("continue")
        if not cont:
            break
        current = {**params, **cont}
    return merged


# ---------------------------------------------------------------------------
# Page construction and matching
# ---------------------------------------------------------------------------

def page_from_api_response(
    page_json: dict[str, Any],
    retrieved_at: str,
    requested_title: str | None = None,
    infobox_pattern: str = DEFAULT_INFOBOX_PATTERN,
) -> WikipediaPage | None:
    if page_json.get("missing") or page_json.get("invalid"):
        return None

    wikidata_id = None
    pageprops = page_json.get("pageprops", {})
    is_disambiguation = False
    if isinstance(pageprops, dict):
        wikidata_id = pageprops.get("wikibase_item")
        is_disambiguation = "disambiguation" in pageprops

    coordinates = None
    coords = page_json.get("coordinates")
    if coords:
        coordinates = {"lat": coords[0]["lat"], "lon": coords[0]["lon"]}

    categories = list(dict.fromkeys(c["title"] for c in page_json.get("categories", [])))
    links = list(dict.fromkeys(
        wiki_url(link["title"]) for link in page_json.get("links", [])
        if link.get("ns", 0) == 0
    ))
    abstract = page_json.get("extract")

    revisions = page_json.get("revisions", [])
    revision_id = None
    infobox: dict[str, Any] = {}
    infobox_links: dict[str, list[str]] = {}
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
            infobox, infobox_links = parse_first_infobox_with_links(content, infobox_pattern)

    title = page_json.get("title") or requested_title or ""
    return WikipediaPage(
        page_id=page_json.get("pageid"),
        title=title,
        source_url=wiki_url(title),
        retrieved_at=retrieved_at,
        wikidata_id=wikidata_id,
        coordinates=coordinates,
        infobox=infobox,
        categories=categories,
        abstract=abstract,
        links=links,
        revision_id=revision_id,
        requested_labels=[requested_title] if requested_title else [],
        infobox_links=infobox_links,
        is_disambiguation=is_disambiguation,
    )


_DASH_VARIANTS = (" - ", " – ", " — ")
EXACT_EQUIVALENT_METHODS = {"exact", "dash_variant"}


def title_key(title: str) -> str:
    """Khóa so khớp tiêu đề: NFC, casefold, dấu gạch chuẩn, vị trí dấu thanh (hoá = hóa)."""
    from vietheritage.normalization.areas import match_key

    return match_key((title or "").replace("_", " "))


def _dash_variants(title: str) -> list[str]:
    """Biến thể dấu gạch nối giữa hai vế tên (NOR-004): ``A - B`` <-> ``A – B``."""
    for dash in _DASH_VARIANTS:
        if dash in title:
            return [title.replace(dash, other) for other in (" - ", " – ") if other != dash]
    return []


def alias_candidates(label: str, rules: list[dict[str, Any]], dash_variants: bool = True) -> list[tuple[str, str]]:
    """API cũ (giữ tương thích): áp các luật regex nối tiếp, trả (tên luật, tiêu đề)."""
    results: list[tuple[str, str]] = []
    current = unicodedata.normalize("NFC", label)
    seen = {normalize_title(current)}

    def add(name: str, title: str) -> None:
        if title and normalize_title(title) not in seen:
            seen.add(normalize_title(title))
            results.append((name, title))

    if dash_variants:
        for variant in _dash_variants(current):
            add("dash_variant", variant)
    for rule in rules or []:
        if rule.get("type") or rule.get("mode") == "branch":
            continue
        replaced = re.sub(r"\s+", " ", re.sub(rule["pattern"], rule.get("replace", ""), current).strip())
        if replaced and normalize_title(replaced) != normalize_title(current):
            add(rule["name"], replaced)
            if dash_variants:
                for variant in _dash_variants(replaced):
                    add(f"{rule['name']}+dash_variant", variant)
            current = replaced
    return results


# ---------------------------------------------------------------------------
# Candidate generation v2 (review 2026-09-24)
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    title: str
    method: str
    needs_evidence: bool = True
    rules: tuple[str, ...] = ()      # chuỗi alias_rules đã áp để ra tiêu đề này (dùng cho chính sách bằng chứng)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;-–")


def _ucfirst(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _lcfirst(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _province_suffix_re(area_resolver) -> re.Pattern[str] | None:
    if area_resolver is None:
        return None
    names = sorted({n for a in area_resolver.areas for n in (a.label, *a.display_aliases)} |
                   {"Hà Nội", "Huế", "TP Hồ Chí Minh", "Hồ Chí Minh"}, key=len, reverse=True)
    body = "|".join(re.escape(n) for n in names)
    return re.compile(rf"(?:\s*[-–,]\s*|\s+)(?:(?:tỉnh|thành phố|tp\.?)\s+)?(?:{body})$", re.IGNORECASE)


def _is_site_category(target: "RegistryTarget", matching: dict[str, Any]) -> bool:
    return (target.registry_category or "") in set(matching.get("site_categories") or [])


def _apply_name_variants(title: str, matching: dict[str, Any]) -> list[str]:
    out = []
    for item in matching.get("name_variants") or []:
        if item["from"] in title:
            out.append(title.replace(item["from"], item["to"]))
    return out


def _starts_with_site_noun(title: str, matching: dict[str, Any]) -> bool:
    lowered = title.casefold()
    return any(lowered == n.casefold() or lowered.startswith(n.casefold() + " ") for n in matching.get("site_nouns") or [])


def title_forms(target: "RegistryTarget", matching: dict[str, Any], area_resolver=None) -> list[tuple[str, str]]:
    """Danh sách (method, tiêu đề) theo thứ tự thử, KHÔNG gồm override (xem ``title_forms_detailed``)."""
    return [(method, title) for method, title, _ in title_forms_detailed(target, matching, area_resolver)]


def title_forms_detailed(target: "RegistryTarget", matching: dict[str, Any],
                         area_resolver=None) -> list[tuple[str, str, tuple[str, ...]]]:
    """Danh sách (method, tiêu đề, chuỗi luật đã áp) theo thứ tự thử, KHÔNG gồm override.

    1. nhãn gốc (+ biến thể dấu gạch) — tương đương exact;
    2. chuỗi luật ``alias_rules`` áp nối tiếp (``mode: chain``) hoặc rẽ nhánh (``branch``);
    3. với danh mục di tích: trước một tên "trần" không mở đầu bằng danh từ loại hình
       (Đền, Chùa, Hồ…) thử trước các dạng có tiền tố ``site_prefixes`` ("Khu di tích lịch sử X")
       — tránh "Bạch Đằng" ra sông, "Bà Triệu" ra người;
    4. với phi vật thể: "Hội X" -> thử thêm "Lễ hội X";
    5. mỗi dạng sinh thêm ``name_variants`` (Pô -> Po, Buôn Mê Thuột -> Buôn Ma Thuột…) và biến thể dấu gạch.
    """
    site = _is_site_category(target, matching)
    province_re = _province_suffix_re(area_resolver)
    forms: list[tuple[str, str, tuple[str, ...]]] = []
    seen: set[str] = set()
    rules_now: list[tuple[str, ...]] = [()]   # chuỗi luật của dạng tên đang được thêm

    def add(method: str, title: str) -> None:
        # Khử trùng theo CHUỖI (không theo title_key): MediaWiki phân biệt hoa/thường và
        # dấu gạch, nên "A - B" và "A – B" đều phải được gửi đi.
        title = _clean(title)
        if not title or title in seen:
            return
        seen.add(title)
        forms.append((method, title, rules_now[0]))
        if matching.get("dash_variants", True):
            for variant in _dash_variants(title):
                if variant not in seen:
                    seen.add(variant)
                    forms.append(("dash_variant" if method == "exact" else f"{method}+dash", variant, rules_now[0]))

    abbreviation = re.compile(((matching.get("alias_rules") or [{}])[0]).get("pattern", r"^\b$"))
    lowercase_words = {w.casefold() for w in matching.get("prefix_lowercase_words") or []}

    def add_prefixed(method: str, core: str) -> None:
        if not site or _starts_with_site_noun(core, matching) or abbreviation.search(core):
            return
        first = core.split(" ", 1)[0].casefold()
        for prefix in matching.get("site_prefixes") or []:
            add(f"{method}+prefix", prefix + core)
            if first in lowercase_words:   # "Khu di tích chiến trường Điện Biên Phủ"
                add(f"{method}+prefix", prefix + _lcfirst(core))

    def add_core(method: str, core: str) -> None:
        if method == "exact":
            add(method, core)            # nhãn gốc luôn thử đầu tiên
            add_prefixed("alias:site_prefix", core)
        else:
            add_prefixed(method, core)   # "Khu di tích lịch sử X" trước "X"
            add(method, core)
        festival = matching.get("festival_prefix")
        if not site and festival and re.match(festival["pattern"], core):
            add(f"{method}+festival", re.sub(festival["pattern"], festival["replace"], core))
        for variant in _apply_name_variants(core, matching):
            add(f"{method}+variant", variant)

    label = unicodedata.normalize("NFC", target.label_vi)
    add_core("exact", label)
    current, chain = label, ()
    for rule in matching.get("alias_rules") or []:
        scope = rule.get("applies_to", "all")
        if (scope == "site" and not site) or (scope == "intangible" and site):
            continue
        if rule.get("type") == "province_suffix":
            new = province_re.sub("", current) if province_re else current
        else:
            new = re.sub(rule["pattern"], rule.get("replace", ""), current)
        new = _ucfirst(_clean(new))
        if not new or title_key(new) == title_key(current):
            continue
        rules_now[0] = chain + (rule["name"],)
        add_core(f"alias:{rule['name']}", new)
        if rule.get("mode", "chain") == "chain":
            current, chain = new, rules_now[0]
    return forms


def component_labels(target: "RegistryTarget", matching: dict[str, Any], area_resolver=None) -> list[str]:
    """Tách di tích gộp ("Hồ Hoàn Kiếm và Đền Ngọc Sơn") thành tên thành phần.

    Chỉ bỏ viết tắt loại hình và phần trong ngoặc trước khi tách; phần mở đầu bằng từ
    chung chung ("những", "các", "hệ thống", "khu vực"…) hoặc quá ngắn bị bỏ.
    """
    cfg = matching.get("components") or {}
    if not cfg.get("enabled", True) or not _is_site_category(target, matching):
        return []
    text = unicodedata.normalize("NFC", target.label_vi)
    for pattern in cfg.get("pre_strip_patterns") or []:
        text = _clean(re.sub(pattern, "", text))
    parts = [_clean(p) for p in re.split(cfg.get("separator_pattern", r"\s+(?:và|VÀ)\s+|\s+[-–]\s+|,\s*"), text)]
    drop = re.compile(cfg.get("drop_pattern", r"^(?:những|các|hệ thống|khu vực|vùng|địa điểm)\b"), re.IGNORECASE)
    min_words = int(cfg.get("min_words", 2))
    province_keys = set()
    if area_resolver is not None:
        province_keys = {title_key(n) for a in area_resolver.areas for n in (a.label, *a.display_aliases, a.group)}
    keep = [_ucfirst(p) for p in parts if p and not drop.search(p) and len(p.split()) >= min_words
            and title_key(p) not in province_keys]
    return keep if len(parts) > 1 else []


def load_overrides(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not path or not Path(path).exists():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    result = {}
    for item in data.get("overrides") or []:
        key = (item["registry_category"], unicodedata.normalize("NFC", item["label_vi"]))
        result[key] = item
    return result


def _exact(title: str) -> str:
    """Khóa chuỗi chính xác kiểu MediaWiki: NFC, "_" = " ", chữ cái đầu viết hoa."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", title or "").replace("_", " ")).strip()
    return text[:1].upper() + text[1:]


class _Lookup:
    """Page đã tải, tra theo ``title_key`` (không phân biệt hoa/thường, dấu gạch, vị trí dấu thanh)."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.pages: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, tuple[str, str]] = {}
        self.fetched: set[str] = set()
        if response:
            self.add(response)

    def add(self, response: dict[str, Any]) -> None:
        query = response.get("query", {}) or {}
        pages = query.get("pages", []) or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        for page in pages:
            self.fetched.add(_exact(page.get("title", "")))
            if not page.get("missing") and not page.get("invalid"):
                self.pages[title_key(page.get("title", ""))] = page
        for row in query.get("normalized", []) or []:
            self.aliases[title_key(row.get("from", ""))] = (title_key(row.get("to", "")), "normalized")
        for row in query.get("redirects", []) or []:
            self.aliases[title_key(row.get("from", ""))] = (title_key(row.get("to", "")), "redirect")
            self.fetched.add(_exact(row.get("from", "")))

    def find(self, title: str) -> tuple[dict[str, Any] | None, str]:
        key = title_key(title)
        method = "exact_title"
        for _ in range(3):
            if key in self.aliases:
                key, step = self.aliases[key]
                if step == "redirect":
                    method = "redirect"
            else:
                break
        return self.pages.get(key), method


def _default_area_resolver():
    try:
        from vietheritage.normalization.areas import default_resolver
        return default_resolver()
    except (OSError, ValueError):  # config thiếu -> không có bằng chứng tỉnh
        return None


def page_rejection_reason(categories: list[str], registry_category: str | None, matching: dict[str, Any]) -> str | None:
    """Chính sách loại page theo thể loại Wikipedia (deterministic, cấu hình trong collector.yaml).

    * ``reject_category_patterns``: page là người, đơn vị hành chính, sông, cuộc khởi nghĩa…
      không phải là chính di sản dù tiêu đề khớp.
    * ``category_requirements[registry_category]``: ví dụ bảo vật quốc gia phải nằm trong
      thể loại "Bảo vật quốc gia…" để loại page khái niệm chung ("Súng thần công", "Long đao").
    """
    for pattern in matching.get("reject_category_patterns", []) or []:
        for category in categories:
            if re.search(pattern, category):
                return f"page type rejected by category {category!r}"
    required = (matching.get("category_requirements", {}) or {}).get(registry_category or "")
    if required and not any(re.search(required, category) for category in categories):
        return f"page lacks required category /{required}/ for {registry_category}"
    return None


def ambiguous_shared_pages(assignments: list[tuple[int, str | None, str]]) -> set[int]:
    """Page được gán cho >1 nhãn KHÁC NHAU trong CÙNG một registry category là page khái
    niệm chung (ví dụ "Sình ca" <- "Dân ca Cao Lan", "Dân ca Sán Chí") -> không dùng.

    ``assignments``: (page_id, registry_category, label_vi).
    """
    labels: dict[tuple[int, str | None], set[str]] = {}
    for page_id, category, label in assignments:
        labels.setdefault((page_id, category), set()).add(" ".join(label.casefold().split()))
    return {page_id for (page_id, _), values in labels.items() if len(values) > 1}


def _page_blob(page: "WikipediaPage") -> str:
    return " \n ".join([page.title, " ".join(page.categories), page.abstract or "",
                        " ".join(str(v) for v in page.infobox.values())])


def province_evidence(target: "RegistryTarget", page: "WikipediaPage", area_resolver,
                      multi_group_is_weak: bool = False) -> tuple[list[str], bool]:
    """(bằng chứng, xung đột) theo tỉnh SAU sáp nhập 2025.

    Bằng chứng: nhóm tỉnh của registry giao với nhóm tỉnh nhắc tới trên page (tiêu đề,
    thể loại, đoạn mở đầu, infobox). Xung đột: cả hai phía đều có tỉnh nhưng không giao
    nhau (ví dụ registry Nam Định -> nhóm Ninh Bình, page Thái Bình -> nhóm Hưng Yên).

    ``multi_group_is_weak``: page nhắc >= 2 nhóm tỉnh (bài về một loại hình phổ biến nhiều
    nơi, ví dụ "Lễ hội nghinh Ông") -> không coi là xung đột, chỉ là "không có bằng chứng".
    """
    if area_resolver is None or not target.location:
        return [], False
    expected = area_resolver.resolve(target.location).areas
    if not expected:
        return [], False
    found = area_resolver.resolve(_page_blob(page)).areas
    found_labels = {area.label for area in found}
    found_groups = {area.group for area in found}
    evidence = []
    for area in expected:
        if area.label in found_labels:
            evidence.append(f"province:{area.label}")
        elif area.group in found_groups:
            evidence.append(f"province:{area.label}->{area.group} (sáp nhập 2025)")
    conflict = bool(found) and not evidence
    if conflict and multi_group_is_weak and len(found_groups) >= 2:
        conflict = False
    return list(dict.fromkeys(evidence)), conflict


_ETHNIC_OWNER_RE = re.compile(r"\bcủa\s+(?:các\s+)?(?:người|dân tộc)\s+(.+)$", re.IGNORECASE)


def ethnic_names(label: str) -> list[str]:
    """Tên dân tộc trong nhãn dạng "X của người Y[, người Z]" (bỏ ngoặc và cụm "ở/tại ...").

    "Kéo co của người Tày, người Giáy" -> ["Tày", "Giáy"];
    "Lễ Cấp sắc (Tủ cải) của người Dao Quần chẹt" -> ["Dao Quần chẹt"].
    """
    text = re.sub(r"\s*\([^)]*\)", "", unicodedata.normalize("NFC", label or ""))
    text = re.sub(r"\s+(?:ở|tại)\s+.+$", "", text)
    match = _ETHNIC_OWNER_RE.search(text)
    if not match:
        return []
    parts = re.split(r",\s*|\s+và\s+", match.group(1))
    names = [re.sub(r"^(?:người|dân tộc)\s+", "", _clean(p), flags=re.IGNORECASE) for p in parts]
    return [n for n in dict.fromkeys(names) if n]


def ethnic_evidence(label: str, candidate_title: str, page: "WikipediaPage") -> list[str]:
    """Bằng chứng dân tộc cho alias đã bỏ "của người Y": page phải nhắc tới dân tộc Y.

    Khớp "người/dân tộc Y" (hoặc chỉ tên gọi đầu, ví dụ "Dao" cho "Dao Quần chẹt"), hoặc tên đầy
    đủ >= 2 âm tiết đứng riêng (phân biệt hoa/thường). Tên đã nằm trong tiêu đề ứng viên thì bỏ qua.
    """
    blob = unicodedata.normalize("NFC", _page_blob(page))
    found = []
    for name in ethnic_names(label):
        if title_key(name) in title_key(candidate_title):
            continue
        head = name.split()[0]
        prefixed = rf"(?:người|dân tộc|tộc)\s+(?:{re.escape(name)}|{re.escape(head)})(?!\w)"
        if re.search(prefixed, blob, re.IGNORECASE) or (
                len(name.split()) >= 2 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", blob)):
            found.append(f"ethnic:{name}")
    return found


def _rule_pattern(matching: dict[str, Any], name: str) -> str | None:
    rule = next((r for r in matching.get("alias_rules") or [] if r.get("name") == name), None)
    return (rule or {}).get("pattern")


def region_evidence(label: str, page: "WikipediaPage", rule_names: set[str], matching: dict[str, Any]) -> list[str]:
    """Luật bỏ hậu tố vùng ("… Nam bộ", "… Tây Nguyên"): bằng chứng = page nhắc lại đúng tên vùng đó."""
    blob = title_key(_page_blob(page))
    found = []
    for name in rule_names:
        pattern = _rule_pattern(matching, name)
        if not pattern:
            continue
        match = re.search(pattern[:-1] if pattern.endswith("$") else pattern, unicodedata.normalize("NFC", label))
        region = _clean(match.group(0)) if match else ""
        if region and title_key(region) in blob:
            found.append(f"region:{region}")
    return found


def _intangible_policy_applies(target: "RegistryTarget", matching: dict[str, Any]) -> bool:
    """Chính sách ``intangible_evidence`` chỉ áp cho category được liệt kê tường minh
    (record không rõ category -> giữ luật cũ, bảo thủ)."""
    policy = matching.get("intangible_evidence") or {}
    return bool(policy.get("enabled", False)) and (target.registry_category or "") in set(policy.get("categories") or [])


def alias_evidence(target: "RegistryTarget", cand: "Candidate", page: "WikipediaPage",
                   province: list[str], matching: dict[str, Any]) -> tuple[list[str] | None, str]:
    """Chính sách bằng chứng cho match qua alias. Trả (bằng chứng, lý do) — bằng chứng None = loại.

    * Category ngoài ``intangible_evidence.categories`` (di tích, bảo vật, không rõ) hoặc chính sách
      tắt: như cũ, BẮT BUỘC có bằng chứng tỉnh.
    * Phi vật thể (``intangible_evidence.categories``), theo các luật đã áp để ra tiêu đề:
      - luật bỏ địa danh (``province_rules``) -> cần bằng chứng tỉnh;
      - luật bỏ tên dân tộc (``ethnic_rules``) -> cần bằng chứng dân tộc;
      - luật bỏ hậu tố vùng (``region_rules``) -> page nhắc lại tên vùng đó, hoặc có bằng chứng tỉnh;
      - chỉ gồm luật "chung chung" (``evidence_free_rules``: bỏ "Nghệ thuật/Dân ca/Hát…", bỏ ngoặc,
        bỏ viết tắt loại hình) -> không cần bằng chứng nếu tiêu đề còn >= ``min_words`` từ và page
        không thuộc thể loại ``evidence_free_reject_category_patterns`` (bài dân tộc, địa danh…);
      - luật khác / không rõ -> cần bằng chứng tỉnh (bảo thủ như cũ).
    """
    policy = matching.get("intangible_evidence") or {}
    no_province = f"alias {cand.method!r} -> {page.title!r} matched without province evidence"
    if not _intangible_policy_applies(target, matching):
        return (province, "") if province else (None, no_province)
    rules = set(cand.rules)
    province_rules = set(policy.get("province_rules") or [])
    ethnic_rules = set(policy.get("ethnic_rules") or [])
    free_rules = set(policy.get("evidence_free_rules") or [])
    region_rules = set(policy.get("region_rules") or []) & rules
    need_province = (bool(rules & province_rules) or not rules
                     or bool(rules - province_rules - ethnic_rules - free_rules - region_rules))
    need_ethnic = bool(rules & ethnic_rules)
    evidence: list[str] = []
    if region_rules:
        region = region_evidence(target.label_vi, page, region_rules, matching)
        if region:
            evidence += region
        elif not province:
            return None, f"alias {cand.method!r} -> {page.title!r} matched without region/province evidence"
    if need_ethnic:
        ethnic = ethnic_evidence(target.label_vi, cand.title, page)
        if not ethnic:
            return None, f"alias {cand.method!r} -> {page.title!r} matched without ethnic evidence"
        evidence += ethnic
    if need_province:
        if not province:
            return None, no_province
        evidence += province
    if not need_province and not need_ethnic and not region_rules:
        if len(cand.title.split()) < int(policy.get("min_words", 2)):
            return None, f"alias {cand.method!r} -> {page.title!r} too short without evidence"
        for pattern in policy.get("evidence_free_reject_category_patterns") or []:
            hit = next((c for c in page.categories if re.search(pattern, c)), None)
            if hit:
                return None, f"alias {cand.method!r} -> {page.title!r} rejected by category {hit!r} (no evidence)"
        evidence.append("rule_scope:" + "+".join(r for r in cand.rules))
    return list(dict.fromkeys(evidence + province)), ""


def _evidence(target: "RegistryTarget", page: "WikipediaPage", area_resolver) -> list[str]:
    return province_evidence(target, page, area_resolver)[0]


@dataclass
class _Match:
    page: WikipediaPage
    method: str
    evidence: list[str]
    part_label: str | None = None


class _Matcher:
    """Chạy các vòng tra cứu MediaWiki cho một nhóm registry target."""

    def __init__(self, cfg: dict[str, Any], fetcher, area_resolver, retrieved_at: str,
                 chunk_size: int = 50, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.cfg = cfg
        self.matching = cfg.get("matching", {}) or {}
        self.fetcher = fetcher
        self.area_resolver = area_resolver
        self.retrieved_at = retrieved_at
        self.chunk_size = chunk_size
        self.sleeper = sleeper
        self.request_cfg = cfg.get("request", {}) or {}
        self.lookup = _Lookup()
        self.calls = 0

    # -- network ----------------------------------------------------------
    def _pause(self, key: str = "delay_seconds") -> None:
        delay = float(self.request_cfg.get(key, 0) or 0)
        if self.calls and delay:
            self.sleeper(delay)
        self.calls += 1

    def fetch_titles(self, titles: list[str]) -> None:
        # MediaWiki phân biệt hoa/thường (trừ chữ cái đầu) -> khử trùng theo chuỗi chính xác.
        todo = []
        for title in titles:
            if _exact(title) not in self.lookup.fetched and title not in todo:
                todo.append(title)
        for batch in _chunks(todo, self.chunk_size):
            self._pause()
            response = query_with_continuation(self.fetcher, self.cfg["api_url"],
                                               build_query_params(batch, self.cfg.get("query", {})), self.request_cfg)
            self.lookup.add(response)
            for title in batch:
                self.lookup.fetched.add(_exact(title))

    def prefix_resolve(self, queries: list[str]) -> None:
        """``list=prefixsearch`` chỉ để tìm ĐÚNG tiêu đề khi khác hoa/thường/dấu gạch; chỉ nhận
        kết quả có ``title_key`` trùng khít với truy vấn (không fuzzy)."""
        ps = self.matching.get("prefixsearch") or {}
        found: list[str] = []
        for query in dict.fromkeys(queries):
            page, _ = self.lookup.find(query)
            if page is not None:
                continue
            self._pause("prefixsearch_delay_seconds")
            response = self.fetcher(self.cfg["api_url"], {
                "action": "query", "format": "json", "formatversion": 2, "list": "prefixsearch",
                "pssearch": query, "pslimit": int(ps.get("limit", 10)), "psnamespace": 0,
            }, self.request_cfg) or {}
            for row in (response.get("query") or {}).get("prefixsearch", []) or []:
                if title_key(row.get("title", "")) == title_key(query):
                    found.append(row["title"])
        if found:
            self.fetch_titles(found)

    # -- evaluation ---------------------------------------------------------
    def evaluate(self, target: RegistryTarget, candidates: list[Candidate], component: bool = False):
        infobox_pattern = (self.cfg.get("infobox", {}) or {}).get("name_pattern", DEFAULT_INFOBOX_PATTERN)
        reason, disambiguations = "no page found for any candidate title", []
        component_re = (self.matching.get("components") or {}).get("required_category_pattern")
        for cand in candidates:
            page_json, lookup_method = self.lookup.find(cand.title)
            if page_json is None:
                continue
            page = page_from_api_response(page_json, self.retrieved_at, requested_title=target.label_vi,
                                          infobox_pattern=infobox_pattern)
            if page is None:
                continue
            if page.is_disambiguation:
                disambiguations.append(page_json)
                reason = f"disambiguation page {page.title!r} (no province-specific page)"
                continue
            policy = page_rejection_reason(page.categories, target.registry_category, self.matching)
            if policy and cand.method != "manual_override":
                reason = f"{policy} (candidate {page.title!r})"
                continue
            if component and component_re and cand.method != "manual_override" and not any(
                    re.search(component_re, c) for c in page.categories):
                reason = f"component page {page.title!r} is not a heritage-type page"
                continue
            policy = self.matching.get("intangible_evidence") or {}
            weak = _intangible_policy_applies(target, self.matching) and bool(policy.get("multi_province_conflict_is_weak"))
            evidence, conflict = province_evidence(target, page, self.area_resolver, multi_group_is_weak=weak)
            if conflict and cand.method != "manual_override" and self.matching.get("reject_province_conflict", True):
                reason = f"province conflict: page {page.title!r} is in another province group"
                continue
            if cand.needs_evidence and self.matching.get("require_evidence_for_alias", True):
                accepted, why = alias_evidence(target, cand, page, evidence, self.matching)
                if accepted is None:
                    reason = why
                    continue
                evidence = accepted
            method = cand.method
            if method in EXACT_EQUIVALENT_METHODS or method == "exact":
                method = lookup_method if method == "exact" else f"{lookup_method}+dash_variant"
            elif lookup_method == "redirect":
                method = f"{method}+redirect"
            if _exact(page.title) != _exact(cand.title) and lookup_method != "redirect":
                method = f"{method}+normalized"   # khác hoa/thường hoặc dấu gạch, cùng title_key
            return _Match(page, method, evidence), reason, disambiguations
        return None, reason, disambiguations

    def _disambiguation_candidates(self, target: RegistryTarget, pages_json: list[dict[str, Any]]) -> list[Candidate]:
        names: list[str] = []
        if self.area_resolver is not None and target.location:
            for area in self.area_resolver.resolve(target.location).areas:
                names += [area.label, area.group]
                if area.label == "Thừa Thiên Huế":
                    names.append("Huế")
        location_key = title_key(target.location or "")
        out: list[Candidate] = []
        for page_json in pages_json:
            base = page_json.get("title", "")
            for name in dict.fromkeys(names):
                out.append(Candidate(f"{base} ({name})", "disambiguation:province"))
            for link in page_json.get("links", []) or []:
                title = link.get("title", "")
                match = re.match(rf"^{re.escape(base)} \((.+)\)$", title)
                if match and title_key(match.group(1)) in location_key:
                    out.append(Candidate(title, "disambiguation:location"))
        return out

    def match(self, targets: list[RegistryTarget], candidates: list[list[Candidate]], component: bool = False):
        self.fetch_titles([c.title for cands in candidates for c in cands])
        results = [self.evaluate(t, c, component) for t, c in zip(targets, candidates)]
        ps = self.matching.get("prefixsearch") or {}
        if ps.get("enabled", True):
            unmatched = [i for i, r in enumerate(results) if r[0] is None]
            queries = []
            skip = re.compile((self.matching.get("alias_rules") or [{}])[0].get("pattern", r"^\b$"))
            for i in unmatched:
                forms = [c.title for c in candidates[i] if c.method != "manual_override" and not skip.search(c.title)]
                queries += list(dict.fromkeys(forms))[: int(ps.get("max_forms", 4))]
            self.prefix_resolve(queries)
            for i in unmatched:
                results[i] = self.evaluate(targets[i], candidates[i], component)
        if self.matching.get("expand_disambiguation", True):
            extra: dict[int, list[Candidate]] = {}
            for i, (match, _, disamb) in enumerate(results):
                if match is None and disamb:
                    extra[i] = self._disambiguation_candidates(targets[i], disamb)
            self.fetch_titles([c.title for cands in extra.values() for c in cands])
            for i, cands in extra.items():
                candidates[i] = candidates[i] + cands
                results[i] = self.evaluate(targets[i], candidates[i], component)
        return results


def build_candidates(target: RegistryTarget, matching: dict[str, Any], area_resolver=None,
                     overrides: dict | None = None) -> tuple[list[Candidate], dict[str, Any] | None]:
    override = (overrides or {}).get((target.registry_category or "", unicodedata.normalize("NFC", target.label_vi)))
    if override:
        return [Candidate(t, "manual_override", False) for t in override.get("titles") or []], override
    return [Candidate(title, method, method not in EXACT_EQUIVALENT_METHODS, rules)
            for method, title, rules in title_forms_detailed(target, matching, area_resolver)], None


def match_targets_to_pages(
    targets: list[RegistryTarget],
    api_response: dict[str, Any],
    retrieved_at: str,
    config: dict[str, Any] | None = None,
    area_resolver=None,
) -> tuple[list[WikipediaPage], list[dict[str, Any]]]:
    """Khớp offline trên MỘT response đã có (không prefixsearch, không tách thành phần).

    Dùng cho test và tương thích API cũ; stage thật dùng ``enrich_many``.
    """
    config = dict(config or {})
    matching = dict(config.get("matching", {}) or {})
    matching["prefixsearch"] = {"enabled": False}
    config["matching"] = matching
    matcher = _Matcher(config, fetcher=None, area_resolver=area_resolver, retrieved_at=retrieved_at)
    matcher.lookup.add(api_response)
    matcher.fetch_titles = lambda titles: None  # type: ignore[method-assign]
    candidates = [build_candidates(t, matching, area_resolver)[0] for t in targets]
    results = matcher.match(targets, candidates)
    links = [(t, r[0]) for t, r in zip(targets, results) if r[0] is not None]
    failures = [{"registry_id": t.registry_id, "label_vi": t.label_vi, "error_code": "ENRICHMENT_MISSING",
                 "reason": r[1], "titles_tried": [c.title for c in cands]}
                for t, r, cands in zip(targets, results, candidates) if r[0] is None]
    pages, more_failures = _assemble_pages([(t, m) for t, m in links], matching, area_resolver)
    return pages, failures + more_failures


_EXACT_METHOD_FAMILIES = ("exact_title", "redirect", "exact")


def _link_rank(match: "_Match") -> int:
    """Độ "trực tiếp" của link: 2 = tiêu đề chính xác/redirect của nhãn gốc, 1 = alias ra ĐÚNG tiêu đề
    page (không qua redirect/định hướng), 0 = còn lại."""
    family = match.method.split("+", 1)[0]
    if family in _EXACT_METHOD_FAMILIES:
        return 2
    if family.startswith("alias:") and "redirect" not in match.method:
        return 1
    return 0


def shared_identity_label(label: str, matching: dict[str, Any], area_resolver=None) -> str:
    """Nhãn dùng để quyết định "cùng một di sản" khi nhiều record trỏ cùng một page.

    Bỏ viết tắt loại hình, mọi phần trong ngoặc, cụm "ở/tại …" và hậu tố tỉnh: "Mo Mường (Hà Nội)",
    "Mo Mường ở Hòa Bình", "Mo Mường" là một; "Dân ca Cao Lan" và "Dân ca Sán Chí" vẫn khác nhau.
    Tên dân tộc ("của người Tày" vs "của người Giáy") được GIỮ: khác dân tộc = di sản khác.
    Tiền tố thể loại ("Nghệ thuật", "Hát", "Dân ca"…) bị bỏ: "Nghệ thuật múa rối nước" = "Múa rối nước".
    """
    abbreviation = ((matching.get("alias_rules") or [{}])[0]).get("pattern", r"^\b$")
    text = re.sub(abbreviation, "", unicodedata.normalize("NFC", label or ""))
    genre = _rule_pattern(matching, "strip_genre_prefix")   # "Nghệ thuật múa rối nước" = "Múa rối nước"
    if genre:
        text = re.sub(genre, "", text)
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = re.sub(r"\s+(?:ở|tại)\s+.+$", "", text)
    province_re = _province_suffix_re(area_resolver)
    if province_re is not None:
        text = province_re.sub("", text)
    return " ".join(_clean(text).casefold().split())


def _assemble_pages(links: list[tuple[RegistryTarget, _Match]], matching: dict[str, Any],
                    area_resolver=None) -> tuple[list[WikipediaPage], list[dict[str, Any]]]:
    """Gom link (record -> page) thành page duy nhất theo page_id + áp luật page dùng chung.

    Page dùng chung bởi >= 2 nhãn KHÁC NHAU (sau ``shared_identity_label``) trong cùng category là
    page khái niệm chung -> bỏ link. Ngoại lệ: nếu ở mức ``_link_rank`` cao nhất chỉ có ĐÚNG MỘT nhãn
    thì giữ link của nhãn đó ("Kéo co" (chính xác) giữ bài "Kéo co", các "Kéo co của người …" bị bỏ;
    "Hát Ca trù" -> "Ca trù" (trực tiếp) thắng "Hát nhà tơ" -> redirect "Ca trù").
    """
    failures: list[dict[str, Any]] = []
    if matching.get("reject_shared_page_different_labels", True):
        def identity(t: RegistryTarget, m: _Match) -> str:
            return shared_identity_label(m.part_label or t.label_vi, matching, area_resolver)

        scored = [(t, m) for t, m in links if m.method != "manual_override"]
        ambiguous = ambiguous_shared_pages([(m.page.page_id, t.registry_category, identity(t, m)) for t, m in scored])
        best: dict[tuple[int, str | None], int] = {}
        for t, m in scored:
            key = (m.page.page_id, t.registry_category)
            best[key] = max(best.get(key, -1), _link_rank(m))
        owners: dict[tuple[int, str | None], set[str]] = {}
        for t, m in scored:
            key = (m.page.page_id, t.registry_category)
            if m.page.page_id in ambiguous and _link_rank(m) == best[key]:
                owners.setdefault(key, set()).add(identity(t, m))
        kept = []
        for t, m in links:
            if m.page.page_id in ambiguous and m.method != "manual_override":
                top = owners.get((m.page.page_id, t.registry_category), set())
                if len(top) == 1 and _link_rank(m) == best[(m.page.page_id, t.registry_category)]:
                    kept.append((t, m))
                    continue
                failures.append({"registry_id": t.registry_id, "label_vi": t.label_vi, "error_code": "ENRICHMENT_MISSING",
                                 "reason": f"ambiguous shared page {m.page.title!r}"})
            else:
                kept.append((t, m))
        links = kept
    pages: dict[int, WikipediaPage] = {}
    for target, match in links:
        page = pages.get(match.page.page_id)
        if page is None:
            page = match.page
            page.match_method, page.match_evidence = match.method, list(match.evidence)
            page.registry_ids, page.requested_labels, page.registry_links = [], [], []
            pages[page.page_id] = page
        if target.registry_id and target.registry_id not in page.registry_ids:
            page.registry_ids.append(target.registry_id)
        if target.label_vi not in page.requested_labels:
            page.requested_labels.append(target.label_vi)
        page.registry_links.append({
            "registry_id": target.registry_id, "label_vi": target.label_vi, "match_method": match.method,
            "match_evidence": list(match.evidence), "part_label": match.part_label,
        })
        for item in match.evidence:
            if item not in page.match_evidence:
                page.match_evidence.append(item)
    return list(pages.values()), failures


def match_registry_labels_to_pages(
    registry_labels: list[Any],
    api_response: dict[str, Any],
    retrieved_at: str,
    config: dict[str, Any] | None = None,
    area_resolver=None,
) -> tuple[list[WikipediaPage], list[dict[str, Any]]]:
    """Tương thích API cũ: nhận list nhãn (str) hoặc dict registry target."""
    return match_targets_to_pages(_as_targets(registry_labels), api_response, retrieved_at, config, area_resolver)


# ---------------------------------------------------------------------------
# Relation candidates (M2-15)
# ---------------------------------------------------------------------------

def _relation_rules(config: dict[str, Any]) -> list[tuple[str, re.Pattern[str], str]]:
    rel_cfg = config.get("relations", {}) or {}
    rules = []
    for relation, spec in (rel_cfg.get("fields", {}) or {}).items():
        rules.append((relation, re.compile(spec["key_pattern"]), spec["target"]))
    return rules


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def resolve_relation_candidates(
    pages: list[WikipediaPage],
    config: dict[str, Any],
    fetcher,
    chunk_size: int = 50,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Link trong infobox -> page_id/QID (MediaWiki) -> P31 (Wikidata) -> quan hệ đã xác minh."""
    rules = _relation_rules(config)
    rel_cfg = config.get("relations", {}) or {}
    classes = {target: set(qids) for target, qids in (rel_cfg.get("target_classes", {}) or {}).items()}
    max_links = int(rel_cfg.get("max_links_per_field", 10))
    stats = {"candidates": 0, "verified": 0}
    if not rules or not pages:
        return stats

    wanted: list[tuple[WikipediaPage, str, str, str]] = []  # (page, relation, key, title)
    for page in pages:
        for key, titles in sorted(page.infobox_links.items()):
            for relation, pattern, target in rules:
                if pattern.search(key):
                    for title in titles[:max_links]:
                        wanted.append((page, relation, key, title))
    if not wanted:
        return stats

    request_cfg = config.get("request", {}) or {}
    delay = float(request_cfg.get("delay_seconds", 0) or 0)
    titles = list(dict.fromkeys(item[3] for item in wanted))
    resolved: dict[str, dict[str, Any]] = {}
    for batch in _chunks(titles, chunk_size):
        if delay:
            sleeper(delay)
        response = query_with_continuation(fetcher, config["api_url"], {
            "action": "query", "format": "json", "formatversion": 2,
            "titles": "|".join(batch), "redirects": 1, "prop": "pageprops", "ppprop": "wikibase_item",
        }, request_cfg)
        lookup = _Lookup(response)
        for title in batch:
            page_json, _ = lookup.find(title)
            if page_json is not None:
                resolved[title] = {
                    "page_id": page_json.get("pageid"),
                    "title": page_json.get("title"),
                    "qid": (page_json.get("pageprops") or {}).get("wikibase_item"),
                }

    qids = sorted({info["qid"] for info in resolved.values() if info.get("qid")})
    instance_of: dict[str, list[str]] = {}
    wikidata_cfg = config.get("wikidata", {}) or {}
    wikidata_api = wikidata_cfg.get("api_url", "https://www.wikidata.org/w/api.php")
    for batch in _chunks(qids, chunk_size):
        if delay:
            sleeper(delay)
        response = fetcher(wikidata_api, {
            "action": "wbgetentities", "format": "json", "ids": "|".join(batch), "props": "claims",
        }, request_cfg) or {}
        for qid, entity in (response.get("entities", {}) or {}).items():
            values = []
            for claim in (entity.get("claims", {}) or {}).get("P31", []) or []:
                value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
                if isinstance(value, dict) and value.get("id"):
                    values.append(value["id"])
            instance_of[qid] = values

    for page, relation, key, title in wanted:
        info = resolved.get(title)
        target_type = next(target for rel, _, target in rules if rel == relation)
        candidate = {
            "relation": relation, "infobox_key": key, "link_title": title,
            "target_type": target_type, "page_id": None, "title": None, "qid": None,
            "instance_of": [], "verified": False,
        }
        if info:
            candidate.update(page_id=info["page_id"], title=info["title"], qid=info.get("qid"))
            p31 = instance_of.get(info.get("qid") or "", [])
            candidate["instance_of"] = p31
            candidate["verified"] = bool(set(p31) & classes.get(target_type, set()))
        if candidate not in page.relation_candidates:
            page.relation_candidates.append(candidate)
            stats["candidates"] += 1
            stats["verified"] += int(candidate["verified"])
    return stats


# ---------------------------------------------------------------------------
# Stage entry points
# ---------------------------------------------------------------------------

def _write_outputs(pages: list[WikipediaPage], failures: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_path = output_dir / "pages.jsonl"
    failures_path = output_dir / "enrichment_failures.jsonl"
    with pages_path.open("w", encoding="utf-8") as fh:
        for page in pages:
            fh.write(json.dumps(page.to_dict(), ensure_ascii=False) + "\n")
    with failures_path.open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
    return pages_path, failures_path


def enrich_many(
    registry_items: list[Any],
    config_path: Path = CONFIG_PATH,
    fetcher=fetch_query,
    output_dir: Path = RAW_DIR,
    chunk_size: int = 50,
    sleeper: Callable[[float], None] = time.sleep,
    area_resolver=None,
    resolve_relations: bool = True,
) -> dict[str, Any]:
    """Enrich registry records theo các vòng: tiêu đề/alias -> prefixsearch -> định hướng
    -> tách di tích gộp; override thủ công (``config/wikipedia_overrides.yaml``) ưu tiên nhất.

    Missing pages are retained in the failure manifest and never remove registry records.
    """
    cfg = load_config(config_path)
    retrieved_at = utc_now_iso()
    client = ApiClient.from_config(cfg) if fetcher is fetch_query else None
    if client is not None:
        fetcher = client
        if client.cache_dir:
            _log(f"[wiki] cache: {client.cache_dir}")
    targets = _as_targets(registry_items)
    matching = cfg.get("matching", {}) or {}
    if area_resolver is None:
        area_resolver = _default_area_resolver()
    overrides_file = matching.get("overrides_file")
    overrides = load_overrides((REPO_ROOT / overrides_file) if overrides_file else None)
    matcher = _Matcher(cfg, fetcher, area_resolver, retrieved_at, chunk_size, sleeper)

    # Vòng chính: mỗi record một danh sách ứng viên; override nhiều tiêu đề -> mỗi tiêu đề một "thành phần".
    main_targets, main_cands, owners, part_of = [], [], [], []
    tried: dict[int, list[str]] = {}
    for index, target in enumerate(targets):
        cands, override = build_candidates(target, matching, area_resolver, overrides)
        titles = (override or {}).get("titles") or []
        if override and len(titles) > 1:
            for title in titles:
                main_targets.append(target); main_cands.append([Candidate(title, "manual_override", False)])
                owners.append(index); part_of.append(title)
        else:
            main_targets.append(target); main_cands.append(cands); owners.append(index); part_of.append(None)
        tried.setdefault(index, []).extend(c.title for c in cands)
    results = matcher.match(main_targets, main_cands)

    matches: dict[int, list[_Match]] = {}
    reasons: dict[int, str] = {}
    for target_index, part, (match, reason, _), cands in zip(owners, part_of, results, main_cands):
        if match is not None:
            match.part_label = part
            matches.setdefault(target_index, []).append(match)
        else:
            reasons[target_index] = reason if not part else f"override title {part!r}: {reason}"

    # Tách di tích gộp cho record di tích chưa khớp (không áp cho record có override).
    sub_targets, sub_cands, sub_owner, sub_labels = [], [], [], []
    for index, target in enumerate(targets):
        if index in matches or build_candidates(target, matching, area_resolver, overrides)[1]:
            continue
        for label in component_labels(target, matching, area_resolver):
            sub = RegistryTarget(label_vi=label, registry_id=target.registry_id,
                                 registry_category=target.registry_category, location=target.location)
            cands = [Candidate(c.title, f"component:{c.method}", True) for c in build_candidates(sub, matching, area_resolver)[0]]
            sub_targets.append(sub); sub_cands.append(cands); sub_owner.append(index); sub_labels.append(label)
            tried[index].extend(c.title for c in cands)
    if sub_targets:
        for owner, label, (match, reason, _) in zip(sub_owner, sub_labels, matcher.match(sub_targets, sub_cands, component=True)):
            if match is not None:
                match.part_label = label
                matches.setdefault(owner, []).append(match)
            elif owner not in matches:
                reasons[owner] = f"components: {reason}"

    links: list[tuple[RegistryTarget, _Match]] = []
    failures: list[dict[str, Any]] = []
    for index, target in enumerate(targets):
        found = matches.get(index, [])
        unique: dict[int, _Match] = {}
        for match in found:
            unique.setdefault(match.page.page_id, match)
        found = list(unique.values())
        if len(found) == 1 and found[0].method.startswith("component:"):
            found[0].part_label = None  # chỉ 1 thành phần có bài -> dùng bài đó cho cả record
        for match in found:
            links.append((target, match))
        if not found:
            failures.append({
                "registry_id": target.registry_id, "label_vi": target.label_vi, "error_code": "ENRICHMENT_MISSING",
                "reason": reasons.get(index, "no page found for any candidate title"),
                "titles_tried": list(dict.fromkeys(tried.get(index, []))),
            })
    pages, shared_failures = _assemble_pages(links, matching, area_resolver)
    failures += shared_failures
    relation_stats = {"candidates": 0, "verified": 0}
    if resolve_relations:
        relation_stats = resolve_relation_candidates(pages, cfg, fetcher, chunk_size, sleeper)
    pages_path, failures_path = _write_outputs(pages, failures, output_dir)
    matched_ids = {link["registry_id"] for page in pages for link in page.registry_links}
    return {
        "matched": len(pages),
        "matched_registry_records": len(matched_ids) if any(t.registry_id for t in targets) else len(targets) - len(failures),
        "split_registry_records": sum(1 for index in matches if len({m.part_label for m in matches[index] if m.part_label}) > 1),
        "missing": len(failures),
        "total": len(targets),
        "wikidata_linked": sum(1 for page in pages if page.wikidata_id),
        "relation_candidates": relation_stats["candidates"],
        "relation_verified": relation_stats["verified"],
        "api_calls": matcher.calls,
        **(client.summary() if client is not None else {}),
        "pages_path": str(pages_path),
        "failures_path": str(failures_path),
    }


def enrich(
    registry_labels: list[Any],
    config_path: Path = CONFIG_PATH,
    fetcher=fetch_query,
    output_dir: Path = RAW_DIR,
) -> dict[str, Any]:
    """Một lô duy nhất (tương thích API cũ)."""
    return enrich_many(registry_labels, config_path=config_path, fetcher=fetcher, output_dir=output_dir,
                       chunk_size=max(1, len(registry_labels) * 4), resolve_relations=False)
