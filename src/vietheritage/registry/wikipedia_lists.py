"""Nguồn bổ sung dạng danh sách trên Wikipedia tiếng Việt (M2-30, DEC-M2-005).

Một số category trong coverage universe (DEC-M2-001) có trang chính thức dsvh.gov.vn rỗng.
Khi nhóm quyết định lấy dữ liệu từ một trang danh sách Wikipedia (``wikipedia_list_sources``
trong ``config/registry_sources.yaml``), module này:

1. tải HTML đã render của trang (``action=parse``), chỉ đọc các section khớp
   ``section_patterns`` (ví dụ section "Việt Nam" của trang "Di sản tư liệu thế giới");
2. đọc bảng (có xử lý rowspan/colspan) và danh sách ``<ul>/<ol>`` trong section, ghi nhận
   tiêu đề section cha làm ngữ cảnh (cấp Thế giới / Khu vực Châu Á - Thái Bình Dương …);
3. **chỉ giữ mục đã được công nhận**: mục khớp ``not_recognized_patterns`` (đề cử, ứng cử …)
   hoặc không có năm công nhận hợp lệ (<= năm hiện tại) bị loại và ghi vào
   ``data/raw/wikipedia_list_excluded.jsonl``;
4. gộp mục trùng (cùng tên hoặc cùng bài Wikipedia, ví dụ một tư liệu được ghi danh cả cấp
   khu vực lẫn thế giới) thành MỘT record registry;
5. tải bài Wikipedia của từng mục (link trong ô tên, hoặc ``item_overrides`` cho mục không có
   link, ví dụ bộ sưu tập của nhạc sĩ Hoàng Vân -> bài "Hoàng Vân (nhạc sĩ)") và ghi page vào
   ``data/raw/pages.jsonl`` theo ``registry_ids`` như enrichment thông thường.

Record sinh ra có cùng schema raw với record registry dạng bảng, ``registry_fields.source =
"wikipedia_list:<key>"``. ``registry_url`` là URL trang danh sách Wikipedia (không giả là
dsvh.gov.vn); mapper ghi provenance ``mediawiki-api`` + CC BY-SA 4.0 cho các record này.

Page có ``page_role: related_subject`` (bài về người/tổ chức liên quan, không phải bài về
chính di sản) chỉ được dùng làm nguồn provenance: mapper KHÔNG lấy QID/tọa độ/mô tả/alias từ
page đó, nên không sinh ``owl:sameAs`` sai.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from parsel import Selector

from vietheritage.normalization.normalizer import canonical_identity_key, iri_to_uri, normalize_nfc, normalize_text

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_CONFIG_PATH = REPO_ROOT / "config" / "registry_sources.yaml"
COLLECTOR_CONFIG_PATH = REPO_ROOT / "config" / "collector.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"

SOURCE_PREFIX = "wikipedia_list:"
REPORT_FILE = "wikipedia_list_report.json"
EXCLUDED_FILE = "wikipedia_list_excluded.jsonl"
WIKI_BASE = "https://vi.wikipedia.org/wiki/"
RELATED_SUBJECT = "related_subject"

_SKIP_CLASSES = ("navbox", "metadata", "ambox", "infobox", "reflist", "references", "toc", "gallery",
                 "mw-references-wrap", "sidebar", "thumb", "hatnote", "vertical-navbox", "noprint")
_YEAR_RE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_FOOTNOTE_RE = re.compile(r"\[(?:\d{1,3}|[a-zA-Z]|cần dẫn nguồn|cần nguồn|chú thích[^\]]*|note \d+)\]")
_NON_ARTICLE_NAMESPACES = {"tập tin", "file", "hình", "image", "thể loại", "category", "wikipedia", "bản mẫu",
                           "template", "đặc biệt", "special", "trợ giúp", "help", "chủ đề", "portal", "thảo luận"}
_LABEL_SPLIT_RE = re.compile(r"\s*(?:\(|–|—|:|\s-\s|,\s*(?:năm|được|ghi danh|công nhận))")


class WikipediaListError(RuntimeError):
    """WIKIPEDIA_LIST_ERROR — không tải/parse được trang danh sách hoặc không thấy section."""


@dataclass
class WikiListSource:
    key: str
    registry_category: str
    page_title: str
    section_patterns: list[str]
    recognized_only: bool = True
    not_recognized_patterns: list[str] = field(default_factory=list)
    level_patterns: dict[str, str] = field(default_factory=dict)
    level_priority: list[str] = field(default_factory=list)
    item_overrides: list[dict[str, Any]] = field(default_factory=list)
    row_overrides: list[dict[str, Any]] = field(default_factory=list)
    location_infobox_pattern: str | None = None
    reference_labels: list[str] = field(default_factory=list)
    min_items: int = 1
    enabled: bool = True


def load_wikipedia_list_sources(config: dict[str, Any] | None = None,
                                config_path: Path = REGISTRY_CONFIG_PATH) -> list[WikiListSource]:
    raw = config if config is not None else (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
    sources = []
    for item in raw.get("wikipedia_list_sources") or []:
        sources.append(WikiListSource(
            key=item["key"], registry_category=item["registry_category"], page_title=item["page_title"],
            section_patterns=list(item.get("section_patterns") or []),
            recognized_only=bool(item.get("recognized_only", True)),
            not_recognized_patterns=list(item.get("not_recognized_patterns") or []),
            level_patterns=dict(item.get("level_patterns") or {}),
            level_priority=list(item.get("level_priority") or []),
            item_overrides=list(item.get("item_overrides") or []),
            row_overrides=list(item.get("row_overrides") or []),
            location_infobox_pattern=item.get("location_infobox_pattern"),
            reference_labels=list(item.get("reference_labels") or []),
            min_items=int(item.get("min_items", 1)),
            enabled=bool(item.get("enabled", True)),
        ))
    return sources


def wiki_url(title: str) -> str:
    return iri_to_uri(WIKI_BASE + normalize_nfc(title).replace(" ", "_"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def clean_text(value: str | None) -> str:
    text = normalize_nfc((value or "").replace("\xa0", " "))
    text = _FOOTNOTE_RE.sub("", text)
    return normalize_text(text)


def _prepare_html(html: str) -> str:
    """Bỏ chú thích, nút sửa, style/script trước khi đọc text."""
    html = re.sub(r"<sup[^>]*class=\"[^\"]*reference[^\"]*\"[^>]*>.*?</sup>", "", html, flags=re.S | re.I)
    html = re.sub(r"<span[^>]*class=\"[^\"]*mw-editsection[^\"]*\"[^>]*>.*?</span>\s*</span>|"
                  r"<span[^>]*class=\"[^\"]*mw-editsection[^\"]*\"[^>]*>.*?</span>", "", html, flags=re.S | re.I)
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    return html


def _has_skip_class(node: Selector) -> bool:
    tokens = set(" ".join(node.xpath("ancestor-or-self::*/@class").getall()).lower().split())
    return any(name in tokens for name in _SKIP_CLASSES)


def link_title(anchor: Selector) -> str | None:
    """Tiêu đề bài từ ``<a>`` nội bộ; bỏ link đỏ (class new), file, thể loại, chú thích, neo."""
    href = anchor.attrib.get("href") or ""
    classes = (anchor.attrib.get("class") or "").split()
    if "new" in classes or not href.startswith("/wiki/"):
        return None
    title = unquote(href[len("/wiki/"):].split("#", 1)[0]).replace("_", " ") or anchor.attrib.get("title") or ""
    title = normalize_nfc(title).strip()
    if not title:
        return None
    namespace = title.split(":", 1)[0].casefold() if ":" in title else ""
    if namespace in _NON_ARTICLE_NAMESPACES:
        return None
    return title


def _cell_links(cell: Selector) -> list[tuple[str, str]]:
    """[(title, anchor text)] của các link bài viết trong một ô/mục."""
    out = []
    for anchor in cell.css("a"):
        title = link_title(anchor)
        if title:
            out.append((title, clean_text(anchor.xpath("string(.)").get())))
    return out


def expand_table(table: Selector) -> list[list[dict[str, Any]]]:
    """Bảng -> lưới ô (rowspan/colspan đã nhân bản). Mỗi ô: text, is_header, links."""
    grid: list[list[dict[str, Any]]] = []
    pending: dict[int, tuple[int, dict[str, Any]]] = {}
    rows = table.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr")
    for row in rows:
        cells_out: list[dict[str, Any]] = []
        col = 0
        cells = row.xpath("./td|./th")
        index = 0
        while index < len(cells) or col in pending:
            if col in pending:
                left, cell = pending[col]
                cells_out.append(cell)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (left - 1, cell)
                col += 1
                continue
            node = cells[index]
            index += 1
            cell = {
                "text": clean_text(node.xpath("string(.)").get()),
                "is_header": node.root.tag == "th",
                "links": _cell_links(node),
            }
            try:
                rowspan = max(1, int(node.attrib.get("rowspan", "1")))
            except ValueError:
                rowspan = 1
            try:
                colspan = max(1, min(20, int(node.attrib.get("colspan", "1"))))
            except ValueError:
                colspan = 1
            for _ in range(colspan):
                cells_out.append(cell)
                if rowspan > 1:
                    pending[col] = (rowspan - 1, cell)
                col += 1
        if cells_out:
            grid.append(cells_out)
    return grid


_COLUMN_ROLES = (
    ("year", r"năm|thời gian|year"),
    ("location", r"lưu giữ|lưu trữ|nơi|địa điểm|địa phương|tỉnh|cơ quan|quản lý|location"),
    ("level", r"cấp|danh sách|chương trình|phạm vi|loại|register"),
    ("status", r"ghi chú|tình trạng|trạng thái|kết quả"),
    ("country", r"quốc gia|nước|country"),
    ("name", r"tên|di sản|tư liệu|hồ sơ|name"),
    ("ordinal", r"^(?:stt|tt|#|số thứ tự)$"),
)


def column_roles(header: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for index, text in enumerate(header):
        key = text.casefold().strip()
        for role, pattern in _COLUMN_ROLES:
            if role not in roles and re.search(pattern, key):
                roles[role] = index
                break
    return roles


@dataclass
class ListItem:
    label: str
    row_text: str
    context: str
    years: list[int]
    link_title: str | None = None
    level_text: str = ""
    location: str | None = None
    origin: str = ""
    recognitions: list[tuple[int, str | None]] | None = None   # đặt bởi row_overrides


def _split_label(text: str) -> str:
    """"Mộc bản triều Nguyễn (2009)" -> "Mộc bản triều Nguyễn"; bỏ phần sau dấu ngăn có năm."""
    matches = list(_LABEL_SPLIT_RE.finditer(text))
    for i, match in enumerate(matches):
        separator = match.group(0).strip()
        if separator == "(":
            close = text.find(")", match.end())
            segment = text[match.end(): close if close >= 0 else len(text)]
        else:
            segment = text[match.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        # Cắt khi phần ngay sau dấu ngăn có năm ("… (2009)", "… – 2011") hoặc là phần mô tả sau ":".
        if _YEAR_RE.search(segment) or separator == ":":
            candidate = text[:match.start()].strip(" ,;.-–—")
            if candidate:
                return candidate
    return _YEAR_RE.sub("", text).strip(" ,;.-–—()")


# Chương trình Ký ức Thế giới (UNESCO) bắt đầu năm 1992: năm nhỏ hơn không phải năm công nhận.
MIN_RECOGNITION_YEAR = 1992
_LIFESPAN_RE = re.compile(r"\(\s*(?:sinh\s+)?\d{4}\s*[-–—]\s*\d{4}\s*\)")


def _years(text: str) -> list[int]:
    """Năm có thể là năm công nhận; bỏ khoảng năm sinh–mất "(1930 – 2018)" trong tên người."""
    current = datetime.now(timezone.utc).year
    text = _LIFESPAN_RE.sub(" ", text or "")
    return [int(y) for y in _YEAR_RE.findall(text) if MIN_RECOGNITION_YEAR <= int(y) <= current + 5]


def _table_items(table: Selector, context: str) -> list[ListItem]:
    grid = expand_table(table)
    if not grid:
        return []
    header_index = next((i for i, row in enumerate(grid) if all(c["is_header"] for c in row)), None)
    roles = column_roles([c["text"] for c in grid[header_index]]) if header_index is not None else {}
    items: list[ListItem] = []
    sub_context = ""
    for i, row in enumerate(grid):
        if header_index is not None and i <= header_index:
            continue
        texts = [c["text"] for c in row]
        if not any(texts):
            continue
        if all(c["is_header"] for c in row) or len({id(c) for c in row}) == 1 and len(row) > 1:
            sub_context = " ".join(dict.fromkeys(t for t in texts if t))  # dòng tiêu đề con trong bảng
            continue
        name_idx = roles.get("name")
        if name_idx is None or name_idx >= len(row):
            # Không có header rõ: ô đầu tiên có link bài viết và không chỉ là năm/số.
            name_idx = next((j for j, c in enumerate(row) if c["links"] and not re.fullmatch(r"[\d\s.,–-]*", c["text"])),
                            None)
            if name_idx is None:
                name_idx = max(range(len(row)), key=lambda j: len(row[j]["text"]) if not _YEAR_RE.fullmatch(row[j]["text"]) else -1)
        name_cell = row[name_idx]
        label = _split_label(name_cell["text"])
        if not label or re.fullmatch(r"[\d\s.,–-]*", label):
            continue
        year_text = row[roles["year"]]["text"] if "year" in roles and roles["year"] < len(row) else " ".join(texts)
        level = row[roles["level"]]["text"] if "level" in roles and roles["level"] < len(row) else ""
        location = row[roles["location"]]["text"] if "location" in roles and roles["location"] < len(row) else None
        link = next((title for title, _ in name_cell["links"]), None)
        items.append(ListItem(
            label=label, row_text=" | ".join(texts), context=" / ".join(x for x in (context, sub_context) if x),
            years=_years(year_text) or _years(" ".join(texts)), link_title=link, level_text=level,
            location=location or None, origin="table",
        ))
    return items


def _li_text(li: Selector) -> str:
    parts = li.xpath("./node()[not(self::ul or self::ol or self::dl)]")
    texts = [(p.get() if isinstance(p.root, str) else p.xpath("string(.)").get()) or "" for p in parts]
    return clean_text("".join(texts))


def _list_items(lst: Selector, context: str) -> list[ListItem]:
    items = []
    for li in lst.xpath("./li"):
        text = _li_text(li)
        if not text:
            continue
        label = _split_label(text)
        links = []
        for anchor in li.xpath("./node()[not(self::ul or self::ol or self::dl)]/descendant-or-self::a"):
            title = link_title(anchor)
            if title:
                links.append((title, clean_text(anchor.xpath("string(.)").get())))
        # Link của mục = link có anchor text nằm trong nhãn (không lấy link tới địa danh/năm trong phần mô tả).
        if re.match(r"^(?:năm|ngày|tháng|\d)", label.casefold()):
            # "Năm 2009, Mộc bản triều Nguyễn được …" -> dùng anchor text dài (>= 2 từ) làm nhãn.
            anchor = next((text_ for _, text_ in links if len(text_.split()) >= 2), None)
            if anchor:
                label = anchor
        label_key = label.casefold()
        link = next((title for title, anchor_text in links
                     if anchor_text and anchor_text.casefold() in label_key and len(anchor_text) >= 0.5 * len(label)), None)
        if not label or (not links and not _years(text)):
            continue
        items.append(ListItem(label=label, row_text=text, context=context, years=_years(text),
                              link_title=link, origin="list"))
    return items


def extract_items(html: str) -> list[ListItem]:
    """HTML (một hoặc nhiều section) -> các mục bảng/danh sách theo thứ tự, kèm tiêu đề section cha."""
    selector = Selector(text=_prepare_html(html))
    heading_stack: dict[int, str] = {}
    items: list[ListItem] = []
    nodes = selector.xpath("//*[self::h2 or self::h3 or self::h4 or self::h5 or self::h6 or self::table "
                           "or self::ul or self::ol]")
    for node in nodes:
        tag = node.root.tag
        if tag in {"h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            heading_stack = {k: v for k, v in heading_stack.items() if k < level}
            heading_stack[level] = clean_text(node.xpath("string(.)").get())
            continue
        if _has_skip_class(node):
            continue
        if node.xpath("ancestor::table") or node.xpath("ancestor::li"):
            continue
        context = " / ".join(heading_stack[k] for k in sorted(heading_stack))
        if tag == "table":
            items.extend(_table_items(node, context))
        else:
            items.extend(_list_items(node, context))
    return items


# ---------------------------------------------------------------------------
# Recognition filter + dedupe
# ---------------------------------------------------------------------------

def classify_level(text: str, level_patterns: dict[str, str]) -> str | None:
    for name, pattern in level_patterns.items():
        if re.search(pattern, text or "", re.IGNORECASE):
            return name
    return None


def recognition_status(item: ListItem, source: WikiListSource) -> str | None:
    """None nếu mục đã được công nhận; ngược lại mã lý do loại."""
    blob = f"{item.context} || {item.row_text}"
    for pattern in source.not_recognized_patterns:
        if re.search(pattern, blob, re.IGNORECASE):
            return "NOT_RECOGNIZED"
    current = datetime.now(timezone.utc).year
    valid = [y for y in item.years if y <= current]
    if not valid:
        return "FUTURE_YEAR" if item.years else "NO_RECOGNITION_YEAR"
    return None


@dataclass
class MergedItem:
    label: str
    link_title: str | None
    recognitions: list[tuple[int, str | None]]
    location: str | None
    contexts: list[str]
    origins: list[str]


def merge_items(items: list[ListItem], source: WikiListSource) -> list[MergedItem]:
    merged: list[MergedItem] = []
    by_key: dict[str, MergedItem] = {}
    for item in items:
        keys = [f"label:{canonical_identity_key(item.label)}"]
        if item.link_title:
            keys.append(f"link:{canonical_identity_key(item.link_title)}")
        target = next((by_key[k] for k in keys if k in by_key), None)
        level = classify_level(item.level_text, source.level_patterns) or classify_level(item.context, source.level_patterns)
        valid_years = [y for y in item.years if y <= datetime.now(timezone.utc).year]
        if target is None:
            target = MergedItem(item.label, item.link_title, [], item.location, [], [])
            merged.append(target)
        target.link_title = target.link_title or item.link_title
        target.location = target.location or item.location
        for recognition in (item.recognitions or [(min(valid_years), level)]):
            if recognition not in target.recognitions:
                target.recognitions.append(recognition)
        if item.context and item.context not in target.contexts:
            target.contexts.append(item.context)
        target.origins.append(item.origin)
        for key in keys:
            by_key.setdefault(key, target)
    for entry in merged:
        entry.recognitions.sort(key=lambda r: (r[0], r[1] or ""))
    return merged


def apply_row_overrides(items: list[ListItem], source: WikiListSource) -> list[str]:
    """row_overrides: sửa mục viết dạng câu văn (section cấp thế giới) — khớp regex trên TOÀN BỘ dòng.

    Mỗi override có thể đặt ``label_vi``, ``page_title`` (null = bỏ link sai trên trang),
    ``recognitions`` ([[năm, cấp], …]) và ``location``. Áp TRƯỚC khi lọc/gộp. Trả các pattern đã dùng.
    """
    used: list[str] = []
    for item in items:
        for override in source.row_overrides:
            pattern = override.get("row_pattern")
            if not pattern or not re.search(pattern, item.row_text, re.IGNORECASE):
                continue
            if override.get("label_vi"):
                item.label = override["label_vi"]
            if "page_title" in override:
                item.link_title = override["page_title"] or None
            if override.get("recognitions"):
                item.recognitions = [(int(year), level) for year, level in override["recognitions"]]
                item.years = [year for year, _ in item.recognitions]
            if override.get("location"):
                item.location = override["location"]
            used.append(pattern)
            break
    return used


def apply_overrides(items: list[MergedItem], source: WikiListSource) -> dict[str, dict[str, Any]]:
    """item_overrides: gán bài Wikipedia cho mục (thường là mục không có link). Trả {label: override}."""
    applied: dict[str, dict[str, Any]] = {}
    for item in items:
        for override in source.item_overrides:
            pattern = override.get("label_pattern")
            if pattern and re.search(pattern, item.label, re.IGNORECASE):
                if override.get("page_title"):
                    item.link_title = override["page_title"]
                if override.get("label_vi"):
                    item.label = override["label_vi"]
                applied[item.label] = override
                break
    return applied


def recognition_text(item: MergedItem) -> str:
    return "; ".join(f"{year} ({level})" if level else str(year) for year, level in item.recognitions)


def highest_level(item: MergedItem, source: WikiListSource) -> str | None:
    order = source.level_priority or list(source.level_patterns)
    levels = [level for _, level in item.recognitions if level]
    return min(levels, key=lambda name: order.index(name) if name in order else len(order)) if levels else None


# ---------------------------------------------------------------------------
# MediaWiki
# ---------------------------------------------------------------------------

def _parse(fetcher, api_url: str, request_cfg: dict[str, Any], title: str, section: str | None = None) -> dict[str, Any]:
    params = {"action": "parse", "format": "json", "formatversion": 2, "page": title, "redirects": 1,
              "prop": "text|sections|displaytitle", "disableeditsection": 1, "disabletoc": 1}
    if section is not None:
        params["section"] = section
    response = fetcher(api_url, params, request_cfg) or {}
    if "error" in response:
        raise WikipediaListError(f"parse {title!r} section={section}: {response['error']}")
    return response.get("parse") or {}


def select_sections(sections: list[dict[str, Any]], patterns: list[str]) -> list[dict[str, Any]]:
    """Section khớp pattern; bỏ section con khi section cha đã được chọn (HTML section cha đã gồm con)."""
    chosen: list[dict[str, Any]] = []
    for section in sections:
        line = clean_text(re.sub(r"<[^>]+>", "", section.get("line") or ""))
        if any(re.search(p, line, re.IGNORECASE) for p in patterns):
            number = str(section.get("number") or "")
            if any(number.startswith(str(c.get("number")) + ".") for c in chosen):
                continue
            chosen.append({**section, "line": line})
    return chosen


def collect_list_items(source: WikiListSource, fetcher, api_url: str, request_cfg: dict[str, Any]) -> dict[str, Any]:
    full = _parse(fetcher, api_url, request_cfg, source.page_title)
    if not full:
        raise WikipediaListError(f"{source.key}: trang {source.page_title!r} không tồn tại")
    page_title = full.get("title") or source.page_title
    sections = select_sections(full.get("sections") or [], source.section_patterns)
    html_parts: list[tuple[str, str]] = []
    if sections:
        for section in sections:
            part = _parse(fetcher, api_url, request_cfg, page_title, str(section["index"]))
            text = part.get("text")
            if isinstance(text, dict):
                text = text.get("*", "")
            html_parts.append((section["line"], text or ""))
        mode = "sections"
    else:
        text = full.get("text")
        if isinstance(text, dict):
            text = text.get("*", "")
        html_parts.append(("", text or ""))
        mode = "full_page_country_rows"
    raw_items: list[ListItem] = []
    for _, html in html_parts:
        items = extract_items(html)
        if mode == "full_page_country_rows":
            # Không thấy section quốc gia: chỉ nhận dòng bảng có nhắc quốc gia trong section_patterns.
            items = [i for i in items if i.origin == "table"
                     and any(re.search(p, i.row_text, re.IGNORECASE) for p in source.section_patterns)]
        raw_items.extend(items)
    return {"page_title": page_title, "page_id": full.get("pageid"), "sections": [s["line"] for s in sections],
            "mode": mode, "items": raw_items, "html_parts": html_parts}


def fetch_item_pages(titles: list[str], fetcher, api_url: str, request_cfg: dict[str, Any],
                     query_cfg: dict[str, Any], retrieved_at: str) -> dict[str, Any]:
    """Tiêu đề yêu cầu -> WikipediaPage (theo redirect). Trả {requested_title: page | None}."""
    from vietheritage.collector.wikipedia import (
        _Lookup, build_query_params, page_from_api_response, query_with_continuation,
    )

    result: dict[str, Any] = {}
    titles = list(dict.fromkeys(t for t in titles if t))
    for start in range(0, len(titles), 20):
        chunk = titles[start:start + 20]
        params = build_query_params(chunk, query_cfg)
        params.pop("prop", None)
        params["prop"] = "pageprops|revisions|coordinates|categories|extracts"
        response = query_with_continuation(fetcher, api_url, params, request_cfg)
        lookup = _Lookup(response)
        for title in chunk:
            page_json, method = lookup.find(title)
            page = page_from_api_response(page_json, retrieved_at, requested_title=title) if page_json else None
            if page is not None:
                page.match_method = "wikipedia_list_link" if method == "exact_title" else f"wikipedia_list_link:{method}"
            result[title] = page
    return result


_WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")


def clean_wikitext(value: str) -> str:
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", " ", value or "", flags=re.S | re.I)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"'{2,}", "", text)
    return clean_text(text)


def infobox_location(page, pattern: str | None) -> tuple[str | None, str | None]:
    if not pattern:
        return None, None
    regex = re.compile(pattern)
    for key, value in (page.infobox or {}).items():
        if regex.search(key):
            text = clean_wikitext(str(value))
            if text:
                return text, key
    return None, None


# ---------------------------------------------------------------------------
# Records + IO
# ---------------------------------------------------------------------------

def _registry_id(page_url: str, category: str, label: str) -> str:
    from vietheritage.registry.collector import deterministic_registry_id

    return deterministic_registry_id(None, page_url, category, canonical_identity_key(label))


def build_records(source: WikiListSource, listing: dict[str, Any], snapshot: str, retrieved_at: str,
                  fetcher, api_url: str, request_cfg: dict[str, Any], query_cfg: dict[str, Any]
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """-> (registry records, page dicts, excluded items, report)."""
    row_overrides_used = apply_row_overrides(listing["items"], source)
    accepted: list[ListItem] = []
    excluded: list[dict[str, Any]] = []
    for item in listing["items"]:
        reason = recognition_status(item, source) if source.recognized_only else None
        if reason:
            excluded.append({"source": SOURCE_PREFIX + source.key, "label_vi": item.label, "reason": reason,
                             "context": item.context, "row_text": item.row_text, "snapshot_id": snapshot})
        else:
            accepted.append(item)
    merged = merge_items(accepted, source)
    overrides = apply_overrides(merged, source)
    page_url = wiki_url(listing["page_title"])
    pages = fetch_item_pages([m.link_title for m in merged if m.link_title], fetcher, api_url, request_cfg,
                             query_cfg, retrieved_at)

    records: list[dict[str, Any]] = []
    page_dicts: dict[int, dict[str, Any]] = {}
    missing_pages: list[dict[str, Any]] = []
    for ordinal, item in enumerate(merged, 1):
        override = overrides.get(item.label) or {}
        registry_id = _registry_id(page_url, source.registry_category, item.label)
        fields: dict[str, Any] = {
            "ordinal": str(ordinal),
            "label_vi": item.label,
            "recognition_text": recognition_text(item),
            "source": SOURCE_PREFIX + source.key,
            "list_page_title": listing["page_title"],
            "list_page_id": listing["page_id"],
            "list_section": " | ".join(item.contexts),
        }
        level = highest_level(item, source)
        if level:
            fields["type"] = level
        if item.location:
            fields["location"] = item.location
            fields["location_source"] = "wikipedia_list_row"
        page = pages.get(item.link_title) if item.link_title else None
        role = override.get("page_role")
        if item.link_title and (page is None or page.is_disambiguation):
            missing_pages.append({"label_vi": item.label, "title": item.link_title,
                                  "reason": "disambiguation" if page is not None else "missing"})
            page = None
        if page is not None:
            fields["wiki_title"] = page.title
            if role:
                fields["page_role"] = role
            if role != RELATED_SUBJECT and "location" not in fields:
                location, key = infobox_location(page, source.location_infobox_pattern)
                if location:
                    fields["location"] = location
                    fields["location_source"] = f"wikipedia_infobox:{key}"
            entry = page_dicts.get(page.page_id)
            if entry is None:
                entry = page.to_dict()
                entry["registry_ids"], entry["registry_links"], entry["requested_labels"] = [], [], []
                entry["match_evidence"] = [f"linked from {listing['page_title']}" if not override
                                           else f"item_override for {listing['page_title']}"]
                if override:
                    entry["match_method"] = "manual_override"
                if role:
                    entry["page_role"] = role
                if role == RELATED_SUBJECT:
                    # Bài về người/tổ chức liên quan: không phải định danh của di sản -> không mang QID/tọa độ.
                    entry["subject_wikidata_id"] = entry.pop("wikidata_id", None)
                    entry["wikidata_id"] = None
                    entry["coordinates"] = None
                page_dicts[page.page_id] = entry
            entry["registry_ids"].append(registry_id)
            entry["registry_links"].append({"registry_id": registry_id, "part_label": None})
            entry["requested_labels"].append(item.label)
        records.append({
            "registry_id": registry_id,
            "registry_category": source.registry_category,
            "label_vi": item.label,
            "registry_url": page_url,
            "source_status": "registry_only",
            "coverage_snapshot": snapshot,
            "retrieved_at": retrieved_at,
            "registry_fields": fields,
        })
    ids = [r["registry_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise WikipediaListError(f"{source.key}: registry_id collision")
    found = {canonical_identity_key(r["label_vi"]) for r in records}
    reference = {canonical_identity_key(label): label for label in source.reference_labels}
    report = {
        "key": source.key, "registry_category": source.registry_category, "page_title": listing["page_title"],
        "page_id": listing["page_id"], "page_url": page_url, "mode": listing["mode"], "sections": listing["sections"],
        "items_seen": len(listing["items"]), "items_excluded": len(excluded), "records": len(records),
        "pages": len(page_dicts), "missing_pages": missing_pages,
        "overrides_applied": sorted(overrides),
        "row_overrides_applied": row_overrides_used,
        "row_overrides_unused": [o.get("row_pattern") for o in source.row_overrides
                                 if o.get("row_pattern") not in row_overrides_used],
        "reference_missing": [label for key, label in reference.items() if key not in found],
        "not_in_reference": [r["label_vi"] for r in records if reference and canonical_identity_key(r["label_vi"]) not in reference],
    }
    if len(records) < source.min_items:
        raise WikipediaListError(f"{source.key}: chỉ trích xuất được {len(records)} mục (< min_items={source.min_items}); "
                                 f"mode={listing['mode']} sections={listing['sections']}")
    return records, list(page_dicts.values()), excluded, report


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_wikipedia_list_record(record: dict[str, Any]) -> bool:
    return str((record.get("registry_fields") or {}).get("source") or "").startswith(SOURCE_PREFIX)


def collect_wikipedia_lists(
    raw_dir: Path = RAW_DIR,
    registry_config_path: Path = REGISTRY_CONFIG_PATH,
    collector_config_path: Path = COLLECTOR_CONFIG_PATH,
    fetcher=None,
    snapshot: str | None = None,
    retrieved_at: str | None = None,
    write_pages: bool = True,
    debug_dir: Path | None = None,
) -> dict[str, Any]:
    """Thu thập mọi ``wikipedia_list_sources`` đang bật, GHÉP vào raw hiện có (idempotent).

    * ``registry_records.jsonl``: bỏ record cũ của cùng nguồn rồi thêm record mới.
    * ``pages.jsonl`` (khi ``write_pages``): bỏ page chỉ trỏ tới record cũ của nguồn rồi thêm page mới.
    * ``wikipedia_list_report.json`` / ``wikipedia_list_excluded.jsonl``: báo cáo + mục bị loại.
    ``snapshot`` mặc định là ``coverage_snapshot`` của registry hiện có (giữ một snapshot duy nhất).
    """
    from vietheritage.collector.wikipedia import ApiClient, load_config as load_collector_config

    registry_cfg = yaml.safe_load(registry_config_path.read_text(encoding="utf-8")) or {}
    sources = [s for s in load_wikipedia_list_sources(registry_cfg) if s.enabled]
    collector_cfg = load_collector_config(collector_config_path)
    request_cfg = collector_cfg.get("request", {}) or {}
    api_url = collector_cfg.get("api_url", "https://vi.wikipedia.org/w/api.php")
    query_cfg = collector_cfg.get("query", {}) or {}
    client = None
    if fetcher is None:
        client = ApiClient.from_config(collector_cfg)
        fetcher = client
    records_path = raw_dir / "registry_records.jsonl"
    existing = _read_jsonl(records_path)
    snapshots = sorted({r.get("coverage_snapshot") for r in existing if r.get("coverage_snapshot")})
    snapshot = snapshot or (snapshots[-1] if snapshots else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    retrieved_at = retrieved_at or utc_now_iso()

    tags = {SOURCE_PREFIX + s.key for s in sources}
    removed_ids = {r["registry_id"] for r in existing if (r.get("registry_fields") or {}).get("source") in tags}
    kept = [r for r in existing if r["registry_id"] not in removed_ids]
    new_records: list[dict[str, Any]] = []
    new_pages: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    existing_ids = {r["registry_id"] for r in kept}
    for source in sources:
        listing = collect_list_items(source, fetcher, api_url, request_cfg)
        if debug_dir is not None:
            debug_dir.mkdir(parents=True, exist_ok=True)
            for index, (line, html) in enumerate(listing["html_parts"], 1):
                (debug_dir / f"{source.key}-section{index}.html").write_text(html, encoding="utf-8")
        records, pages, bad, report = build_records(source, listing, snapshot, retrieved_at, fetcher, api_url,
                                                    request_cfg, query_cfg)
        clash = [r["registry_id"] for r in records if r["registry_id"] in existing_ids]
        if clash:
            raise WikipediaListError(f"{source.key}: registry_id trùng record hiện có: {clash[:3]}")
        existing_ids.update(r["registry_id"] for r in records)
        new_records += records
        new_pages += pages
        excluded += bad
        reports.append(report)

    _write_jsonl(records_path, kept + new_records)
    if write_pages:
        pages_path = raw_dir / "pages.jsonl"
        old_pages = _read_jsonl(pages_path)
        kept_pages = []
        for page in old_pages:
            ids = set(page.get("registry_ids") or []) | {l.get("registry_id") for l in page.get("registry_links") or []}
            if ids and ids <= removed_ids:
                continue
            kept_pages.append(page)
        _write_jsonl(pages_path, kept_pages + new_pages)
    _write_jsonl(raw_dir / EXCLUDED_FILE, excluded)
    summary = {
        "snapshot_id": snapshot, "retrieved_at": retrieved_at, "sources": reports,
        "records_added": len(new_records), "records_replaced": len(removed_ids), "pages_added": len(new_pages),
        "registry_total": len(kept) + len(new_records),
        **({"http": client.summary()} if client is not None else {}),
    }
    (raw_dir / REPORT_FILE).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["pages"] = new_pages
    return summary


def coverage_increments(summary: dict[str, Any]) -> dict[str, int]:
    """{registry_category: số record} để cộng vào coverage report của category đích."""
    out: dict[str, int] = {}
    for report in summary.get("sources") or []:
        out[report["registry_category"]] = out.get(report["registry_category"], 0) + int(report["records"])
    return out
