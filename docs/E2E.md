# VietHeritageLOD — End-to-End Runbook

Hướng dẫn này dành cho người clone một checkout mới và muốn chạy toàn bộ project từ đầu. Chạy trên Windows PowerShell, với GNU Make và Docker Desktop trong `PATH`.

## 0. Điều kiện trước khi chạy

Yêu cầu:

- Python `>=3.12,<3.14`.
- Docker Desktop đang chạy.
- Docker Compose v2.
- GNU Make.
- Kết nối Internet cho full collection và các endpoint external.

Kiểm tra:

```powershell
python --version
docker version
docker compose version
make --version
git --version
```

Python phải nằm trong khoảng `3.12` đến nhỏ hơn `3.14`. Nếu `make` không tồn tại, cài GNU Make hoặc dùng môi trường Windows có GNU Make đã được cấu hình; không thay `make` bằng lệnh đoán khác.

## 1. Clone và kiểm tra checkout

```powershell
git clone <REPOSITORY_URL> VietHeritageLOD
Set-Location .\VietHeritageLOD
git status --short
```

Nếu checkout có thay đổi local hoặc có các artifact từ lần chạy trước, nên dùng một checkout/worktree riêng cho lần chạy E2E này.

## 2. Tạo `.env` và đặt credentials local

Không commit `.env`.

```powershell
Copy-Item .env.example .env
notepad .env
```

Trong `.env`, đặt các giá trị local thật, không dùng placeholder trong môi trường dùng chung:

```text
FUSEKI_ADMIN_PASSWORD=<local-fuseki-password>
NEO4J_USER=neo4j
NEO4J_PASSWORD=<random-password-at-least-16-characters>
NEO4J_AUTH=neo4j/<same-random-password>
NEO4J_DATABASE=neo4j
RUN_MODE=sample
```

`NEO4J_PASSWORD` được Python loader và Cypher runner sử dụng. `NEO4J_AUTH` được Docker Compose sử dụng khi khởi tạo Neo4j. Hai password phải giống nhau. Với một Neo4j volume đã tồn tại, password là password được dùng lúc volume được khởi tạo; không reset volume nếu chưa sao lưu dữ liệu.

## 3. Cài dependencies và chạy regression

```powershell
make setup
make test
```

Expected release baseline:

```text
153 passed
```

Một số collector tests ghi fixture vào các thư mục output dùng chung. Vì vậy phải chạy `make test` trước sample/full pipeline, hoặc dùng checkout riêng. Nếu chạy test sau khi đã có full snapshot, cần chạy lại full pipeline trước khi staging dữ liệu.

## 4. Giai đoạn A — sample gate offline/fixture

Sample gate kiểm tra pipeline trước khi gọi network thật:

```powershell
make pipeline-sample
```

Sau đó khởi động và nạp Fuseki:

```powershell
make fuseki-up
make fuseki-load RUN_MODE=sample
make cq-test
```

Khởi động và nạp Neo4j:

```powershell
make neo4j-up
make neo4j-load RUN_MODE=sample
make cypher-test
```

Chạy sample acceptance:

```powershell
make verify RUN_MODE=sample
```

Phải thấy:

```text
FINAL STATUS: PASS
```

Nếu sample fail, không chuyển sang full. Sửa lỗi rồi chạy lại từ stage bị fail.

## 5. Giai đoạn B — full collection và build dữ liệu thật

`RUN_MODE=full` gọi network tới registry chính thức, Wikipedia, Wikidata/DBpedia theo stage tương ứng. Chạy tuần tự:

```powershell
make pipeline RUN_MODE=full
```

`make pipeline` thực hiện theo thứ tự:

1. Collect registry chính thức và Wikipedia enrichment.
2. Normalize raw JSONL.
3. Resolve identity và kiểm tra collision.
4. Map canonical records.
5. Generate RDF Turtle.
6. Build verified external links.
7. Chạy reasoning và sinh inferred triples.
8. Validate RDF/ontology (yêu cầu cả `external-links.ttl` và `inferred.ttl` đã tồn tại từ bước 6–7).

Không chạy `pipeline-sample` ở giữa các bước full.

## 6. Load full data vào Fuseki và kiểm tra SPARQL

```powershell
make fuseki-up
make fuseki-load RUN_MODE=full
make cq-test
```

Endpoint:

```text
http://localhost:3031/vietheritage/sparql
```

Có thể kiểm tra linked-data adapter nếu stage đó được triển khai:

```powershell
make linked-data-test
```

## 7. Load full data vào Neo4j và kiểm tra Cypher parity

```powershell
make neo4j-up
make neo4j-load RUN_MODE=full
make cypher-test
```

Endpoints:

```text
Neo4j Browser: http://localhost:7474
Neo4j Bolt:    bolt://localhost:7687
```

`cypher-test` so sánh kết quả LPG với kết quả RDF/SPARQL. Warning về relationship type không có instance trong snapshot có thể xuất hiện; điều kiện chấp nhận là kết quả cuối phải là `10/10 PASS` và không có `LPG_RDF_MISMATCH`.

## 8. Khởi động explorer và smoke test UX/API

```powershell
make app-up
make app-smoke
```

Mở trình duyệt:

```text
http://localhost:3030
```

API docs:

```text
http://localhost:3030/docs
http://localhost:3030/openapi.json
```

## 9. Full acceptance verification

```powershell
make traceability-check
make verify RUN_MODE=full
```

Kết quả phải là:

```text
FINAL STATUS: PASS
```

Release baseline hiện tại:

- Registry/canonical: `860 / 860`.
- Registry coverage: `100%` trên 17 category đã cấu hình.
- Wikipedia pages: `42`.
- Verified external links: `114`.
- RDF triples: `7,249`.
- Inferred triples: `1,782`.
- SPARQL: `10/10 PASS`.
- Cypher/RDF parity: `10/10 PASS`.

## 10. Xem evidence và trạng thái service

```powershell
Get-Content .\reports\full\verify.json
Get-Content .\logs\full-pipeline-utf8.log -Tail 80
docker compose ps
git status --short
```

`reports/` và `logs/` là runtime evidence, không phải credentials và thường bị ignore bởi Git. Raw release data nằm trong `data/raw/`.

## 11. Dừng services sau khi chạy

```powershell
make app-down
make fuseki-down
make neo4j-down
```

Không dùng `make fuseki-reset` hoặc `make neo4j-reset` trên dữ liệu cần giữ; các target reset xóa Docker volume.

## 12. Nếu cần chạy lại từ đầu

### Checkout sạch, giữ raw release

Không dùng `git checkout -- .` trên thư mục có thay đổi chưa backup. Cách an toàn là clone một checkout/worktree mới, sau đó chạy:

```powershell
git status --short
make pipeline RUN_MODE=full
make fuseki-load RUN_MODE=full
make neo4j-load RUN_MODE=full
make traceability-check
make cq-test
make cypher-test
make verify RUN_MODE=full
```

### Chạy lại hoàn toàn cả Docker data

Chỉ làm khi chắc chắn không cần dữ liệu trong volume:

```powershell
make fuseki-reset
make neo4j-reset
make fuseki-up
make neo4j-up
```

Sau đó chạy lại từ bước 5. `*-reset` là thao tác destructive đối với Docker volumes; không chạy trên máy dùng chung nếu chưa có backup.

## 13. Quy tắc không làm sai full snapshot

- Không dùng `git add .`.
- Không commit `.env`.
- Không chạy sample/test collector trên checkout đang giữ full snapshot nếu chưa có backup.
- Sau bất kỳ sample/test nào có ghi output, chạy lại `make pipeline RUN_MODE=full` trước khi verify/stage.
- Raw data có thể được commit theo release policy hiện tại; credentials, logs, reports và user files không được commit.
- Không push nếu chưa có yêu cầu rõ ràng.
