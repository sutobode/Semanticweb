from __future__ import annotations

import json
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "processed" / "canonical.jsonl"
OUTPUT = ROOT / "data" / "raw" / "wikidata_sparql_exact_enrichment.jsonl"
LOG = ROOT / "logs" / "wikidata-sparql-enrichment-utf8.log"
STATUS = ROOT / "logs" / "wikidata-sparql-enrichment-status.txt"
ENDPOINT = "https://query.wikidata.org/sparql"
UA = "VietHeritageLOD/1.0 (deterministic heritage linker)"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def emit(handle, message: str) -> None:
    line = f"[{now()}] {message}\n"
    handle.write(line)
    handle.flush()
    print(line, end="", flush=True)


def main() -> int:
    chunk_size = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    records = [json.loads(line) for line in CANONICAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing = {r["entity_id"] for r in records if (r.get("external_ids") or {}).get("wikidata")}
    candidates = [r for r in records if r["entity_id"] not in existing]
    found: dict[str, list[str]] = defaultdict(list)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as log:
        emit(log, f"START total_records={len(records)} candidates={len(candidates)} chunk_size={chunk_size}")
        STATUS.write_text(f"RUNNING\nstarted={now()}\ncandidates={len(candidates)}\nlog={LOG}\n", encoding="utf-8")
        session = requests.Session()
        for start in range(0, len(candidates), chunk_size):
            batch = candidates[start : start + chunk_size]
            labels = sorted({r["label_vi"] for r in batch}, key=key)
            values = " ".join(f'"{escape(label)}"@vi' for label in labels)
            query = f"""SELECT ?label ?item WHERE {{ VALUES ?label {{ {values} }} ?item <http://www.w3.org/2000/01/rdf-schema#label> ?label . FILTER(LANG(?label) = 'vi') }}"""
            try:
                response = session.post(ENDPOINT, data={"query": query, "format": "json"}, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=120)
                emit(log, f"BATCH start={start} size={len(batch)} http={response.status_code}")
                response.raise_for_status()
                bindings = response.json().get("results", {}).get("bindings", [])
                for binding in bindings:
                    label = binding.get("label", {}).get("value", "")
                    item = binding.get("item", {}).get("value", "")
                    if item.rsplit("/", 1)[-1].startswith("Q"):
                        found[key(label)].append(item.rsplit("/", 1)[-1])
                emit(log, f"BATCH start={start} results={len(bindings)}")
            except (requests.RequestException, ValueError) as exc:
                emit(log, f"BATCH start={start} ERROR={exc}")
            if start + chunk_size < len(candidates):
                time.sleep(2)
        rows = []
        for record in candidates:
            qids = sorted(set(found.get(key(record["label_vi"]), [])))
            if len(qids) == 1:
                rows.append({"entity_id": record["entity_id"], "label_vi": record["label_vi"], "wikidata_id": qids[0], "method": "wikidata-sparql-exact-label", "retrieved_at": now()})
        prior: dict[str, dict] = {}
        if OUTPUT.exists():
            for line in OUTPUT.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    prior[row["entity_id"]] = row
        for row in rows:
            prior[row["entity_id"]] = row
        merged_rows = list(prior.values())
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in merged_rows) + ("\n" if merged_rows else ""), encoding="utf-8")
        emit(log, f"END unique_exact_matches={len(merged_rows)} output={OUTPUT}")
        STATUS.write_text(f"FINISHED\nfinished={now()}\nmatched={len(merged_rows)}\noutput={OUTPUT}\nlog={LOG}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
