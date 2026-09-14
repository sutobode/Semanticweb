# VietHeritageLOD — Release Runbook

## Release snapshot

- Registry snapshot: `20260914T040348Z` (final post-regression collection).
- Collection result: `860` registry records; `10` expected `REGISTRY_EMPTY_SOURCE` entries for official pages returning HTTP 200 with no extractable rows.
- Registry coverage: `100%` for all valid records in the 17 configured official categories. Ten currently empty categories have `0` discovered records and are retained in the coverage manifest rather than silently omitted.
- Wikipedia enrichment: `42` matched pages; missing matches remain as registry entities.
- Downstream rebuild: `860` normalized, `0` skipped, `860` resolved, `0` identity collisions, `7,249` RDF triples, `1,782` inferred triples, `114/114` reviewed links verified.
- External links: `89` Wikidata and `25` DBpedia verified links.

The final acceptance evidence is generated locally in `reports/full/verify.json`; the stage log is `logs/full-pipeline-utf8.log`. Runtime reports and logs are intentionally ignored by Git.

## Raw data inventory

The release raw snapshot contains the JSONL files under `data/raw/`. The audit before staging recorded:

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
```

Expected final checks:

- `python -m pytest -q` → `149 passed`.
- Full verification → `FINAL STATUS: PASS`.
- Full metrics → `860` canonical/registry records, `114` verified external links, `10/10` Cypher checks.

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
