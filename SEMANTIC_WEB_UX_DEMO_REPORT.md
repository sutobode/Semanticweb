# VietHeritageLOD — Semantic Web UX and Demo Report

**Goal:** `GOAL_PROMPT_SEMANTIC_WEB_UX_DEMO.md`
**Snapshot:** `20260914T040348Z`
**Evidence mode:** local Docker services, offline from external data sources
**Verdict:** **FUNCTIONALLY COMPLETE and UX-ready in the verified local profile**

The Explorer now provides a semantic-aware user experience for visitors, researchers, and power users. It remains a read-only presentation layer over RDF/Fuseki. The report does not claim W3C certification or a formal WCAG 2.2 AA conformance audit.

## 1. Before and after

Before this iteration, the local Explorer was functional but had insufficient evidence and several UX gaps: limited semantic discoverability, stale/configured endpoint links, nested form labels, weak focus/live-region handling, no machine-readable UX audit, no reproducible demo runbook, and no real viewport/keyboard evidence.

After this iteration:

- UI endpoint links are obtained from read-only `/api/config` and use the published dataset/resource identity.
- Entity detail explicitly exposes canonical URI, ontology types, categories, provenance, verified identity links, asserted triples, novel inferred triples, closure triples, and named graph identifiers.
- Search supports labeled filters for Vietnamese keyword, entity type, registry category, location, and year.
- Explorer markup has a skip link, semantic landmarks, explicit labels, live regions, focus management, error/retry states, reduced-motion support, and responsive styling.
- API mutation methods `POST`, `PUT`, `PATCH`, and `DELETE` return `405` with `Allow: GET`.
- Offline demo and audit commands are documented and produce snapshot-bound evidence.

## 2. Semantic UX acceptance

| Criterion | Evidence | Result |
|---|---|---|
| Visitor search journey | `app-smoke: 16/16 PASS`; browser search via keyboard and Vietnamese `Huế` path | PASS |
| Researcher URI/provenance journey | Direct resource HTML/Turtle/JSON-LD checks; browser detail check `canonical`, `turtle`, `jsonld`, `provenance` all true | PASS |
| Asserted/inferred/closure semantics | Direct HTML and browser checks verify all three labels; each triple displays graph identifier | PASS |
| Verified identity distinction | UI labels `Verified external identity` and `verified`; API retains `owl:sameAs` semantics | PASS |
| Power-user CQ journey | Allowlisted CQ route `200`; query catalogue has 10 items and SHA-256 contract hashes | PASS |
| Read-only boundary | API mutation methods all `405`; public Graph Store writes `405`; public SPARQL Update `401` | PASS |
| Canonical representations | HTML `200`, Turtle `200`, JSON-LD `200`, missing resource `404`, unsupported XML `406` | PASS |

The UI does not read raw JSONL. Its data path remains UI → API → Fuseki/RDF graph → canonical URI/predicates/named graph.

## 3. Accessibility evidence

Static accessibility audit:

```text
ux-audit: PASS (14/14 runtime checks, 11/11 static accessibility checks)
```

Static checks include:

- `lang="vi"` and viewport metadata;
- skip link and `main` landmark;
- labeled navigation;
- `aria-live`, `aria-busy`, and alert states;
- explicit input/select labels;
- visible `:focus-visible` styling;
- reduced-motion media rule;
- responsive CSS;
- accessible error alerts.

Browser-backed evidence using Chromium via pinned Playwright `1.55.0`:

```text
browser-ux-audit: PASS (7/7)
```

The browser audit verified keyboard navigation to search, keyboard activation of the result/detail path, an accessibility-tree snapshot, named controls, live result region, canonical/Turtle/JSON-LD links, semantic asserted/inferred/provenance labels, simulated network-error alert, and zero browser console errors.

This is strong automated and keyboard evidence, but it is **not a formal WCAG 2.2 AA certification**. A human screen-reader audit remains a documented follow-up.

## 4. Responsive and visual evidence

Browser evidence covered:

```text
320x800
768x1024
1280x800
1440x900
```

All four viewports passed:

- no horizontal overflow;
- `scrollWidth == viewport width`;
- no unnamed buttons;
- no images missing `alt` (the current UI has no image content);
- `main` landmark present;
- labeled navigation present.

Deterministic screenshots were written under:

```text
reports/20260914T094900Z/screenshots/
```

The machine-readable visual artifact is:

```text
reports/20260914T094900Z/visual_regression.json
```

## 5. Performance and resilience

The local audit uses a documented `3000 ms` per-request budget and three samples per flow. Final report:

```text
reports/20260914T094542Z/performance.json
```

Measured p50/p95 values were within the local budget:

| Flow | p50 | p95 | HTTP |
|---|---:|---:|---|
| Home | `2038.24 ms` | `2038.24 ms` | `200` |
| Search | `2186.95 ms` | `2186.95 ms` | `200` |
| Entity | `2056.16 ms` | `2056.16 ms` | `200` |
| CQ | `2078.80 ms` | `2078.80 ms` | `200` |

These are local measurements, not production SLAs. The browser audit simulated a `503` API/Fuseki dependency failure and verified one accessible `role="alert"` error state. Empty result, loading, retry, and malformed/unavailable response paths are covered by client behavior and live audit checks.

## 6. Reproducible offline demo

Runbook:

```text
docs/DEMO.md
```

Commands:

```powershell
make fuseki-up
make fuseki-load RUN_MODE=full
make app-up
make ux-audit
make app-smoke
```

The runbook covers prerequisites, local-only credentials, preflight, a visitor/researcher/power-user script, canonical RDF representations, public write rejection, recovery, offline behavior, and safe teardown. The audit writes:

```text
reports/<run_id>/ux_audit.json
reports/<run_id>/accessibility.json
reports/<run_id>/performance.json
reports/<run_id>/visual_regression.json
reports/<run_id>/demo.json
```

The active snapshot ID is recorded in each Python audit artifact and in browser evidence. No external registry or enrichment endpoint is called by the UX audit/demo smoke.

## 7. Full regression and Semantic Web acceptance

Final validation after the UX changes:

```text
python -m pytest -q                         155 passed
linked-data-test                            PASS (200, 19 triples)
app-test                                    14 passed
app-smoke                                   16/16 PASS
ux-audit                                    14/14 runtime, 11/11 static PASS
browser-ux-audit                            7/7 PASS
cq-test                                     10/10 PASS
cypher-test                                 10/10 PASS
traceability-check                          PASS
docker compose config --quiet                PASS
make verify RUN_MODE=full                   FINAL STATUS: PASS
```

The full verify artifact retained the Semantic Web metrics: `860` canonical records, `114` verified external links, `10/10` Cypher checks, and services `PASS/PASS`.

Neo4j still emits known warnings for absent `LOCATED_IN`, `ASSOCIATED_WITH_PERSON`, and `PART_OF` relationship types. The parity result remains `10/10 PASS`.

## 8. Changed files and scope safety

Implementation/documentation changes:

- `src/vietheritage/web/api.py`
- `src/vietheritage/web/server.py`
- `src/vietheritage/web/smoke.py`
- `src/vietheritage/web/static/app.js`
- `src/vietheritage/web/static/index.html`
- `src/vietheritage/web/static/styles.css`
- `tests/unit/test_web_api.py`
- `tests/unit/test_web_server.py`
- `tools/ux_audit.py`
- `tools/browser_ux_audit.cjs`
- `Makefile`
- `docs/DEMO.md`
- `docs/UX_DESIGN.md`
- `docs/E2E.md`
- `docs/USER_GUIDE.md`
- `docs/API.md`
- `README.md`

Frozen ontology and RDF source-of-truth were not changed. Raw data and protected diagnostic files were not changed. Runtime reports and screenshots remain generated evidence and are not source data.

## 9. Remaining limitations

1. The canonical origin is still `localhost` in the local profile; production requires a stable HTTPS domain and a full URI/deployment revalidation.
2. Automated browser accessibility evidence does not replace a human screen-reader audit.
3. The performance budget is a local development budget, not a production SLA.
4. Formal visual diff approval and human UX review are still release-review activities even though deterministic screenshots and browser structural checks pass.

## 10. Conclusion

The UX/demo goal is **FUNCTIONALLY COMPLETE** for the verified local Semantic Web profile. Visitor, researcher, and power-user journeys are implemented and evidenced without weakening RDF semantics, canonical identity, provenance, reasoning distinctions, or read-only service boundaries. The remaining items are explicitly scoped production/accessibility review steps, not hidden failures.
