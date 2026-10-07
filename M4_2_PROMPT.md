Implement MEMBER 4 PHASE M4.2: CANONICAL DATA -> NEO4J LPG.

M4.1 is COMPLETE.
Do NOT modify Fuseki, SPARQL CQs, ontology, reasoning, enrichment,
external-link generation, Web Explorer, or Cypher queries.

Goal:
Make the current Neo4j loader conform exactly to the existing
PROJECT_SPEC Appendix C LPG contract and load the current production
snapshot idempotently.

# Authority

Use:
1. PROJECT_SPEC.md Appendix C
2. current canonical schema/data
3. current verified-link data
4. existing tests/code

Do NOT invent a new LPG design.

Neo4j is a projection from canonical data, NOT from Turtle/RDF.
RDF/Fuseki remains authoritative for semantic reasoning.

# Inspect only

- PROJECT_SPEC.md Appendix C
- data/processed/canonical.jsonl
- schema/canonical-record.schema.json
- current verified-link manifest/data
- src/vietheritage/lpg/loader.py
- src/vietheritage/cli.py
- docker-compose.yml
- .env.example
- existing LPG/Neo4j tests

Do not broadly inspect unrelated code.

# Known Phase 0 drift to fix

Current loader incorrectly:
- uses common label `Entity` instead of `Resource`
- uses `label` instead of `labelVi`
- omits `uri`
- omits `sourceUrl`
- omits `retrievedAt`
- lacks required uniqueness constraint
- does not map site subtype labels from `site_types`
- omits `built_by -> BUILT_BY`
- uses `External` instead of `ExternalResource`
- omits `SAME_AS.targetDataset`
- does not report created/merged relationship counts
- does not report dangling references
- has report-format drift from Appendix C
- may use Neo4j auth variables inconsistent with Compose

Fix these with the minimum necessary changes.

# Required LPG contract

Common internal node label:

    Resource

Use canonical type labels as specified by Appendix C, including appropriate
labels such as:

    HeritageSite
    AdministrativeArea
    HistoricalPerson
    ...

For site subtype arrays, add the corresponding subtype labels where the
Appendix C/current semantic contract requires them.

Required core properties include:

    entityId
    uri
    labelVi
    sourceUrl
    retrievedAt

Preserve any other Appendix-C-required fields.

Create the required uniqueness constraint:

    Resource.entityId

Relationships must follow the existing mapping contract, including at least:

    LOCATED_IN
    PART_OF
    HAS_MEMBER
    ASSOCIATED_WITH_PERSON
    ASSOCIATED_WITH_EVENT
    BELONGS_TO_PERIOD
    BUILT_BY
    RECOGNIZED_BY
    HAS_ARCHITECTURAL_STYLE
    SAME_AS

Do not infer OWL-only relationships inside Neo4j unless Appendix C explicitly
requires materialized values from canonical data.

External identity nodes:

    ExternalResource

`SAME_AS` must preserve required metadata such as:

    targetDataset

Only verified external links may become SAME_AS relationships.

# Loading behavior

The loader must be:

- deterministic
- idempotent
- safe to run repeatedly
- explicit about dangling references
- explicit about malformed/unsupported records
- free of duplicate Resource nodes

Second execution against the same snapshot must not create duplicate nodes or
relationships.

Do not silently drop dangling references.
Report them.

# Authentication/config

Align Compose and Python configuration so one documented set of environment
variables controls Neo4j credentials consistently.

Do not hard-code credentials.

Expected runtime:

- Neo4j 5.26.0
- Bolt: bolt://localhost:7687
- Browser: http://localhost:7474

# Reporting

Produce the Appendix-C-compatible load report.

At minimum report:

- canonical records processed
- Resource nodes created/merged
- counts by important node label
- ExternalResource nodes
- relationships created/merged by type
- SAME_AS count
- dangling references
- skipped/rejected records
- load status
- timing if required by the existing contract

Use actual values from the current enriched snapshot.

# Focused tests

Add only M4.2 tests needed to prove:

1. `Resource.entityId` uniqueness constraint exists.
2. Required core properties are present.
3. Canonical entity types map to required Neo4j labels.
4. HeritageSite subtype labels map correctly.
5. All required relationship mappings work.
6. `built_by -> BUILT_BY`.
7. Verified external links produce:
       Resource -[:SAME_AS]-> ExternalResource
8. `targetDataset` is preserved.
9. Dangling references are reported.
10. Repeated loading creates no duplicate nodes/relationships.
11. Neo4j authentication/config is consistent.

Do NOT write SPARQL/Cypher parity tests yet.

# Runtime acceptance

After implementation:

1. Start Neo4j.
2. Reset its development/test database only if required for deterministic
   acceptance.
3. Load the CURRENT canonical + verified-link production snapshot.
4. Run the same load a second time.
5. Confirm no duplicate growth.
6. Run focused M4.2 tests.
7. Run `git diff --check`.

Do NOT rerun:
- collection/enrichment
- RDF generation
- reasoning
- Fuseki loading
- external linking
- SPARQL CQ acceptance

# Acceptance criteria

M4.2 is COMPLETE only if:

- Neo4j 5.26.0 runs successfully.
- Appendix C mapping is implemented.
- common internal label is `Resource`.
- required properties are present.
- uniqueness constraint exists.
- required relationships are mapped.
- `BUILT_BY` is supported.
- verified external links use `ExternalResource` + `SAME_AS`.
- `targetDataset` is preserved.
- dangling references are explicitly reported.
- load report matches contract.
- first production load succeeds.
- second identical load is idempotent.
- focused tests PASS.
- `git diff --check` PASS.

Do NOT implement Cypher CQ files in this phase.

# Final output

# MEMBER 4 PHASE M4.2 FINAL REPORT

## Status
COMPLETE / PARTIAL / BLOCKED

## Files changed

## Neo4j runtime
- version
- Bolt URL
- Browser URL
- authentication configuration

## LPG mapping
| Canonical concept | Neo4j representation |

## Production load counts
- canonical records
- Resource nodes
- ExternalResource nodes
- counts by major labels
- relationships by type
- SAME_AS
- dangling references
- rejected/skipped

## Idempotency
First load:
Second load:
Duplicate growth:

## Tests
| Check | Status |

## Remaining issues

## M4.3 readiness

End exactly with:

READY FOR M4.3

or

NOT READY FOR M4.3: <reason>

Efficiency:
- reuse current loader
- follow Appendix C exactly
- no broad audit
- no unrelated refactor
- no Cypher/parity work
- stop once M4.2 acceptance passes