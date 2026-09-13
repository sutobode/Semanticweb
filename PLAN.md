# PLAN.md — Kế hoạch triển khai VietHeritageLOD cho 4 thành viên

> **Nguồn duy nhất của Plan này là `PROJECT_SPEC.md`.** Mọi ID (`COMP-*`, `FR-*`, `NFR-*`, `AX-*`, `TEST-*`, `AC-*`, `DEC-*`, `G0`–`G12`, `make <target>`) trong file này đều trích dẫn trực tiếp từ `PROJECT_SPEC.md` hiện tại. Nếu một mục trong Plan mâu thuẫn với `PROJECT_SPEC.md`, `PROJECT_SPEC.md` thắng và Plan phải được sửa lại.

> **Quy ước:** `MUST` = việc chặn Gate, không xong thì không được sang Gate sau. `SHOULD` = nên làm trong tuần đó nhưng không chặn. Mỗi task có `Input`, `Output`, `Test/AC` để một người ngoài có thể chấm được PASS/FAIL không cần hỏi thêm.

---

## 0. Vì sao chia vai trò như thế này

`PROJECT_SPEC.md` định nghĩa 11 component (`COMP-000`…`COMP-010` ở Section 7, `COMP-011` ở Phụ lục C) và 13 Gate (`G0`–`G12` ở Section 43). Plan này gom 11 component thành 4 nhóm trách nhiệm theo đúng ranh giới dữ liệu chảy qua pipeline (Section 6, Section 31), để mỗi người sở hữu một đoạn liên tục của luồng dữ liệu và không ai phải chờ người khác *trong cùng một stage*:

```text
COMP-000, COMP-001                  → Member 2 (Data Acquisition)
COMP-002, COMP-003, COMP-004        → Member 2 (Normalization/Identity/Mapping)
COMP-005, COMP-006, COMP-008        → Member 1 (Ontology + RDF + Reasoning)
COMP-007                            → Member 3 (External Linking)
COMP-009, COMP-010, COMP-011        → Member 4 (Triple Store + LPG + CLI)
```

| Member | Vai trò | Component sở hữu | Lý do gom nhóm |
|---|---|---|---|
| **M1** | Ontology & Reasoning Lead | `COMP-005` (RDF Generator), `COMP-006` (Validator), `COMP-008` (Reasoner) | Người hiểu ontology sâu nhất phải là người viết RDF generator và kiểm reasoning, vì mọi lỗi domain/range/axiom lộ ra ngay ở bước này |
| **M2** | Data Acquisition & Normalization Lead | `COMP-000` (Registry Collector), `COMP-001` (Wikipedia Collector), `COMP-002` (Normalizer), `COMP-003` (Entity Resolver), `COMP-004` (Canonical Mapper) | Toàn bộ "raw → canonical" là một luồng liên tục, tách ra sẽ phải handoff JSON qua lại nhiều lần trong ngày |
| **M3** | External Linking Lead | `COMP-007` (External Linker), Silk rule (Section 22.3), `owl:sameAs` policy (Section 23) | Linking là công việc độc lập về mặt input (chỉ cần `canonical.jsonl` + candidate), phù hợp làm song song toàn thời gian mà không block ai |
| **M4** | Triple Store, LPG & Deployment Lead | `COMP-009` (Fuseki Loader), `COMP-010` (CQ Runner), `COMP-011` (Neo4j LPG Loader — Phụ lục C), CLI/`Makefile`/`docker-compose.yml` | Người vận hành hạ tầng phải sở hữu cả hai triple/graph store và toàn bộ 27 `make` target để không ai khác phải đoán cách chạy |

Không ai làm việc một mình 7 tuần liên tục — Section "Cross-review" ở cuối file quy định rõ ai phải xem lại việc của ai, ở tuần nào.

---

## 1. Bảng mapping Requirement → Member (kiểm tra chồng lấp)

| FR/NFR (Section 4–5) | Component | Member | Test | AC |
|---|---|---|---|---|
| FR-001 Official registry collection | COMP-000 | M2 | TEST-076…081 | AC-024/025/026 |
| FR-001A Wikipedia enrichment | COMP-001 | M2 | TEST-001…004 | AC-002/026 |
| FR-002 Raw validation | schema | M2 | TEST-005 | AC-002 |
| FR-003 Normalization | COMP-002 | M2 | TEST-006…011 | AC-003 |
| FR-004 Entity identity | COMP-003 | M2 | TEST-012…016 | AC-004 |
| FR-005 Ontology mapping | COMP-004 | M2 (config) + M1 (review) | TEST-017…020, TEST-090 | AC-003 |
| FR-006 RDF generation | COMP-005 | M1 | TEST-021…027 | AC-005 |
| FR-007 Wikidata linking | COMP-007 | M3 | TEST-034/035 | AC-012 |
| FR-008 DBpedia candidate linking | COMP-007 | M3 | TEST-036…038 | AC-012 |
| FR-009 Link review | COMP-007 | M3 | TEST-039/040 | AC-012 |
| FR-010 RDF validation | COMP-006 | M1 | TEST-028…033 | AC-006 |
| FR-011 Reasoning | COMP-008 | M1 | TEST-041…045, TEST-082…085 | AC-007 |
| FR-012 Fuseki | COMP-009 | M4 | TEST-046…050 | AC-008/009 |
| FR-013 SPARQL CQ | COMP-010 | M4 (runner) + M1 (query đúng ontology) | TEST-051…060, TEST-086 | AC-010 |
| FR-014 Run report | reporting | M4 | contract tests | AC-015 |
| FR-015 CLI | Makefile | M4 | command contract | AC-001/016 |
| FR-016 Test suite | tests/ | Cả 4 người, mỗi người viết test cho phần mình | TEST-001…090 | AC-016/017 |
| FR-017 Resource dereference | linked-data adapter | M4 | TEST-048 | AC-011 |
| FR-018 License/provenance | RDF generator | M1 | TEST-025/032, TEST-061 | AC-019/020 |
| Phụ lục C — Neo4j LPG | COMP-011 | M4 | TEST-066…075 | AC-021…023 |

Không có ô nào bị bỏ trống — nếu một requirement không xuất hiện ở đây, đó là lỗi của Plan này, không phải của spec (đối chiếu Section 39 Requirement Traceability Matrix).

---

## 2. Chi tiết theo Member

### 2.1 Member 1 — Ontology & Reasoning Lead

**Sở hữu:** `ontology/vietheritage.ttl`, `src/vietheritage/rdf/`, `src/vietheritage/validation/`, `src/vietheritage/reasoning/`.

**Đọc trước khi code:** Section 15 (Ontology Contract, gồm 15.0.0 ontology header, 15.1–15.3 class/property, 19.1 mapping category→subclass), Section 16 (`AX-001`…`AX-009`), Section 20 (RDF Generation), Section 21 (Provenance), Section 26 (Reasoning + bảng engine-per-axiom ở 26.1.1).

| Tuần | Task | Input | Output | Test/AC chặn |
|---|---|---|---|---|
| 1 | Viết `ontology/vietheritage.ttl` đủ 23 class (Section 15.1), `owl:Ontology` header (15.0.0), `rdfs:label` song ngữ `@vi`/`@en` cho mọi class/property (15.1.1) | Section 15 | `ontology/vietheritage.ttl` v0.1 | `TEST-033` (namespace inventory) |
| 1 | Viết 12 object property + 10 datatype property đúng domain/range (15.2, 15.3), gồm domain union của `vh:locatedIn` (15.2.1) | Section 15.2–15.3 | ontology v0.1 (tiếp) | `AC-014` (đếm class/property) |
| 2 | Viết `src/vietheritage/rdf/` — RDF Generator dùng RDFLib 7.1.3, sort triple deterministic (Section 20.1) | `data/fixtures/canonical.jsonl` (từ M2) | `data/rdf/vietheritage.ttl` | `TEST-021`…`TEST-027`, `AC-005` |
| 2 | Sinh `dataset-metadata.ttl` với `dcat:Dataset`, license, provenance (Section 21.2) | ontology + canonical | `data/rdf/dataset-metadata.ttl` | `TEST-061`, `AC-019` |
| 3 | Cài đủ 9 axiom `AX-001`…`AX-009` vào ontology (Section 16), bao gồm `owl:AllDisjointClasses` cho 7 nhánh chính (AX-004) và `owl:disjointUnionOf` cho 3 subclass intangible (AX-008) | ontology v0.1 | ontology v1 **frozen** | Không đổi ontology lớn sau tuần 3 |
| 3 | Viết `src/vietheritage/validation/` — parse, namespace, required label, datatype, provenance, URI check (Section 26.1.1 gồm cả `CARDINALITY_VIOLATION` cho AX-009) | RDF + ontology | `reports/<run_id>/rdf_validation.json` | `TEST-028`…`TEST-033`, `AC-006` |
| 5 | Viết `src/vietheritage/reasoning/` dùng Jena OWL Mini reasoner qua CLI (Section 26.1, `http://jena.hpl.hp.com/2003/OWLMiniFBRuleReasoner`) | ontology + data | `data/rdf/inferred.ttl`, `reports/<run_id>/reasoning.json` | `TEST-041`…`045`, `TEST-082`…`085`, `AC-007` |
| 5 | Chạy before/after reasoning demo theo fixture Section 26.2 (UNESCO inference, symmetric `hasRelatedSite`, `builtBy`→`associatedWithPerson`) | fixture Section 26.2 | reasoning report có đủ 6 inferred triple kỳ vọng | `AC-007` |
| 6 | Review 10 file SPARQL (`sparql/CQ01`…`CQ10`) do M4 chạy — xác nhận mọi class/property dùng trong query có tồn tại trong ontology | `sparql/*.rq` | Sign-off ghi trong PR | `TEST-051`…`060` |
| 7 | Viết Section "Ontology Design" của report (2–3 trang, Section 53.2 mục 3), review consistency cuối cùng | ontology final | phần report | — |

**Ràng buộc riêng của M1:** không được tạo class/property mới sau khi ontology v1 freeze ở tuần 3 (Development Plan tuần 3, Section 42) — mọi thay đổi sau đó `MUST` cập nhật `Specification Version` và Decision Register (Phụ lục A) trước.

---

### 2.2 Member 2 — Data Acquisition & Normalization Lead

**Sở hữu:** `config/registry_sources.yaml`, `config/collector.yaml`, `config/mapping.yaml`, `src/vietheritage/registry/`, `src/vietheritage/collector/`, `src/vietheritage/normalization/`, `src/vietheritage/identity/`, `src/vietheritage/mapping/`.

**Đọc trước khi code:** Section 7 COMP-000…COMP-004, Section 11 (Raw Data Contract), Section 12 (Canonical Data Contract, đặc biệt 12.2 field theo entity type và 19.1 mapping category→subclass), Section 13 (Identity Contract), Section 17 (`NOR-001`…`NOR-015`), Phụ lục D.1–D.3.

| Tuần | Task | Input | Output | Test/AC chặn |
|---|---|---|---|---|
| 1 | Viết `config/registry_sources.yaml` đủ 17 category (Section 7 COMP-000, Phụ lục D.1) với `row_selector`, `columns`, `entity_type`, `ontology_subclass` | Danh sách 17 URL trong Section 7 | `config/registry_sources.yaml` | `TEST-076`…`081` |
| 1 | Tạo 20–30 fixture record thủ công đại diện đủ 14 canonical entity type (Section 12.2) để cả team dùng chung, đặt tại `data/fixtures/` theo mẫu `canonical.jsonl` (Section 9 repo tree) | Section 12.2 | `data/fixtures/canonical.jsonl` | Input cho M1/M3/M4 tuần 2 |
| 1 | Viết `schema/raw-page.schema.json`, `schema/canonical-record.schema.json` đúng Phụ lục B.1/B.2 | Phụ lục B | 2 file schema | `TEST-005` |
| 2 | Viết `src/vietheritage/registry/` — HTTP GET/retry (`NFR-007`: timeout 30s, 3 retry, backoff 2/4/8s), parse HTML table, `REGISTRY_PARSE_ERROR`/`REGISTRY_ID_COLLISION` | `config/registry_sources.yaml` | `data/raw/registry_records.jsonl`, `data/raw/registry_failures.jsonl`, `reports/<run_id>/coverage.json` | `TEST-076`…`081`, `AC-024`…`026` |
| 2 | Viết `src/vietheritage/collector/` — MediaWiki API (`action=query`, các `prop` theo Section 7 COMP-001), matching exact title/alias rồi QID, giữ `registry_only` khi không match | Registry labels | `data/raw/pages.jsonl`, `data/raw/enrichment_failures.jsonl` | `TEST-001`…`004`, `AC-002` |
| 3 | Viết `src/vietheritage/normalization/` — cài đủ 15 rule `NOR-001`…`NOR-015` (gồm `canonical_dash` cho `NOR-004`) | raw JSONL | `data/processed/normalized.jsonl`, `data/processed/skipped_records.jsonl` | `TEST-006`…`011`, `AC-003` |
| 3 | Viết `src/vietheritage/identity/` — thứ tự resolution 5 bậc (Section 13.2: registry_id → QID → page_id → canonical key → SHA-256), `IDENTITY_COLLISION` khi trùng type | normalized JSONL | `data/processed/entities.jsonl`, `identity_map.jsonl`, `collision_report.json` | `TEST-012`…`016`, `AC-004` |
| 4 | Viết `config/mapping.yaml` đủ bảng Section 19 + `registry_category_subclass` (Section 19.1, Phụ lục D.3) | Section 19 | `config/mapping.yaml` | `TEST-090` |
| 4 | Viết `src/vietheritage/mapping/` — Canonical Mapper áp `config/mapping.yaml`, `object_must_be: vh:HistoricalPerson` cho `built_by` (chặn inference AX-007) | entities.jsonl | `data/processed/canonical.jsonl` | `TEST-017`…`020`, `AC-003` |
| 5–6 | Mở rộng crawl thật tới 150–250 heritage site (mục tiêu Development Plan tuần 6, không phải cap cứng — xem MET-006/007 floor rule Section 3.1) | registry + Wikipedia thật | canonical dataset mở rộng | `MET-005a`, `AC-013` |
| 7 | Viết Section "Data Collection" của report (2 trang, Section 53.2 mục 4) | pipeline hoàn chỉnh | phần report | — |

**Ràng buộc riêng của M2:** `FR-004` cấm fuzzy matching trong core identity (Decision Register `DEC-007`) — không được tự thêm thư viện fuzzy-match để "cho dễ".

---

### 2.3 Member 3 — External Linking Lead

**Sở hữu:** `src/vietheritage/linking/`, `silk/linkage-rules.xml`, `data/linking/`.

**Đọc trước khi code:** Section 22 (External Linking Contract, gồm bảng quyết định DBpedia đầy đủ 22.2 và Silk rule 22.3), Section 23 (`owl:sameAs` Policy), Section 7 COMP-007.

| Tuần | Task | Input | Output | Test/AC chặn |
|---|---|---|---|---|
| 1–2 | Nghiên cứu Wikidata SPARQL endpoint và cấu trúc QID; viết script thử nghiệm lấy QID cho 20 fixture của M2 | fixture M2 | ghi chú kỹ thuật | Chuẩn bị cho tuần 4 |
| 4 | Viết phần Wikidata deterministic linking trong `src/vietheritage/linking/` — nếu `wikidata_id` khớp `^Q[0-9]+$` thì sinh `status=verified, confidence=1.0` ngay (Section 22.1) | canonical.jsonl có `wikidata_id` | `data/linking/wikidata_links.csv` | `TEST-034`/`035`, `AC-012` |
| 5 | Viết `silk/linkage-rules.xml` đúng nội dung freeze ở Section 22.3 (Levenshtein threshold 0.90, geographic distance 5km) | Section 22.3 | `silk/linkage-rules.xml` | Không tự đổi threshold |
| 5 | Viết Python scorer thực thi rule Silk (label_similarity + haversine distance + type_compatible) làm executor thật vì Silk XML chỉ là policy source (Section 22.3) | canonical + DBpedia candidate | `data/linking/dbpedia_candidates.csv` | `TEST-036`…`038` |
| 6 | Cài đủ bảng quyết định Section 22.2 (bao gồm nhánh `score>=0.90` + `distance 5–20km` → `manual_review`); mọi tổ hợp không khớp dòng nào MUST làm stage FAIL | dbpedia_candidates.csv | `data/linking/link_review.csv` | `TEST-039`/`040` |
| 6 | Review thủ công candidate `manual_review`, chuyển `verified` hoặc `rejected`; sinh `data/rdf/external-links.ttl` chỉ từ `verified` (Section 23 `owl:sameAs` Policy) | link_review.csv | `data/rdf/external-links.ttl` | `AC-012` |
| 6 | Đạt tối thiểu 100 verified link (`MET-008` floor, không phải cap) | full canonical dataset | external-links.ttl mở rộng | `AC-013` |
| 7 | Viết Section "External Linking" của report (1–2 trang, Section 53.2 mục 6) — bắt buộc có precision trên sample đã verify thủ công | link review data | phần report | — |

**Ràng buộc riêng của M3:** `owl:sameAs` **chỉ** được sinh khi QID tồn tại hoặc DBpedia candidate `verified` — không tự nới điều kiện dù thiếu link để đạt `MET-008`. Site và website chính thức, class và instance, hai entity chỉ trùng label — **không** dùng `owl:sameAs` cho các trường hợp này (Section 23); dùng `rdfs:seeAlso`/`foaf:homepage` thay thế.

---

### 2.4 Member 4 — Triple Store, LPG & Deployment Lead

**Sở hữu:** `Makefile`, `docker-compose.yml`, `deployment/`, `src/vietheritage/lpg/`, `src/vietheritage/reporting/`, `sparql/`, `cypher/`.

**Đọc trước khi code:** Section 8 (Technology Stack), Section 27 (Fuseki Specification, gồm compose hợp nhất 27.3), Section 28 (Linked Data Publication), Section 30 (CLI Contract — 27 target), Phụ lục C (Neo4j LPG Layer, COMP-011).

| Tuần | Task | Input | Output | Test/AC chặn |
|---|---|---|---|---|
| 1 | Bootstrap repository: tạo cây thư mục đúng Section 9, `requirements.txt`, `.env.example` (gồm `NEO4J_*` theo Section 10.1/10.2), `Makefile` với 27 target rỗng (chưa cần logic, chỉ cần tồn tại và trả đúng exit code khi thiếu input) | Section 9, Section 30 | repo skeleton | `make setup`, `make test` chạy được (Gate `G0`) |
| 1 | Viết `schema/run-report.schema.json`, `schema/link-review.schema.json`, `schema/coverage.schema.json` (Phụ lục B.3–B.5) | Phụ lục B | 3 file schema | Contract test cho `G1` |
| 4 | Viết `deployment/fuseki/Dockerfile` + `deployment/fuseki/config.ttl` (TDB2, `tdb2:unionDefaultGraph true`, dataset `vietheritage`) | Section 27.1–27.2 | Fuseki image build được | `TEST-046`…`050` |
| 4 | Viết `docker-compose.yml` **hợp nhất** cả `fuseki` và `neo4j` đúng Section 27.3 (bao gồm `NEO4J_AUTH` interpolation từ `.env`, hai volume `fuseki-data`/`neo4j-data`, cả hai port chỉ bind loopback) | Section 27.3 | `docker-compose.yml` | `AC-008`, `DEC-026` |
| 4 | Viết loader Graph Store Protocol: 5 lệnh `PUT` theo đúng thứ tự ontology→data→external-links→inferred→metadata (Section 27.5) | 5 file Turtle | dataset `vietheritage` loaded | `make fuseki-load`, `AC-009` |
| 4 | Viết `deployment/linked-data/resource_query.py` — adapter `GET /resource/{entity_id}` → `DESCRIBE` → SPARQL, `200`/`404` (Section 27.6) | Fuseki endpoint | Resource dereferenceable | `TEST-048`, `AC-011` |
| 5 | Viết `sparql/CQ01-sites-by-location.rq` … `CQ10-english-label-from-snapshot.rq` — chép đúng nguyên văn 10 query ở Section 24, không tự sửa biến | Section 24 | 10 file `.rq` | `TEST-051`…`060` |
| 5 | Viết CQ Runner (`COMP-010`): parse query, hash SHA-256, gửi HTTP tới Fuseki, so bindings với file trong `data/fixtures/expected/` theo mẫu `CQ01.json` … `CQ10.json` (format SPARQL 1.1 Results JSON, Section 35.1) | Fuseki + 10 query | `reports/<run_id>/cq_results.json` | `AC-010` |
| 6 | Viết `src/vietheritage/lpg/` — Neo4j loader dùng `MERGE` theo `entityId` (idempotent), map label/relationship đúng bảng C.2, parse `xsd:gYear`/`xsd:decimal` sang `integer`/`float` | canonical.jsonl | Neo4j database, `reports/<run_id>/neo4j_load.json` | `TEST-066`…`070` |
| 6 | Viết 10 file `cypher/CQ01-sites-by-location.cypher` … `CQ10` tương ứng 1:1 với SPARQL, và Cypher Runner so `entityId` set với kết quả SPARQL (Section C.6, mã lỗi `LPG_RDF_MISMATCH`) | Fuseki + Neo4j đã load | `reports/<run_id>/cypher_results.json` | `TEST-071`…`075`, `AC-021`…`023` |
| 6–7 | Viết `src/vietheritage/reporting/` — run report đủ key bắt buộc (Section 34: `collected`, `rdf_triples`, `lpg_nodes`, `cypher_passed`, …), logging JSON Lines (Section 33) | mọi stage counter | `reports/<run_id>/run_report.json`, `logs/<run_id>/*.jsonl` | `TEST-088`, `AC-015` |
| 7 | Viết `make verify` full chain (18 bước Section 45), `make traceability-check` đọc `config/requirements.yaml` (Phụ lục D.5), Five-Star check (`TEST-061`…`065`) | toàn bộ artifact | `FINAL STATUS: PASS` | `AC-016`…`020` |
| 7 | Chạy `make verify` trên clean checkout để xác nhận reproducibility (Section 41), viết Section "SPARQL and Reasoning" + "Evaluation" của report (Section 53.2 mục 7–8) | repo freeze | phần report + evidence | `AC-018` |

**Ràng buộc riêng của M4:** Neo4j **MUST NOT** được dùng để chứng minh 5-Star LOD, `owl:sameAs`, hoặc dereferenceable URI (Section C.1) — nếu một AC nào yêu cầu 5-Star, luôn trỏ về Fuseki, không trỏ về Neo4j dù nhanh hơn.

---

## 3. Lịch 7 tuần — Gate nào đóng ở tuần nào

Bảng dưới ghép Development Plan có sẵn (Section 42) với Gate `G0`–`G12` (Section 43) và người chịu trách nhiệm chính đóng gate:

| Tuần | Gate đóng | Goal (Section 42) | Người chịu trách nhiệm chính | Milestone kiểm tra được |
|---|---|---|---|---|
| 1 | `G0`, `G1` | Freeze CQ, scope, field schema, URI, ontology sketch | M4 (bootstrap) + M2 (schema) + M1 (ontology v0.1) | `make setup && make test` PASS |
| 2 | — (giữa `G1`–`G2`) | MediaWiki fixture/API → JSONL → RDF/Turtle | M2 (collector) + M1 (RDF generator) | `AC-002`…`AC-005` |
| 3 | `G2`, `G4`, `G5` | Ontology v1 frozen, 50–100 site, CQ01–CQ05 | M1 (ontology freeze) + M2 (normalize + identity) | `make validate`, `make cq-test` partial |
| 4 | `G6`, `G8` | URI, provenance, license, Fuseki, dereference | M4 (Fuseki + adapter) + M2 (mapping) | `AC-008`, `AC-009`, `AC-011` |
| 5 | `G9`, `G10` | AX-001…AX-009 và CQ01–CQ08 PASS | M1 (reasoning) + M4 (CQ runner) | `AC-007`, `AC-010` partial |
| 6 | `G3`, `G7` | Wikidata deterministic, DBpedia candidate/review, 100 link, CQ09/CQ10 | M3 (linking) + M4 (LPG C.4–C.6) | `AC-012`, `AC-013`, `AC-021`…`023` |
| 7 | `G11`, `G12` | Freeze code/data/schema, verify, report, slide, video | M4 (verify) + cả 4 người (report/slide/video) | `AC-014`…`AC-020`, `FINAL STATUS: PASS` |

Lưu ý quan trọng: `G3` (Collector) được đóng ở tuần 6 trong bảng trên chỉ vì cột "Goal" gốc của Section 42 xếp collector mở rộng ở giữa kế hoạch — thực tế **M2 phải có collector chạy được từ tuần 2** (prototype end-to-end) để không lặp lại `RISK-6` (integration quá muộn). Bảng Gate ở đây mô tả *thời điểm gate được coi là đóng hoàn toàn*, không phải thời điểm *bắt đầu*.

---

## 4. Cross-review bắt buộc

Không ai làm việc biệt lập. Các cặp review sau **MUST** diễn ra, đúng tinh thần "hiểu toàn bộ pipeline trước ngày presentation" (Section 42 tuần 7):

| Tuần | Cặp review | Nội dung | Nếu fail |
|---|---|---|---|
| 1 | M1 ↔ M2 | Ontology 23 class có đủ để biểu diễn field thật trong 17 registry category không | M1 sửa ontology trước khi freeze tuần 3 |
| 2 | M2 ↔ M1 | 20-30 fixture của M2 có map được hết vào canonical schema mà M1 cần cho RDF generator không | M2 bổ sung fixture |
| 3 | M1 ↔ M4 | 10 Competency Question (Section 24) có dùng đúng property/class đã freeze trong ontology không | M1 sửa ontology hoặc M4 sửa query, không sửa cả hai tùy ý |
| 4 | M2 ↔ M4 | `config/mapping.yaml` của M2 sinh canonical đúng field mà Fuseki loader của M4 cần | M2 bổ sung mapping |
| 5 | M1 ↔ M3 | Ontology có đủ chỗ cho `owl:sameAs` không phá disjointness (AX-004/AX-008) | M1 xác nhận trước khi M3 sinh external-links.ttl |
| 6 | M3 ↔ M4 | `external-links.ttl` của M3 nạp đúng vào Fuseki graph `external-links` và Neo4j `SAME_AS` relationship của M4 | M4 kiểm tra load log |
| 6 | M4 (RDF) ↔ M4 (LPG) | Tự-review parity Cypher↔SPARQL (Section C.6) — cùng người sở hữu cả hai layer nên đây là self-check bắt buộc trước khi merge | Không merge nếu có `LPG_RDF_MISMATCH` |
| 7 | Cả 4 người | Chạy `make verify` cùng nhau, mỗi người giải thích được phần người khác làm | Không presentation nếu có người không giải thích được |

---

## 5. Rủi ro theo vai trò (không lặp lại risk chung, chỉ nêu risk gắn với phân công)

| Rủi ro | Ai bị ảnh hưởng | Biện pháp |
|---|---|---|
| M2 chậm ở registry collector (17 category thật, selector HTML có thể đổi) làm M1/M3/M4 không có canonical thật để test | M1, M3, M4 | Dùng `data/fixtures/canonical.jsonl` (tuần 1) làm input giả lập từ tuần 2, không chờ registry thật; M2 chuyển sang full crawl chỉ ở tuần 5–6 |
| M1 đổi ontology sau tuần 3 làm M2 (mapping) và M4 (Fuseki loader, CQ) phải sửa lại | M2, M4 | Ontology freeze cứng cuối tuần 3 (Development Plan); mọi đổi sau đó phải qua Decision Register và thông báo cả nhóm trong ngày |
| M4 một mình sở hữu cả Fuseki và Neo4j — nếu M4 nghỉ, không ai vận hành được hạ tầng | Cả nhóm | M1 học đủ để chạy `make fuseki-up`/`make fuseki-load` làm backup (đã đọc Section 27 khi review reasoning) |
| M3 phụ thuộc DBpedia endpoint public khi demo — endpoint có thể lỗi/chậm | M3, M4 (demo) | CQ10 blocking chạy offline trên file expected trong `data/fixtures/expected/` (Section 35.1); federated demo (`CQ10-federated-demo.rq`) là optional, không phải fallback duy nhất |

---

## 6. Checklist trước khi nộp (rút gọn từ Section 40, 46, 53 — xem file gốc để đủ chi tiết)

- [ ] `make verify` trả `FINAL STATUS: PASS`, exit code `0` (`AC-016`).
- [ ] 23 class, 12 object property, 10 datatype property, 9 axiom (`AC-014`, `AC-007`).
- [ ] Registry coverage 100% trên snapshot đã cấu hình (`AC-024`, `AC-025`).
- [ ] 10/10 CQ PASS (`AC-010`), 10/10 Cypher PASS không `LPG_RDF_MISMATCH` (`AC-023`).
- [ ] ≥100 verified external link (`MET-008` floor, `AC-013`).
- [ ] Five-Star 1–5 PASS (`AC-020`).
- [ ] Report ≤15 trang theo đúng 9 mục Section 53.2; slide ~15 phút theo đúng 6 phần; video 3–5 phút có offline fallback.
- [ ] Cả 4 người trả lời được câu hỏi về phần người khác làm.

---

*Hết PLAN.md. Mọi chi tiết kỹ thuật đầy đủ (schema field, threshold, error code, command chính xác) nằm trong `PROJECT_SPEC.md`; file này chỉ là lớp điều phối con người lên trên spec đó.*
