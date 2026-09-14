# VietHeritageLOD

Đồ thị tri thức Linked Open Data về Di sản Văn hóa Việt Nam. `PROJECT_SPEC.md` là nguồn yêu cầu có thẩm quyền; `PLAN.md` mô tả phân công và trình tự triển khai.
Hướng dẫn chạy lại đầy đủ từ checkout sạch: [`docs/E2E.md`](./docs/E2E.md).

## Trạng thái release

Full release snapshot đã được thu thập và kiểm chứng. Phạm vi claim “đầy đủ” là **100% entity hợp lệ trong 17 category registry chính thức được cấu hình của Cục Di sản văn hóa**, không phải mọi fact văn hóa tồn tại bên ngoài registry đó. Entity không tìm được Wikipedia vẫn được giữ trong canonical dataset.

| Hạng mục | Kết quả đã kiểm chứng |
|---|---:|
| Official registry / canonical records | `860 / 860` |
| Registry coverage | `100%` trên cả 17 category đã cấu hình |
| Wikipedia pages matched | `42` |
| Wikidata links verified | `89` |
| DBpedia links verified | `25` |
| Verified external links | `114` |
| RDF triples | `6,224` |
| Inferred triples | `1,782` |
| SPARQL competency questions | `10/10 PASS` |
| Cypher/RDF parity | `10/10 PASS` |
| Regression tests | `136 passed` |

Evidence acceptance cuối: `reports/full/verify.json` và log: `logs/full-pipeline-utf8.log` (hai thư mục này là runtime evidence và đang bị ignore). Full verification đã trả `FINAL STATUS: PASS`.

## Quick start — full release

### Windows PowerShell

```powershell
Copy-Item .env.example .env
# Đổi các giá trị password local trong .env trước khi khởi động service.
make setup
make test
make pipeline RUN_MODE=full
make fuseki-up
make fuseki-load RUN_MODE=full
make cq-test
make neo4j-up
make neo4j-load RUN_MODE=full
make cypher-test
make verify RUN_MODE=full
```

### Bash / Git Bash

```bash
cp .env.example .env
make setup
make test
make pipeline RUN_MODE=full
make fuseki-up && make fuseki-load RUN_MODE=full
make cq-test
make neo4j-up && make neo4j-load RUN_MODE=full
make cypher-test
make verify RUN_MODE=full
```

`make pipeline RUN_MODE=full` gọi network tới registry chính thức, Wikipedia và các endpoint external theo cấu hình. Với golden fixture offline, dùng `make pipeline-sample` rồi các target service/query tương ứng.

> **Cảnh báo artifact:** `pipeline-sample` và một số test collector ghi vào cùng `data/raw`, `data/processed`, `data/rdf` và `data/linking` với full run. Không chạy sample/test trên checkout đang giữ snapshot full nếu chưa sao lưu hoặc dùng checkout/worktree riêng; sau regression, cần chạy lại full pipeline trước khi staging dữ liệu.

## Services và endpoint

- Fuseki SPARQL: `http://localhost:3030/vietheritage/sparql`
- Fuseki service/UI: `http://localhost:3030`
- Linked-data resource adapter: `http://localhost:3030/resource/{entity_id}` khi adapter được triển khai theo spec
- Neo4j Browser: `http://localhost:7474`
- Neo4j Bolt: `bolt://localhost:7687`

Các port Docker chỉ bind loopback theo `docker-compose.yml`. Không dùng password mặc định trong môi trường chia sẻ; `.env` luôn local-only và không được commit.

## Dữ liệu và reproducibility

Raw full snapshot được commit theo yêu cầu release. Các file raw chính gồm:

- `data/raw/registry_records.jsonl` — 860 registry records.
- `data/raw/registry_failures.jsonl` — 10 category hiện trả HTTP 200 nhưng không có hàng trích xuất; mỗi dòng có `REGISTRY_EMPTY_SOURCE` và snapshot ID.
- `data/raw/pages.jsonl` — 42 Wikipedia pages matched.
- `data/raw/enrichment_failures.jsonl` — các registry label không có exact Wikipedia match; đây là manifest thiếu enrichment, không xóa registry entity.
- Wikidata manifests: `wikidata_exact_enrichment.jsonl`, `wikidata_exact_missing.jsonl`, `wikidata_sparql_exact_enrichment.jsonl`.
- DBpedia manifests: `dbpedia_lookup_candidates.jsonl`, `dbpedia_exact_candidates.jsonl`, `dbpedia_wikidata_candidates.jsonl`.

Full raw audit không phát hiện credential/private-key/API-key pattern. Không commit `.env`, credentials, user files hoặc các file chẩn đoán untracked được bảo vệ. Xem quy trình và inventory tại [`docs/RELEASE.md`](./docs/RELEASE.md).

## Acceptance và requirements

Pipeline đã bao phủ các phần blocking của `PROJECT_SPEC.md`: official collection, raw validation, normalization, deterministic identity/collision check, ontology mapping, RDF generation/validation, OWL reasoning, Wikidata/DBpedia verified linking, Fuseki, 10 SPARQL CQ, Neo4j LPG, Cypher/RDF parity, reports và CLI Make targets. Các commit implementation gần nhất:

- `ceea695` — verified DBpedia identity links.
- `61e9d30` — RDF/LPG competency parity.
- `32adf52` — strict RDF/LPG parity verification.

## Yêu cầu môi trường

- Python `>=3.12,<3.14` (xem `DEC-046` trong `PROJECT_SPEC.md`, Phụ lục A).
- Docker Desktop (Fuseki + Neo4j).
- GNU Make có trong `PATH` (Windows có thể dùng GNU Make đi kèm project setup).

## Cấu trúc và tài liệu

- [`PROJECT_SPEC.md`](./PROJECT_SPEC.md) — specification authoritative.
- [`PLAN.md`](./PLAN.md) — plan theo component/member.
- [`docs/RELEASE.md`](./docs/RELEASE.md) — release inventory, validation và post-release checklist.
- Section 9 của `PROJECT_SPEC.md` — repository structure đầy đủ.
