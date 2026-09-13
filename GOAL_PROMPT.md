# GOAL_PROMPT.md — Prompt cho Kiro CLI Goal Mode (VietHeritageLOD, end-to-end)

> Copy toàn bộ nội dung trong khối lệnh dưới đây vào goal mode. Đây là **một goal duy nhất, chạy hết một lượt**: agent tự dựng pipeline, tự kiểm chứng bằng golden fixture (sample) như một cổng nội bộ, và nếu sample PASS thì **tự động chuyển sang crawl dữ liệu thật** (`dsvh.gov.vn` + Wikipedia tiếng Việt) mà không cần bạn xác nhận lại giữa đường. Kết thúc goal, bạn nhận một project hoàn chỉnh đã `make verify` PASS trên dữ liệu thật.

> **Vì sao có bước sample trước:** không phải để bạn phải tự bấm "tiếp tục" — mà để agent tự phát hiện lỗi logic/ontology/mapping bằng dữ liệu nhỏ, rẻ, không tốn network, trước khi đổ hàng trăm request thật vào site chính phủ và Wikipedia. Nếu sample fail, chạy full trên nền logic sai chỉ tạo ra rất nhiều dữ liệu sai — sample là bảo hiểm cho chính lần chạy full, không phải rào cản.

---

## Prompt

```text
Bạn là Coding Agent triển khai project VietHeritageLOD từ đầu đến cuối trong MỘT
lượt làm việc. Nguồn duy nhất có thẩm quyền là hai file tại repository root:

  1. PROJECT_SPEC.md — implementation specification, MUST tuân thủ tuyệt đối.
  2. PLAN.md — phân công 4 vai trò (M1 Ontology/Reasoning, M2 Data Acquisition,
     M3 External Linking, M4 Triple Store/LPG/Deployment) và trình tự theo tuần.

Bạn đóng vai trò của CẢ 4 thành viên trong PLAN.md. Mục tiêu cuối cùng: một
repository hoàn chỉnh, đã chạy `make verify` PASS trên dữ liệu THẬT (registry
chính thức dsvh.gov.vn + enrichment từ Wikipedia tiếng Việt), sẵn sàng để nộp.

====================================================================
GIAI ĐOẠN A — XÂY DỰNG VÀ TỰ KIỂM CHỨNG BẰNG SAMPLE (bắt buộc trước)
====================================================================

Đi qua Gate G0 → G12 ở Section 43 của PROJECT_SPEC.md theo đúng thứ tự, dùng
RUN_MODE=sample và golden fixture (Section 35, data/fixtures/) cho TOÀN BỘ pipeline.
KHÔNG gọi HTTP thật tới dsvh.gov.vn, vi.wikipedia.org, wikidata.org, dbpedia.org
trong Giai đoạn A dưới bất kỳ hình thức nào — mọi test collector dùng API mock/
fixture (Section 37 TEST-001..004, TEST-076..081).

  1. G0: tạo cây thư mục Section 9, Makefile 27 target, requirements.txt,
     .env.example, .gitignore (loại data/raw/, .env, logs/, reports/). Chạy
     make setup và make test, xác nhận exit 0. Commit.
  2. G1-G2: JSON Schema (Phụ lục B) và ontology 23 class/12 object property/
     10 datatype property/9 axiom (Section 11, 12, 15, 16). Commit.
  3. G3: viết COMP-000 (registry collector) và COMP-001 (Wikipedia collector)
     với unit test bằng fixture mock. Chạy make collect-sample. Commit.
  4. G4-G7: normalize, resolve identity, ontology mapping, generate RDF, external
     linking trên canonical.jsonl fixture. Commit riêng từng gate.
  5. G8: Fuseki thật qua Docker (Docker daemon đã xác nhận hoạt động trên máy
     này), load RDF sample.
  6. G9-G10: 10 SPARQL CQ và OWL Mini reasoning trên dữ liệu sample.
  7. G11 (Neo4j LPG) và G12: load Neo4j, Cypher parity, rồi chạy
     `RUN_MODE=sample make verify`.

CỔNG CHUYỂN GIAI ĐOẠN (tự kiểm tra, không hỏi người):
  - Nếu `make verify` (RUN_MODE=sample) in ra "FINAL STATUS: PASS" và exit code 0
    → tự động sang GIAI ĐOẠN B ngay, không dừng lại chờ xác nhận.
  - Nếu FAIL → tự sửa lỗi trong phạm vi contract của PROJECT_SPEC.md (không đổi
    ontology đã freeze, không đổi số class/property/axiom) và chạy lại Giai đoạn A
    từ Gate bị fail. Lặp lại tối đa 5 lần sửa cho cùng một Gate; nếu vẫn FAIL sau
    5 lần, DỪNG LẠI, báo cáo chi tiết lỗi, và hỏi tôi — không tự nới lỏng test
    hoặc xóa bớt điều kiện PASS để "cho qua".

====================================================================
GIAI ĐOẠN B — DỮ LIỆU THẬT (chỉ chạy khi Giai đoạn A đã PASS thật)
====================================================================

Chuyển RUN_MODE=full. Không tạo lại code đã viết ở Giai đoạn A — tái sử dụng,
chỉ đổi input từ fixture sang nguồn thật.

  - COMP-000 MUST crawl thật toàn bộ 17 category chính thức tại dsvh.gov.vn theo
    danh sách URL ở Section 7 PROJECT_SPEC.md. Không tự thêm/bỏ category.
  - COMP-001 MUST enrich bằng Vietnamese Wikipedia qua MediaWiki API thật
    (https://vi.wikipedia.org/w/api.php), đúng request contract Section 7
    COMP-001 (action=query, prop=pageprops|revisions|coordinates|categories|
    extracts|links, formatversion=2). Registry entity không tìm được page khớp
    MUST giữ source_status=registry_only, KHÔNG bị loại khỏi canonical dataset.
  - Wikidata linking (COMP-007) dùng QID deterministic; DBpedia candidate dùng
    Silk scoring (Section 22). Coverage universe do registry quyết định
    (Section 12.4.1) — Wikipedia/Wikidata/DBpedia CHỈ enrich/link, KHÔNG tự thêm
    entity ngoài registry vào canonical dataset.
  - MET-005 MUST đạt 100% trên snapshot registry đã crawl. AC-024, AC-025 là
    blocking, KHÔNG được ghi SKIPPED_SAMPLE_MODE ở giai đoạn này.

RÀO AN TOÀN BẮT BUỘC KHI GỌI NETWORK THẬT (không nới lỏng để nhanh hơn):
  - Retry/backoff đúng NFR-007: timeout 30s, tối đa 3 retry, backoff 2s/4s/8s.
  - Crawl tuần tự theo category, không multi-thread ồ ạt vào dsvh.gov.vn.
  - User-Agent rõ ràng có ý nghĩa (ví dụ "VietHeritageLOD-Collector/1.0"), không
    giả User-Agent trình duyệt để né chặn.
  - Nếu dsvh.gov.vn trả liên tục HTTP 403/429/5xx trên nhiều category khác nhau
    (không phải lỗi selector), DỪNG TOÀN BỘ collection, không thử né bằng cách
    đổi User-Agent hay thêm proxy — báo tôi ngay.
  - Với MediaWiki API, giữ tốc độ hợp lý, không gửi hàng trăm request/giây; nghỉ
    hợp lý giữa các batch nếu số lượng entity lớn.
  - Nếu MỘT category trong 17 category hoàn toàn không crawl được do lỗi selector
    (không phải do site chặn), agent ĐƯỢC PHÉP tự sửa config/registry_sources.yaml
    và crawl lại category đó — đây là quyền đã cấp sẵn ở Section 7, không cần hỏi.
  - Registry hoặc Wikipedia failure ở một record cụ thể không làm sập toàn run;
    ghi vào registry_failures.jsonl/enrichment_failures.jsonl (Section 32) và
    tiếp tục.

  Sau khi crawl xong:
  8. Chạy lại G4-G7 (normalize, identity, mapping, RDF, linking) trên dữ liệu
     thật vừa crawl.
  9. Load lại Fuseki (G8) và Neo4j (G11) với dữ liệu thật, chạy lại CQ (G9) và
     reasoning (G10) trên dữ liệu thật.
  10. Chạy `RUN_MODE=full make verify`. Đây là điều kiện DUY NHẤT để coi toàn bộ
      goal là hoàn thành.

====================================================================
QUYẾT ĐỊNH ĐÃ CHỐT TRƯỚC (áp dụng cho cả hai giai đoạn, không hỏi lại)
====================================================================

  - Máy chạy Python 3.13.13, khác AC-001 ghi 3.12.8. QUYẾT ĐỊNH: nới AC-001 thành
    "Python >=3.12,<3.14" cho môi trường local; ghi quyết định này vào Decision
    Register (Phụ lục A) dưới một DEC-ID mới trước khi code.
  - NEO4J_PASSWORD trong .env thực tế PHẢI là chuỗi ngẫu nhiên tự sinh (>=16 ký
    tự), KHÔNG dùng placeholder "change-me-local-only". .env vào .gitignore,
    không commit .env.
  - Được phép crawl thật dsvh.gov.vn và vi.wikipedia.org ở Giai đoạn B theo đúng
    rào an toàn ở trên — đây là quyết định đã xác nhận.
  - Giai đoạn A PASS là điều kiện bắt buộc để vào Giai đoạn B — không được bỏ qua
    Giai đoạn A "để tiết kiệm thời gian" dù có tự tin vào code.
  - Nếu gặp ambiguity KHÔNG nằm trong các quyết định trên (hai đoạn spec mâu
    thuẫn số liệu/path, thiếu định nghĩa khiến phải đoán, hoặc registry/Wikipedia
    trả về mô hình dữ liệu khác hẳn spec mô tả — không phải lỗi selector đơn
    giản), DỪNG LẠI và hỏi tôi. Không tự suy diễn.

====================================================================
QUY TẮC BẮT BUỘC (Section 44 AUTONOMOUS CODING RULES)
====================================================================

  1. Đọc toàn bộ PROJECT_SPEC.md và PLAN.md trước khi tạo file đầu tiên.
  2. Inspect repository hiện tại trước khi tạo file (repo hiện đang trống).
  3. Implement đúng contract, không tự đổi schema field hay số lượng class/
     property/axiom đã freeze.
  4. Viết test cùng lúc với implementation.
  5. Không dùng screenshot hoặc metric ước lượng thay cho output lệnh thật.
  6. Sau mỗi Gate, chạy test của Gate đó và báo PASS/FAIL bằng output thật.
  7. Raw dataset từ crawl thật (data/raw/) MUST NOT được commit — chỉ golden
     sample (data/fixtures/) được commit (Section 9.1).

====================================================================
QUY TẮC GIT (được phép dùng, có giới hạn)
====================================================================

  - ĐƯỢC PHÉP: git add <file/thư mục cụ thể>, git commit, git branch (nhánh làm
    việc riêng, ví dụ feature/g0-bootstrap), git log, git diff, git status.
  - PHẢI COMMIT theo từng Gate — không dồn cả 12 Gate vào một commit. Message
    dạng: "G<n>: <tên gate> — <mô tả ngắn artifact chính>". Khi chuyển từ Giai
    đoạn A sang B, commit một mốc riêng: "Sample verify PASS — chuyển sang
    RUN_MODE=full".
  - KHÔNG BAO GIỜ: git push, git push --force, git reset --hard, git clean -f,
    git branch -D, hoặc lệnh ghi đè/xóa lịch sử, trừ khi tôi yêu cầu rõ bằng chữ.
  - KHÔNG dùng "git add ." — luôn liệt kê rõ file/thư mục để tránh commit nhầm
    .env, credentials, hoặc raw dataset lớn.
  - KHÔNG amend commit trừ khi đang sửa lỗi ngay sau khi vừa commit trong cùng
    phiên và chưa báo Gate đó là PASS.
  - Nếu phát hiện file có khả năng chứa secret trong working tree, DỪNG LẠI,
    báo tôi, không commit file đó.

====================================================================
ĐIỀU KIỆN HOÀN THÀNH GOAL (chỉ gọi complete khi TẤT CẢ đúng)
====================================================================

  - Giai đoạn A: `RUN_MODE=sample make verify` đã PASS thật (có log làm bằng
    chứng) trước khi vào Giai đoạn B.
  - Giai đoạn B: `RUN_MODE=full make verify` in "FINAL STATUS: PASS", exit code 0,
    có log lệnh làm bằng chứng.
  - coverage.json xác nhận registry_total == canonical_registry_derived_entities,
    coverage_percent == 100.0 trên toàn bộ 17 category (AC-024, AC-025).
  - Toàn bộ commit đã tạo theo từng Gate, git log cho thấy lịch sử rõ ràng cả
    hai giai đoạn.
  - Không có secret nào bị commit; data/raw/ không có trong git log của bất kỳ
    commit nào (xác nhận bằng git log --stat).
  - Báo cáo cuối theo đúng template Section 54 của PROJECT_SPEC.md, liệt kê rõ
    G0..G12 PASS/FAIL cho CẢ HAI giai đoạn và toàn bộ metric thật từ run report
    của lần chạy full (không phải số của sample) — không tự điền số.

Kết quả bạn cần nhận được sau khi goal này hoàn thành: một repository đầy đủ,
đã verify PASS trên dữ liệu thật, sẵn sàng nộp — không phải một pipeline mới
chạy được trên fixture rồi dừng ở đó.
```

---

## Ghi chú khi dùng prompt này

- Đây là **một goal duy nhất, tự chuyển giai đoạn** theo đúng yêu cầu: agent tự xác nhận sample PASS làm cổng nội bộ, rồi tự crawl dữ liệu thật, không cần bạn bấm tiếp giữa đường.
- Vẫn có 2 nơi agent **phải** dừng lại hỏi bạn dù đang ở goal mode: (1) một Gate fail liên tục 5 lần sửa mà không qua được, (2) `dsvh.gov.vn` chặn crawl (403/429/5xx liên tục) hoặc trả về mô hình dữ liệu khác hẳn spec. Đây là rào an toàn có chủ đích, không phải lỗi thiết kế — nếu bỏ hai rào này, agent có thể tự nới lỏng test hoặc tự thử né chặn site chính phủ để "hoàn thành goal", đều là hành vi không nên tự động hóa.
- Trước khi dán prompt, mở terminal riêng chạy `docker ps` để chắc Docker daemon còn sống — cả Giai đoạn A và B đều cần nó.
- Quá trình Giai đoạn B (crawl 17 category + enrichment Wikipedia) có thể mất nhiều phút do rate limit chủ động — đây là đánh đổi có chủ đích để không tạo tải bất thường lên site chính phủ, không phải lỗi.
- Sau khi agent báo hoàn thành, tự chạy lại `RUN_MODE=full make verify` một lần từ máy của bạn để xác nhận độc lập trước khi tin tưởng hoàn toàn.
