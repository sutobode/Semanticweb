from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "processed" / "canonical.jsonl"
OUTPUT = ROOT / "data" / "raw" / "dbpedia_wikidata_candidates.jsonl"
STATUS = ROOT / "logs" / "dbpedia-wikidata-link-status.txt"
ENDPOINT = "http://dbpedia.org/sparql"
UA = "VietHeritageLOD/1.0 (deterministic linker)"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _query(qids: list[str]) -> dict[str, set[str]]:
    values = " ".join(f"<http://www.wikidata.org/entity/{qid}>" for qid in qids)
    query = f"""PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?resource ?qid WHERE {{
  ?resource owl:sameAs ?qid .
  VALUES ?qid {{ {values} }}
  FILTER(STRSTARTS(STR(?resource), "http://dbpedia.org/resource/"))
}}"""
    response = requests.get(
        ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
        timeout=180,
    )
    response.raise_for_status()
    result: dict[str, set[str]] = {}
    for binding in response.json().get("results", {}).get("bindings", []):
        qid = binding.get("qid", {}).get("value", "").rsplit("/", 1)[-1]
        resource = binding.get("resource", {}).get("value", "")
        if qid.startswith("Q") and resource.startswith("http://dbpedia.org/resource/"):
            result.setdefault(qid, set()).add(resource)
    return result


def main() -> int:
    records = [
        json.loads(line)
        for line in CANONICAL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    qids = sorted({
        (record.get("external_ids") or {}).get("wikidata")
        for record in records
        if (record.get("external_ids") or {}).get("wikidata")
    })
    by_qid = _query(qids)
    retrieved_at = now()
    candidates: list[dict[str, Any]] = []
    for record in records:
        qid = (record.get("external_ids") or {}).get("wikidata")
        resources = sorted(by_qid.get(qid, set()))
        if len(resources) != 1:
            continue
        candidates.append({
            "entity_id": record["entity_id"],
            "label_vi": record["label_vi"],
            "uri": resources[0],
            "score": 1.0,
            "distance_km": None,
            "type_compatible": True,
            "method": "dbpedia-wikidata-sameas",
            "wikidata_id": qid,
            "evidence": "DBpedia HTTP SPARQL explicit owl:sameAs to the canonical Wikidata QID",
            "retrieved_at": retrieved_at,
        })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in candidates),
        encoding="utf-8",
    )
    STATUS.write_text(
        f"FINISHED\nfinished={retrieved_at}\nqids={len(qids)}\n"
        f"explicit_dbpedia_qids={len(by_qid)}\ncandidates={len(candidates)}\n"
        f"output={OUTPUT}\n",
        encoding="utf-8",
    )
    print(f"dbpedia-wikidata-candidates: {len(candidates)} candidates from {len(by_qid)} explicit QID mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
