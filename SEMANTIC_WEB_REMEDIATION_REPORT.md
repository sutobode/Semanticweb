# VietHeritageLOD — Semantic Web Remediation Report

**Remediation goal:** `GOAL_PROMPT_SEMANTIC_WEB_REMEDIATION.md`
**Pre-remediation audit:** `SEMANTIC_WEB_AUDIT_REPORT.md`
**Remediation date:** 2026-09-14
**Snapshot:** `20260914T040348Z`
**Mode:** full snapshot, local Docker runtime
**Verdict:** **SUBSTANTIALLY COMPLIANT within the verified local-development profile**

This report records implementation and runtime evidence after the project was assessed as `PARTIALLY COMPLIANT`. It does not claim W3C certification or production-public dereferenceability. The verified profile uses the documented local canonical origin `http://localhost:3030` and a separate public Fuseki read endpoint on port `3031`.

## 1. Executive verdict

The three blocking findings from the audit are closed in the tested local profile:

1. The canonical resource URI now serves content-negotiated HTML, Turtle, and JSON-LD directly.
2. The public Fuseki service is query/read-only; mutation is kept on the authenticated admin service or rejected by the public service.
3. Dataset-level DCAT/PROV metadata is generated, SHACL-validated, and loaded as a fifth named graph.

The result is appropriately claimed as `SUBSTANTIALLY COMPLIANT`, rather than unconditional `COMPLIANT`, because the canonical base is a localhost development URI and the runtime still emits non-failing Neo4j warnings for relationship types absent from the current snapshot. No formal standards certification is asserted.

## 2. Scope and frozen baseline

The remediation preserved the frozen ontology contract:

- `23` OWL classes.
- `12` object properties.
- `10` datatype properties.
- `9` OWL axioms/restrictions.

The existing full snapshot was reused; raw data was not recollected or deleted. The verified scope is `100% of the selected official registry snapshot`, not every cultural fact about Vietnam.

Final snapshot metrics:

| Metric | Result |
|---|---:|
| Snapshot ID | `20260914T040348Z` |
| Registry/canonical records | `860 / 860` |
| Asserted RDF triples | `7,249` |
| Inferred closure triples | `9,358` |
| Reasoning inferred delta | `1,782` |
| Verified external links | `114` (`89` Wikidata, `25` DBpedia) |
| Wikipedia pages matched | `42` |
| SPARQL competency questions | `10/10 PASS` |
| Cypher/RDF parity | `10/10 PASS` |
| Python regression suite | `153 passed` |

## 3. Blocker closure matrix

| Audit blocker | Implementation | Final evidence | Status |
|---|---|---|---|
| Canonical URI was not dereferenceable | Explorer is bound to host port `3030`; canonical routing serves `/vietheritage/resource/{entity_id}` and `/vietheritage/ontology/`; old root aliases remain backward-compatible | Entity `registry-b043193f37c5`: HTML `200`, Turtle `200`, JSON-LD `200`, unsupported XML `406`, missing entity `404`; Turtle and JSON-LD each round-trip to `19` triples; responses include `Vary: Accept` and a self-canonical `Link` | **PASS** |
| Public Fuseki exposed mutation surfaces | `vietheritage` has only `serviceQuery` and `serviceReadGraphStore`; `vietheritage-admin` retains update/upload/read-write Graph Store for the loader; custom Shiro policy permits public reads but protects admin/mutation routes | Public query `200`; public Graph Store GET `200`; public Graph Store PUT/POST/DELETE `405`; public SPARQL Update `401`; authenticated admin query/update `200`; `fuseki-load` loaded all five artifacts | **PASS** |
| Dataset metadata was absent | Generator emits `data/rdf/dataset-metadata.ttl`; loader requires ontology, asserted data, external links, inferred closure, and metadata; dataset/activity/distribution shapes are validated | Metadata parses as `268` triples, contains exactly one `dcat:Dataset`, snapshot identifier `20260914T040348Z`, CC BY-SA license, provenance links, and `5` distributions; validation and Fuseki load pass | **PASS** |

### 3.1 Canonical URI evidence

Canonical local origin:

```text
http://localhost:3030/vietheritage/resource/registry-b043193f37c5
```

Observed responses from the direct HTTP endpoint:

| Request | Result |
|---|---|
| `Accept: text/html` | `200`, `text/html; charset=utf-8` |
| `Accept: text/turtle` | `200`, `text/turtle; charset=utf-8`, RDF parse succeeds |
| `Accept: application/ld+json` | `200`, `application/ld+json; charset=utf-8`, RDF parse succeeds |
| `Accept: application/xml` | `406` |
| Missing resource | `404` |

All three successful representations advertise `Vary: Accept`. The response `Link` header points to the same canonical resource URI. HTML canonical and alternate links use the canonical `/vietheritage/resource/` path. JSON-LD exposes `@context`, root `@id`, and root `@type`; Turtle and JSON-LD describe the same entity semantics.

The ontology URI is also served by the Explorer at:

```text
http://localhost:3030/vietheritage/ontology/
```

and the ontology representation parsed as `327` triples during the final evidence collection.

### 3.2 Fuseki boundary evidence

Documented endpoints:

```text
Public query:  http://localhost:3031/vietheritage/sparql
Public graph:  http://localhost:3031/vietheritage/data
Admin service:  http://localhost:3031/vietheritage-admin
```

The public service has no update, upload, or read-write Graph Store service declaration. The final direct probes returned:

```text
PUBLIC_QUERY       200
PUBLIC_GRAPH_GET   200
PUBLIC_PUT        405
PUBLIC_POST       405
PUBLIC_DELETE     405
PUBLIC_UPDATE    401
```

The authenticated admin service remained operational, and the final command reported:

```text
fuseki-load (full): loaded ontology,data,external-links,inferred,metadata
```

The Explorer API remains GET-only. The live application smoke test includes the public mutation rejection policy and passed `13/13`.

### 3.3 Dataset/DCAT metadata evidence

Metadata artifact:

```text
data/rdf/dataset-metadata.ttl
```

Dataset resource:

```text
http://localhost:3030/vietheritage/resource/dataset/vietheritage
```

The artifact contains `268` triples and exactly one `dcat:Dataset`. It publishes:

- Snapshot identifier `20260914T040348Z`.
- Title, Vietnamese description, CC BY-SA license, issued/modified values.
- `prov:wasGeneratedBy` activity and `prov:wasDerivedFrom` manifest.
- Official registry source URLs and source/checksum descriptions.
- Counts for registry records, canonical records, asserted triples, closure triples, inferred delta, and verified external links.
- Five distributions with public Graph Store access URLs for `ontology`, `asserted`, `external-links`, `inferred`, and `metadata` named graphs.

The five named graph inventory loaded by the admin loader is:

```text
http://localhost:3030/vietheritage/graph/ontology
http://localhost:3030/vietheritage/graph/data
http://localhost:3030/vietheritage/graph/external-links
http://localhost:3030/vietheritage/graph/inferred
http://localhost:3030/vietheritage/graph/metadata
```

No credentials, access tokens, or private keys are included in the metadata artifact.

## 4. Secondary semantic remediation

### 4.1 Asserted versus inferred semantics

`inferred.ttl` remains a closure graph by design. The API no longer labels the entire closure as novel inference:

- `asserted_triples` comes from the asserted/data graph.
- `closure_triples` represents the complete inferred closure.
- `inferred_triples` represents only novel triples not present in the asserted set.

The reasoning report records:

```json
{
  "source_triples": 7576,
  "closure_triples": 9358,
  "inferred_triples": 1782,
  "status": "PASS"
}
```

This explicitly distinguishes the ontology-plus-asserted input from closure size and inferred delta.

### 4.2 JSON-LD contract

The resource JSON-LD contract is compact-resource form: the root has `@context`, `@id`, and `@type`, while related nodes are preserved through `@included` where required. The live JSON-LD response parsed back to `19` RDF triples. Media type is `application/ld+json`, and the API/detail and direct resource representations use the same canonical identity namespace.

### 4.3 SHACL coverage

SHACL now validates both entity data and required dataset metadata. The dataset shapes cover the dataset type, snapshot identifier, title, license IRI, generation activity, activity start time, and the required five distributions. Positive and negative dataset fixtures are present in `tests/unit/test_shacl.py`.

Final validation artifacts report:

```text
reports/full/validation.json:    PASS, 860 canonical records, SHACL PASS
reports/full/rdf_validation.json: PASS, 860 canonical records, SHACL PASS
```

Missing or invalid metadata is a validation failure rather than a silently skipped artifact.

### 4.4 External-link provenance

All `114` verified link rows now carry:

- Automated reviewer/process identity.
- UTC review timestamp.
- Verification method.
- Verification reason/evidence.
- Status.

Only verified rows produce final `owl:sameAs` triples. Automated verification is identified as automated; it is not represented as human review.

### 4.5 Report and snapshot contracts

Snapshot-aware verification reads `coverage_snapshot` from the active canonical artifact, selects the matching coverage report, fails if no matching report exists, and records the snapshot ID in `reports/full/verify.json`.

The final verify artifact reports:

```json
{
  "run_mode": "full",
  "status": "PASS",
  "metrics": {
    "snapshot_id": "20260914T040348Z",
    "canonical_records": 860,
    "verified_external_links": 114,
    "cypher_passed": 10,
    "cypher_total": 10
  }
}
```

Both `validation.json` and `rdf_validation.json` are maintained as explicit report outputs, and reasoning is available in both the run report and `data/rdf/reasoning-report.json` according to the documented compatibility contract.

## 5. Final validation evidence

The final post-policy acceptance run completed successfully:

```text
fuseki-load: loaded ontology,data,external-links,inferred,metadata
linked-data-test: PASS (200, 19 triples)
app-test: 12 passed
app-smoke: 13/13 PASS
cq-test: 10/10 PASS
cypher-test: 10/10 PASS
traceability-check: PASS
docker compose config: PASS
verify (full): coverage=PASS, external_links=114, services=PASS/PASS
FINAL STATUS: PASS
```

The complete Python regression suite was also rerun after the implementation changes:

```text
153 passed in 8.11s
```

The final working-tree checks passed:

```text
git diff --check: PASS
git diff --stat -- data/raw: no output; raw data unchanged
docker compose config --quiet: PASS
```

No commit or push was performed.

## 6. Remaining gaps and operational notes

These items do not block the verified local remediation verdict but must remain explicit:

1. **Production publication:** `localhost:3030` is a local-development canonical origin. A production deployment must replace it with a stable HTTPS domain or reverse-proxy origin and regenerate/revalidate all public identity and access URLs as one controlled change.
2. **Neo4j warnings:** `cypher-test` emits warnings because the current snapshot has no instances of `LOCATED_IN`, `ASSOCIATED_WITH_PERSON`, or `PART_OF`. The parity result remains `10/10 PASS`; the warnings are retained rather than hidden.
3. **Credentials:** local admin credentials are deployment configuration and are not reproduced in this report. They must be changed for any shared environment; `.env` and secrets remain excluded from version control.
4. **Certification language:** this is an evidence-based project compliance verdict within a declared scope, not W3C certification.

## 7. Changed implementation areas

The remediation changed the canonical web router/API and smoke tests, Fuseki service/security packaging, RDF generator/loader/reasoner, SHACL and validation contracts, link provenance, verification snapshot binding, documentation, and isolated collector tests. The protected diagnostic files were not modified, and no raw release data was changed.

## 8. Final conclusion

The audit verdict `PARTIALLY COMPLIANT` is closed to **SUBSTANTIALLY COMPLIANT within the verified local-development profile**. The canonical URI, public/admin Fuseki boundary, and dataset-level RDF metadata requirements have direct implementation and runtime evidence. Semantic distinctions, JSON-LD identity, SHACL coverage, external-link provenance, and snapshot-bound reporting have also been completed and validated.
