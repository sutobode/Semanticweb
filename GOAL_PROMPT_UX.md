# GOAL 3 — VietHeritageLOD User Experience, Linked Data API & Interactive Explorer

Bạn là Coding Agent tiếp tục VietHeritageLOD sau khi full pipeline, RDF,
reasoning, Fuseki, Neo4j và RDF/LPG parity đã hoàn thành.

Mục tiêu của Goal này không phải dựng lại data pipeline. Mục tiêu là biến
VietHeritageLOD từ một project chủ yếu được trải nghiệm bằng SPARQL/Cypher
thành một hệ thống người dùng có thể:

  - mở trình duyệt;
  - tìm kiếm di sản bằng tiếng Việt;
  - lọc theo loại/category/địa điểm/năm;
  - xem trang chi tiết một entity;
  - xem provenance và external links;
  - xem RDF/Turtle hoặc JSON-LD;
  - truy cập linked-data resource URI;
  - sử dụng các query mẫu mà không cần tự viết SPARQL.

SPARQL vẫn phải được giữ lại cho người dùng nâng cao và làm query backend.
Không được thay thế RDF/SPARQL bằng database hoặc JSON API thuần túy.

====================================================================
TRẠNG THÁI HIỆN TẠI
====================================================================

Các capability hiện đã có:

  - RDF/Turtle dataset.
  - Ontology/RDFS/OWL.
  - OWL reasoning.
  - Fuseki SPARQL endpoint.
  - 10 SPARQL competency questions.
  - Neo4j LPG và Cypher parity.
  - CLI/Make pipeline.
  - linked_data_test kiểm tra DESCRIBE nội bộ.

Các capability còn thiếu hoặc chưa hoàn thiện:

  - Không có web explorer cho end user.
  - Không có HTTP API read-only rõ ràng cho search/entity detail.
  - Không có content negotiation thực tế cho resource URI.
  - Người dùng hiện phải biết SPARQL hoặc Cypher để khám phá dữ liệu.
  - Không có UI hiển thị provenance, external links và ontology type một cách
    trực quan.

Không thay đổi:

  - 23 ontology classes.
  - 12 object properties.
  - 10 datatype properties.
  - 9 OWL axioms.
  - Identity policy.
  - Registry coverage boundary.
  - Verified-link policy.
  - Existing full raw snapshot.
  - Existing RDF/LPG parity contract.

====================================================================
SEMANTIC WEB CONFORMANCE — NORMATIVE CONTRACT
====================================================================

Goal này MUST cải thiện trải nghiệm người dùng mà không biến VietHeritageLOD
thành REST application có RDF ở phía sau một cách hình thức. RDF graph,
ontology và SPARQL endpoint vẫn là semantic source of truth. API và UI chỉ là
các presentation/access layer có thể tái sinh từ graph.

### 1. RDF graph là nguồn dữ liệu có thẩm quyền

  - Không tạo một JSON/SQL document store thứ hai làm canonical source.
  - API MUST đọc dữ liệu từ Fuseki/RDF graph hoặc một read model có provenance
    rõ ràng và được rebuild deterministic từ RDF.
  - UI MUST không đọc trực tiếp raw JSONL để hiển thị kết quả khác với graph
    đang được publish.
  - Mọi entity trong API MUST có `@id` là stable HTTP URI và `@type` là URI
    của ontology class, không chỉ có string `id`/`type` cục bộ.
  - Các field convenience như `label`, `location`, `external_links` được phép
    cho UX, nhưng không được làm mất URI/predicate/provenance tương ứng.

### 2. URI design và dereferenceability

Dùng base URI từ `VH_BASE_URI`, không hardcode URI mới trong UI/API.

  - Entity URI: `${VH_BASE_URI}/resource/{entity_id}`.
  - Ontology URI: `${VH_BASE_URI}/ontology/{term}`.
  - Dataset/metadata URI phải ổn định và khác entity URI.
  - URI entity không được phụ thuộc vào label hiển thị, ngôn ngữ, pagination hoặc
    thứ tự kết quả.
  - Đổi label không được làm đổi identity URI.
  - Mọi entity URI hợp lệ phải dereference được khi service đang chạy.
  - Response phải có `Content-Type` đúng và `Vary: Accept` khi content negotiation.
  - Có thể dùng HTTP 303 See Other cho non-information resource tới representation
    document. Nếu implementation dùng HTTP 200 trực tiếp cho representation, phải
    ghi rõ trade-off trong `docs/UX_DESIGN.md` và test đầy đủ; không được tùy tiện
    trộn hai pattern.
  - HTML representation phải có `<link rel="canonical">` và link tới RDF/JSON-LD
    representations.
  - RDF representation phải giữ lại subject URI canonical, không tạo URI tạm.

### 3. RDF 1.1 media types và content negotiation

Resource endpoint MUST hỗ trợ các media type RDF 1.1 chuẩn:

  - `text/turtle` cho Turtle.
  - `application/ld+json` cho JSON-LD.
  - `text/html` cho human-readable document.
  - `application/json` chỉ là convenience API response và phải chứa liên kết
    tới canonical RDF resource; không được coi là RDF thay thế.

Mỗi representation phải:

  - trả status code đúng;
  - trả `Content-Type` đúng;
  - giữ ngôn ngữ literal (`@vi`, `@en`) khi có;
  - giữ URI cho resource/object thay vì flatten toàn bộ thành label;
  - không bỏ `rdfs:label`, `rdf:type`, provenance hoặc external identity links.

### 4. JSON-LD context bắt buộc

JSON-LD response MUST có context explicit, ổn định và version-controlled.
Không sinh context ad hoc theo từng response.

Context tối thiểu phải map các prefix/vocabulary đang dùng:

  - `vh` — VietHeritage ontology.
  - `vhr` — VietHeritage resource.
  - `rdf` — RDF.
  - `rdfs` — RDFS.
  - `owl` — OWL.
  - `dcterms` — DCMI Terms.
  - `prov` — PROV-O.
  - `dcat` — DCAT.
  - `skos` — SKOS.
  - `geo` — WGS84 Geo hoặc vocabulary geo đã chọn trong ontology.
  - `foaf` — FOAF nếu được dùng trong ontology.

JSON-LD entity response phải có dạng semantic tương đương:

  {
    "@context": "/contexts/vietheritage.jsonld",
    "@id": "http://localhost:3030/vietheritage/resource/example",
    "@type": [
      "http://localhost:3030/vietheritage/ontology/HeritageSite"
    ],
    "label": [
      { "@value": "...", "@language": "vi" }
    ]
  }

Tên field ngắn được phép cho UX nhưng context MUST map chúng về predicate URI.
Không dùng JSON-LD `@type` là tên class không có namespace.

### 5. RDF, RDFS và OWL phải được phản ánh trong UX

UI/API MUST phân biệt:

  - asserted type/triple từ data graph;
  - inferred type/triple từ inferred graph;
  - ontology/schema term từ ontology graph.

Không được trình bày inferred triple như thể đó là fact trực tiếp từ registry.
Nếu API gom các named graph thành một kết quả, response phải có provenance hoặc
trường `asserted_in_graph`/`inferred_in_graph` phù hợp với graph thực tế.

Trang entity nên hiển thị:

  - direct RDF types;
  - inferred superclasses nếu có;
  - human-readable `rdfs:label` của class/property;
  - link tới ontology term;
  - distinction giữa source assertion và OWL/RDFS inference.

Không được sửa ontology hoặc giảm reasoning chỉ để làm UI đơn giản hơn.

### 6. Named graphs và provenance

Giữ semantic separation của các named graph hiện có:

  - ontology graph;
  - asserted data graph;
  - verified external-links graph;
  - inferred graph;
  - dataset metadata graph.

API/UI có thể dùng union default graph cho search, nhưng detail/provenance phải
có khả năng truy ngược graph nguồn.

Dataset metadata MUST dùng vocabulary chuẩn khi có thể:

  - `dcat:Dataset` cho dataset.
  - `dcterms:title`, `dcterms:description`, `dcterms:license`.
  - `dcterms:issued` hoặc `dcterms:modified` cho snapshot.
  - `dcterms:source` cho nguồn registry/Wikipedia/external.
  - `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:generatedAtTime`.

UI không được hiển thị provenance như text trang trí không có URI; mỗi source
nên có `dcterms:source`/`prov:wasDerivedFrom` hoặc URI tương ứng.

### 7. SHACL validation

Bổ sung SHACL shapes, ví dụ:

  shapes/vietheritage.shacl.ttl

SHACL MUST kiểm tra public graph contract mà API/UI dựa vào, tối thiểu:

  - entity có stable URI;
  - entity có `rdf:type` hợp lệ;
  - label có language tag hoặc datatype policy rõ ràng;
  - required provenance/source fields;
  - datatype tọa độ/năm hợp lệ;
  - verified link có target URI hợp lệ;
  - không có violation làm API trả entity không có identity.

SHACL không được biến các field optional thành required nếu canonical schema/spec
không yêu cầu. Tách rõ:

  - shapes cho asserted data;
  - shapes cho inferred/public view nếu cần;
  - severity `Violation`, `Warning`, `Info`.

Chạy SHACL trên sample và full snapshot, ghi machine-readable report, và nối
stage vào `make validate` hoặc một target validation rõ ràng. SHACL bổ sung cho
validator hiện tại, không được xóa các validation contract cũ.

### 8. SPARQL 1.1 và service semantics

Fuseki vẫn là SPARQL 1.1 service chính:

  - query endpoint read-only cho UI/power users;
  - không expose SPARQL Update trong public UI/API;
  - trả `application/sparql-results+json` hoặc `text/csv` cho SELECT;
  - giữ query hash, endpoint, timeout và result limit trong audit log.

Expose hoặc document SPARQL Service Description theo chuẩn `sd:` nếu Fuseki
hỗ trợ native; nếu không, tạo metadata endpoint/read-only representation có:

  - `sd:Service`;
  - `sd:endpoint`;
  - supported query language `sd:SPARQL11Query`;
  - result formats;
  - default/named graph information;
  - dataset URI.

Các competency questions hiện có phải được expose như allowlisted query templates,
không hardcode lại thành các kết quả JSON không có liên kết tới SPARQL/RDF.

### 9. Verified links và linkset semantics

Wikidata/DBpedia links phải giữ policy hiện tại:

  - `owl:sameAs` chỉ cho verified identity evidence;
  - label giống nhau không đủ để tạo `owl:sameAs`;
  - external link chưa verified phải là candidate/review artifact, không đưa vào
    public verified link view;
  - `rdfs:seeAlso`/homepage dùng cho related information không phải identity.

API/UI phải phân biệt:

  - verified identity link;
  - candidate/manual-review link;
  - source/reference link.

Nếu tạo linkset metadata, dùng vocabulary chuẩn như `void:Linkset`, `void:subjectsTarget`,
`void:objectsTarget`, `void:triples`, `dcterms:source` và provenance tương ứng.
Không trình bày mọi external URL như cùng một loại identity.

### 10. API/UI là lớp trình bày, không thay thế Semantic Web

API endpoint MUST có cách truy ngược:

  UI item → API URL → canonical entity URI → RDF predicates → SPARQL graph.

Mỗi entity detail cần có các liên kết:

  - canonical URI;
  - HTML representation;
  - Turtle representation;
  - JSON-LD representation;
  - SPARQL endpoint/query mẫu;
  - provenance source;
  - verified external identity links.

Không được thiết kế API chỉ trả:

  { "id": 1, "name": "...", "type": "site" }

mà không có URI/predicate semantics. Convenience response có thể tồn tại,
nhưng phải có `@id`, `@type`, context hoặc links tới semantic representations.

### 11. Semantic Web acceptance criteria

Goal chỉ PASS nếu:

  - entity URI dereference được;
  - content negotiation trả đúng HTML/Turtle/JSON-LD;
  - JSON-LD context map đúng predicate/class URI;
  - RDF output parse được bằng RDFLib/Jena;
  - SHACL sample/full validation PASS hoặc chỉ có warning đã được giải thích;
  - SPARQL 1.1 endpoint vẫn query được;
  - ontology graph, asserted graph, inferred graph và link graph không bị trộn
    mất provenance;
  - UI/API không tạo canonical data model riêng;
  - `owl:sameAs` chỉ hiển thị verified links;
  - inferred facts được phân biệt với asserted facts;
  - API/UI smoke tests không làm giảm các acceptance hiện có:
      coverage 100%
      CQ 10/10
      Cypher/RDF parity 10/10
      FINAL STATUS: PASS.

====================================================================
PHASE 1 — AUDIT VÀ THIẾT KẾ
====================================================================

Đọc trước:

  PROJECT_SPEC.md
  PLAN.md
  README.md
  docs/E2E.md
  docs/RELEASE.md
  ontology/vietheritage.ttl
  docker-compose.yml
  Makefile
  src/vietheritage/reporting/linked_data_test.py
  src/vietheritage/reporting/query_runner.py
  src/vietheritage/lpg/cypher_runner.py

Kiểm tra:

  - Fuseki query endpoint hiện tại.
  - Cách resource URI được sinh trong RDF.
  - Các predicate/class đang được dùng trong full Turtle.
  - 10 SPARQL query hiện có.
  - Schema canonical record.
  - Các field có thể hiển thị cho người dùng:
      label_vi
      entity_type
      registry_category
      description_vi
      location/address
      coordinates
      recognition_year
      aliases
      source_status
      provenance
      external_ids
      verified external links
      ontology types

Không được đoán field mới nếu field đó không tồn tại trong canonical/RDF.
Nếu cần field mới, phải cập nhật schema/spec/test trước.

Tạo tài liệu thiết kế:

  docs/UX_DESIGN.md

Tài liệu phải mô tả:

  - User personas.
  - Search flow.
  - Entity detail flow.
  - SPARQL power-user flow.
  - API flow.
  - Content negotiation.
  - Error states.
  - Security boundary.
  - Data provenance display.
  - Pagination and query limits.

====================================================================
PHASE 2 — READ-ONLY LINKED DATA API
====================================================================

Implement một HTTP service read-only. Ưu tiên framework nhẹ, rõ ràng và dễ chạy
local. Có thể dùng FastAPI/Uvicorn nếu phù hợp, nhưng dependency mới phải được
pin exact version trong requirements.txt và có test. Không thêm dependency chỉ
để tạo UI nếu vanilla HTML/JS là đủ.

Service phải truy vấn Fuseki, không đọc trực tiếp file JSONL để tạo kết quả
khác với graph đang được publish.

API tối thiểu:

  GET /api/health

Response:

  {
    "status": "ok",
    "fuseki": "ok",
    "dataset": "vietheritage"
  }

  GET /api/stats

Phải trả các metric có thể lấy từ graph:

  - total entities
  - counts by class/entity type
  - verified external links
  - available categories
  - snapshot/provenance nếu có trong graph

  GET /api/search

Query parameters:

  - q
  - entity_type
  - registry_category
  - location
  - year
  - page
  - page_size

Rules:

  - page_size mặc định 25.
  - page_size tối đa 100.
  - page và page_size phải được validate.
  - Không cho phép SPARQL UPDATE.
  - Không nối chuỗi input người dùng trực tiếp vào SPARQL.
  - Dùng query template an toàn, escaping literal/IRI đúng chuẩn.
  - Có timeout rõ ràng khi gọi Fuseki.
  - Có lỗi rõ ràng nếu Fuseki unavailable.
  - Trả pagination metadata:
      page
      page_size
      total
      has_next
  - Kết quả phải gồm:
      id
      uri
      label
      entity_type
      category
      location
      year
      source_status
      external_links

  GET /api/entities/{entity_id}

Phải trả detail của một entity:

  - stable internal URI
  - label tiếng Việt
  - English label nếu có
  - ontology classes
  - entity type
  - category
  - description
  - aliases
  - location/address
  - coordinates nếu có
  - years nếu có
  - relations
  - provenance
  - registry source
  - Wikipedia source nếu có
  - verified Wikidata/DBpedia links nếu có

Entity không tồn tại phải trả HTTP 404 với JSON error chuẩn.

  GET /resource/{entity_id}

Đây là linked-data resource endpoint.

Phải hỗ trợ content negotiation:

  Accept: text/html
      → trang entity HTML dễ đọc

  Accept: text/turtle
      → RDF Turtle của entity

  Accept: application/ld+json
      → JSON-LD của entity

  Accept: application/json
      → JSON representation cho API client

Nếu không có Accept phù hợp, dùng JSON hoặc HTML theo policy đã ghi trong
docs/UX_DESIGN.md.

Không được dùng DESCRIBE không giới hạn cho toàn bộ dataset. Query resource
phải giới hạn entity/related triples hợp lý.

  GET /api/queries

Trả danh sách 10 competency questions có sẵn:

  - id
  - title
  - description
  - query endpoint
  - whether it is safe/read-only

  GET /api/queries/{query_id}/run

Chỉ cho phép chạy 10 query đã allowlist trong `sparql/`.
Không cho phép client gửi arbitrary UPDATE query.
Nếu cho phép arbitrary SELECT cho power user, endpoint phải:

  - read-only;
  - có timeout;
  - có LIMIT bắt buộc;
  - giới hạn query size;
  - không cho UPDATE/LOAD/CLEAR/DROP/DELETE/INSERT;
  - không expose credentials;
  - được tách khỏi public UI.

====================================================================
PHASE 3 — WEB EXPLORER CHO NGƯỜI DÙNG
====================================================================

Tạo UI đơn giản, ưu tiên server-rendered HTML hoặc vanilla HTML/CSS/JS để
không cần build tool frontend nặng.

Tối thiểu phải có:

  1. Trang home:
       - tên project;
       - mô tả ngắn;
       - coverage metrics;
       - ô tìm kiếm;
       - link tới SPARQL endpoint;
       - link tới API docs;
       - link tới danh sách competency questions.

  2. Trang search:
       - ô tìm kiếm label;
       - filter entity type;
       - filter category;
       - filter location;
       - filter year;
       - pagination;
       - link tới entity detail;
       - trạng thái loading/empty/error.

  3. Trang entity detail:
       - label;
       - type/class;
       - description;
       - location;
       - year;
       - provenance;
       - registry URL;
       - Wikipedia link;
       - Wikidata link;
       - DBpedia link;
       - URI;
       - nút xem Turtle;
       - nút xem JSON-LD;
       - danh sách relations.

  4. Trang competency questions:
       - hiển thị 10 query mẫu;
       - mô tả query;
       - nút chạy query;
       - bảng kết quả;
       - link tới SPARQL endpoint cho power user.

  5. Trang error:
       - Fuseki unavailable;
       - entity not found;
       - invalid filter;
       - timeout.

UI phải:

  - hỗ trợ tiếng Việt;
  - responsive cơ bản;
  - dùng semantic HTML;
  - có label/aria cho form;
  - không yêu cầu người dùng biết SPARQL;
  - không hiển thị password hoặc environment variable;
  - không cho phép UPDATE query từ UI.

MAY HAVE, chỉ làm sau khi MVP PASS:

  - bản đồ Leaflet cho entity có coordinates;
  - graph visualization cho relations;
  - lọc theo province trên bản đồ;
  - chuyển ngôn ngữ Việt/Anh;
  - autocomplete label.

Không để map hoặc graph visualization làm blocker cho search/detail/API.

====================================================================
PHASE 4 — DOCKER VÀ MAKE TARGETS
====================================================================

Bổ sung service explorer vào docker-compose.yml, chỉ bind loopback, ví dụ:

  http://localhost:8000

Service explorer phải nhận environment:

  FUSEKI_QUERY_URL
  FUSEKI_DATASET
  APP_HOST
  APP_PORT

Không hardcode password.
Không expose Docker service ra toàn mạng.

Bổ sung Make targets:

  make app-up
  make app-down
  make app-test
  make app-smoke
  make api-docs

Nếu dùng OpenAPI, endpoint phải có:

  /docs
  /openapi.json

`make app-smoke` phải kiểm tra tối thiểu:

  - GET /
  - GET /api/health
  - GET /api/stats
  - GET /api/search?q=Huế
  - GET /api/entities/{known_entity_id}
  - GET /resource/{known_entity_id} với Accept text/turtle
  - GET /resource/{known_entity_id} với Accept application/ld+json
  - entity không tồn tại trả 404

Cập nhật docs/E2E.md theo thứ tự:

  1. make pipeline RUN_MODE=full
  2. make fuseki-up
  3. make fuseki-load RUN_MODE=full
  4. make cq-test
  5. make neo4j-up
  6. make neo4j-load RUN_MODE=full
  7. make cypher-test
  8. make app-up
  9. make app-smoke
  10. make verify RUN_MODE=full

====================================================================
PHASE 5 — TEST VÀ QUALITY
====================================================================

Viết test cùng implementation.

Bắt buộc có:

  - API health test.
  - Search pagination test.
  - Search filter test.
  - Empty result test.
  - 404 entity test.
  - Fuseki unavailable test.
  - Invalid page/page_size test.
  - Query injection rejection test.
  - UPDATE query rejection test.
  - Content negotiation test cho Turtle.
  - Content negotiation test cho JSON-LD.
  - Provenance/external-link response test.
  - Allowlist competency-query test.
  - HTML smoke test.
  - API OpenAPI/contract test.
  - Docker/Make command contract test.

Không gọi network Internet trong unit tests.
Mock Fuseki trong unit tests.
Integration tests được phép dùng Fuseki local Docker.
E2E test phải có điều kiện rõ ràng nếu Docker không chạy.

Security checks:

  - Không log query chứa secret.
  - Không log `.env`.
  - Không cho SPARQL UPDATE.
  - Không cho arbitrary filesystem path.
  - Không dùng `eval`.
  - Giới hạn result size.
  - Timeout Fuseki.
  - Không expose Neo4j credentials qua API.
  - CORS chỉ bật local origin cần thiết hoặc tắt mặc định.

====================================================================
PHASE 6 — DOCUMENTATION VÀ USER DEMO
====================================================================

Tạo:

  docs/API.md
  docs/USER_GUIDE.md
  docs/UX_DESIGN.md

`docs/USER_GUIDE.md` phải hướng dẫn một người không biết SPARQL:

  1. Chạy Docker/services.
  2. Mở web explorer.
  3. Tìm “Huế”, “Hội An”, “Vịnh Hạ Long”.
  4. Lọc theo loại/category.
  5. Mở entity detail.
  6. Xem provenance.
  7. Mở RDF Turtle/JSON-LD.
  8. Chạy một competency question mẫu.
  9. Khi nào dùng SPARQL trực tiếp.

README phải có:

  - Web Explorer URL.
  - API URL.
  - SPARQL URL.
  - Neo4j URL.
  - command `make app-up`.
  - command `make app-smoke`.
  - ví dụ curl/PowerShell.
  - giới hạn local-only/security.

Ví dụ phải có:

  curl http://localhost:8000/api/health
  curl "http://localhost:8000/api/search?q=Huế"
  curl http://localhost:8000/api/entities/<entity_id>
  curl -H "Accept: text/turtle" \
       http://localhost:8000/resource/<entity_id>

====================================================================
PHASE 7 — FINAL VALIDATION
====================================================================

Không chạy sample/test trên checkout đang giữ full snapshot nếu không có
worktree riêng. Nếu collector tests ghi đè artifacts, chạy lại full pipeline
trước validation cuối:

  make pipeline RUN_MODE=full
  make fuseki-up
  make fuseki-load RUN_MODE=full
  make cq-test
  make neo4j-up
  make neo4j-load RUN_MODE=full
  make cypher-test
  make app-up
  make app-smoke
  make traceability-check
  make verify RUN_MODE=full

Điều kiện PASS:

  - Existing regression suite PASS.
  - New API/UI tests PASS.
  - make app-smoke PASS.
  - API health PASS.
  - Search real full data trả kết quả.
  - Entity detail trả 200 cho entity thật.
  - Entity không tồn tại trả 404.
  - Turtle content negotiation PASS.
  - JSON-LD content negotiation PASS.
  - Không có SPARQL UPDATE từ public API/UI.
  - CQ 10/10 PASS.
  - Cypher/RDF parity 10/10 PASS.
  - Full verify trả FINAL STATUS: PASS.
  - Không làm thay đổi ontology count/axiom.
  - Không làm giảm coverage hoặc verified links.

====================================================================
PHASE 8 — COMMIT VÀ SAFETY
====================================================================

Stage explicit:

  src/... API/UI files
  tests/... new tests
  docker-compose.yml
  Makefile
  requirements.txt nếu có dependency mới
  docs/API.md
  docs/USER_GUIDE.md
  docs/UX_DESIGN.md
  docs/E2E.md
  README.md

Không stage:

  .env
  secrets
  reports/runtime
  logs
  Docker volumes
  protected files
  raw data nếu không có yêu cầu mới
  unrelated generated files

Chạy:

  git diff --cached --check
  git diff --cached --stat
  git status --short

Tạo commit mới:

  git commit -m "Add user-facing linked data explorer"

Không push.
Không amend commit cũ.
Không rewrite Git history.
Không dùng `git add .`.

====================================================================
ĐIỀU KIỆN HOÀN THÀNH
====================================================================

Chỉ báo hoàn thành khi:

  1. Người dùng có thể mở browser và tìm kiếm entity mà không cần viết SPARQL.
  2. API search/detail/health hoạt động trên full data.
  3. Resource URI hỗ trợ HTML, Turtle và JSON-LD.
  4. Provenance và verified external links hiển thị được.
  5. SPARQL vẫn hoạt động cho power user.
  6. Public UI/API chỉ read-only.
  7. API có pagination, timeout, validation và query safety.
  8. `make app-smoke` PASS.
  9. Existing full verify vẫn PASS.
  10. Test mới PASS.
  11. Documentation có USER_GUIDE/API/UX.
  12. Không commit credentials/secrets.
  13. Có commit implementation rõ ràng.
  14. Không push.

Báo cáo cuối phải nêu rõ:

  - URL web explorer.
  - URL API.
  - URL SPARQL.
  - Các lệnh khởi động.
  - Các test đã chạy.
  - Những phần optional chưa làm.
  - Cách người dùng không biết SPARQL có thể trải nghiệm project.
