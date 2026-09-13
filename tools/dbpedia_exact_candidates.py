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
OUTPUT = ROOT / "data" / "raw" / "dbpedia_exact_candidates.jsonl"
LOG = ROOT / "logs" / "dbpedia-enrichment-utf8.log"
STATUS = ROOT / "logs" / "dbpedia-enrichment-status.txt"
ENDPOINT = "https://dbpedia.org/sparql"
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
    chunk_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    records = [json.loads(line) for line in CANONICAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = records
    resources: dict[str, set[str]] = defaultdict(set)
    labels_by_key: dict[str, str] = {}
    with LOG.open("a", encoding="utf-8", newline="\n") as log:
        emit(log, f"START total_records={len(records)} chunk_size={chunk_size}")
        STATUS.write_text(f"RUNNING\nstarted={now()}\ncandidates={len(candidates)}\nlog={LOG}\n", encoding="utf-8")
        session = requests.Session()
        for start in range(0, len(candidates), chunk_size):
            batch = candidates[start : start + chunk_size]
            labels = sorted({r["label_vi"] for r in batch}, key=key)
            for label in labels:
                labels_by_key[key(label)] = label
            values = " ".join(f'"{escape(label)}"@vi' for label in labels)
            query = f"""SELECT ?label ?resource WHERE {{ VALUES ?label {{ {values} }} ?resource <http://www.w3.org/2000/01/rdf-schema#label> ?label . FILTER(LANG(?label) = 'vi') }}"""
            try:
                response = session.get(ENDPOINT, params={"query": query, "format": "json"}, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=120)
                emit(log, f"BATCH start={start} size={len(batch)} http={response.status_code}")
                response.raise_for_status()
                bindings = response.json().get("results", {}).get("bindings", [])
                for binding in bindings:
                    label = binding.get("label", {}).get("value", "")
                    resource = binding.get("resource", {}).get("value", "")
                    if resource.startswith("http://dbpedia.org/resource/"):
                        resources[key(label)].add(resource)
                emit(log, f"BATCH start={start} results={len(bindings)}")
            except (requests.RequestException, ValueError) as exc:
                emit(log, f"BATCH start={start} ERROR={exc}")
            if start + chunk_size < len(candidates):
                time.sleep(2)
        rows = []
        for record in records:
            matches = sorted(resources.get(key(record["label_vi"]), set()))
            if len(matches) == 1:
                rows.append({"entity_id": record["entity_id"], "label_vi": record["label_vi"], "uri": matches[0], "label": labels_by_key.get(key(record["label_vi"]), record["label_vi"]), "score": 1.0, "distance_km": None, "type_compatible": True, "method": "dbpedia-exact-label"})
        OUTPUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
        emit(log, f"END unique_candidates={len(rows)} output={OUTPUT}")
        STATUS.write_text(f"FINISHED\nfinished={now()}\nunique_candidates={len(rows)}\noutput={OUTPUT}\nlog={LOG}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
