from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "processed" / "canonical.jsonl"
OUTPUT = ROOT / "data" / "raw" / "dbpedia_lookup_candidates.jsonl"
LOG = ROOT / "logs" / "dbpedia-lookup-utf8.log"
STATUS = ROOT / "logs" / "dbpedia-lookup-status.txt"
ENDPOINT = "https://lookup.dbpedia.org/api/search"
UA = "VietHeritageLOD/1.0 (deterministic heritage linker)"
_TAG_RE = re.compile(r"<[^>]+>")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def key(value: str) -> str:
    value = _TAG_RE.sub("", html.unescape(value))
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def emit(handle, message: str) -> None:
    line = f"[{now()}] {message}\n"
    handle.write(line)
    handle.flush()
    print(line, end="", flush=True)


def compatible(entity_type: str, type_names: list[str]) -> bool:
    names = {str(item).casefold() for item in type_names}
    if entity_type == "HeritageSite":
        return bool(names & {"place", "location", "worldheritagesite", "architecturalstructure", "monument"})
    if entity_type == "Museum":
        return bool(names & {"museum", "building", "place"})
    if entity_type == "HistoricalPerson":
        return "person" in names
    if entity_type in {"CulturalObject", "NationalTreasure", "Artisan"}:
        return bool(names & {"person", "work", "artifact", "place"})
    return bool(names)


def main() -> int:
    max_queries = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    records = [json.loads(line) for line in CANONICAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = [r for r in records if not (r.get("external_ids") or {}).get("wikidata")][:max_queries]
    rows = []
    with LOG.open("a", encoding="utf-8", newline="\n") as log:
        emit(log, f"START total_records={len(records)} candidates={len(candidates)} max_queries={max_queries}")
        STATUS.write_text(f"RUNNING\nstarted={now()}\ncandidates={len(candidates)}\nlog={LOG}\n", encoding="utf-8")
        session = requests.Session()
        for index, record in enumerate(candidates, 1):
            try:
                response = session.get(ENDPOINT, params={"query": record["label_vi"], "maxResults": 10, "format": "JSON"}, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
                response.raise_for_status()
                docs = response.json().get("docs", [])
                exact = []
                for doc in docs:
                    labels = list(doc.get("redirectlabel", [])) + list(doc.get("label", []))
                    if any(key(label) == key(record["label_vi"]) for label in labels):
                        uri = (doc.get("resource") or doc.get("id") or [""])[0]
                        if uri:
                            exact.append((uri, compatible(record.get("entity_type", ""), doc.get("typeName", []))))
                exact = sorted(set(exact))
                if len(exact) == 1 and exact[0][1]:
                    rows.append({"entity_id": record["entity_id"], "label_vi": record["label_vi"], "uri": exact[0][0], "label": record["label_vi"], "score": 1.0, "distance_km": None, "type_compatible": True, "method": "dbpedia-lookup-exact-label"})
                    emit(log, f"MATCH {index}/{len(candidates)} entity={record['entity_id']} uri={exact[0][0]}")
                else:
                    emit(log, f"MISS {index}/{len(candidates)} entity={record['entity_id']} exact={len(exact)} http={response.status_code}")
            except (requests.RequestException, ValueError) as exc:
                emit(log, f"ERROR {index}/{len(candidates)} entity={record['entity_id']} error={exc}")
            if index < len(candidates):
                time.sleep(0.2)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
        emit(log, f"END unique_candidates={len(rows)} output={OUTPUT}")
        STATUS.write_text(f"FINISHED\nfinished={now()}\nunique_candidates={len(rows)}\noutput={OUTPUT}\nlog={LOG}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
