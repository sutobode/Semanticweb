# VietHeritageLOD — Member 2 Data Coverage Enrichment Prompt

You are performing a bounded Member 2 DATA COVERAGE ENRICHMENT round for VietHeritageLOD.

This task is NOT ontology design.
Do NOT modify ontology semantics, axioms, namespaces, reasoning rules, or validators.

# Current authoritative snapshot

Ontology version: 1.7.1

Member 1: COMPLETE
Member 2 core enrichment: COMPLETE

Current ontology inventory:
- 24 project-owned classes
- 12 object properties
- 10 datatype properties

Current semantic contract:
- AX-001...AX-011 PASS
- AX-017 PASS

Current production baseline:
- canonical records: 1088
- asserted triples: 13277
- external links: 222

Already completed enrichment includes:
- Đình Thái Khê locatedIn Hà Nội
- Đường Trường Sơn / Đường Hồ Chí Minh multi-area locatedIn
- Thành Nhà Hồ HeritageComplex + 3 hasMember
- Tháp Nhạn:
  - ReligiousSite
  - 2 ArchitecturalStyle
  - 1 HistoricalPeriod
- 1 hasHistoricalSuccessor edge
- 1 asserted hasRelatedSite pair

Do NOT redo these.

# Goal

Increase DATA COVERAGE for underrepresented ontology classes/properties using real, authoritative, source-backed Vietnamese cultural-heritage data.

This is intended to make the dataset less sparse before final reporting/demo.

Priority targets:

| Class / property | Current approximate coverage | Desired target |
|---|---:|---:|
| HeritageComplex | 1 | 3–5 |
| ArchitecturalStyle | 2 | 5–10 |
| HistoricalPeriod | 1 | 5–10 |
| ReligiousSite | 1 | 10–30 |
| HistoricalEvent | 6 | 10–20 |
| hasRelatedSite | 1 asserted pair | 5–10 asserted pairs |
| hasHistoricalSuccessor | 1 | 3–5 |

These are TARGET RANGES, not quotas.

Do NOT fabricate weak entities merely to reach the number.

Semantic quality and provenance are more important than counts.

# Authoritative source priority

Prefer:

1. Cục Di sản Văn hóa
2. UNESCO World Heritage Centre
3. Bảo tàng Lịch sử Quốc gia
4. official central/local government heritage sources
5. other official institutional cultural-heritage sources

Do NOT use:
- blogs
- tourism websites
- unsourced aggregators

Wikipedia/Wikidata may assist identity matching but must NOT be the sole canonical evidence for new domain facts.

# Important modeling rules

## HeritageComplex

Only create a HeritageComplex when the source clearly describes a property/complex/group composed of identifiable heritage components.

Potential strong candidates to investigate:
- Complex of Hué Monuments
- Yên Tử–Vĩnh Nghiêm–Côn Sơn, Kiếp Bạc
- other UNESCO serial/complex properties

Do NOT retype an existing HeritageSite into HeritageComplex if identity or granularity is ambiguous.

Prefer:
    distinct parent HeritageComplex
    + source-backed HeritageSite members

Use `hasMember` only when membership is explicitly supported.

Do not assert `hasPart` or `partOf` manually if they are intended to be inferred.

## ReligiousSite

Add this type only where the authoritative source explicitly supports a religious, worship, sacred, ritual, temple, pagoda, shrine, sanctuary, or equivalent function.

Site subclasses may overlap.

A resource may legitimately be both:
- HistoricalSite
- ReligiousSite
- ArchaeologicalSite
- ArchitecturalSite

Do NOT remove existing compatible types.

## ArchitecturalStyle

Create/reuse an ArchitecturalStyle only when the source explicitly identifies a named architectural/artistic style.

Examples worth investigating from official Mỹ Sơn / Champa material:
- Mỹ Sơn E1
- Hòa Lai
- Đồng Dương
- Mỹ Sơn A1
- Bình Định

Do NOT convert vague resemblance/influence into a style assertion without clear evidence.

`hasArchitecturalStyle` is multi-valued.

## HistoricalPeriod

Follow the existing project convention:
HistoricalPeriod may represent:
- named historical/dynastic/polity period;
- named chronological period;
- explicit historical era.

Do not invent artificial periods merely from a single year.

Prefer reusable concepts where appropriate, e.g. a source-backed dynasty/historical era shared by several sites.

## HistoricalEvent

Create events only when they are clearly identifiable historical events in authoritative sources.

Do not fragment events excessively.

## hasHistoricalSuccessor

Meaning:

    A hasHistoricalSuccessor B

means B is the DIRECT next event in an explicitly ordered/curated sequence.

Do NOT infer successor solely because:

    date(A) < date(B)

Do NOT create:
- self edges
- reciprocal edges
- transitive shortcut edges

## hasRelatedSite

Use only when an authoritative source establishes a meaningful historical, religious, architectural, cultural, or functional relationship between two specific sites.

Do NOT use:
- geographic proximity alone
- same province alone
- same period alone
- same style alone
- co-membership in the same complex alone

Assert only one direction when appropriate and let AX-006 symmetric reasoning provide the reverse.

# Existing data reuse

Before creating any entity:

1. Search canonical records for existing identity.
2. Check aliases/source titles.
3. Reuse existing entity when identity is sufficiently confident.
4. Do not create duplicate canonical concepts.

For reusable entities such as:
- HistoricalPeriod
- ArchitecturalStyle
- HistoricalEvent
- AdministrativeArea

prefer one canonical concept reused across multiple records.

# Provenance

Every new fact/entity must preserve:

- authoritative source URL
- exact or concise source-backed evidence
- retrieval/source metadata according to current project convention
- original wording when normalization is involved

Do NOT manually patch RDF only.

All changes must flow through the current Member 2 canonical/mapping pipeline.

# Work strategy

Work in small batches.

Recommended order:

1. HeritageComplex + members
2. ReligiousSite typing
3. ArchitecturalStyle
4. HistoricalPeriod
5. HistoricalEvent
6. hasRelatedSite
7. hasHistoricalSuccessor

After each batch:

- regenerate only affected data/artifacts;
- verify canonical isolation;
- run focused mapping/RDF tests;
- run `git diff --check`.

Do NOT run production Jena after every single entity.

Run Jena only once at the END of this enrichment round.

# Scope protection

Do NOT modify:

- ontology/vietheritage.ttl
- PROJECT_SPEC semantic contract
- AX-001...AX-011
- AX-017
- reasoner behavior
- validator behavior
- external-link policy
- Member 4 files

Do NOT:
- rerun external linking;
- redesign canonical schema;
- broad-refactor mapper/generator;
- add dependencies;
- replace existing approved enrichments.

If current pipeline lacks a small mapping field required for a legitimate enrichment, make the minimum reusable mapping change and test it.

# Stop conditions

Stop enrichment when either:

A. target ranges are reasonably populated with strong source-backed data; OR

B. further additions would require weak evidence, speculative classification, or disproportionate implementation work.

Do NOT pursue numerical balance for its own sake.

# Final verification

After all accepted enrichment:

1. Generate current canonical/asserted RDF.
2. Run relevant Member 2 regression tests.
3. Run Apache Jena 4.10.0 OWL Mini ONCE on:
       ontology + asserted A-Box
4. Run final semantic/SHACL validation.
5. Verify no fixture contamination.
6. Verify all current axioms remain PASS.
7. Verify no new:
   - domain violations
   - range violations
   - disjointness violations
   - identity contradictions

Also report production coverage for:
- HeritageComplex
- ArchitecturalStyle
- HistoricalPeriod
- ReligiousSite
- HistoricalEvent
- hasMember
- hasArchitecturalStyle
- belongsToPeriod
- hasRelatedSite
- hasHistoricalSuccessor

# Required output

# MEMBER 2 COVERAGE ENRICHMENT FINAL REPORT

## 1. Final status

COMPLETE / PARTIAL / BLOCKED

## 2. Coverage before/after

| Class/property | Before | After | Target | Status |

## 3. Added entities

Summarize by category, not every raw triple.

## 4. Added relations

| Property | Count added | Example | Source |

## 5. Sources

| Source organization | What it supported |

## 6. Data-quality decisions

Report:
- identities reused
- duplicates avoided
- ambiguous candidates rejected
- any normalization decisions

## 7. Reasoning impact

Report production evidence for any newly activated reasoning, especially:
- hasMember -> hasPart -> partOf
- hasRelatedSite symmetry
- AX-017 non-vacuous successor validation
- subtype overlap

## 8. Final counts

Canonical records:
Asserted triples:
Inferred delta:
Closure:
External links:
Final graph:

## 9. Validation

Member 2 tests:
Jena:
Semantic validation:
SHACL:
Fixture contamination:

## 10. Rejected / deferred candidates

Only real candidates that were inspected and intentionally not added.

## 11. Files changed

Concise list only.

## 12. Final handoff

State whether the new snapshot is:

    READY FOR MEMBER 4

# Efficiency constraints

- prioritize high-value batches;
- avoid one-agent-turn-per-instance;
- reuse sources and existing mappings;
- no broad repository audit;
- no ontology redesign;
- no repeated Jena runs;
- stop when additional enrichment no longer materially improves coverage.
