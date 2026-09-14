# VietHeritageLOD — Offline Semantic Web Demo Runbook

## Scope

This demo uses the existing full snapshot and local Docker services. It does not call the official registry, Wikipedia, Wikidata, or DBpedia. The RDF graph, ontology, reasoning output, and Fuseki remain the source of truth; the Explorer is a read-only presentation layer.

Current local endpoints:

```text
Explorer:       http://localhost:3030
API config:     http://localhost:3030/api/config
Resource:       http://localhost:3030/vietheritage/resource/{entity_id}
SPARQL query:   http://localhost:3031/vietheritage/sparql
Graph Store:    http://localhost:3031/vietheritage/data
```

Current snapshot:

```text
snapshot_id: 20260914T040348Z
canonical_records: 860
asserted_triples: 7249
inferred_closure_triples: 9358
inferred_delta_triples: 1782
verified_external_links: 114
```

## 1. Prerequisites and safe setup

Required:

- Python `>=3.12,<3.14`.
- Docker Desktop and Docker Compose v2.
- GNU Make.
- A checkout containing the committed RDF artifacts and local `.env`.

Create local configuration without committing it:

```powershell
Copy-Item .env.example .env
# Set local-only Fuseki/Neo4j credentials in .env.
```

Do not run collection or external-link stages during this offline demo. Do not run reset commands against a release volume.

## 2. Start and preflight

```powershell
make fuseki-up
make fuseki-load RUN_MODE=full
make app-up
make ux-audit
```

Expected result:

```text
ux-audit: PASS (... runtime checks, ... static accessibility checks)
```

The audit writes machine-readable evidence under:

```text
reports/<run_id>/ux_audit.json
reports/<run_id>/accessibility.json
reports/<run_id>/performance.json
reports/<run_id>/visual_regression.json
reports/<run_id>/demo.json
```

The generated reports contain the active snapshot ID, commit SHA, local endpoints, checks, timings, warnings, and evidence paths. Runtime reports are local evidence and are not release data.

Manual preflight checks:

```powershell
Invoke-RestMethod http://localhost:3030/api/config
Invoke-RestMethod http://localhost:3030/api/health
Invoke-RestMethod http://localhost:3030/api/stats
```

Preflight must show `read_only: true`, a canonical resource template, a public SPARQL endpoint, and a healthy Fuseki-backed dataset.

## 3. Five-to-ten-minute demo script

### Step A — Visitor search

1. Open `http://localhost:3030`.
2. Use **Tìm kiếm**.
3. Search for `Huế`.
4. Optionally filter by entity type, category, location, or year.
5. Show the result count, canonical URI, RDF type badges, and empty-state behavior by using an unlikely term.

Expected result: results are loaded from the RDF-backed API, with no raw JSONL access from the browser.

### Step B — Researcher entity detail

1. Open `registry-b043193f37c5` or select a search result.
2. Show the canonical resource URI.
3. Use **Sao chép URI** or open the URI directly.
4. Show ontology types and categories.
5. Show source/derivation links and verified external identity links.
6. Expand:
   - `Asserted từ dữ liệu nguồn`;
   - `Inferred bởi reasoning (novel)`;
   - `Closure graph`.
7. Open Turtle and JSON-LD in separate tabs.

Expected result: the UI distinguishes asserted, novel inferred, and closure triples and displays the named graph for each triple.

### Step C — Power-user query

1. Open **Competency Questions**.
2. Select a query and show its SHA-256 contract hash.
3. Run the query.
4. Open the public SPARQL endpoint if a custom read query is needed.
5. Confirm the UI does not provide an update form or arbitrary mutation route.

Expected result: only allowlisted CQ templates run through the read-only API; public Fuseki query works while public writes are rejected.

### Step D — Representation and accessibility

1. Navigate the main UI using only `Tab`, `Shift+Tab`, `Enter`, and `Space`.
2. Show the visible focus ring and skip link.
3. Resize to a narrow viewport or use browser zoom.
4. Trigger an empty result and a service/API error state if available.
5. Confirm loading/status messages are announced through live regions.

Expected result: the primary visitor journey remains operable without a mouse and does not lose the canonical RDF links at narrow widths.

## 4. Offline resilience/recovery

If Explorer is unavailable:

```powershell
docker compose ps
make app-up
```

If Fuseki is unavailable:

```powershell
make fuseki-up
make fuseki-load RUN_MODE=full
```

Then rerun:

```powershell
make ux-audit
```

The UI should show an actionable error rather than a blank page. An empty result is not the same as a Fuseki/API error.

## 5. Acceptance commands

```powershell
make app-test
make app-smoke
make ux-audit
make linked-data-test
make cq-test
make traceability-check
make verify RUN_MODE=full
```

Required results:

- `app-test` passes;
- `app-smoke` passes all checks;
- `ux-audit: PASS`;
- linked-data test passes with HTTP `200` and parseable RDF;
- CQ and traceability checks pass;
- final verification reports `FINAL STATUS: PASS`.

## 6. Teardown

Stop services without deleting volumes or release artifacts:

```powershell
make app-down
make fuseki-down
```

Do not use `docker compose down -v`, `fuseki-reset`, or `neo4j-reset` during a release demo unless the volume is disposable and explicitly backed up.


## 7. Browser-backed UX evidence

The repository does not add a browser package to the Python runtime. For a repeatable local audit, install the exact pinned Playwright tool outside the checkout:

```powershell
$temp = Join-Path $env:TEMP 'vietheritage-ux-playwright'
New-Item -ItemType Directory -Force $temp | Out-Null
npm install --prefix $temp --no-save playwright@1.55.0
npx --yes playwright@1.55.0 install chromium
$env:NODE_PATH = Join-Path $temp 'node_modules'
node tools/browser_ux_audit.cjs
```

The browser audit runs Chromium headless at `320x800`, `768x1024`, `1280x800`, and `1440x900`; checks horizontal overflow and accessible control names; navigates search and entity detail with keyboard activation; verifies canonical/Turtle/JSON-LD links and asserted/inferred labels; and simulates a Fuseki/API failure to check the error state.

Expected result:

```text
browser-ux-audit: PASS (7/7)
```

It writes `browser_ux.json`, `visual_regression.json`, and deterministic viewport screenshots under a snapshot-bound `reports/<run_id>/` directory. The automated browser result does not replace a human screen-reader audit.
