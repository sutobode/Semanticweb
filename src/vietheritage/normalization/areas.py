"""AdministrativeArea resolution from registry location text (M2-10).

Tách ô địa điểm của registry (ví dụ ``"Xã Song Hồ, huyện Thuận Thành, tỉnh Bắc
Ninh"`` hoặc ``"Tỉnh Nghệ An Tỉnh Hà Tĩnh"``) thành danh sách đơn vị hành chính
cấp tỉnh theo bảng tường minh ``config/areas.yaml``.

Không có fuzzy matching (DEC-007): mọi tên và biến thể đều là chuỗi chính xác
sau khi chuẩn hóa khóa (NFC, casefold, canonical dash, vị trí dấu thanh).
Chuỗi không khớp tên tỉnh nào được trả về dưới dạng warning ``AREA_UNMAPPED``
để review, không bao giờ bị đoán.

Hai lớp (DEC-M2-004):

* ``resolve`` — lớp SO KHỚP, trả về tỉnh CŨ (63 tên như nguồn ghi). Dùng cho bằng chứng
  tỉnh (``group``) ở collector Wikipedia và parser bài viết dsvh.
* ``resolve_published`` / ``publish`` — lớp CÔNG BỐ, quy tỉnh cũ về đơn vị SAU sắp xếp 2025
  (``merged_areas``) và bỏ trùng khi ``publish_level: merged_2025``. Mapper dùng lớp này
  cho ``relations.located_in`` và entity ``AdministrativeArea``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vietheritage.normalization.normalizer import (
    canonical_dash,
    canonical_identity_key,
    normalize_nfc,
    normalize_text,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
AREAS_CONFIG_PATH = REPO_ROOT / "config" / "areas.yaml"

# Vị trí dấu thanh kiểu cũ -> kiểu mới. Áp dụng cho CẢ HAI phía khi so khớp,
# nên chỉ cần nhất quán, không cần đúng chính tả tuyệt đối ("quý" không bị ảnh hưởng
# vì không có trong khóa tên tỉnh).
_TONE_MARKS = {
    "oá": "óa", "oà": "òa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oé": "óe", "oè": "òe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}
_TONE_RE = re.compile("|".join(sorted(_TONE_MARKS, key=len, reverse=True)))


def match_key(text: str) -> str:
    """Khóa so khớp địa danh: NFC + casefold + canonical dash + dấu thanh + khoảng trắng."""
    value = normalize_nfc(normalize_text(text)).casefold()
    value = canonical_dash(value)
    value = re.sub(r"\s*-\s*", " - ", value)
    value = _TONE_RE.sub(lambda m: _TONE_MARKS[m.group(0)], value)
    return re.sub(r"\s+", " ", value).strip()


def sha256_12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def area_id_for_label(label: str, qid: str | None = None) -> str:
    """Section 13.1 — ``area-wikidata-{qid}`` hoặc ``area-name-{sha256(normalized_name)[:12]}``."""
    if qid:
        return f"area-wikidata-{qid.lower()}"
    return f"area-name-{sha256_12(canonical_identity_key(label))}"


@dataclass(frozen=True)
class AreaDef:
    label: str
    entity_id: str
    level: str | None = None
    display_aliases: tuple[str, ...] = ()
    qid: str | None = None
    merged_into: str | None = None

    @property
    def group(self) -> str:
        """Tỉnh/thành sau sắp xếp 2025 (config ``merged_into``); dùng so khớp bằng chứng."""
        return self.merged_into or self.label


@dataclass
class AreaMatch:
    areas: list[AreaDef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str | None = None


PUBLISH_LEVELS = ("merged_2025", "source")


class AreaResolver:
    """Resolve location text -> province-level ``AreaDef`` list (deterministic)."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.country_code = config.get("country_code", "VN")
        self.publish_level = config.get("publish_level", "source")
        if self.publish_level not in PUBLISH_LEVELS:
            raise ValueError(f"CONFIG_INVALID: publish_level {self.publish_level!r} not in {PUBLISH_LEVELS}")
        self.areas: list[AreaDef] = []
        variants: list[tuple[str, AreaDef]] = []
        for item in config.get("areas", []):
            area = AreaDef(
                label=item["label"],
                entity_id=area_id_for_label(item["label"], item.get("qid")),
                level=item.get("level"),
                display_aliases=tuple(item.get("display_aliases") or ()),
                qid=item.get("qid"),
                merged_into=item.get("merged_into"),
            )
            self.areas.append(area)
            for name in [item["label"], *(item.get("display_aliases") or []), *(item.get("match_variants") or [])]:
                variants.append((match_key(name), area))
        ids = [area.entity_id for area in self.areas]
        if len(ids) != len(set(ids)):
            raise ValueError("CONFIG_INVALID: duplicate area label in config/areas.yaml")
        # Lớp công bố: đơn vị sau sắp xếp 2025, khóa theo label (= giá trị merged_into).
        self.merged_areas: dict[str, AreaDef] = {}
        for item in config.get("merged_areas") or []:
            if item["label"] in self.merged_areas:
                raise ValueError(f"CONFIG_INVALID: duplicate merged area {item['label']!r}")
            self.merged_areas[item["label"]] = AreaDef(
                label=item["label"],
                entity_id=area_id_for_label(item["label"], item.get("qid")),
                level=item.get("level"),
                display_aliases=tuple(item.get("display_aliases") or ()),
                qid=item.get("qid"),
                merged_into=item["label"],
            )
        if self.publish_level == "merged_2025":
            unknown = sorted({area.group for area in self.areas} - set(self.merged_areas))
            if unknown:
                raise ValueError(f"CONFIG_INVALID: merged_into without merged_areas entry: {unknown}")
        # Dài trước để "thừa thiên - huế" thắng "huế".
        variants.sort(key=lambda item: (-len(item[0]), item[0]))
        self._variants = variants
        self._patterns = [
            (re.compile(rf"(?<!\w){re.escape(key)}(?!\w)"), area) for key, area in variants
        ]
        prefixes = [match_key(p) for p in config.get("sub_provincial_prefixes", [])]
        self._sub_prefix_re = re.compile(
            r"(?:^|[\s,;(])(?:" + "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True)) + r")\s*$"
        ) if prefixes else None
        by_label = {area.label: area for area in self.areas}
        self._district_hints = []
        for district, province in (config.get("district_hints") or {}).items():
            if province not in by_label:
                raise ValueError(f"CONFIG_INVALID: district hint {district!r} -> unknown area {province!r}")
            self._district_hints.append(
                (re.compile(rf"(?<!\w){re.escape(match_key(district))}(?!\w)"), by_label[province])
            )

    def groups(self, text: str | None) -> set[str]:
        """Tập tỉnh/thành SAU sáp nhập 2025 được nhắc tới trong ``text``.

        Ví dụ "Tỉnh Bắc Kạn" và "tỉnh Thái Nguyên" cùng nhóm "Thái Nguyên"; "Thái Bình"
        (-> Hưng Yên) và "Nam Định" (-> Ninh Bình) khác nhóm.
        """
        return {area.group for area in self.resolve(text).areas}

    def publish(self, areas: list[AreaDef]) -> list[AreaDef]:
        """Tỉnh cũ -> đơn vị công bố theo ``publish_level``; giữ thứ tự xuất hiện, bỏ trùng.

        ``merged_2025``: Hải Dương -> Hải Phòng; "Bắc Giang, Bắc Ninh" -> [Bắc Ninh].
        ``source``: trả nguyên danh sách tỉnh cũ.
        """
        if self.publish_level == "source":
            return list(areas)
        out: dict[str, AreaDef] = {}
        for area in areas:
            target = self.merged_areas[area.group]
            out.setdefault(target.entity_id, target)
        return list(out.values())

    def resolve_published(self, location: str | None) -> AreaMatch:
        """Như ``resolve`` nhưng ``areas`` là đơn vị công bố (xem ``publish``)."""
        match = self.resolve(location)
        return AreaMatch(areas=self.publish(match.areas), warnings=match.warnings, method=match.method)

    @property
    def published_areas(self) -> list[AreaDef]:
        """Toàn bộ đơn vị có thể công bố (34 hoặc 63 tùy ``publish_level``)."""
        return list(self.merged_areas.values()) if self.publish_level == "merged_2025" else list(self.areas)

    @classmethod
    def from_config(cls, path: Path = AREAS_CONFIG_PATH) -> "AreaResolver":
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def _is_sub_provincial(self, text: str, start: int) -> bool:
        if self._sub_prefix_re is None:
            return False
        segment_start = max(text.rfind(",", 0, start), text.rfind(";", 0, start)) + 1
        return bool(self._sub_prefix_re.search(text[segment_start:start]))

    def resolve(self, location: str | None) -> AreaMatch:
        result = AreaMatch()
        if not location or not normalize_text(location):
            return result
        text = match_key(location)
        taken = [False] * len(text)
        found: dict[str, AreaDef] = {}
        order: list[tuple[int, str]] = []
        for pattern, area in self._patterns:
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(taken[start:end]):
                    continue
                for index in range(start, end):
                    taken[index] = True
                if self._is_sub_provincial(text, start):
                    continue
                if area.entity_id not in found:
                    found[area.entity_id] = area
                    order.append((start, area.entity_id))
        if found:
            result.areas = [found[entity_id] for _, entity_id in sorted(order)]
            result.method = "province_name"
            return result
        for pattern, area in self._district_hints:
            if pattern.search(text):
                result.areas = [area]
                result.method = "district_hint"
                return result
        result.warnings.append("AREA_UNMAPPED")
        return result


@lru_cache(maxsize=4)
def default_resolver(path: str = str(AREAS_CONFIG_PATH)) -> AreaResolver:
    return AreaResolver.from_config(Path(path))
