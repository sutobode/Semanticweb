"""Nguồn registry dạng "danh sách bài viết" trên dsvh.gov.vn (M2-26).

Khác với các category dạng BẢNG (``collector.py``), một số mục chỉ có danh sách link bài
giới thiệu, mỗi bài một di tích, phân trang bằng ``?_pageIndex=N``. Ví dụ:
``https://dsvh.gov.vn/di-tich-quoc-gia-130`` ("Di tích quốc gia", ~16 trang x 10 bài).

Luồng xử lý (khai báo ở ``config/registry_sources.yaml`` -> ``article_sources``):

1. **Danh sách**: đọc "Trang x/N", duyệt ``page_param=1..N`` (tối đa ``max_pages``), lấy
   link bài ``/<slug>-<id số>``. Trang trả về đúng tập link của trang trước ->
   ``PAGINATION_NOT_ADVANCING`` (dừng, ghi cảnh báo — không đoán).
2. **Bài chi tiết**: chỉ nhận bài có breadcrumb trỏ về trang danh sách (loại link "Thông báo
   mới"… ở sidebar). Từ văn bản bài:
   * ``label_vi``: ``<h1>`` bỏ đuôi ", tỉnh/thành phố X";
   * ``location``: cụm hành chính trong ngoặc ngay sau tên ("(xã Mê Linh, Thành phố Hà Nội)")
     hoặc sau "thuộc/tại/ở …" ở đầu bài (giữ nguyên "(nay là …)"); thiếu tỉnh thì ghép đuôi
     tiêu đề;
   * ``recognition_text``: câu "xếp hạng … quốc gia" -> "<số quyết định> ngày dd/mm/yyyy";
   * ``type``: loại hình trong câu xếp hạng (di tích lịch sử / kiến trúc nghệ thuật / …).
3. **Loại vào quarantine** (``registry_article_quarantine.jsonl``, không đoán): thiếu tên,
   thiếu số quyết định, bài xếp hạng "quốc gia ĐẶC BIỆT" (thuộc category khác), bài trùng tên
   với record đã có trong cùng category hoặc trong ``national_special_monuments``.

Record sinh ra có cùng schema với record dạng bảng (``registry_fields``: ``ordinal``,
``label_vi``, ``recognition_text``, ``location``, ``type``) cộng các trường truy vết
``source`` = ``article_list:<key>``, ``article_id``, ``title_raw``. ``registry_url`` là URL
bài; ``registry_id`` tính theo URL danh sách (khác URL bảng -> không đụng ID cũ).

Chạy riêng (gộp vào snapshot đang có, dùng cho chế độ ``wikipedia_only`` của notebook):

    python -m vietheritage.registry.articles --merge [--save-html DIR]

Chạy lại là idempotent: record cũ của cùng nguồn bị thay bằng kết quả mới.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests
from parsel import Selector

from vietheritage.normalization.normalizer import canonical_identity_key
from vietheritage.registry.collector import (
    CONFIG_PATH,
    RAW_DIR,
    REPO_ROOT,
    RegistryParseError,
    RegistryRecord,
    assign_registry_ids,
    fetch_page,
    load_config,
    utc_now_iso,
)

SOURCE_PREFIX = "article_list:"
QUARANTINE_FILE = "registry_article_quarantine.jsonl"
REPORT_FILE = "registry_article_report.json"

_ARTICLE_HREF_RE = re.compile(r"^/[a-z0-9]+(?:-[a-z0-9]+)*-(\d+)/?$")
_PAGE_INFO_RE = re.compile(r"Trang\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_ADMIN = r"(?:thôn|làng|xóm|ấp|bản|khu phố|tổ dân phố|xã|phường|thị trấn|thị xã|huyện|quận|thành phố|tỉnh|tp\.?)"
_PAREN_LOCATION_RE = re.compile(rf"\(\s*({_ADMIN}\s[^()]*(?:\([^()]*\)[^()]*)*)\)", re.IGNORECASE)
_PHRASE_LOCATION_RE = re.compile(
    rf"(?:thuộc|tại|ở|nằm ở|nằm tại|tọa lạc tại|toạ lạc tại|tọa lạc ở|toạ lạc ở)\s+(?:địa phận\s+)?"
    # Cho phép số nhà/tên phố trước đơn vị hành chính: "tại số 1 phố Hỏa Lò, phường Trần Hưng Đạo, …"
    rf"((?:số\s+[^,.;()]{{1,40}},\s*)?{_ADMIN}\s[^.;]*)", re.IGNORECASE)
_LOCATION_STOP_RE = re.compile(
    r",\s*(?:là|được|có|nằm|với|nơi|cách|thờ|gồm|do|đã|một|trên|trong|vào|từ|năm|đầu|sau|khi)\b"
    r"|\s+(?:là|được|có|thờ|nằm|do)\s", re.IGNORECASE)
# Đơn vị hành chính trong câu xếp hạng. Cấp dưới tỉnh phải viết thường ("Đền Xã Tắc" không phải xã);
# loại "tỉnh ủy", "huyện đội"…
_REC_ADMIN_RE = re.compile(
    r"(?:\b(?:thôn|làng|xóm|ấp|bản|khu phố|xã|phường|thị trấn|thị xã|huyện|quận|thành phố|tỉnh)"
    r"|\b(?:Thành phố|Tỉnh))\s(?!(?:ủy|uỷ|đội|lỵ|trưởng)\b)")
_SUB_PROVINCE_RE = re.compile(r"\b(?:thôn|làng|xóm|ấp|bản|khu phố|xã|phường|thị trấn|thị xã|huyện|quận)\s")
_RANK_SUBJECT_END_RE = re.compile(
    r"\s*,?\s*(?:đã\s+)?(?:được|đuợc)\s+(?:Bộ|Thủ tướng|UBND|Ủy ban|Chủ tịch|Nhà nước)", re.IGNORECASE)
_TITLE_LOCATION_RE = re.compile(r"^(?:tỉnh|thành phố|tp\.?)\s+\S", re.IGNORECASE)
# Số quyết định: "2103/QĐ-BVHTTDL", "15/2003/QĐ-BVHTT", "310-QĐ/BT", và dạng có khoảng trắng
# "1543 QĐ/VH", "51 QĐ/BT" (bài cũ). "Ð" (U+00D0) đã được _nfc đổi thành "Đ".
_DECISION_RE = re.compile(
    r"(?:Quyết định|QĐ)\s*(?:số)?\s*:?\s*"
    r"(\d[\d\s]{0,6}(?:\s*[-/]\s*\d{4})?\s*[-/]?\s*(?:VH\s*/\s*)?\s*(?:QĐ|QD|VH)[0-9A-Za-zĐđ/\-]*"
    r"(?:\s*/\s*QĐ)?)", re.IGNORECASE)
_DATE_RE = re.compile(
    r"ngày\s+(\d{1,2})\s*(?:/|-|\.|\s+tháng\s+)\s*(\d{1,2})\s*(?:/|-|\.|\s+năm\s+)\s*(\d{4})", re.IGNORECASE)
_SPECIAL_RE = re.compile(r"quốc\s+gia\s+đặc\s+biệt", re.IGNORECASE)
_SITE_TYPES = (
    ("kiến trúc nghệ thuật", "di tích kiến trúc nghệ thuật"),
    ("lịch sử", "di tích lịch sử"),
    ("khảo cổ", "di tích khảo cổ"),
    ("danh lam thắng cảnh", "danh lam thắng cảnh"),
    ("nghệ thuật", "di tích kiến trúc nghệ thuật"),   # tên cũ "di tích nghệ thuật quốc gia" (Bộ VH-TT, 1990s)
)
_RANK_VERB = r"(?:xếp\s+hạng|công\s+nhận)"


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _nfc(text: str | None) -> str:
    text = unicodedata.normalize("NFC", (text or "").replace("\xa0", " ").replace("\u00d0", "Đ").replace("\u00f0", "đ"))
    return re.sub(r"[\s\u200b]+", " ", text).strip()


@dataclass
class ArticleSource:
    key: str
    registry_category: str
    list_url: str
    page_param: str = "_pageIndex"
    max_pages: int = 40
    item_link_selector: str | None = None
    body_stop_markers: tuple[str, ...] = ("Văn bản pháp luật", "Thông báo mới", "Ấn phẩm tài liệu")
    duplicate_categories: tuple[str, ...] = ()
    enabled: bool = True

    @property
    def list_path(self) -> str:
        return urlparse(self.list_url).path.rstrip("/")


def load_article_sources(raw_cfg: dict[str, Any]) -> list[ArticleSource]:
    sources = []
    for item in raw_cfg.get("article_sources") or []:
        if not str(item.get("list_url", "")).startswith("https://dsvh.gov.vn/"):
            raise RegistryParseError(f"article source {item.get('key')}: list_url must be official https dsvh.gov.vn")
        sources.append(ArticleSource(
            key=item["key"], registry_category=item["registry_category"], list_url=item["list_url"],
            page_param=item.get("page_param", "_pageIndex"), max_pages=int(item.get("max_pages", 40)),
            item_link_selector=item.get("item_link_selector"),
            body_stop_markers=tuple(item.get("body_stop_markers") or ArticleSource.body_stop_markers),
            duplicate_categories=tuple(item.get("duplicate_categories") or ()),
            enabled=bool(item.get("enabled", True)),
        ))
    return sources


# ---------------------------------------------------------------------------
# Trang danh sách
# ---------------------------------------------------------------------------

def page_url(source: ArticleSource, number: int) -> str:
    separator = "&" if "?" in source.list_url else "?"
    return f"{source.list_url}{separator}{source.page_param}={number}"


def parse_page_info(html: str) -> tuple[int | None, int | None]:
    text = _nfc(" ".join(Selector(text=html).xpath("//body//text()").getall()))
    match = _PAGE_INFO_RE.search(text)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def parse_list_items(html: str, source: ArticleSource, base_url: str) -> list[tuple[str, str]]:
    """[(url bài, tiêu đề)] theo thứ tự xuất hiện; KHÔNG gồm link menu/phân trang.

    Có ``item_link_selector`` thì dùng; không thì lấy mọi ``<a>`` trỏ tới
    ``/<slug>-<id số>`` trên dsvh.gov.vn, có chữ (không phải ảnh), không bị cắt "...". Link
    sidebar lọt qua bước này sẽ bị loại ở bước kiểm tra breadcrumb của bài chi tiết.
    """
    sel = Selector(text=html)
    if source.item_link_selector:
        anchors = sel.css(source.item_link_selector)
    else:   # bỏ link trong menu/header/footer (khung trang), phần còn lại lọc tiếp bên dưới
        anchors = sel.xpath(
            "//a[@href][not(ancestor::nav or ancestor::header or ancestor::footer"
            " or ancestor::*[contains(concat(' ', translate(@class, 'MENUAV', 'menuav'), ' '), 'menu')"
            " or contains(translate(@class, 'NAV', 'nav'), 'nav')])]")
    items: dict[str, str] = {}
    for anchor in anchors:
        href = (anchor.attrib.get("href") or "").strip()
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc not in {"dsvh.gov.vn", "www.dsvh.gov.vn"} or parsed.query or parsed.fragment:
            continue
        if not _ARTICLE_HREF_RE.match(parsed.path) or parsed.path.rstrip("/") == source.list_path:
            continue
        text = _nfc(anchor.attrib.get("title") or " ".join(anchor.xpath(".//text()").getall()))
        if not text or len(text) < 4 or text.endswith("...") or anchor.css("img"):
            continue
        items.setdefault(f"https://dsvh.gov.vn{parsed.path.rstrip('/')}", text)
    return list(items.items())


def crawl_list(source: ArticleSource, request_cfg: dict[str, Any], base_url: str, fetcher: Callable[..., str],
               sleeper: Callable[[float], None], save_dir: Path | None = None,
               checksums: dict[str, str] | None = None) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Duyệt mọi trang danh sách. Trả (link ứng viên, thông tin phân trang/cảnh báo)."""
    delay = float(request_cfg.get("delay_seconds", 0) or 0)
    candidates: dict[str, str] = {}
    info: dict[str, Any] = {"pages_declared": None, "pages_fetched": 0, "page_urls": [], "warnings": []}
    previous: set[str] | None = None
    page_items: list[set[str]] = []
    number, total = 1, None
    while number <= (total or source.max_pages) and number <= source.max_pages:
        if number > 1 and delay:
            sleeper(delay)
        url = page_url(source, number)
        html = fetcher(url, request_cfg)
        info["pages_fetched"] += 1
        info["page_urls"].append(url)
        if checksums is not None:
            checksums[url] = hashlib.sha256(html.encode("utf-8")).hexdigest()
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)
            (save_dir / f"{source.key}-list-p{number:03d}.html").write_text(html, encoding="utf-8")
        current, declared = parse_page_info(html)
        if number == 1 and declared:
            total = declared
            info["pages_declared"] = declared
        items = parse_list_items(html, source, base_url)
        keys = {u for u, _ in items}
        if current is not None and current != number:
            info["warnings"].append(f"PAGINATION_NOT_ADVANCING: {url} báo 'Trang {current}' thay vì {number}")
            break
        if previous is not None and keys == previous:
            info["warnings"].append(f"PAGINATION_NOT_ADVANCING: {url} trùng hoàn toàn trang trước")
            break
        if not items:
            info["warnings"].append(f"EMPTY_LIST_PAGE: {url}")
            break
        page_items.append(keys)
        for item_url, title in items:
            candidates.setdefault(item_url, title)
        previous = keys
        number += 1
    if total and info["pages_fetched"] < min(total, source.max_pages) and not info["warnings"]:
        info["warnings"].append(f"PAGES_TRUNCATED: {info['pages_fetched']}/{total} (max_pages={source.max_pages})")
    # Link xuất hiện ở >= 3 trang và >= 1/2 số trang là khung trang (sidebar), không phải bài của mục.
    if len(page_items) >= 3:
        counts = Counter(u for keys in page_items for u in keys)
        chrome = {u for u, n in counts.items() if n >= 3 and n * 2 >= len(page_items)}
        for u in chrome:
            candidates.pop(u, None)
        info["chrome_links_removed"] = len(chrome)
    return list(candidates.items()), info


# ---------------------------------------------------------------------------
# Bài chi tiết
# ---------------------------------------------------------------------------

def _in_section(sel: Selector, source: ArticleSource, base_url: str) -> bool:
    for href in sel.css("a::attr(href)").getall():
        if urlparse(urljoin(base_url, href.strip())).path.rstrip("/") == source.list_path:
            return True
    return False


def _article_text(sel: Selector, h1, source: ArticleSource) -> str:
    """Văn bản bài: tổ tiên gần nhất của <h1> có nội dung đáng kể, cắt ở marker sidebar."""
    title = _nfc(" ".join(h1.xpath(".//text()").getall())) if h1 is not None else ""
    text = ""
    if h1 is not None:
        for ancestor in reversed(h1.xpath("ancestor::*")):   # gần nhất trước
            candidate = _nfc(" ".join(ancestor.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall()))
            if len(candidate) > len(title) + 200:
                text = candidate
                break
    if not text:
        text = _nfc(" ".join(sel.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)]").getall()))
    if title and title in text:
        text = text[text.index(title) + len(title):]
    cut = [text.find(m) for m in source.body_stop_markers if text.find(m) > 200]
    return (text[:min(cut)] if cut else text).strip()


def split_title(title: str) -> tuple[str, str | None]:
    """"Đình Tri Lễ, Thành phố Hà Nội" -> ("Đình Tri Lễ", "Thành phố Hà Nội")."""
    title = _nfc(title).rstrip(" .;:")
    if "," in title:
        head, tail = title.rsplit(",", 1)
        if _TITLE_LOCATION_RE.match(tail.strip()):
            return head.strip(), tail.strip()
    return title, None


def _trim_location(text: str) -> str:
    """Cắt cụm địa điểm: dừng ở ")" không có "(" tương ứng (cụm bắt đầu bên trong ngoặc của bài,
    ví dụ "(thuộc thôn …, tỉnh Hà Tĩnh), là nơi …") và ở từ dừng nằm ngoài ngoặc."""
    text = re.sub(r"\s+([,)])", r"\1", _nfc(text))
    depth = 0
    for i, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                text = text[:i]
                break
            depth -= 1
    for stop in _LOCATION_STOP_RE.finditer(text):   # bỏ qua từ dừng nằm trong ngoặc: "(nay là …)"
        if text[:stop.start()].count("(") == text[:stop.start()].count(")"):
            text = text[:stop.start()]
            break
    if text.count("(") > text.count(")"):
        text = text[:text.rfind("(")]
    return text.strip(" ,;:-")[:240]


def location_from_recognition(sentence: str | None) -> str | None:
    """Địa điểm trong chủ ngữ câu xếp hạng: "Đình X, xã Y, huyện Z, tỉnh T đã được Bộ trưởng … xếp hạng"."""
    if not sentence:
        return None
    end = _RANK_SUBJECT_END_RE.search(sentence)
    if not end:
        return None
    subject = sentence[:end.start()]
    admin = _REC_ADMIN_RE.search(subject)
    return _trim_location(subject[admin.start():]) or None if admin else None


_AREA_RESOLVER = None


def _area_groups(text: str | None) -> set[str]:
    global _AREA_RESOLVER
    if not text:
        return set()
    if _AREA_RESOLVER is None:
        from vietheritage.normalization.areas import default_resolver
        _AREA_RESOLVER = default_resolver()
    return {area.group for area in _AREA_RESOLVER.resolve(text).areas}


def choose_location(intro: str | None, recognition: str | None, title_location: str | None) -> tuple[str | None, str]:
    """(địa điểm, nguồn). Câu xếp hạng nói về CHÍNH di tích; đoạn mở đầu bài có thể là quê quán nhân vật
    ("Khu lưu niệm Phạm Thận Duật" -> "tỉnh Sơn Tây …"). Thứ tự:

    1. câu xếp hạng có đơn vị dưới tỉnh -> dùng nó;
    2. đoạn mở đầu, trừ khi nhóm tỉnh (sau sáp nhập 2025) của nó KHÔNG giao với nhóm tỉnh của câu xếp
       hạng/tiêu đề (bằng chứng lấy nhầm nơi khác);
    3. câu xếp hạng (chỉ có tỉnh) -> tiêu đề.
    Thiếu tên tỉnh của tiêu đề thì ghép thêm (như cũ).
    """
    def with_title(location: str | None) -> str | None:
        if location and title_location:
            core = re.sub(r"^(?:tỉnh|thành phố|tp\.?)\s+", "", title_location, flags=re.IGNORECASE)
            if canonical_identity_key(core) not in canonical_identity_key(location):
                return f"{location}, {title_location}"
        return location or title_location

    if recognition and _SUB_PROVINCE_RE.search(recognition):
        return with_title(recognition), "recognition_sentence"
    if intro:
        reference = _area_groups(recognition) or _area_groups(title_location)
        intro_groups = _area_groups(intro)
        if not (reference and intro_groups and not intro_groups & reference):
            return with_title(intro), "intro"
    if recognition:
        return with_title(recognition), "recognition_sentence"
    return title_location, "title" if title_location else "none"


def extract_location(body: str, label: str, title_location: str | None) -> str | None:
    head = body[:900]
    found: list[tuple[int, str]] = []
    paren = _PAREN_LOCATION_RE.search(head)
    if paren:
        found.append((paren.start(), _trim_location(paren.group(1))))
    phrase = _PHRASE_LOCATION_RE.search(head)
    if phrase:
        found.append((phrase.start(), _trim_location(phrase.group(1))))
    location = min(found)[1] if found else None
    if title_location:
        if not location:
            return title_location
        core = re.sub(r"^(?:tỉnh|thành phố|tp\.?)\s+", "", title_location, flags=re.IGNORECASE)
        if canonical_identity_key(core) not in canonical_identity_key(location):
            location = f"{location}, {title_location}"
    return location or None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ“\"(*])", text) if s.strip()]


def _clean_decision(value: str) -> str:
    """"3238/ QĐ-BVHTTDL" -> "3238/QĐ-BVHTTDL"; "8 87/QĐ" -> "887/QĐ" (lỗi gõ); "1543 QĐ/VH" giữ nguyên."""
    value = re.sub(r"\s*([/-])\s*", r"\1", value.strip())
    value = re.sub(r"(?<=\d)\s+(?=\d)", "", value)
    return value.rstrip(".,;:)-/")


def extract_recognition(body: str) -> dict[str, Any]:
    """Câu xếp hạng/công nhận di tích -> số quyết định, ngày, loại hình, hạng (national/special).

    Câu hợp lệ có "xếp hạng", hoặc "công nhận" kèm "di tích"; ưu tiên câu có "quốc gia"
    kèm số quyết định. Hạng "special" chỉ khi "đặc biệt" nằm GIỮA động từ và số quyết định
    ("xếp hạng di tích quốc gia đặc biệt tại QĐ …"); câu kiểu "xếp hạng di tích quốc gia tại QĐ …
    và là 1 điểm trong di tích quốc gia đặc biệt …" (Bến K15) vẫn là "national".
    """
    # "xếp hạng" đủ để nhận câu; "công nhận" phải kèm "di tích" (chịu lỗi gõ "d i tích") để tránh
    # "được UNESCO công nhận …", "công nhận Bằng khen …".
    ranked = [s for s in _sentences(body) if re.search(r"xếp\s+hạng", s, re.IGNORECASE) or (
        re.search(r"công\s+nhận", s, re.IGNORECASE) and re.search(r"d\s?i\s+tích", s, re.IGNORECASE))]
    with_decision = [s for s in ranked if _DECISION_RE.search(s)]
    national = [s for s in with_decision if re.search(r"quốc\s+gia", s, re.IGNORECASE)]
    chosen = (national or with_decision or [s for s in ranked if re.search(r"quốc\s+gia", s, re.IGNORECASE)]
              or [None])[0]
    result: dict[str, Any] = {"sentence": chosen, "decision": None, "date": None, "types": [], "rank": None,
                              "special_mentioned": any(_SPECIAL_RE.search(s) for s in ranked)}
    if not chosen:
        return result
    decision = _DECISION_RE.search(chosen)
    if decision:
        result["decision"] = _clean_decision(decision.group(1))
    # HTML hay cắt số thành nhiều span: "ngày 2 3 / 8 /20 04", "năm 202 4" -> ghép chữ số trong cụm ngày.
    dated = re.sub(r"ngày[\s\d/.\-thángnăm]{0,40}",
                   lambda m: re.sub(r"(?<=\d)\s+(?=\d)", "", m.group(0)), chosen)
    offset = len(dated) - len(chosen)
    date = (_DATE_RE.search(dated[max(0, decision.start() + offset):] if decision else dated)
            or _DATE_RE.search(dated))
    if date:
        result["date"] = f"{int(date.group(1)):02d}/{int(date.group(2)):02d}/{date.group(3)}"
    verb = re.search(_RANK_VERB, chosen, re.IGNORECASE)
    start = verb.end() if verb else 0
    # Thường "xếp hạng <loại hình> quốc gia tại QĐ …"; có bài viết ngược "QĐ … xếp hạng <tên> là <loại hình>
    # quốc gia" (làng Nôm) -> khi QĐ đứng trước động từ, span kết thúc ở "quốc gia".
    if decision and decision.start() > start:
        end = decision.start()
    else:
        tail = re.search(r"quốc\s+gia(?:\s+đặc\s+biệt)?", chosen[start:], re.IGNORECASE)
        end = start + tail.end() if tail else len(chosen)
    span = chosen[start:end]
    phrase = re.sub(r"\s*,\s*", " ", span).casefold()
    hits: list[tuple[int, str]] = []
    covered: list[tuple[int, int]] = []
    for key, value in _SITE_TYPES:
        for match in re.finditer(re.escape(key), phrase):
            if not any(a <= match.start() < b for a, b in covered):
                hits.append((match.start(), value))
                covered.append((match.start(), match.end()))
    result["types"] = list(dict.fromkeys(v for _, v in sorted(hits)))
    result["rank"] = "special" if _SPECIAL_RE.search(span) else "national"
    return result


def parse_article(html: str, url: str, source: ArticleSource, base_url: str,
                  list_title: str | None = None) -> dict[str, Any]:
    """Bài chi tiết -> {"fields": {...}} hoặc {"error_code", "reason"}."""
    sel = Selector(text=html)
    if not _in_section(sel, source, base_url):
        return {"error_code": "ARTICLE_OUTSIDE_SECTION", "reason": f"không có breadcrumb về {source.list_url}"}
    page_text = _nfc(" ".join(sel.xpath("//body//text()").getall()))
    if _PAGE_INFO_RE.search(page_text):   # trang mục/danh sách (breadcrumb "Di tích"), không phải bài
        return {"error_code": "ARTICLE_IS_LISTING", "reason": "trang có phân trang 'Trang x/N' -> trang danh sách"}
    h1 = next((h for h in sel.css("h1") if len(_nfc(" ".join(h.xpath(".//text()").getall()))) > 3), None)
    title = _nfc(" ".join(h1.xpath(".//text()").getall())) if h1 is not None else _nfc(list_title or sel.css("title::text").get())
    label, title_location = split_title(title)
    if not label:
        return {"error_code": "REGISTRY_RECORD_INVALID", "reason": "missing label_vi"}
    body = _article_text(sel, h1, source)
    recognition = extract_recognition(body)
    if not recognition["decision"]:   # phần thân bài cắt hụt -> thử toàn trang (câu xếp hạng vẫn phải có "quốc gia")
        whole = extract_recognition(page_text)
        if whole["decision"]:
            recognition = whole
    location, location_source = choose_location(
        extract_location(body, label, None), location_from_recognition(recognition["sentence"]), title_location)
    base = {"title_raw": title, "label_vi": label, "location": location, "recognition_sentence": recognition["sentence"]}
    if recognition["rank"] == "special":
        return {**base, "error_code": "ARTICLE_SPECIAL_RANK",
                "reason": "bài xếp hạng di tích quốc gia đặc biệt -> không thuộc national_monuments"}
    if not recognition["decision"]:
        return {**base, "error_code": "REGISTRY_RECORD_INVALID", "reason": "missing recognition decision number"}
    recognition_text = recognition["decision"] + (f" ngày {recognition['date']}" if recognition["date"] else "")
    fields = {"label_vi": label, "recognition_text": recognition_text, "location": location,
              "location_source": location_source,
              "type": recognition["types"][0] if recognition["types"] else None,
              "types_all": "; ".join(recognition["types"]) or None, "title_raw": title,
              "article_id": _ARTICLE_HREF_RE.match(urlparse(url).path).group(1) if _ARTICLE_HREF_RE.match(urlparse(url).path) else None}
    return {"fields": {k: v for k, v in fields.items() if v not in (None, "")}}


# ---------------------------------------------------------------------------
# Thu thập một nguồn
# ---------------------------------------------------------------------------

def collect_article_source(
    source: ArticleSource,
    request_cfg: dict[str, Any],
    base_url: str,
    coverage_snapshot: str,
    retrieved_at: str,
    existing_records: list[dict[str, Any]],
    fetcher: Callable[..., str] = fetch_page,
    sleeper: Callable[[float], None] = time.sleep,
    save_html_dir: Path | None = None,
    checksums: dict[str, str] | None = None,
) -> tuple[list[RegistryRecord], list[dict[str, Any]], dict[str, Any]]:
    """Trả (record hợp lệ, quarantine, report). Lỗi mạng ở trang danh sách -> raise RegistryParseError."""
    delay = float(request_cfg.get("delay_seconds", 0) or 0)
    candidates, info = crawl_list(source, request_cfg, base_url, fetcher, sleeper, save_html_dir, checksums)
    _log(f"[articles] {source.key}: {len(candidates)} link ứng viên từ {info['pages_fetched']} trang"
         f" (khai báo {info['pages_declared']})" + (f"; {info['warnings']}" if info["warnings"] else ""))
    existing_keys: dict[tuple[str, str], str] = {}
    for record in existing_records:
        category = record.get("registry_category")
        if category == source.registry_category or category in source.duplicate_categories:
            existing_keys.setdefault((category, canonical_identity_key(record["label_vi"])), record.get("registry_id", ""))

    records: list[RegistryRecord] = []
    quarantine: list[dict[str, Any]] = []
    seen_labels: dict[str, str] = {}
    errors = Counter()
    for index, (url, list_title) in enumerate(candidates, start=1):
        if delay:
            sleeper(delay)
        try:
            html = fetcher(url, request_cfg)
        except RegistryParseError as exc:
            errors["ARTICLE_FETCH_FAILED"] += 1
            quarantine.append(_quarantine(source, url, coverage_snapshot, "ARTICLE_FETCH_FAILED", str(exc), list_title))
            continue
        if checksums is not None:
            checksums[url] = hashlib.sha256(html.encode("utf-8")).hexdigest()
        if save_html_dir is not None:
            (save_html_dir / f"{source.key}-{url.rsplit('-', 1)[-1]}.html").write_text(html, encoding="utf-8")
        parsed = parse_article(html, url, source, base_url, list_title)
        if "fields" not in parsed:
            errors[parsed["error_code"]] += 1
            if parsed["error_code"] not in {"ARTICLE_OUTSIDE_SECTION", "ARTICLE_IS_LISTING"}:   # khung trang: chỉ đếm
                quarantine.append(_quarantine(source, url, coverage_snapshot, parsed["error_code"], parsed["reason"],
                                              list_title, {k: v for k, v in parsed.items() if k not in {"error_code", "reason"}}))
            continue
        fields = parsed["fields"]
        key = canonical_identity_key(fields["label_vi"])
        duplicate = next((c for c in (source.registry_category, *source.duplicate_categories) if (c, key) in existing_keys), None)
        if duplicate:
            errors["ARTICLE_DUPLICATE"] += 1
            quarantine.append(_quarantine(source, url, coverage_snapshot, "ARTICLE_DUPLICATE",
                                          f"trùng tên với record {existing_keys[(duplicate, key)]} ({duplicate})", list_title,
                                          {"label_vi": fields["label_vi"]}))
            continue
        if key in seen_labels and seen_labels[key] == fields.get("location"):
            errors["ARTICLE_REPEATED"] += 1
            continue
        seen_labels[key] = fields.get("location")
        records.append(RegistryRecord(
            registry_id="", registry_category=source.registry_category, label_vi=fields["label_vi"],
            registry_url=url, source_status="registry_only", coverage_snapshot=coverage_snapshot,
            retrieved_at=retrieved_at,
            registry_fields={"ordinal": str(index), **fields, "source": SOURCE_PREFIX + source.key},
        ))
        if index % 10 == 0:
            _log(f"[articles] {source.key}: {index}/{len(candidates)} bài, {len(records)} record")
    assign_registry_ids(records, source.list_url)
    report = {
        "key": source.key, "registry_category": source.registry_category, "list_url": source.list_url,
        **{k: v for k, v in info.items() if k != "page_urls"}, "page_urls": info["page_urls"],
        "candidates": len(candidates), "records": len(records),
        "quarantined": len(quarantine), "skipped": dict(errors),
        "missing_location": sum(1 for r in records if not r.registry_fields.get("location")),
        "missing_type": sum(1 for r in records if not r.registry_fields.get("type")),
    }
    return records, quarantine, report


def _quarantine(source: ArticleSource, url: str, snapshot: str, code: str, reason: str,
                list_title: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"registry_category": source.registry_category, "registry_url": url, "error_code": code, "reason": reason,
            "list_title": list_title, "source": SOURCE_PREFIX + source.key, "snapshot_id": snapshot, **(extra or {})}


def coverage_increment(report: dict[str, Any]) -> dict[str, int]:
    """Phần cộng thêm vào counter coverage của category (discovered/valid/invalid/retrieved)."""
    invalid = report["quarantined"] - report["skipped"].get("ARTICLE_DUPLICATE", 0)
    return {"discovered": report["records"] + invalid, "valid": report["records"],
            "invalid": invalid, "retrieved": report["records"]}


# ---------------------------------------------------------------------------
# Gộp vào snapshot đang có (chế độ wikipedia_only)
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def merge_into_snapshot(
    config_path: Path = CONFIG_PATH,
    raw_dir: Path = RAW_DIR,
    reports_root: Path | None = None,
    fetcher: Callable[..., str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    save_html_dir: Path | None = None,
    source_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Thu thập các ``article_sources`` và gộp vào ``registry_records.jsonl`` của snapshot hiện có.

    * record cũ của cùng nguồn (``registry_fields.source``) bị thay thế -> chạy lại idempotent;
    * record mang ``coverage_snapshot`` của snapshot đang có (mapper cập nhật đúng coverage);
    * counter của category trong ``reports/<snapshot>/coverage.json`` được trừ phần lần trước
      (lưu ở ``registry_article_report.json``) rồi cộng phần mới; thêm URL nguồn + checksum.
    """
    raw_cfg, _ = load_config(config_path)
    sources = [s for s in load_article_sources(raw_cfg) if s.enabled and (not source_keys or s.key in source_keys)]
    request_cfg = raw_cfg.get("request", {}) or {}
    reports_root = reports_root or (REPO_ROOT / "reports")
    records_path = raw_dir / "registry_records.jsonl"
    all_records = _read_jsonl(records_path)
    source_tags = {SOURCE_PREFIX + s.key for s in sources}
    base_records = [r for r in all_records if (r.get("registry_fields") or {}).get("source") not in source_tags]
    snapshots = Counter(r.get("coverage_snapshot") for r in base_records if r.get("coverage_snapshot"))
    if not snapshots:
        raise RegistryParseError("không có snapshot registry để gộp (chạy `vietheritage.cli collect` trước)")
    snapshot = snapshots.most_common(1)[0][0]
    retrieved_at = utc_now_iso()
    session = requests.Session()
    fetch = fetcher or (lambda url, cfg: fetch_page(url, cfg, session=session))

    previous = {}
    report_path = raw_dir / REPORT_FILE
    if report_path.exists():
        previous = {item["key"]: item for item in json.loads(report_path.read_text(encoding="utf-8")).get("sources", [])}
    old_quarantine = [q for q in _read_jsonl(raw_dir / QUARANTINE_FILE) if q.get("source") not in source_tags]

    checksums: dict[str, str] = {}
    new_records: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    known_ids = {r["registry_id"] for r in base_records}
    for source in sources:
        records, bad, report = collect_article_source(
            source, request_cfg, raw_cfg["base_url"], snapshot, retrieved_at, base_records + new_records,
            fetch, sleeper, save_html_dir, checksums)
        for record in records:
            if record.registry_id in known_ids:
                raise RegistryParseError(f"registry_id collision: {record.registry_id} ({record.label_vi})")
            known_ids.add(record.registry_id)
        new_records += [r.to_dict() for r in records]
        quarantine += bad
        report["coverage_increment"] = coverage_increment(report)
        reports.append(report)

    _write_jsonl(records_path, base_records + new_records)
    _write_jsonl(raw_dir / QUARANTINE_FILE, old_quarantine + quarantine)
    summary = {"snapshot_id": snapshot, "retrieved_at": retrieved_at, "sources": reports,
               "records_added": len(new_records), "registry_total": len(base_records) + len(new_records)}
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    coverage_path = reports_root / snapshot / "coverage.json"
    if coverage_path.exists():
        _update_coverage(coverage_path, reports, previous, checksums)
        summary["coverage_path"] = str(coverage_path)
    return summary


def _update_coverage(path: Path, reports: list[dict[str, Any]], previous: dict[str, Any], checksums: dict[str, str]) -> None:
    coverage = json.loads(path.read_text(encoding="utf-8"))
    by_category = {item["registry_category"]: item for item in coverage.get("categories", [])}
    for report in reports:
        item = by_category.get(report["registry_category"])
        if item is None:
            continue
        old = (previous.get(report["key"]) or {}).get("coverage_increment") or {}
        for counter, value in report["coverage_increment"].items():
            item[counter] = max(0, int(item.get(counter) or 0) - int(old.get(counter, 0)) + value)
        item["canonicalized"] = min(int(item.get("canonicalized") or 0), item["valid"])
        item["coverage_percent"] = round(100.0 * item["canonicalized"] / item["valid"], 4) if item["valid"] else 100.0
        coverage["source_urls"] = list(dict.fromkeys([*coverage.get("source_urls", []), report["list_url"]]))
    coverage.setdefault("source_checksums", {}).update(checksums)
    coverage["registry_total"] = sum(int(c.get("valid") or 0) for c in coverage.get("categories", []))
    path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thu thập nguồn registry dạng danh sách bài viết (M2-26)")
    parser.add_argument("--merge", action="store_true", help="gộp vào registry_records.jsonl của snapshot hiện có")
    parser.add_argument("--source", action="append", help="chỉ chạy nguồn có key này (lặp lại được)")
    parser.add_argument("--save-html", type=Path, help="lưu HTML danh sách + bài vào thư mục này")
    parser.add_argument("--probe", type=int, metavar="N", help="chỉ đọc trang 1 và N bài đầu, in kết quả parse, không ghi gì")
    args = parser.parse_args(argv)
    if args.probe:
        return probe(args.probe, args.source, args.save_html)
    if not args.merge:
        parser.error("dùng --merge hoặc --probe N")
    summary = merge_into_snapshot(save_html_dir=args.save_html, source_keys=args.source)
    for report in summary["sources"]:
        print(json.dumps({k: v for k, v in report.items() if k != "page_urls"}, ensure_ascii=False))
    print(f"articles: +{summary['records_added']} record -> registry_total={summary['registry_total']} "
          f"(snapshot {summary['snapshot_id']})")
    return 0


def probe(n_articles: int, source_keys: list[str] | None = None, save_dir: Path | None = None) -> int:
    """Chẩn đoán nhanh trên site thật: phân trang (trang 1 vs 2) và parse N bài đầu."""
    raw_cfg, _ = load_config(CONFIG_PATH)
    request_cfg = raw_cfg.get("request", {}) or {}
    session = requests.Session()
    for source in load_article_sources(raw_cfg):
        if source_keys and source.key not in source_keys:
            continue
        pages = [fetch_page(page_url(source, n), request_cfg, session=session) for n in (1, 2)]
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            for n, html in zip((1, 2), pages):
                (save_dir / f"{source.key}-list-p{n:03d}.html").write_text(html, encoding="utf-8")
        items = [parse_list_items(html, source, raw_cfg["base_url"]) for html in pages]
        print(f"== {source.key}: page_info={[parse_page_info(h) for h in pages]}, "
              f"items p1={len(items[0])} p2={len(items[1])}, p2 khác p1: {set(items[0]) != set(items[1])}")
        for url, title in items[0][:n_articles]:
            time.sleep(float(request_cfg.get("delay_seconds", 1)))
            html = fetch_page(url, request_cfg, session=session)
            if save_dir:
                (save_dir / f"{source.key}-{url.rsplit('-', 1)[-1]}.html").write_text(html, encoding="utf-8")
            print(json.dumps({"url": url, "list_title": title, **parse_article(html, url, source, raw_cfg["base_url"], title)},
                             ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
