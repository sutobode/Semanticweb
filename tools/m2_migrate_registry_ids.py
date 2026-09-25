"""M2-02/M2-03 — áp logic collector mới lên snapshot registry ĐÃ CÓ, không gọi network.

Snapshot cũ có hai lỗi của collector trước đây:
  * ``registry_id`` băm cả số thứ tự và href -> đổi khi danh sách đổi thứ tự;
  * ``registry_url`` là trang chủ, ``http://`` hoặc ``https://https://``.

Script tính lại đúng ``registry_id``/``registry_url`` mà collector mới sẽ sinh ra
cho cùng dữ liệu (dùng chung ``assign_registry_ids`` và ``normalize_registry_url``),
rồi (với ``--apply``) ghi đè:
  * ``data/raw/registry_records.jsonl``;
  * ``entity_id`` trong các manifest key theo entity (Wikidata/DBpedia của M3):
    ``wikidata_exact_enrichment.jsonl``, ``wikidata_sparql_exact_enrichment.jsonl``,
    ``wikidata_exact_missing.jsonl``, ``dbpedia_*_candidates.jsonl``;
  * ``registry_ids`` trong ``pages.jsonl`` nếu có;
và ghi bảng chuyển đổi ``data/raw/registry_id_migration.jsonl`` để M3/M4 đối chiếu.

Chạy:
    python tools/m2_migrate_registry_ids.py            # dry-run, chỉ in thống kê
    python tools/m2_migrate_registry_ids.py --apply    # ghi đè + tạo bảng chuyển đổi
Idempotent: chạy lại trên snapshot đã migrate không đổi gì.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vietheritage.identity.resolver import registry_entity_id  # noqa: E402
from vietheritage.normalization.normalizer import normalize_registry_url  # noqa: E402
from vietheritage.registry.collector import (  # noqa: E402
    RegistryRecord,
    assign_registry_ids,
    load_config,
    release_shared_registry_urls,
)

RAW = REPO_ROOT / "data" / "raw"
ENTITY_MANIFESTS = (
    "wikidata_exact_enrichment.jsonl",
    "wikidata_sparql_exact_enrichment.jsonl",
    "wikidata_exact_missing.jsonl",
    "dbpedia_lookup_candidates.jsonl",
    "dbpedia_exact_candidates.jsonl",
    "dbpedia_wikidata_candidates.jsonl",
)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def migrate(raw_dir: Path = RAW, apply: bool = False) -> dict:
    raw_cfg, categories = load_config()
    category_urls = {category.key: category.url for category in categories}
    base_url = raw_cfg["base_url"]
    rows = _read(raw_dir / "registry_records.jsonl")

    by_category: dict[str, list[tuple[dict, RegistryRecord]]] = {}
    for row in rows:
        fields = dict(row.get("registry_fields") or {})
        category_url = category_urls[row["registry_category"]]
        url, repair = normalize_registry_url(row.get("registry_url"), category_url, base_url)
        if repair and repair != "REGISTRY_URL_EMPTY":
            fields["registry_url_repair"] = repair
        elif repair == "REGISTRY_URL_EMPTY":
            fields.pop("registry_url_repair", None)
        record = RegistryRecord(
            registry_id="", registry_category=row["registry_category"], label_vi=row["label_vi"],
            registry_url=url, source_status=row["source_status"], coverage_snapshot=row["coverage_snapshot"],
            retrieved_at=row["retrieved_at"], registry_fields=fields,
        )
        by_category.setdefault(row["registry_category"], []).append((row, record))

    for key, pairs in by_category.items():
        records = [record for _, record in pairs]
        release_shared_registry_urls(records, category_urls[key])
        assign_registry_ids(records, category_urls[key])

    mapping: dict[str, str] = {}
    migrated_rows: list[dict] = []
    migration_log: list[dict] = []
    url_repairs: Counter = Counter()
    ordered = {id(row): record for pairs in by_category.values() for row, record in pairs}
    for row in rows:
        record = ordered[id(row)]
        old_entity = registry_entity_id(row["registry_id"])
        new_entity = registry_entity_id(record.registry_id)
        mapping[old_entity] = new_entity
        url_repairs[record.registry_fields.get("registry_url_repair", "unchanged")] += 1
        migrated_rows.append(record.to_dict())
        migration_log.append({
            "old_entity_id": old_entity, "new_entity_id": new_entity,
            "old_registry_url": row.get("registry_url"), "new_registry_url": record.registry_url,
            "registry_category": record.registry_category, "label_vi": record.label_vi,
        })
    if len(set(mapping.values())) != len(mapping):
        raise SystemExit("REGISTRY_ID_COLLISION: migration would merge distinct records")

    manifest_updates: dict[str, int] = {}
    for filename in ENTITY_MANIFESTS:
        path = raw_dir / filename
        manifest = _read(path)
        changed = 0
        for item in manifest:
            new = mapping.get(item.get("entity_id"))
            if new and new != item["entity_id"]:
                item["entity_id"] = new
                changed += 1
        manifest_updates[filename] = changed
        if apply and path.exists():
            _write(path, manifest)

    pages_path = raw_dir / "pages.jsonl"
    pages = _read(pages_path)
    pages_changed = 0
    for page in pages:
        if page.get("registry_ids"):
            updated = [mapping.get(registry_entity_id(value), value) for value in page["registry_ids"]]
            pages_changed += int(updated != page["registry_ids"])
            page["registry_ids"] = updated
    if apply:
        _write(raw_dir / "registry_records.jsonl", migrated_rows)
        _write(raw_dir / "registry_id_migration.jsonl", migration_log)
        if pages_changed:
            _write(pages_path, pages)

    return {
        "records": len(rows),
        "entity_ids_changed": sum(1 for old, new in mapping.items() if old != new),
        "registry_url_repairs": dict(url_repairs),
        "manifest_entity_ids_rewritten": manifest_updates,
        "pages_registry_ids_rewritten": pages_changed,
        "applied": apply,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="ghi đè file trong data/raw")
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    args = parser.parse_args()
    print(json.dumps(migrate(args.raw_dir, args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
