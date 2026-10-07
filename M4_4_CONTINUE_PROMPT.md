Resume MEMBER 4 PHASE M4.4 from the CURRENT partial state.

Previous interruption check concluded:

SAFE TO CONTINUE

Already DONE:
- Fuseki healthy
- Neo4j healthy
- Explorer healthy
- UX audit PASS
- Explorer smoke 16/16 PASS
- real production Linked Data dereference PASS
- reasoning refreshed
- semantic validation PASS
- SHACL PASS
- SPARQL CQ 10/10 PASS
- Cypher CQ 10/10 PASS
- parity 10/10 PASS
- production Neo4j load/idempotency PASS
- git diff --check previously PASS

Current production metrics:
- canonical: 1111
- ontology triples: 344
- asserted triples: 13577
- inferred delta: 713580
- external links: 222
- metadata triples: 1526
- final public graph: 729247

Current remaining issue:
`reports/full/final_integration.json` is still FAIL because it predates the latest source fixes for:
1. compact JSON-LD identifier handling;
2. unavailable historical `coverage.json`.

Do NOT restart M4.4 from scratch.

Do NOT redesign:
- ontology
- RDF
- reasoning
- Fuseki
- Neo4j
- SPARQL
- Cypher
- parity
- Explorer architecture

# Resume tasks

## 1. Add focused tests first

Read only:
- `src/vietheritage/reporting/verify.py`
- `tests/unit/test_final_integration.py`

Add the minimum focused tests for:

A. compact JSON-LD identifiers
- verify the current JSON-LD semantic check accepts the compact-ID form that the Explorer actually returns;
- still reject genuinely incorrect identifiers.

B. unavailable historical coverage report
- if historical `coverage.json` does not exist, final verification must not fail solely because that historical artifact is unavailable;
- report it as unavailable/not-applicable according to current contract;
- do not invent coverage values.

Do not broaden the test suite.

Run focused tests.

If they fail:
fix only the relevant verifier branch.

## 2. Re-run lightweight runtime checks

Confirm existing services are still healthy:

- Fuseki
- Neo4j
- Explorer

Run only lightweight checks needed before final verification:
- Explorer health
- one real production Linked Data URI
- Turtle
- JSON-LD/content negotiation if required

Do not rerun Member 1–3 pipelines unnecessarily.

## 3. Re-run final verification

Run the existing final verification command or exact CLI equivalent.

Require:

    FINAL STATUS: PASS

Inspect the newly generated final integration report.

The report must correctly include current evidence for:

- production metrics
- reasoning
- semantic validation
- SHACL
- Fuseki
- SPARQL 10/10
- Neo4j
- Cypher 10/10
- parity 10/10
- Explorer
- Linked Data dereference

Do not reuse stale FAIL status.

## 4. Run demo smoke

Read:
- `src/vietheritage/reporting/demo_smoke.py`
- relevant Make target

Run the existing eight-step demo smoke.

Require all steps PASS.

Produce the actual runtime `demo_smoke.json` report.

Do not create another parallel demo workflow.

## 5. Final focused verification

Run:
- focused final integration tests
- relevant Explorer tests if needed
- live integration checks only if final verification depends on them
- `git diff --check`

Avoid full unrelated test suites unless required by current project contract.

## 6. Documentation alignment

ONLY after final runtime PASS:

Update stale final facts in:
- README.md
- PLAN.md
- relevant demo/release docs only if they contain stale runtime facts

Use verified current values only.

Update where applicable:
- service URLs
- launch commands
- 1111 canonical records
- 13577 asserted triples
- 713580 inferred delta
- 222 external links
- 729247 final graph
- SPARQL 10/10
- Cypher 10/10
- parity 10/10
- Member 4 COMPLETE
- final integration PASS

Do NOT rewrite historical planning sections.

If any Member 3 evaluation document remains stale, report it separately rather
than fabricating updated evaluation results.

# Acceptance criteria

M4.4 is COMPLETE only if:

- focused compact-JSON-LD tests PASS
- missing-coverage behavior tests PASS
- final verification PASS
- final machine-readable integration report says PASS
- demo smoke PASS
- demo_smoke runtime report exists
- Explorer/Fuseki/Neo4j remain healthy
- SPARQL 10/10 remains PASS
- Cypher 10/10 remains PASS
- parity 10/10 remains PASS
- final integration tests PASS
- git diff --check PASS
- runtime docs aligned with verified evidence

# Final output

# MEMBER 4 PHASE M4.4 FINAL REPORT

## Status
COMPLETE / PARTIAL / BLOCKED

## Files changed

## Fixes completed
- compact JSON-LD
- unavailable coverage handling

## Runtime services
| Service | Version | URL | Status |

## Production snapshot
- canonical
- ontology triples
- asserted triples
- inferred delta
- external links
- metadata triples
- final graph

## Final verification
- command
- status
- report path

## Demo smoke
| Step | Status |

## Semantic/query acceptance
| Component | Status |
- reasoning
- semantic validation
- SHACL
- SPARQL
- Cypher
- parity

## Tests

## Documentation updated

## Remaining limitations
Only real non-blocking items.

## Final project readiness

End exactly with:

FINAL STATUS: PASS

or

FINAL STATUS: FAIL — <reason>

Efficiency:
- continue from current worktree
- no broad audit
- no reimplementation
- no unnecessary regeneration
- no unrelated refactor
- stop immediately once final acceptance is proven