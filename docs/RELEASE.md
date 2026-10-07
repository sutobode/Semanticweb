# VietHeritageLOD — Release Runbook

## Current verified semantic snapshot

- Snapshot ID: `20260925T034421Z`.
- Canonical records: `1,111`.
- Ontology/asserted/inferred-delta triples: `344 / 13,577 / 713,580`.
- Verified external links: `222`.
- Metadata/final-public-graph triples: `1,526 / 729,247`.
- SPARQL/Cypher/parity acceptance: `10/10 / 10/10 / 10/10 PASS`.
- Final integration: `PASS`; demo smoke: `8/8 PASS`.
- Historical collector `coverage.json` is unavailable in the current workspace; M4.4 did not rerun collection or invent a replacement coverage claim.

The Member 3 evaluation in `docs/link-evaluation.md` remains a historical evaluation of 1,068 records and 221 published links. The current artifact contains 222 links, but evaluation metrics were not rerun and are not inferred from that count.

The final acceptance evidence is generated locally in `reports/full/verify.json`; the stage log is `logs/full-pipeline-utf8.log`. Runtime reports and logs are intentionally ignored by Git.

## Historical raw data inventory

The earlier raw-data release audit recorded the inventory below. M4.4 validates the current semantic artifacts and does not reinterpret these historical collection figures:

| File | Rows | Bytes | Meaning |
|---|---:|---:|---|
| `registry_records.jsonl` | 860 | 450,099 | Official registry records |
| `registry_failures.jsonl` | 10 | 2,940 | Expected empty official sources |
| `pages.jsonl` | 42 | 150,753 | Wikipedia pages matched |
| `enrichment_failures.jsonl` | 810 | 101,379 | Missing Wikipedia enrichment manifest |
| `wikidata_exact_missing.jsonl` | 397 | 85,998 | No exact Wikidata match manifest |
| `wikidata_sparql_exact_enrichment.jsonl` | 48 | 9,651 | Wikidata SPARQL enrichment |
| `wikidata_exact_enrichment.jsonl` | 3 | 563 | Exact Wikidata enrichment |
| `dbpedia_wikidata_candidates.jsonl` | 25 | 9,681 | Explicit DBpedia/Wikidata evidence |
| `dbpedia_lookup_candidates.jsonl` | 0 | 0 | Empty candidate manifest |
| `dbpedia_exact_candidates.jsonl` | 0 | 0 | Empty candidate manifest |

The full data scan found zero credential-like hits, including private-key, cloud-key, password/secret assignment, and authorization patterns. `.env` is ignored and must remain local. Protected untracked files (`_analyze_categories.py`, `_category_analysis.txt`, `nOTE.TXT`, `tools/diagnose_full_rdf.py`) are not release artifacts.

## Reproduce and verify

From a clean environment:

```text
Copy .env.example to .env and set local-only credentials.
make setup
make test
make pipeline RUN_MODE=full
make fuseki-up
make fuseki-load RUN_MODE=full
make cq-test
make neo4j-up
make neo4j-load RUN_MODE=full
make cypher-test
make app-up
make app-smoke
make verify RUN_MODE=full
make demo-smoke
```

Expected final checks:

- Full verification → `FINAL STATUS: PASS`.
- Demo smoke → `8/8 PASS`.
- Full metrics → `1,111` canonical records, `13,577` asserted triples, `713,580` inferred delta, `222` verified external links, and `729,247` final public triples.
- Query acceptance → SPARQL `10/10`, Cypher `10/10`, parity `10/10`.

See [`docs/E2E.md`](./E2E.md) for the complete Windows PowerShell procedure.

For a faster fixture run use `make pipeline-sample`, but do so in an isolated checkout/worktree because sample and full stages, as well as some collector tests, share output paths.

## Explicit release staging policy

Only approved release paths should be staged. The raw data commit uses an explicit force-add because full data is ignored by the repository policy:

```text
git add README.md docs/RELEASE.md
git add -f data/raw/*.jsonl
git diff --cached --check
git diff --cached --stat
```

Do not use `git add .`. Never stage `.env`, credentials, user files, runtime logs/reports, diagnostic scripts, or unrelated temporary files. Do not push automatically.

## Post-release checklist

1. Review the staged file list and commit locally.
2. Keep `.env` and Docker credentials outside Git.
3. Start Fuseki and Neo4j only when needed; stop them with `make fuseki-down` and `make neo4j-down`.
4. If publishing the graph, expose only the intended Fuseki/linked-data endpoints and review the license/provenance output first.
5. Re-run `make verify RUN_MODE=full` after any data, ontology, query, or loader change.
6. Push or open a release PR only after a human reviews the staged diff and explicitly requests publication.
