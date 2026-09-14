# GOAL PROMPT — VietHeritageLOD Semantic Web UX, Accessibility and Demo Readiness

## 1. Vai trò và mục tiêu

Bạn là Semantic Web UX engineer, accessibility engineer và release verifier tiếp tục VietHeritageLOD sau khi Semantic Web remediation đã đạt mức:

```text
SUBSTANTIALLY COMPLIANT trong verified local-development profile
```

Mục tiêu của goal này là đưa trải nghiệm UI/UX và demo từ mức **functional local demo** lên mức **evidence-based production-ready experience**, mà không biến project thành một REST/JSON application có RDF chỉ để trang trí.

RDF graph, ontology, reasoning output, SHACL và Fuseki/SPARQL vẫn là semantic source of truth. HTTP API, browser Explorer và demo script chỉ là access/presentation layers có thể tái tạo từ graph.

Goal này phải tạo ra bằng chứng kiểm tra được cho:

- user journey của người không biết SPARQL;
- Semantic Web navigation của researcher;
- accessibility mục tiêu WCAG 2.2 AA;
- responsive và visual regression;
- performance và network resilience;
- demo offline/reproducible;
- liên kết rõ ràng từ UI/API đến canonical URI, RDF predicate, named graph và provenance.

Không được claim W3C certification nếu không có cơ chế chứng nhận chính thức.

## 2. Trạng thái hiện tại và gap cần đóng

Các capability đã có và phải giữ nguyên:

- Explorer local tại `http://localhost:3030`.
- Canonical resource tại `/vietheritage/resource/{entity_id}`.
- HTML, Turtle và JSON-LD content negotiation.
- Search, filter, entity detail, ontology type, provenance, source links và verified external links.
- Mười allowlisted competency questions.
- API/Explorer read-only.
- Loading, empty và error states.
- Public Fuseki query/read Graph Store và private admin loader service.
- `app-test: 12 passed`.
- `app-smoke: 13/13 PASS`.
- Canonical HTTP resource, Turtle và JSON-LD đã được kiểm tra trực tiếp.

Các gap chưa được xem là đóng hoàn toàn:

- Chưa có audit WCAG/axe hoặc bằng chứng keyboard và screen-reader đầy đủ.
- Chưa có responsive matrix và visual regression baseline.
- Chưa có performance budget và kết quả đo ổn định.
- Chưa có network-resilience test matrix cho Fuseki/API failure, timeout, empty result và retry.
- Chưa có demo runbook offline với preflight, thời lượng, expected output và recovery path rõ ràng.
- Một số UI link/config còn có thể phụ thuộc local host; phải phân biệt rõ local demo URL với production canonical domain.
- Chưa có machine-readable UX/demo acceptance report được liên kết với snapshot ID và commit.

## 3. Invariants bắt buộc

Không được:

- thay đổi frozen ontology: `23` classes, `12` object properties, `10` datatype properties, `9` OWL axioms/restrictions;
- thay đổi identity policy hoặc regenerate raw data chỉ để làm UI pass;
- tạo một JSON/SQL/document store thứ hai làm canonical source;
- cho UI đọc raw JSONL để tạo kết quả khác graph đang publish;
- flatten URI thành label rồi làm mất `@id`, `@type`, predicate, language tag hoặc provenance;
- hiển thị inferred fact như asserted fact;
- hiển thị candidate external link như verified identity link;
- mở write surface mới trong API/Explorer;
- commit secrets, `.env`, credentials, private keys hoặc user files;
- dùng `git add .`, reset history, force push hoặc push nếu chưa được yêu cầu.

Giữ nguyên snapshot hiện tại khi có thể:

```text
snapshot_id: 20260914T040348Z
canonical_records: 860
asserted_triples: 7249
inferred_closure_triples: 9358
inferred_delta_triples: 1782
verified_external_links: 114
```

Nếu cần dữ liệu fixture mới, dùng fixture deterministic và ghi rõ không thay thế full release snapshot.

## 4. Semantic UX contract

### 4.1 Ba user journey bắt buộc

#### Visitor — người không biết SPARQL

Visitor phải có thể:

1. mở Explorer;
2. tìm kiếm bằng nhãn tiếng Việt;
3. lọc theo category/type/năm nếu dữ liệu có field tương ứng;
4. xem empty state và biết cách sửa truy vấn;
5. mở entity detail;
6. hiểu tên, loại di sản, category, mô tả, nguồn và external links;
7. mở representation HTML, Turtle và JSON-LD;
8. quay lại kết quả mà không mất trạng thái cần thiết.

#### Researcher — người cần kiểm chứng dữ liệu

Researcher phải có thể:

1. nhìn thấy canonical HTTP URI;
2. sao chép/mở URI trực tiếp;
3. biết entity thuộc ontology class nào;
4. phân biệt asserted triples và inferred/closure triples;
5. biết triple hoặc field đến từ named graph nào;
6. mở `dcterms:source` và `prov:wasDerivedFrom`;
7. phân biệt verified identity link với reference/source link;
8. mở Turtle/JSON-LD và kiểm tra RDF round-trip;
9. truy cập SPARQL hoặc competency question tương ứng.

#### Power user — người dùng Semantic Web

Power user phải có thể:

- mở public SPARQL query endpoint;
- chạy CQ allowlist mà không cần arbitrary update;
- truy ngược UI item → API response → canonical URI → RDF predicate → named graph;
- thấy query ID/hash hoặc link đến query contract khi CQ được dùng trong UI.

### 4.2 Identity và representation

UI/API MUST dùng các URI đã publish bởi RDF:

```text
Entity:   http://localhost:3030/vietheritage/resource/{entity_id}
Ontology: http://localhost:3030/vietheritage/ontology/{term}
```

Không hardcode URI khác trong component nếu URI có thể lấy từ API/JSON-LD.

Resource endpoint phải giữ contract:

- `text/html` → HTML human-readable;
- `text/turtle` → Turtle parse được;
- `application/ld+json` → JSON-LD parse được;
- `application/json` → convenience response có `@id`, `@type` hoặc link rõ đến canonical resource;
- `Vary: Accept`;
- canonical `Link` tự trỏ về chính resource URI;
- HTML có `<link rel="canonical">` và alternate links;
- entity không tồn tại trả `404`;
- media type không hỗ trợ trả `406` hoặc documented policy.

Không dùng link cũ `/resource/{id}`, port cũ hoặc URI không dereferenceable trong UI mới.

### 4.3 Asserted, inferred và provenance trong UI

UI phải dùng label rõ ràng, ví dụ:

- `Asserted từ dữ liệu nguồn`;
- `Inferred bởi reasoning`;
- `Closure graph` nếu đang hiển thị toàn bộ closure;
- `Verified external identity`;
- `Reference/source link`.

Không dùng từ “fact” cho inferred triple nếu không có qualifier. Mỗi provenance item nên có URI hoặc link mở được, không chỉ là chuỗi text.

Dataset-level metadata cần có đường dẫn UI/API cho:

- dataset URI;
- snapshot ID;
- license;
- issued/modified;
- generated/derived activity;
- distributions/named graphs.

### 4.4 Context và linked-data discoverability

JSON-LD context phải ổn định và version-controlled. UI convenience field được phép, nhưng phải giữ mapping đến predicate URI.

Mỗi entity detail phải có hoặc link được tới:

- canonical URI;
- HTML representation;
- Turtle representation;
- JSON-LD representation;
- ontology class URI;
- source/provenance URI;
- verified external links;
- query/CQ hoặc SPARQL endpoint phù hợp.

## 5. Accessibility — mục tiêu WCAG 2.2 AA

Đây là target kiểm chứng, không chỉ là tuyên bố trong docs.

Phải kiểm tra tối thiểu:

- semantic landmarks: header, nav, main, footer;
- heading hierarchy không nhảy cấp vô lý;
- mỗi input có accessible label và trạng thái lỗi;
- mọi thao tác dùng được chỉ bằng keyboard, không yêu cầu pointer;
- thứ tự tab hợp lý và focus visible;
- focus không bị che bởi header/modal;
- button/link có tên accessible rõ ràng;
- loading, empty, error và query result update dùng live region phù hợp;
- color contrast đạt WCAG AA;
- thông tin không chỉ truyền bằng màu;
- zoom 200% không làm mất chức năng;
- viewport rộng khoảng 320 CSS px không tạo horizontal overflow ngoài chủ ý;
- `prefers-reduced-motion` được tôn trọng nếu có animation;
- external links có tên/behavior rõ ràng;
- screen-reader smoke path cho search → result → detail → RDF link.

Dùng công cụ tự động phù hợp với môi trường, ví dụ axe hoặc Lighthouse, nhưng không coi automated scan là đủ. Phải có checklist keyboard/manual và ghi violation, severity, rule, URL, screenshot hoặc reproduction path.

Không thêm dependency mở range. Nếu thêm tool, dùng version pin và cập nhật reproducibility docs.

## 6. Responsive và visual regression

Kiểm tra tối thiểu các viewport:

- `320x800` mobile;
- `768x1024` tablet;
- `1280x800` desktop;
- `1440x900` wide desktop.

Các trạng thái cần baseline:

- home;
- search có kết quả;
- search không có kết quả;
- entity detail;
- provenance/external links;
- competency question catalogue/result;
- loading;
- API/Fuseki error;
- long Vietnamese label và missing optional field.

Phải kiểm tra:

- không có layout break;
- không mất canonical/RDF links;
- bảng/card không cắt nội dung quan trọng;
- focus/hover/active state nhìn thấy được;
- screenshot baseline deterministic hoặc lý do sai khác được ghi rõ.

Nếu có visual test, artifact phải gắn với snapshot/commit và không commit screenshot sinh ngẫu nhiên vào raw data.

## 7. Performance và network resilience

Thiết lập budget đo được trong local demo profile, không dùng claim không có measurement:

- initial Explorer document và static assets không tải dữ liệu raw trực tiếp;
- search request có timeout và page-size limit;
- entity detail không tải vô hạn triple hoặc external endpoint trực tiếp từ browser;
- query response có loading state và không chặn toàn bộ UI không cần thiết;
- Fuseki/API timeout hiển thị lỗi có thể hành động;
- retry không tạo request loop;
- empty result khác error;
- partial optional provenance không làm mất entity detail;
- repeated search/debounce hoặc cancellation tránh request thừa nếu phù hợp.

Đo tối thiểu:

- cold start và warm navigation;
- search với 0, 1 và nhiều kết quả;
- detail entity lớn;
- Fuseki unavailable/slow;
- network timeout và malformed response.

Báo cáo phải ghi environment, timestamp, browser/runtime, request count và p50/p95 nếu dùng percentile. Không được biến benchmark local thành production SLA.

## 8. Reproducible offline demo

Tạo runbook, đề xuất:

```text
docs/DEMO.md
```

Runbook phải có:

1. prerequisites và phiên bản;
2. cách chuẩn bị `.env` từ `.env.example` mà không commit secrets;
3. cách khởi động Fuseki/Explorer;
4. preflight kiểm tra service health, snapshot ID và named graph inventory;
5. demo script 5–10 phút cho ba persona;
6. expected result cụ thể sau mỗi bước;
7. đường dẫn canonical resource, Turtle, JSON-LD và SPARQL;
8. offline mode không phụ thuộc live registry/Wikipedia/DBpedia;
9. recovery khi container hoặc Fuseki chưa sẵn sàng;
10. teardown an toàn không xóa release data;
11. command để tạo machine-readable demo result.

Demo phải chứng minh graph semantics, không chỉ screenshot UI. Tối thiểu phải trình diễn:

- search một entity tiếng Việt;
- mở detail và canonical URI;
- xem source/provenance;
- xem asserted/inferred distinction;
- mở Turtle/JSON-LD;
- chạy một CQ allowlisted;
- cho thấy public write bị từ chối hoặc không xuất hiện trong UI;
- xử lý một empty/error state.

## 9. Test và artifact contract

Không được làm giảm các acceptance hiện tại:

```text
python -m pytest -q                  → 153 passed hoặc baseline mới có giải thích
make linked-data-test                → PASS
make app-test                        → PASS
make app-smoke                       → 13/13 PASS hoặc mở rộng với tất cả check cũ
make cq-test                         → 10/10 PASS
make cypher-test                     → 10/10 PASS
make traceability-check              → PASS
make verify RUN_MODE=full            → FINAL STATUS: PASS
```

Bổ sung test phù hợp:

- unit test cho semantic UI/API link contract;
- live HTTP test cho canonical resource và representation links;
- accessibility automated report;
- keyboard/manual checklist;
- responsive viewport test;
- visual baseline test nếu có;
- network resilience test;
- offline demo smoke test.

Tạo machine-readable report, đề xuất:

```text
reports/<run_id>/ux_audit.json
reports/<run_id>/accessibility.json
reports/<run_id>/visual_regression.json
reports/<run_id>/performance.json
reports/<run_id>/demo.json
```

Mỗi report phải có tối thiểu:

- `run_id`;
- `snapshot_id`;
- commit SHA nếu có;
- environment/browser/runtime;
- status;
- checks và evidence paths;
- warnings/errors;
- timestamp UTC.

Tạo báo cáo tổng hợp:

```text
SEMANTIC_WEB_UX_DEMO_REPORT.md
```

Báo cáo phải phân biệt:

- functional pass;
- accessibility pass;
- responsive/visual pass;
- performance/resilience pass;
- demo reproducibility pass;
- remaining gaps;
- local-development evidence versus production evidence.

## 10. Documentation updates

Cập nhật nhất quán nếu implementation thay đổi:

- `docs/UX_DESIGN.md`;
- `docs/USER_GUIDE.md`;
- `docs/API.md`;
- `docs/E2E.md`;
- `docs/RELEASE.md`;
- `README.md`;
- `PROJECT_SPEC.md` chỉ khi contract normative thật sự thay đổi.

Documentation phải không quảng bá:

- accessibility đã đạt nếu chưa có evidence;
- production public URI nếu chỉ kiểm tra localhost;
- human review nếu provenance chỉ là automated review;
- demo offline nếu demo vẫn cần network.

## 11. Definition of done

Goal chỉ được xem là hoàn thành khi tất cả điều kiện sau có evidence:

1. User journey visitor/researcher/power user chạy được trong offline demo.
2. Canonical URI và RDF representation links không có stale host/path.
3. Asserted, inferred, closure, provenance và verified links được trình bày đúng semantics.
4. API/UI vẫn là read-only projection của RDF/Fuseki.
5. Automated accessibility scan không có blocker/critical violation.
6. Keyboard checklist pass cho các journey chính.
7. Responsive matrix pass ở bốn viewport.
8. Visual regression baseline được tạo hoặc limitation được giải thích.
9. Performance/resilience measurements có report và environment.
10. Demo runbook chạy lại được từ checkout sạch với snapshot offline.
11. Existing full regression và Semantic Web acceptance không giảm.
12. UX/demo reports và summary report có snapshot ID, commit/evidence path.
13. `git diff --check` pass; không có secret/raw-data/protected-file violation.

Nếu một điều kiện chưa có bằng chứng, verdict phải là `PARTIALLY READY` hoặc `FUNCTIONALLY COMPLETE`, không được gọi là production-ready.

## 12. Final response contract

Khi hoàn tất, trả lời bằng tiếng Việt và ghi rõ:

- verdict trước/sau;
- files đã thay đổi;
- functional/accessibility/responsive/performance/demo evidence;
- commands và kết quả;
- limitation còn lại;
- có commit hay chưa;
- không push nếu chưa được yêu cầu.
