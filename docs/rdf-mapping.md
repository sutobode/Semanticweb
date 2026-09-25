# RDF Mapping — VietHeritageLOD (Thành viên 3, COMP-005)

Tài liệu này diễn giải bằng văn xuôi mapping đã được triển khai và đóng băng trong
`config/mapping.yaml` (nguồn authoritative duy nhất, PROJECT_SPEC.md §19) và
`src/vietheritage/rdf/generator.py` (COMP-005). Không có logic mapping nào được
hard-code rải rác trong code; mọi thay đổi mapping MUST đi qua `config/mapping.yaml`.

## 1. URI design

Namespace (`ontology/vietheritage.ttl:1-12`, PROJECT_SPEC §14–15):

| Prefix | Namespace | Dùng cho |
|---|---|---|
| `vh:` | `{BASE}/ontology/` | Class, object property, datatype property project-owned |
| `vhr:` | `{BASE}/resource/` | Mọi entity instance (A-Box) |
| `rdf:`, `rdfs:`, `owl:`, `xsd:` | chuẩn W3C | Core RDF/RDFS/OWL |
| `dcterms:` | `http://purl.org/dc/terms/` | Provenance, license, metadata |
| `prov:` | `http://www.w3.org/ns/prov#` | Provenance (wasDerivedFrom, wasGeneratedBy, Activity) |
| `dcat:` | `http://www.w3.org/ns/dcat#` | Dataset/Distribution metadata |
| `geo:` | `http://www.w3.org/2003/01/geo/wgs84_pos#` | Toạ độ (`lat`/`long`) |
| `foaf:`, `schema:` | chuẩn | Reserved cho mở rộng, chưa dùng trong A-Box hiện tại |

`{BASE}` mặc định `http://localhost:3030/vietheritage`, đọc từ `VH_BASE_URI`
(`validation/semantic.py:base_uri()`); generator từ chối base URI có trailing
slash, query hoặc fragment (`generator.py:_base()`).

Resource URI = `{BASE}/resource/{entity_id}` (`generator.py:entity_uri()`).
`entity_id` MUST khớp regex tại `src/vietheritage/validation/policy.py` (`ENTITY_ID`):

```text
(registry|person|area|event|period|complex|organization|style|site)-[A-Za-z0-9._~-]+
```

- `registry-*`: entity có nguồn trực tiếp từ registry Cục Di sản văn hóa (sha256
  12 ký tự của `category_url | category | label_key` — Thành viên 2, `COMP-003`).
- `person-*`, `area-*`, `event-*`, `period-*`, `complex-*`, `organization-*`,
  `style-*`: entity phái sinh (derived) — ví dụ `organization-unesco`,
  `area-hanoi`, hoặc `person-wikidata-q<QID>` khi person chỉ xác định được qua
  Wikidata.
- `site-*`: CHỈ dùng trong `data/fixtures/` và ví dụ tài liệu. `generate-rdf
  --run-mode full` chủ động reject (`FIXTURE_ID_IN_PRODUCTION`) nếu một
  `entity_id` production bắt đầu bằng `site-` (`generator.py:run()`).

URI vì vậy: unique (hash hoặc ID nguồn xác định), stable (không phụ thuộc
label — đổi tên di tích không đổi URI), không percent-encode (mọi ký tự tiếng
Việt chỉ nằm trong literal), và dereferenceable qua Explorer/Fuseki Graph Store
tại chính `{BASE}/resource/{entity_id}`.

## 2. Mapping bảng chính — canonical field → RDF

Nguồn: `config/mapping.yaml` (`entity_types`, `literal_properties`,
`coordinate_properties`, `relation_properties`, `provenance_properties`).
Cột "Hàm sinh" trỏ tới hàm trong `generator.py` xử lý nhóm field đó.

### 2.1 Class (rdf:type)

| `entity_type` canonical | Class RDF | Điều kiện phụ |
|---|---|---|
| `HeritageSite` | `vh:HeritageSite` | + subtype từ `site_types` (xem 2.1.1); + `vh:UNESCOHeritageSite` được **suy luận** (không assert trực tiếp) khi `vh:recognizedBy vhr:organization-unesco` |
| `AdministrativeArea` | `vh:AdministrativeArea` | — |
| `HistoricalPerson` | `vh:HistoricalPerson` | — |
| `HistoricalEvent` | `vh:HistoricalEvent` | — |
| `HistoricalPeriod` | `vh:HistoricalPeriod` | — |
| `HeritageComplex` | `vh:HeritageComplex` | — |
| `Organization` | `vh:Organization` | — |
| `ArchitecturalStyle` | `vh:ArchitecturalStyle` | — |
| `Museum` | `vh:Museum` | — |
| `NationalTreasure` | `vh:NationalTreasure` | — |
| `DocumentaryHeritage` | `vh:DocumentaryHeritage` | — |
| `Artisan` | `vh:Artisan` | — |
| `CulturalObject` | `vh:CulturalObject` | — |
| `IntangibleHeritage` | `vh:IntangibleHeritage` + subclass sau | Xem 2.1.2 |

Hàm sinh: `add_entity_type_triples()` (`generator.py:84-107`).

#### 2.1.1 `site_types` → HeritageSite subtype (token map)

```text
"lịch sử"   -> vh:HistoricalSite
"tôn giáo"  -> vh:ReligiousSite
"khảo cổ"   -> vh:ArchaeologicalSite
"kiến trúc" -> vh:ArchitecturalSite
```

Token match là substring, case-insensitive, trên chuỗi đã normalize; một site
có thể nhận nhiều subtype cùng lúc (multi-`rdf:type`), đúng khả năng overlap
của class hierarchy (§ ontology, Thành viên 1).

#### 2.1.2 `registry_category` → IntangibleHeritage subclass (exclusivity)

| `registry_category` | Subclass đóng băng (AX-008 `owl:disjointUnionOf`) |
|---|---|
| `intangible_representative` | `vh:RepresentativeIntangibleHeritage` |
| `intangible_urgent` | `vh:UrgentSafeguardingIntangibleHeritage` |
| `national_intangible` | `vh:NationalIntangibleHeritage` |

Generator raise `MAPPING_TYPE_MISMATCH` nếu một category thuộc bảng này xuất
hiện trên record không phải `entity_type=IntangibleHeritage` — bảo vệ tính
exclusivity mà AX-008 cần (mỗi entity chỉ ở đúng một trong ba subclass).

### 2.2 Literal properties

| Canonical field | Predicate | Datatype/lang | Bắt buộc | Ghi chú |
|---|---|---|---|---|
| `label_vi` | `rdfs:label` | `@vi` | Có | Domain-checked; nếu domain ontology không khớp type của entity thì **bỏ qua triple** thay vì raise (an toàn khi mapping mở rộng) |
| `description_vi` | `rdfs:comment` + `dcterms:description` | `@vi` | Không | Sinh cả hai predicate cho cùng giá trị |
| `construction_year` | `vh:constructionYear` | `xsd:gYear` | Không | Format `%04d` |
| `recognition_year` | `vh:recognitionYear` | `xsd:gYear` | Không | Number-only, đã loại số hiệu quyết định (M2-01) |
| `birth_year` / `death_year` | `vh:birthYear` / `vh:deathYear` | `xsd:gYear` | Không | |
| `address` | `vh:address` | `xsd:string` | Không | |
| `level` | `vh:areaLevel` | `xsd:string` | Không | |
| `source_page_id` | `vh:sourcePageId` | `xsd:integer` | Chỉ khi `source_status != registry_only` | |
| `source_title` | `vh:sourceTitle` | `xsd:string` | Chỉ khi `source_status != registry_only` | |
| `aliases_vi[]` | `skos:altLabel` | `@vi` | Không | Bỏ alias trùng `label_vi` |
| `coordinates.lat` | `geo:lat` | `xsd:decimal` | Cặp | Chỉ sinh khi **cả** lat và lon có giá trị |
| `coordinates.lon` | `geo:long` | `xsd:decimal` | Cặp | |

Hàm sinh: `add_label_and_literals()` (`generator.py:120-148`). Mọi predicate đi
qua `_domain_matches()` — nếu `rdfs:domain` của predicate trong ontology không
match type đã gán cho subject, triple bị bỏ, không được sinh sai domain rồi
dựa vào SHACL để bắt sau.

### 2.3 Object properties (relation fields)

| Canonical field | Predicate | Ràng buộc range bổ sung |
|---|---|---|
| `located_in` | `vh:locatedIn` | range `vh:AdministrativeArea` (kiểm bằng `Contract.matches`) |
| `parent_area` | `vh:locatedIn` | dùng cho `AdministrativeArea → AdministrativeArea` (chuỗi phường→quận→tỉnh) |
| `associated_persons` | `vh:associatedWithPerson` | range `vh:HistoricalPerson` |
| `associated_events` | `vh:associatedWithEvent` | range `vh:HistoricalEvent` |
| `periods` | `vh:belongsToPeriod` | range `vh:HistoricalPeriod` |
| `part_of` | `vh:partOf` | range `vh:HeritageComplex` |
| `member_sites` | `vh:hasMember` | 1 triple / member, range mở (`vh:CulturalHeritageEntity`) |
| `recognized_by` | `vh:recognizedBy` | range `vh:Organization`, chỉ khi subject là `HeritageSite` |
| `built_by` | `vh:builtBy` | **bắt buộc thêm** `object_must_be: vh:HistoricalPerson` — target là Organization sẽ bị loại thầm lặng, không raise |
| `architectural_styles` | `vh:hasArchitecturalStyle` | range `vh:ArchitecturalStyle` |

Hàm sinh: `add_relations()` (`generator.py:159-185`). Quy trình cho mỗi target:

1. Predicate phải pass domain check trên subject (như literal).
2. `target_id` phải khớp `ENTITY_ID` (regex hợp lệ) — id rác bị bỏ, không raise.
3. Target phải **đã có `rdf:type`** trong graph hiện tại (tức entity đích tồn
   tại thật, không phải tham chiếu treo) và match toàn bộ `rdfs:range` +
   `object_must_be` (nếu có).
4. Chỉ khi cả ba điều kiện đúng, triple mới được thêm.

Kết quả: generator **im lặng bỏ qua** quan hệ thiếu điều kiện thay vì tạo
triple sai hoặc raise và làm fail cả record (đúng tinh thần PROJECT_SPEC §19
"omit relation" cho từng dòng mapping).

`world_heritage` là trường hợp đặc biệt không qua `relation_properties`: khi
`registry_category == world_heritage` và `entity_type == HeritageSite`,
generator tự thêm `vh:recognizedBy vhr:organization-unesco` (named individual
cố định khai trong `mapping.yaml > derived_entities`), để reasoner suy ra
`vh:UNESCOHeritageSite` qua AX-005 thay vì assert class đó trực tiếp.

### 2.4 Provenance (mọi source-derived entity)

Hàm sinh: `add_provenance()` (`generator.py:199-219`), theo PROJECT_SPEC §21.1.

```turtle
vhr:registry-xxxx
    dcterms:source <registry_url_hoặc_source_url> ;
    prov:wasDerivedFrom <cùng URI> ;
    dcterms:license <https://creativecommons.org/licenses/by-sa/4.0/> ;
    dcterms:modified "2026-09-12"^^xsd:date ;
    prov:wasGeneratedBy vhr:activity-run-<hash-snapshot> .
```

Thứ tự ưu tiên nguồn: `provenance.source` (nếu M2 đã ghi rõ) → `registry_url`
→ `source_url`; mọi URI khác-nhau-nhưng-không-trùng đều được giữ (một entity
`registry+wikipedia` có cả hai `dcterms:source`). `registry_only` record vẫn
có provenance đầy đủ (chỉ thiếu `vh:sourcePageId`/`vh:sourceTitle`), đúng OWA
(PROJECT_SPEC §1.4.1) — thiếu enrichment không có nghĩa thiếu nguồn gốc.

`activity` URI dùng chung cho mọi entity trong cùng một run
(`_activity_uri()` = hash của `coverage_snapshot` mới nhất), nên
`prov:wasGeneratedBy` cho phép truy vết "record này sinh ra từ snapshot nào"
mà không tạo một Activity/entity.

### 2.5 Dataset-level metadata (`data/rdf/dataset-metadata.ttl`)

`build_dataset_metadata()` (`generator.py:290-353`) sinh một `dcat:Dataset`
duy nhất tại `{BASE}/dataset/vietheritage` với: song ngữ title, description,
license, `dcterms:created`/`modified`, `dcterms:identifier` = snapshot ID,
`prov:wasGeneratedBy` → `prov:Activity` (start/end time, `prov:used` mọi
source URL kèm checksum nếu coverage report có), `dcat:accessURL`/
`downloadURL` trỏ Fuseki thật, và 5 `dcat:Distribution` — một cho mỗi named
graph (`ontology`, `data`, `external-links`, `inferred`, `metadata`). Số liệu
vận hành (triples, verified links, canonical records) được ghi dưới dạng
`dcterms:extent "key=value"` và được `refresh_dataset_metadata_metrics()` cập
nhật lại sau mỗi lần `link`/`reason` mà không cần chạy lại toàn bộ generate-rdf.

## 3. Vocabulary reuse — không có property tự chế khi đã có chuẩn

| Nhu cầu | Vocabulary chuẩn dùng | KHÔNG tự tạo |
|---|---|---|
| Nhãn, mô tả | `rdfs:label`, `rdfs:comment`, `skos:altLabel` | `vh:label` |
| Toạ độ | `geo:lat`, `geo:long` (WGS84) | `vh:latitude` |
| Nguồn, license, ngày | `dcterms:source`, `dcterms:license`, `dcterms:modified`, `dcterms:created`, `dcterms:description`, `dcterms:subject` | `vh:sourceUrl` |
| Provenance/dataset | `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:Activity`, `prov:used`, `dcat:Dataset`, `dcat:Distribution` | `vh:derivedFrom` |
| Identity link | `owl:sameAs` | `vh:sameAs` |
| Datatype | `xsd:gYear`, `xsd:decimal`, `xsd:integer`, `xsd:date`, `xsd:dateTime`, `xsd:string` | — |

`vh:` chỉ định nghĩa property **không có tương đương chuẩn phù hợp** trong
domain di sản văn hóa: `constructionYear`, `recognitionYear`, `birthYear`,
`deathYear`, `address`, `areaLevel`, `sourcePageId`, `sourceTitle`, và 12
object property T-Box (`locatedIn`, `partOf`, `hasPart`, …) — các quan hệ này
không có equivalent trực tiếp trong FOAF/DCTerms/PROV nên là chọn lựa đúng,
không phải reinventing.

## 4. RDFLib transformation — pipeline thực thi

```text
data/processed/canonical.jsonl (COMP-004, đã validate JSON Schema)
        │  Draft202012Validator + FormatChecker (generator.py:run())
        ▼
build_graph(records)                       # generator.py:233-246
    ├─ Pass 1: add_entity_type_triples() cho MỌI record trước
    │           (để add_relations() ở pass 2 luôn thấy đủ rdf:type của target)
    └─ Pass 2: record_to_triples() = type + literal + registry-subject + relation + provenance
        ▼
serialize_deterministic(g)                 # sort (subject, predicate, object) trước serialize
        ▼
data/rdf/vietheritage.ttl  (round-trip parse lại ngay để chặn Turtle hỏng — Section 20 failure rule)
data/rdf/dataset-metadata.ttl
```

Toàn bộ transformation dùng trực tiếp `rdflib.Graph/Literal/URIRef/Namespace`
và `rdflib.namespace.{RDF,RDFS,XSD,DCTERMS,PROV,SKOS}` — không tự viết Turtle
bằng string formatting ở bất kỳ đâu trong `generator.py`.

## 5. Kết quả đo được trên snapshot hiện tại

Chạy lại toàn bộ `normalize → resolve → map → generate-rdf` trên snapshot
`data/raw/registry_records.jsonl` hiện có (`RUN_MODE=full`, 2026-09-25):

| Metric | Giá trị |
|---|---:|
| Canonical record (registry + derived) | 1009 + 59 = 1068 |
| RDF triples (asserted, `data/rdf/vietheritage.ttl`) | 12 786 |
| Dataset metadata triples | 1 484 |
| Ontology triples | 321 |
| `HeritageSite` instances | 271 |
| `AdministrativeArea` instances (`vh:locatedIn` triples: 803) | 34 |
| Round-trip Turtle parse | PASS (RDFLib re-parse trong `generator.py:run()`) |

Xem thêm số liệu external linking tại `docs/link-evaluation.md`.
