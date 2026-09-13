from __future__ import annotations

import json
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "processed" / "canonical.jsonl"
OUTPUT = ROOT / "data" / "raw" / "wikidata_exact_enrichment.jsonl"
LOG = ROOT / "logs" / "wikidata-enrichment-utf8.log"
STATUS = ROOT / "logs" / "wikidata-enrichment-status.txt"
API = "https://www.wikidata.org/w/api.php"
UA = "VietHeritageLOD/1.0 (deterministic heritage linker)"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def emit(handle, message: str) -> None:
    line = f"[{now()}] {message}\n"
    handle.write(line)
    handle.flush()
    print(line, end="", flush=True)


def main() -> int:
    max_queries = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    records = [json.loads(line) for line in CANONICAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = [
        record for record in records
        if not (record.get("external_ids") or {}).get("wikidata")
    ][:max_queries]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    found: list[dict] = []
    missing: list[dict] = []
    session = requests.Session()
    with LOG.open("a", encoding="utf-8", newline="\n") as log:
        emit(log, f"START total_records={len(records)} candidates={len(candidates)} max_queries={max_queries}")
        STATUS.write_text(f"RUNNING\nstarted={now()}\ncandidates={len(candidates)}\nlog={LOG}\n", encoding="utf-8")
        for index, record in enumerate(candidates, 1):
            label = record["label_vi"]
            params = {
                "action": "wbsearchentities",
                "search": label,
                "language": "vi",
                "uselang": "vi",
                "type": "item",
                "limit": 10,
                "format": "json",
            }
            try:
                response = session.post(API, data=params, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
                response.raise_for_status()
                results = response.json().get("search", [])
                exact = [item for item in results if key(item.get("label", "")) == key(label) and item.get("id", "").startswith("Q")]
                if len(exact) == 1:
                    row = {"entity_id": record["entity_id"], "label_vi": label, "wikidata_id": exact[0]["id"], "method": "wikidata-exact-label", "retrieved_at": now()}
                    found.append(row)
                    emit(log, f"MATCH {index}/{len(candidates)} entity={record['entity_id']} qid={row['wikidata_id']}")
                else:
                    missing.append({"entity_id": record["entity_id"], "label_vi": label, "reason": "NO_UNIQUE_EXACT_LABEL_MATCH", "candidate_count": len(exact)})
                    emit(log, f"MISS {index}/{len(candidates)} entity={record['entity_id']} exact={len(exact)}")
            except requests.RequestException as exc:
                missing.append({"entity_id": record["entity_id"], "label_vi": label, "reason": "WIKIDATA_REQUEST_ERROR", "error": str(exc)})
                emit(log, f"ERROR {index}/{len(candidates)} entity={record['entity_id']} error={exc}")
            if index < len(candidates):
                time.sleep(0.2)
        OUTPUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in found) + ("\n" if found else ""), encoding="utf-8")
        manifest = ROOT / "data" / "raw" / "wikidata_exact_missing.jsonl"
        manifest.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in missing) + ("\n" if missing else ""), encoding="utf-8")
        emit(log, f"END matched={len(found)} missing={len(missing)} output={OUTPUT}")
        STATUS.write_text(f"FINISHED\nfinished={now()}\nmatched={len(found)}\nmissing={len(missing)}\noutput={OUTPUT}\nlog={LOG}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
