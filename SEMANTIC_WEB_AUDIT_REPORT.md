# VietHeritageLOD — Semantic Web Compliance Audit Report

**Audit prompt:** `GOAL_PROMPT_SEMANTIC_WEB_AUDIT.md`
**Audit date:** 2026-09-14
**Repository HEAD:** `0facebc Add Semantic Web user experience`
**Audit mode:** read-only inspection and non-destructive runtime checks; no implementation, raw/canonical data, commit, or push was performed.

## A. Executive verdict

### Verdict: `PARTIALLY COMPLIANT`

VietHeritageLOD đã có nền tảng Semantic Web thật, không chỉ là REST API: RDF/Turtle parse được; ontology có đúng 23 class, 12 object property và 10 datatype property; resource-level provenance có mặt cho 860 entity; reasoning closure được tách thành graph riêng; Fuseki có named graphs; SHACL chạy được với positive/negative fixture; API và Explorer đều truy cập dữ liệu qua Fuseki; CQ và Cypher parity đều đạt.

Tuy nhiên project **chưa thể claim `COMPLIANT` cho public Linked Data** vì final acceptance gate còn fail ở ba điểm:

1. Canonical resource URI mà RDF/API công bố (`http://localhost:3030/vietheritage/resource/{id}`) trả `404` với cả HTML, Turtle và JSON-LD; chỉ route Explorer khác origin/port `http://localhost:8000/resource/{id}` trả `200`.
2. Fuseki service vẫn expose `serviceUpdate`, `serviceUpload` và `serviceReadWriteGraphStore`; API Explorer GET-only nhưng triple-store surface không read-only.
3. Dataset-level metadata bắt buộc (`data/rdf/dataset-metadata.ttl`, `dcat:Dataset`, dataset provenance/license) không tồn tại và không được load; chỉ có bốn named graphs thực tế.

### Scope và giới hạn claim

- Coverage claim được kiểm tra là `100% of selected official registry snapshot`, không phải toàn bộ tri thức văn hóa Việt Nam.
- Snapshot được audit: `20260914T040348Z`.
- Canonical records: `860`; registry failures expected: `10`; Wikipedia pages matched: `42`.
- Verified external links: `114` gồm `89` Wikidata và `25` DBpedia.
- Development base URI trong `PROJECT_SPEC.md` là localhost; đây là hợp lệ cho local development nhưng chưa phải bằng chứng public production dereferenceability.

### Điểm mạnh

- Graph và ontology là source of truth; API code dùng Fuseki query thay vì hard-code canonical JSON.
- RDF và ontology có provenance/identity semantics rõ; 860 labelled entities đều có type, `dcterms:source` và `prov:wasDerivedFrom`.
- Có kiểm chứng runtime thực tế: HTTP content negotiation, SHACL, CQ, Cypher parity, coverage và Explorer smoke đều pass.

### Rủi ro lớn nhất

- Người dùng dereference canonical URI sẽ nhận `404`, vi phạm điều kiện Linked Data cốt lõi.
- Public Fuseki endpoint có mutation surfaces nếu bị expose ngoài localhost hoặc không được network-isolate.
- Closure graph bị trình bày như toàn bộ inferred triples; asserted triples bị lặp trong `inferred_triples`, có thể làm người dùng hiểu sai inferred fact.

## B. Standards matrix

| ID | Area/standard | Requirement | Status | Severity | Evidence | Gap/remediation |
|---|---|---|---|---|---|---|
| RDF-01 | RDF 1.1/Turtle | Toàn bộ ontology, asserted, inferred, external-link và SHACL Turtle parse được | `PASS` | INFO | Read-only RDFLib parse: ontology `327`, asserted `7,249`, inferred `9,358`, external `114`, shapes `40` triples | Duy trì parser/round-trip test |
| RDF-02 | RDF identity/IRI | Public entity có stable absolute URI, collision-free identity | `PARTIAL` | HIGH | 860 entity URI dạng `http://localhost:3030/vietheritage/resource/...`; không có blank-node public subject; nhưng URI không dereference được tại canonical host | Dùng public base URI/reverse proxy đồng nhất với HTTP resource service; giữ URI deterministic |
| RDF-03 | Labels/literals | Vietnamese labels có language tag; literals có datatype/language phù hợp | `PASS` | INFO | Asserted graph có `968` language-tagged literals và `926` typed literals; ontology semantic tests pass | Tiếp tục kiểm tra literal normalization |
| OWL-01 | RDFS/OWL 2 ontology | Đúng 23 class, 12 object property, 10 datatype property; labels bilingual; axioms AX-001..AX-009 pass | `PASS` | INFO | Ontology inventory: `23/12/10`; `23` classes và `22` properties bilingual; non-mutating semantic/contract subset `117 passed` | Không thay đổi frozen ontology ngoài spec revision |
| OWL-02 | Reasoning | Phân biệt asserted và inferred, closure không ghi đè asserted | `PARTIAL` | HIGH | `inferred.ttl` có `9,358`; intersection với asserted là `7,249`; reasoning report delta `1,782` trên ontology+asserted input; API entity có asserted `15`, inferred `19`, overlap `15`, novel inferred `4` | Xuất graph delta riêng hoặc gọi rõ closure; API chỉ đưa triple mới vào `inferred_triples` hoặc ghi rõ closure semantics |
| HTTP-01 | Linked Data dereferenceability | Canonical resource URI phải trả representation hữu ích | `FAIL` | `BLOCKER` | Direct requests: `http://localhost:3030/vietheritage/resource/registry-b043193f37c5` trả `404` cho `text/html`, `text/turtle`, `application/ld+json`; Explorer port 8000 trả `200` | Canonical URI phải trỏ tới/reverse-proxy tới Explorer hoặc một resource server thật; kiểm tra lại bằng HTTP tại chính URI công bố |
| HTTP-02 | Content negotiation | HTML/Turtle/JSON-LD, `Vary`, canonical `Link`, `406`, `404` | `PARTIAL` | HIGH | Port 8000: cả ba representation `200`, `Vary: Accept`, canonical `Link`, unsupported media type `406`, missing entity `404`; nhưng canonical port 3030 fail | Không claim pass trước khi canonical URI hoạt động; thêm live test kiểm tra canonical host |
| JSONLD-01 | JSON-LD 1.1/context | JSON-LD parse lại thành RDF và có context/id/type semantics | `PARTIAL` | MEDIUM | HTTP JSON-LD parse thành `19` triples; `@context=True`; root payload không có `@id`/`@type` (`@graph` chứa resource); `/api/entities` có `@id`/`@type` | Document rõ graph form hoặc compact resource thành root `@id`/`@type`; kiểm tra round-trip trong live test |
| SPARQL-01 | SPARQL 1.1 Query/CQ | 10 CQ chạy đúng, kết quả expected, pagination/query allowlist hoạt động | `PASS` | INFO | `cq-test: 10/10 PASS`; live `/api/queries` có `10` items; `/api/queries/CQ01/run` có SPARQL `head/results` | Tiếp tục pin query SHA và expected bindings |
| SPARQL-02 | SPARQL read-only/API | API không nhận arbitrary query/update; GET-only | `PASS` | INFO | Live API POST `/api/health` trả `405`, `Allow: GET`; CQ route chỉ allowlist `CQ01..CQ10`; app smoke `11/11 PASS` | Đây chỉ là API surface; xem FUSEKI-01 cho underlying service |
| FUSEKI-01 | SPARQL Protocol/Graph Store security | Public semantic service phải không expose mutation ngoài loader/admin boundary | `FAIL` | `HIGH` | `deployment/fuseki/config.ttl` bật `fuseki:serviceUpdate "update"`, `fuseki:serviceUpload "upload"`, `fuseki:serviceReadWriteGraphStore "data"` | Tách loader/admin endpoint; disable/update-protect public service; network-isolate write surface; test PUT/UPDATE policy sau remediation |
| GRAPH-01 | Named graphs | Tách ontology, asserted data, external links, inferred và metadata | `PARTIAL` | `HIGH` | Live graph inventory có `ontology=327`, `data=7249`, `external-links=114`, `inferred=9358`; không có metadata graph; loader chỉ load metadata nếu file tồn tại | Tạo và load `dataset-metadata.ttl`; kiểm tra graph inventory bắt buộc 5 graph |
| SHACL-01 | SHACL | Có valid/invalid evidence và pipeline fail khi public graph không conform | `PASS` | INFO | `make validate RUN_MODE=full`: `shacl (full): PASS`, `validate (full): PASS (860 canonical records)`; tests gồm accept và reject provenance | Giữ negative fixtures trong CI |
| SHACL-02 | SHACL coverage | Shapes phải bao phủ public semantic contract đủ rõ | `PARTIAL` | MEDIUM | `shapes/vietheritage.shacl.ttl` có 3 shapes: PublicEntity, Latitude, Longitude; target chủ yếu `rdfs:label`, chưa kiểm tra đầy đủ 23 class/22 property, range/cardinality/category/license | Mở rộng shapes hoặc ghi explicit scope; thêm negative fixtures cho type/range/category/provenance/language |
| PROV-01 | Resource provenance | Entity fact phải truy được source/derivation | `PASS` | INFO | 860/860 labelled entities có `dcterms:source` và `prov:wasDerivedFrom`; 860/860 cũng có entity-level license triple | Duy trì provenance per assertion khi enrich nhiều nguồn |
| PROV-02 | Dataset provenance/DCAT | Dataset-level catalog, retrieval time, license, source checksums và derivation phải là RDF artifact | `FAIL` | `HIGH` | `PROJECT_SPEC.md` MUST #12 và COMP-005 yêu cầu `data/rdf/dataset-metadata.ttl`; file không tồn tại; grep không có `dcat:Dataset`; loader output thực tế không có metadata graph; snapshot data chỉ nằm trong JSON coverage report | Sinh dataset metadata RDF với `dcat:Dataset`, `dcterms:license`, `dcterms:issued/modified`, `prov:wasDerivedFrom`, source/checksum references; load vào named graph |
| LINK-01 | External links/`owl:sameAs` | Chỉ verified identity links được đưa vào final graph | `PASS` | INFO | `link-review.jsonl`: `114` rows, all `verified`; `89` Wikidata + `25` DBpedia; external graph `114` `owl:sameAs` triples; all verified rows có method/reason | Giữ deterministic QID và DBpedia threshold policy |
| LINK-02 | Link provenance/review | Verified link phải có review actor/time/evidence đủ audit trail | `PARTIAL` | MEDIUM | All verified rows có method/reason, nhưng `reviewer_nonnull=0`, `reviewed_at_nonnull=0`; linker tạo `reviewer: None`, `reviewed_at: None` | Ghi `reviewed_at`, reviewer/process identity và source evidence; phân biệt automated verification với human review |
| API-01 | API as RDF projection | API đọc Fuseki, giữ `@id/@type/@context`, named graph/provenance và không tạo canonical second source | `PASS` | INFO | `src/vietheritage/web/api.py` dùng `FusekiClient`; live stats/search/entity/CQ pass; API docs xác nhận RDF authoritative | Bổ sung schema/media types đầy đủ vào OpenAPI |
| UI-01 | Explorer UX/accessibility | Non-SPARQL user có search/filter/detail/provenance/alternate RDF/error state | `PARTIAL` | LOW | Live `app-smoke: 11/11 PASS`; source có HTML semantic, Vietnamese UI, links Turtle/JSON-LD và loading/error/empty views | Chạy automated accessibility check và test canonical links sau khi sửa URI |
| REPRO-01 | Coverage/reproducibility | Raw → canonical → RDF → links → reports có snapshot/provenance nhất quán | `PASS` | INFO | Snapshot `20260914T040348Z`; raw registry `860`, failures `10`, pages `42`, enrichment failures `810`; coverage `860/860`, `17` categories all `100%`; `traceability-check: PASS` | Gắn snapshot ID vào mọi downstream report, không chỉ coverage |
| REPRO-02 | Test/release contract | Full command surface và artifact naming phải tái lập được | `PARTIAL` | MEDIUM | `compose config --quiet`, `compileall`, `verify FINAL STATUS: PASS`, subset `117 passed`; release evidence trước đó ghi full `149 passed`; nhưng full suite không rerun trong audit vì cảnh báo test có thể ghi shared artifacts; spec yêu cầu `reports/<run_id>/rdf_validation.json`/reasoning report trong khi runtime dùng `reports/full/validation.json` và `data/rdf/reasoning-report.json` | Tách test artifact dirs hoặc isolated worktree; đồng bộ spec/report filenames và snapshot IDs |
| SEC-01 | Security/release hygiene | Không stage secrets; dependencies/config có policy rõ | `PASS` | LOW | `git status` không có tracked source/data changes; secret-pattern scan `0`; `.env` ignored; Compose binds localhost; direct dependencies pinned (`rdflib`, `requests`, `pyshacl`, etc.) | Pin build-system/base-image policy; không expose default local credentials ngoài localhost |

## C. Evidence inventory

### Commands and results

| Command/check | Result |
|---|---|
| RDFLib parse of ontology/asserted/inferred/external/shapes | PASS; `327/7249/9358/114/40` triples |
| Ontology inventory script | `23` classes, `12` object properties, `10` datatype properties; all `23` classes and `22` properties bilingual |
| Public entity/provenance scan | `860` labelled; `860` typed; `860` with `dcterms:source`; `860` with `prov:wasDerivedFrom` |
| Reasoning overlap scan | asserted `7249`; inferred closure `9358`; overlap `7249`; new beyond asserted `2109`; report delta over ontology+asserted `1782` |
| `make validate RUN_MODE=full` | SHACL PASS; validation PASS (`860` canonical records) |
| `make linked-data-test` | PASS (`200`) for Fuseki DESCRIBE path |
| `make app-test` | `10 passed` |
| `make app-smoke` | `11/11 PASS` |
| `make cq-test` | `10/10 PASS` |
| `make cypher-test` | `10/10 PASS`; Neo4j emitted known warnings for absent `LOCATED_IN`, `ASSOCIATED_WITH_PERSON`, `PART_OF` relationship types |
| `make traceability-check` | PASS |
| `docker compose config --quiet` | PASS |
| `python -m compileall -q src tests` | PASS |
| Non-mutating regression subset | `117 passed in 2.17s` |
| `make verify RUN_MODE=full` | `coverage=PASS, external_links=114, services=PASS/PASS`, `FINAL STATUS: PASS` |
| Live named graph query | `ontology=327`, `data=7249`, `external-links=114`, `inferred=9358`; metadata absent |

### Live HTTP evidence

Tested entity: `registry-b043193f37c5`.

- Explorer `/resource/{id}` with `Accept: text/html`: `200`, `text/html`, `Vary: Accept`, canonical `Link`.
- Explorer `/resource/{id}` with `Accept: text/turtle`: `200`, `text/turtle`, `Vary: Accept`, canonical `Link`; RDF parse `19` triples.
- Explorer `/resource/{id}` with `Accept: application/ld+json`: `200`, `application/ld+json`, `Vary: Accept`, canonical `Link`; JSON-LD parse `19` triples and `@context` present.
- Explorer `?format=turtle`: `200`, `text/turtle`.
- Unsupported `Accept: application/xml`: `406`.
- Missing entity: `404` with `ENTITY_NOT_FOUND`.
- `/api/health`: `200`; `/api/stats`: `200`; `/api/queries`: `200` and `10` entries.
- `/api/queries/CQ01/run`: `200`, result contains SPARQL `head/results`.
- POST to API: `405`, `Allow: GET`.
- Fuseki `/$/ping`: `200`.
- Canonical port-3030 resource URI: `404` for all three tested media types.

### Current artifacts

- `reports/20260914T040348Z/coverage.json`: snapshot `20260914T040348Z`, registry/canonical `860`, `17` categories, all `100%`.
- `reports/full/verify.json`: status `PASS`, `114` external links, CQ/Cypher `10/10`, services `PASS/PASS`.
- `reports/full/validation.json`: `PASS`, `860`, SHACL `PASS`.
- `reports/full/shacl.json`: `conforms=true`.
- `data/rdf/reasoning-report.json`: `{ "status": "PASS", "inferred_triples": 1782 }`.
- `data/rdf/dataset-metadata.ttl`: **missing**.

## D. Blocking/high findings

### F-001 — Canonical Linked Data URI is not dereferenceable (`BLOCKER`)

**Reproduction:** GET `http://localhost:3030/vietheritage/resource/registry-b043193f37c5` with `Accept: text/html`, `text/turtle`, and `application/ld+json` returned `404 text/plain`. The Explorer route at port `8000` returned `200` for all three. API `Link` and JSON-LD identity still advertise the port-3030 URI.

**Impact:** The project has a working local presentation route, but not a dereferenceable canonical resource URI. This fails the Linked Data final gate and makes RDF links resolve to a different/nonexistent HTTP route.

**Remediation:** Select one public/canonical base URI and make that exact URI serve or redirect to content-negotiated HTML/Turtle/JSON-LD. For local deployment, use a reverse proxy or configure `VH_BASE_URI` to the Explorer origin consistently; for publication, use a stable non-localhost domain.

### F-002 — Fuseki write surfaces remain enabled (`HIGH`)

**Evidence:** `deployment/fuseki/config.ttl` explicitly enables `fuseki:serviceUpdate`, `fuseki:serviceUpload`, and `fuseki:serviceReadWriteGraphStore`. The application API is GET-only, but direct Fuseki service configuration is mutable.

**Impact:** A public or accidentally exposed Fuseki port could accept dataset mutation independent of the read-only API contract.

**Remediation:** Separate private loader/admin access from public query/Graph Store read access, disable update/upload/write Graph Store on the public service, enforce authentication/network policy, and add a non-mutating policy test plus controlled negative update test in an isolated dataset.

### F-003 — Dataset-level RDF metadata is missing (`HIGH`)

**Evidence:** `PROJECT_SPEC.md` Section 2.1 MUST #12 and COMP-005 require dataset-level provenance and `data/rdf/dataset-metadata.ttl`; the file is absent. Fuseki live graph inventory has no metadata graph. The generator docstring claims that output but `run()` only writes `vietheritage.ttl`; no `dcat:Dataset` triple was found.

**Impact:** Retrieval time, snapshot identity, source checksums, dataset license and derivation are not published as RDF and cannot be followed through the Linked Data graph.

**Remediation:** Generate/load a metadata graph containing a stable `dcat:Dataset`, `dcterms:license`, `dcterms:issued/modified`, `prov:wasDerivedFrom`, source distribution/checksum references and snapshot ID.

## E. Compliance scorecard

Using the audit prompt's reference scoring (`PASS=1`, `PARTIAL=0.5`, `FAIL/BLOCKED=0`) over the 20 standards-matrix rows:

- `PASS`: 8
- `PARTIAL`: 9
- `FAIL`: 3
- `BLOCKED`: 0
- `N/A`: 0
- Reference score: `(8 + 9×0.5) / 20 = 62.5%`

This score is informational only. The three `FAIL` rows include final-gate conditions, so the verdict cannot be upgraded to `COMPLIANT` by score alone.

## F. Final acceptance gate

| Gate | Result | Evidence |
|---|---|---|
| RDF parses and entity identity is stable | `PARTIAL` | RDF parse/identity pass; canonical URI dereference fails |
| Ontology/data/reasoning have no unexplained drift | `PARTIAL` | Ontology counts pass; closure-vs-delta presentation and report-path drift remain |
| Resource URI dereferences HTML/Turtle/JSON-LD | `FAIL` | Port 3030 canonical URI returned `404` for all three |
| JSON-LD has context and round-trip semantics | `PARTIAL` | 19-triple round-trip and context pass; root convenience `@id/@type` absent |
| SPARQL/query layer read-only with graph policy | `FAIL` | API GET-only; Fuseki update/upload/read-write Graph Store enabled |
| SHACL has positive and negative evidence | `PASS` | Full SHACL pass and unit valid/invalid fixtures pass |
| External links follow verified identity policy | `PARTIAL` | 114 verified rows and graph pass; reviewer/time provenance absent |
| API/UI remain presentation/access layer | `PASS` | API Fuseki-backed; live API/Explorer checks pass |
| Tests/docs/Docker/Make/release artifacts reproducible | `PARTIAL` | 117 non-mutating tests, runtime gates and compose pass; full suite/report contract not fully rerun/aligned |
| No secrets or out-of-scope artifacts in commit | `PASS` | Secret scan `0`; status contains only intended audit prompt and pre-existing protected/generated untracked artifacts |

## G. Đã đạt / Chưa đạt / Bị chặn / Ưu tiên

### Đã đạt

- RDF/Turtle validity and deterministic full snapshot artifacts.
- Frozen ontology inventory and semantic axiom tests.
- Resource-level source/provenance coverage for all `860` entities.
- SHACL valid/invalid behavior and full validation.
- 10 CQ, Cypher parity, traceability, coverage and service health.
- Working Explorer representations on port 8000 with HTML/Turtle/JSON-LD, `Vary`, `Link`, 406 and 404 behavior.
- API GET-only behavior, query allowlist, JSON-LD context and Fuseki-backed projections.

### Chưa đạt

- Canonical URI dereferenceability at the URI actually published in RDF/API.
- Dataset-level RDF metadata and metadata named graph.
- Read-only public Fuseki configuration.
- Strict asserted-vs-inferred delta presentation.
- Full SHACL coverage of the ontology/data contract.
- Complete external-link review provenance.
- Full alignment between `PROJECT_SPEC.md` report contracts and generated artifact paths.

### Bị chặn

- Public Linked Data compliance verdict is blocked by F-001 until the canonical URI route is fixed.
- A strict read-only deployment verdict is blocked by F-002 until Fuseki mutation surfaces are isolated/disabled.
- Dataset-level provenance/catalog compliance is blocked by F-003 until the metadata graph exists.

### Bước tiếp theo ưu tiên

1. Fix canonical base URI/reverse proxy and add a live test against the canonical URI, not only port 8000.
2. Make public Fuseki query/read Graph Store read-only and keep loader/admin write access private.
3. Generate/load `dataset-metadata.ttl` and add DCAT/PROV/DCTERMS acceptance tests.
4. Decide whether `inferred.ttl` is a closure graph or a delta graph; expose that distinction explicitly in API/UI.
5. Expand SHACL and link review provenance, then rerun the full pipeline and all acceptance gates in an isolated checkout.

## Audit safety note

No source, ontology, raw data, canonical data, generated RDF, Docker configuration, service state, commit, or push was changed by this audit. The repository status after checks remained limited to the requested untracked audit prompt and the pre-existing protected/generated artifacts.
