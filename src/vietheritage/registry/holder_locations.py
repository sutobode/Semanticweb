"""Tỉnh của nơi lưu giữ (bảo tàng, di tích, cơ quan lưu trữ) — M2-31, DEC-M2-006.

Cột địa điểm của ``national_treasures`` (và ``documentary_heritage``) là NƠI LƯU GIỮ, không phải
địa chỉ hành chính. Mapper vẫn giữ nguyên chuỗi ở ``current_holder``/``custodian``, đồng thời suy ra
``relations.located_in`` theo vị trí của nơi lưu giữ (``mapping.yaml > registry_field_roles``:
role ``holder_located_in``).

Thứ tự xác định (deterministic, không fuzzy — DEC-007):

1. ``registry_text`` — tên tỉnh có ngay trong chuỗi ("Bảo tàng tỉnh Bắc Ninh", "Bảo tàng Lịch sử
   thành phố Hồ Chí Minh", "Chùa Bút Tháp, …, tỉnh Bắc Ninh") qua ``config/areas.yaml``.
   Riêng "Hồ Chí Minh" chỉ được hiểu là thành phố khi đứng sau "thành phố"/"TP" — "Bảo tàng
   Hồ Chí Minh" là tên người (bảo tàng ở Hà Nội), không phải TP.HCM.
2. ``wikipedia`` — bài Wikipedia về nơi lưu giữ (tiêu đề chính xác/redirect -> prefixsearch
   khớp khóa tiêu đề -> search có đủ mọi từ của tên). Tỉnh lấy lần lượt từ infobox (vị trí,
   địa chỉ, …), đoạn mở đầu, thể loại; chỉ nhận khi ra đúng MỘT nhóm tỉnh (sau sáp nhập 2025).
3. ``manual`` — ``config/holder_locations.yaml`` (đã kiểm tra tay), dùng khi 1–2 không ra. Nếu
   Wikipedia ra tỉnh khác với bản tay -> dùng bản tay và ghi ``conflict`` để review.

Kết quả: ``data/raw/holder_locations.jsonl`` (mỗi nơi lưu giữ một dòng, kèm bằng chứng).
Mapper chỉ đọc file này trong stage ``map`` (không gọi mạng).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"
HOLDER_FILE = "holder_locations.jsonl"
MANUAL_CONFIG_PATH = REPO_ROOT / "config" / "holder_locations.yaml"
MAPPING_PATH = REPO_ROOT / "config" / "mapping.yaml"
COLLECTOR_CONFIG_PATH = REPO_ROOT / "config" / "collector.yaml"
HOLDER_ROLE = "holder_located_in"

_HCM_RE = re.compile(r"hồ\s+chí\s+minh", re.IGNORECASE)
_CITY_BEFORE_RE = re.compile(r"(?:thành\s+phố|tp\.?|t\.p\.?)\s*$", re.IGNORECASE)
_INFOBOX_LOCATION_RE = re.compile(
    r"(?:^|_)(?:vị_trí|địa_chỉ|địa_điểm|nơi_đặt|trụ_sở|thành_phố|tỉnh|quốc_gia_vị_trí|location|address|city|"
    r"headquarters|vị_trí_bản_đồ)(?:$|_|\d)")


def holder_key(text: str) -> str:
    from vietheritage.normalization.areas import match_key

    return match_key(text or "")


def guard_person_names(text: str) -> str:
    """Bỏ "Hồ Chí Minh" là tên người (không đứng sau "thành phố"/"TP") trước khi tìm tỉnh."""
    def replace(match: re.Match[str]) -> str:
        before = text[max(0, match.start() - 14):match.start()]
        return match.group(0) if _CITY_BEFORE_RE.search(before) else " … "
    return _HCM_RE.sub(replace, text or "")


def text_areas(text: str | None, resolver) -> list:
    """Tỉnh CŨ (AreaDef) nhắc trong chuỗi, sau khi bỏ tên người trùng tên tỉnh."""
    if not text:
        return []
    return resolver.resolve(guard_person_names(text)).areas


def _groups(areas: list) -> list[str]:
    return list(dict.fromkeys(area.group for area in areas))


def holder_areas(value: str | None, resolver, holder_index: dict[str, list[str]] | None = None) -> tuple[list, str]:
    """-> (AreaDef cũ, method). Ưu tiên ``holder_index`` (holder_locations.jsonl), sau đó text."""
    if not value:
        return [], "empty"
    if holder_index:
        labels = holder_index.get(holder_key(value))
        if labels is not None:
            by_label = {area.label: area for area in resolver.areas}
            return [by_label[label] for label in labels if label in by_label], "holder_index"
    areas = text_areas(value, resolver)
    return areas, ("registry_text" if areas else "unresolved")


def load_holder_index(path: Path | None = None) -> dict[str, list[str]]:
    path = path or (RAW_DIR / HOLDER_FILE)
    index: dict[str, list[str]] = {}
    if not path.exists():
        return index
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("area_labels"):
                index[row["holder_key"]] = list(row["area_labels"])
    return index


def holder_categories(mapping: dict[str, Any]) -> dict[str, list[str]]:
    """{category: [cột registry có role holder_located_in]} theo mapping.yaml."""
    out: dict[str, list[str]] = {}
    for category, roles in (mapping.get("registry_field_roles") or {}).items():
        for column, targets in (roles or {}).items():
            if HOLDER_ROLE in (targets or []):
                out.setdefault(category, []).append(column)
    return out


def collect_holders(records: list[dict[str, Any]], mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Nơi lưu giữ khác nhau (theo holder_key) -> {holder, categories, count}."""
    columns = holder_categories(mapping)
    holders: dict[str, dict[str, Any]] = {}
    for record in records:
        for column in columns.get(record.get("registry_category"), []):
            value = (record.get("registry_fields") or {}).get(column)
            if not value:
                continue
            key = holder_key(value)
            entry = holders.setdefault(key, {"holder": value, "categories": set(), "count": 0})
            entry["categories"].add(record["registry_category"])
            entry["count"] += 1
    return holders


def load_manual(path: Path = MANUAL_CONFIG_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {holder_key(item["holder"]): item for item in data.get("holders") or []}


# ---------------------------------------------------------------------------
# Wikipedia lookup
# ---------------------------------------------------------------------------

def title_candidates(holder: str) -> list[str]:
    """"Trung tâm Lưu trữ quốc gia III, Cục Văn thư …" -> [đầy đủ, "Trung tâm Lưu trữ quốc gia III", …]."""
    base = re.sub(r"\s+", " ", holder).strip()
    forms = [base]
    first = re.split(r"\s*[,;(]\s*", base)[0]
    forms.append(first)
    forms.append(re.split(r"\s+(?:thuộc|do)\s+", first, flags=re.IGNORECASE)[0])
    out: list[str] = []
    for form in forms:
        form = form.strip(" ,.;")
        if not form:
            continue
        for variant in (form, form.replace(" - ", " – "), form.replace(" – ", " - ")):
            if variant not in out:
                out.append(variant)
    return out


def _title_key(title: str) -> str:
    from vietheritage.collector.wikipedia import title_key

    return title_key(title)


def _query_pages(fetcher, api_url: str, request_cfg: dict[str, Any], titles: list[str]) -> dict[str, Any]:
    from vietheritage.collector.wikipedia import _Lookup, query_with_continuation

    params = {"action": "query", "format": "json", "formatversion": 2, "titles": "|".join(titles), "redirects": 1,
              "prop": "pageprops|revisions|categories|extracts|coordinates", "rvprop": "ids|content",
              "rvslots": "main", "exintro": 1, "explaintext": 1, "exlimit": "max", "cllimit": "max"}
    return _Lookup(query_with_continuation(fetcher, api_url, params, request_cfg))


def _prefix_titles(fetcher, api_url: str, request_cfg: dict[str, Any], form: str) -> list[str]:
    params = {"action": "query", "format": "json", "formatversion": 2, "list": "prefixsearch",
              "pssearch": form, "pslimit": 10}
    response = fetcher(api_url, params, request_cfg) or {}
    rows = (response.get("query") or {}).get("prefixsearch") or []
    key = _title_key(form)
    return [row["title"] for row in rows
            if _title_key(row.get("title", "")) == key or _title_key(row.get("title", "")).startswith(key + " (")]


def _search_titles(fetcher, api_url: str, request_cfg: dict[str, Any], form: str) -> list[str]:
    params = {"action": "query", "format": "json", "formatversion": 2, "list": "search",
              "srsearch": form, "srlimit": 5, "srnamespace": 0}
    response = fetcher(api_url, params, request_cfg) or {}
    rows = (response.get("query") or {}).get("search") or []
    words = [w for w in re.split(r"[\s\-–,]+", form.casefold()) if w]
    out = []
    for row in rows:
        title = row.get("title", "")
        tokens = set(re.split(r"[\s\-–,()]+", title.casefold()))
        if words and all(word in tokens for word in words):
            out.append(title)
    return out[:1]


def _clean_wikitext(value: str) -> str:
    from vietheritage.registry.wikipedia_lists import clean_wikitext

    return clean_wikitext(value)


def province_from_page(page, resolver) -> tuple[list, str | None, str | None]:
    """-> (AreaDef cũ của MỘT nhóm tỉnh, nguồn bằng chứng, đoạn text bằng chứng) hoặc ([], lý do, None)."""
    evidence_sources: list[tuple[str, str]] = []
    for key, value in (page.infobox or {}).items():
        if _INFOBOX_LOCATION_RE.search(key):
            text = _clean_wikitext(str(value))
            if text:
                evidence_sources.append((f"infobox:{key}", text))
    if page.abstract:
        sentences = re.split(r"(?<=[.!?])\s+", page.abstract.strip())
        evidence_sources.append(("abstract", " ".join(sentences[:3])))
    if page.categories:
        evidence_sources.append(("categories", " ; ".join(c.split(":", 1)[-1] for c in page.categories)))
    ambiguous = None
    for origin, text in evidence_sources:
        areas = text_areas(text, resolver)
        groups = _groups(areas)
        if len(groups) == 1:
            return areas, origin, text[:300]
        if len(groups) > 1 and ambiguous is None:
            ambiguous = f"ambiguous:{origin}:{'/'.join(groups)}"
    return [], ambiguous or "no_province_in_page", None


def lookup_wikipedia(holder: str, fetcher, api_url: str, request_cfg: dict[str, Any], retrieved_at: str):
    """-> (WikipediaPage | None, method, titles_tried)."""
    from vietheritage.collector.wikipedia import page_from_api_response

    forms = title_candidates(holder)
    tried: list[str] = []
    for step, finder in (("exact", None), ("prefixsearch", _prefix_titles), ("search", _search_titles)):
        titles: list[str] = []
        if finder is None:
            titles = forms
        else:
            for form in forms:
                titles.extend(finder(fetcher, api_url, request_cfg, form))
        titles = [t for t in dict.fromkeys(titles) if t]
        if not titles:
            continue
        tried.extend(titles)
        lookup = _query_pages(fetcher, api_url, request_cfg, titles)
        for title in titles:
            page_json, how = lookup.find(title)
            if not page_json:
                continue
            page = page_from_api_response(page_json, retrieved_at, requested_title=title)
            if page is None or page.is_disambiguation:
                continue
            return page, f"{step}:{how}", tried
    return None, "no_page", tried


def resolve_holders(
    holders: dict[str, dict[str, Any]], resolver, fetcher=None, api_url: str | None = None,
    request_cfg: dict[str, Any] | None = None, manual: dict[str, dict[str, Any]] | None = None,
    retrieved_at: str | None = None, use_wikipedia: bool = True,
) -> list[dict[str, Any]]:
    retrieved_at = retrieved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manual = manual or {}
    by_label = {area.label: area for area in resolver.areas}
    rows: list[dict[str, Any]] = []
    for key in sorted(holders):
        info = holders[key]
        holder = info["holder"]
        row: dict[str, Any] = {"holder": holder, "holder_key": key, "categories": sorted(info["categories"]),
                               "records": info["count"], "retrieved_at": retrieved_at}
        areas = text_areas(holder, resolver)
        method, evidence = "registry_text", holder
        if not areas and use_wikipedia and fetcher is not None:
            try:
                page, how, tried = lookup_wikipedia(holder, fetcher, api_url, request_cfg or {}, retrieved_at)
            except RuntimeError as exc:  # EnrichmentMissingError sau khi hết retry: không chặn, để bảng tay xử lý
                page, how, tried = None, "error", []
                row["wikipedia_error"] = str(exc)[:300]
            row["wikipedia_titles_tried"] = tried
            if page is not None:
                row.update(wikipedia_title=page.title, wikipedia_page_id=page.page_id, wikipedia_url=page.source_url,
                           wikipedia_lookup=how)
                areas, origin, evidence = province_from_page(page, resolver)
                method = f"wikipedia:{origin}" if areas else "unresolved"
                if not areas:
                    row["wikipedia_reason"] = origin
            else:
                method = "unresolved"
        elif not areas:
            method = "unresolved"
        entry = manual.get(key)
        if entry is not None:
            manual_area = by_label.get(entry["area"])
            if manual_area is None:
                raise ValueError(f"CONFIG_INVALID: holder_locations.yaml area {entry['area']!r} không có trong areas.yaml")
            if not areas:
                areas, method, evidence = [manual_area], "manual", entry.get("note")
            elif _groups(areas) != [manual_area.group]:
                row["conflict"] = {"found": [a.label for a in areas], "found_method": method, "manual": entry["area"]}
                areas, method, evidence = [manual_area], "manual_conflict", entry.get("note")
        row.update(area_labels=[a.label for a in areas], area_groups=_groups(areas), method=method,
                   evidence=evidence)
        rows.append(row)
    return rows


def run_holder_locations(raw_dir: Path = RAW_DIR, fetcher=None, use_wikipedia: bool = True,
                         mapping_path: Path = MAPPING_PATH, manual_path: Path = MANUAL_CONFIG_PATH,
                         collector_config_path: Path = COLLECTOR_CONFIG_PATH) -> dict[str, Any]:
    """Đọc registry_records.jsonl -> ghi holder_locations.jsonl. Trả tóm tắt."""
    from vietheritage.collector.wikipedia import ApiClient, load_config as load_collector_config
    from vietheritage.normalization.areas import default_resolver

    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    records = [json.loads(line) for line in (raw_dir / "registry_records.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    holders = collect_holders(records, mapping)
    collector_cfg = load_collector_config(collector_config_path)
    client = None
    if use_wikipedia and fetcher is None:
        client = ApiClient.from_config(collector_cfg)
        fetcher = client
    rows = resolve_holders(holders, default_resolver(), fetcher, collector_cfg.get("api_url"),
                           collector_cfg.get("request", {}) or {}, load_manual(manual_path),
                           use_wikipedia=use_wikipedia)
    with (raw_dir / HOLDER_FILE).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    methods: dict[str, int] = {}
    for row in rows:
        family = row["method"].split(":")[0]
        methods[family] = methods.get(family, 0) + 1
    summary = {
        "holders": len(rows),
        "resolved": sum(1 for r in rows if r["area_labels"]),
        "records_covered": sum(r["records"] for r in rows if r["area_labels"]),
        "records_total": sum(r["records"] for r in rows),
        "methods": methods,
        "unresolved": [r["holder"] for r in rows if not r["area_labels"]],
        "conflicts": [r for r in rows if r.get("conflict")],
        **({"http": client.summary()} if client is not None else {}),
    }
    return summary
