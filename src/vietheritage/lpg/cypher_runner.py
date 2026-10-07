"""Deterministic Cypher CQ acceptance and RDF/LPG parity (Appendix C.5/C.6)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import requests
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from vietheritage.lpg.loader import _neo4j_config, _read_jsonl, _read_links, load_records


REPO_ROOT = Path(__file__).resolve().parents[3]
CYPHER_DIR = REPO_ROOT / "cypher"
SPARQL_DIR = REPO_ROOT / "sparql"
EXPECTED_DIR = REPO_ROOT / "data" / "fixtures" / "expected"
FIXTURE_CANONICAL = REPO_ROOT / "data" / "fixtures" / "canonical.jsonl"
FIXTURE_LINKS = REPO_ROOT / "data" / "fixtures" / "cq-links.csv"
REPORTS_DIR = REPO_ROOT / "reports"

CQ_CONTRACT = {
    "CQ01-sites-by-location.cypher": ("CQ01-sites-by-location.rq", "site"),
    "CQ02-unesco-before-year.cypher": ("CQ02-unesco-before-year.rq", "site"),
    "CQ03-sites-by-type.cypher": ("CQ03-sites-by-type.rq", "site"),
    "CQ04-sites-by-person.cypher": ("CQ04-sites-by-person.rq", "site"),
    "CQ05-sites-by-event-or-period.cypher": ("CQ05-sites-by-event-or-period.rq", "site"),
    "CQ06-top-areas.cypher": ("CQ06-top-areas.rq", "area"),
    "CQ07-persons-with-many-sites.cypher": ("CQ07-persons-with-many-sites.rq", "person"),
    "CQ08-sites-in-complex.cypher": ("CQ08-sites-in-complex.rq", "site"),
    "CQ09-external-links.cypher": ("CQ09-external-links.rq", "site"),
    "CQ10-english-label-from-snapshot.cypher": ("CQ10-english-label-from-snapshot.rq", "site"),
}


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:6]}"


def _normalize_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, float):
        text = format(Decimal(str(value)).normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        normalized = format(Decimal(text).normalize(), "f")
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
    for marker in ("/vietheritage/resource/", "/vietheritage/ontology/"):
        if marker in text:
            return text.split(marker, 1)[1]
    return text


def _normalize_rows(
    rows: list[dict[str, Any]], aliases: dict[str, str]
) -> set[tuple[tuple[str, str], ...]]:
    normalized = []
    for row in rows:
        mapped = {
            aliases.get(key, key): _normalize_value(value)
            for key, value in row.items()
        }
        normalized.append(tuple(sorted(mapped.items())))
    return set(normalized)


def _entity_ids(rows: list[dict[str, Any]]) -> list[str]:
    values: set[str] = set()
    for row in rows:
        value = row.get("entityId")
        if not isinstance(value, str) or not value:
            raise ValueError("CYPHER_ENTITY_ID_MISSING")
        values.add(value)
    return sorted(values)


def _expected_entity_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, list)
        or not payload
        or any(not isinstance(value, str) or not value for value in payload)
        or len(payload) != len(set(payload))
    ):
        raise ValueError("CYPHER_EXPECTED_INVALID")
    return sorted(payload)


def _sparql_bindings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = payload.get("results", {}).get("bindings")
    if not isinstance(bindings, list) or any(not isinstance(row, dict) for row in bindings):
        raise ValueError("SPARQL_BINDINGS_INVALID")
    return bindings


def _sparql_entity_ids(payload: dict[str, Any], variable: str) -> list[str]:
    values: set[str] = set()
    for row in _sparql_bindings(payload):
        term = row.get(variable)
        if not isinstance(term, dict) or not isinstance(term.get("value"), str):
            raise ValueError("SPARQL_ENTITY_ID_MISSING")
        values.add(_normalize_value(term))
    return sorted(values)


def _sparql_row_set(payload: dict[str, Any]) -> set[str]:
    return {
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in _sparql_bindings(payload)
    }


def _query_fuseki(
    query: str,
    *,
    request_get: Callable[..., Any] = requests.get,
    endpoint: str | None = None,
) -> tuple[dict[str, Any], int]:
    url = endpoint or (
        f"{os.getenv('FUSEKI_URL', 'http://localhost:3031').rstrip('/')}"
        f"/{os.getenv('FUSEKI_CQ_DATASET', 'vietheritage-cq')}/sparql"
    )
    response = request_get(
        url,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    status = int(getattr(response, "status_code", 200))
    response.raise_for_status()
    return response.json(), status


def _invariant(name: str, value: Any, expected: Any) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "expected": expected,
        "status": "PASS" if value == expected else "FAIL",
    }


def _check_invariants(
    transaction: Any,
    records: list[dict[str, Any]],
    links: list[dict[str, Any]],
    load_report: dict[str, Any],
) -> list[dict[str, Any]]:
    resource_count = transaction.run(
        "MATCH (n:Resource) RETURN count(n) AS value"
    ).single()["value"]
    heritage_site_count = transaction.run(
        "MATCH (n:HeritageSite) RETURN count(n) AS value"
    ).single()["value"]
    missing_properties = transaction.run(
        "MATCH (n:Resource) "
        "WHERE n.entityId IS NULL OR n.uri IS NULL OR n.labelVi IS NULL "
        "OR n.sourceUrl IS NULL OR n.retrievedAt IS NULL "
        "RETURN count(n) AS value"
    ).single()["value"]
    duplicate_ids = transaction.run(
        "MATCH (n:Resource) WITH n.entityId AS entityId, count(*) AS copies "
        "WHERE copies > 1 RETURN count(*) AS value"
    ).single()["value"]
    same_as_count = transaction.run(
        "MATCH (:Resource)-[r:SAME_AS]->(:ExternalResource) RETURN count(r) AS value"
    ).single()["value"]
    wrong_targets = transaction.run(
        "MATCH (:Resource)-[r]->(target) "
        "WHERE (type(r) = 'SAME_AS' AND NOT target:ExternalResource) "
        "OR (type(r) <> 'SAME_AS' AND NOT target:Resource) "
        "RETURN count(r) AS value"
    ).single()["value"]
    actual_pairs = {
        (row["sourceUri"], row["targetUri"])
        for row in transaction.run(
            "MATCH (source:Resource)-[:SAME_AS]->(target:ExternalResource) "
            "RETURN source.uri AS sourceUri, target.uri AS targetUri"
        ).data()
    }
    verified_pairs = {
        (link["source_uri"], link["target_uri"])
        for link in links
        if link.get("status") == "verified"
    }
    return [
        _invariant("Resource count", resource_count, len(records)),
        _invariant(
            "HeritageSite count",
            heritage_site_count,
            sum(record.get("entity_type") == "HeritageSite" for record in records),
        ),
        _invariant("Resources missing required properties", missing_properties, 0),
        _invariant("Duplicate Resource.entityId groups", duplicate_ids, 0),
        _invariant("Verified SAME_AS count", same_as_count, len(verified_pairs)),
        _invariant("SAME_AS verified pair set", sorted(actual_pairs), sorted(verified_pairs)),
        _invariant("Relationships with invalid target labels", wrong_targets, 0),
        _invariant("Loader dangling references", load_report["skipped_dangling"], 0),
    ]


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(
    *,
    request_get: Callable[..., Any] = requests.get,
    driver_factory: Callable[..., Any] = GraphDatabase.driver,
    cypher_dir: Path = CYPHER_DIR,
    sparql_dir: Path = SPARQL_DIR,
    expected_dir: Path = EXPECTED_DIR,
    reports_dir: Path = REPORTS_DIR,
    fixture_canonical: Path = FIXTURE_CANONICAL,
    fixture_links: Path = FIXTURE_LINKS,
    fuseki_endpoint: str | None = None,
) -> int:
    run_id = _run_id()
    started_at = datetime.now(timezone.utc)
    report_dir = reports_dir / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "cypher_results.json"
    rows: list[dict[str, Any]] = []
    invariants: list[dict[str, Any]] = []
    report_error: str | None = None

    expected_files = list(CQ_CONTRACT)
    actual_files = sorted(path.name for path in cypher_dir.glob("CQ*.cypher"))
    if actual_files != sorted(expected_files):
        report_error = "CYPHER_FILE_CONTRACT_MISMATCH"
    else:
        try:
            records = list(_read_jsonl(fixture_canonical))
            links = list(_read_links(fixture_links))
            uri, auth, database = _neo4j_config()
            with driver_factory(uri, auth=auth) as driver:
                with driver.session(database=database) as session:
                    session.run(
                        "CREATE CONSTRAINT resource_entity_id IF NOT EXISTS "
                        "FOR (n:Resource) REQUIRE n.entityId IS UNIQUE"
                    ).consume()
                    transaction = session.begin_transaction()
                    try:
                        transaction.run("MATCH (n) DETACH DELETE n").consume()
                        load_report = load_records(
                            transaction,
                            records,
                            links,
                            ensure_constraint=False,
                        )
                        if load_report["status"] != "PASS":
                            raise ValueError("CYPHER_FIXTURE_LOAD_FAILED")

                        for cypher_name, (sparql_name, primary_variable) in CQ_CONTRACT.items():
                            cq_id = cypher_name[:4]
                            query_started = perf_counter()
                            row: dict[str, Any] = {
                                "cq": cq_id,
                                "file": f"cypher/{cypher_name}",
                                "sparql_file": f"sparql/{sparql_name}",
                                "entity_ids": [],
                                "expected_entity_ids": [],
                                "sparql_entity_ids": [],
                                "actual_row_count": 0,
                                "expected_row_count": 0,
                                "sparql_row_count": 0,
                                "http_status": None,
                                "acceptance": False,
                                "parity": False,
                                "match": False,
                                "status": "FAIL",
                            }
                            cypher_rows: list[dict[str, Any]] = []
                            try:
                                expected_ids = _expected_entity_ids(
                                    expected_dir / f"cypher_{cq_id}.json"
                                )
                                expected_sparql = json.loads(
                                    (expected_dir / f"{cq_id}.json").read_text(encoding="utf-8")
                                )
                                sparql_text = (sparql_dir / sparql_name).read_text(encoding="utf-8")
                                actual_sparql, http_status = _query_fuseki(
                                    sparql_text,
                                    request_get=request_get,
                                    endpoint=fuseki_endpoint,
                                )
                                row["http_status"] = http_status
                                row["expected_row_count"] = len(_sparql_bindings(expected_sparql))
                                row["sparql_row_count"] = len(_sparql_bindings(actual_sparql))
                                if _sparql_row_set(actual_sparql) != _sparql_row_set(expected_sparql):
                                    raise ValueError("SPARQL_EXPECTED_MISMATCH")

                                cypher_text = (cypher_dir / cypher_name).read_text(encoding="utf-8")
                                cypher_rows = transaction.run(cypher_text).data()
                                entity_ids = _entity_ids(cypher_rows)
                                sparql_ids = _sparql_entity_ids(actual_sparql, primary_variable)
                                row.update(
                                    {
                                        "entity_ids": entity_ids,
                                        "expected_entity_ids": expected_ids,
                                        "sparql_entity_ids": sparql_ids,
                                        "actual_row_count": len(cypher_rows),
                                        "acceptance": entity_ids == expected_ids,
                                        "parity": entity_ids == sparql_ids,
                                        "match": entity_ids == sparql_ids,
                                    }
                                )
                                if not row["acceptance"]:
                                    raise ValueError("CYPHER_EXPECTED_MISMATCH")
                                if not row["parity"]:
                                    raise ValueError("LPG_RDF_MISMATCH")
                                row["status"] = "PASS"
                            except (
                                OSError,
                                KeyError,
                                TypeError,
                                ValueError,
                                Neo4jError,
                                requests.RequestException,
                            ) as exc:
                                row["error"] = str(exc)
                            finally:
                                row["duration_seconds"] = round(
                                    perf_counter() - query_started, 6
                                )
                                artifact = report_dir / f"{cq_id}.json"
                                artifact.write_text(
                                    json.dumps(
                                        {
                                            "cq": cq_id,
                                            "file": cypher_name,
                                            "rows": cypher_rows,
                                            "entity_ids": row["entity_ids"],
                                            "status": row["status"],
                                        },
                                        ensure_ascii=False,
                                        indent=2,
                                    )
                                    + "\n",
                                    encoding="utf-8",
                                )
                                row["artifact"] = str(artifact)
                            rows.append(row)

                        invariants = _check_invariants(
                            transaction,
                            records,
                            links,
                            load_report,
                        )
                    finally:
                        transaction.rollback()
        except (OSError, ValueError, Neo4jError, requests.RequestException) as exc:
            report_error = str(exc)
        except Exception as exc:
            report_error = f"CYPHER_DRIVER_ERROR: {exc}"

    passed = sum(row["status"] == "PASS" for row in rows)
    parity_passed = sum(row["parity"] for row in rows)
    invariants_passed = bool(invariants) and all(
        row["status"] == "PASS" for row in invariants
    )
    complete = (
        report_error is None
        and passed == len(CQ_CONTRACT)
        and parity_passed == len(CQ_CONTRACT)
        and invariants_passed
    )
    finished_at = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 6),
        "fixture": str(fixture_canonical),
        "fixture_isolation": "rollback_transaction",
        "queries": rows,
        "invariants": invariants,
        "passed": passed,
        "failed": len(CQ_CONTRACT) - passed,
        "total": len(CQ_CONTRACT),
        "parity_passed": parity_passed,
        "invariants_passed": invariants_passed,
        "status": "PASS" if complete else "FAIL",
    }
    if report_error:
        report["error"] = report_error
    _write_report(report_path, report)
    print(
        f"cypher-test: {passed}/{len(CQ_CONTRACT)} PASS, "
        f"parity {parity_passed}/{len(CQ_CONTRACT)} PASS -> {report_path}"
    )
    return 0 if complete else 1
