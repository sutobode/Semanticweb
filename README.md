# VietHeritageLOD

Đồ thị tri thức Linked Open Data về Di sản Văn hóa Việt Nam. `PROJECT_SPEC.md` là nguồn yêu cầu có thẩm quyền; `PLAN.md` mô tả phân công và trình tự triển khai.
Hướng dẫn chạy lại đầy đủ từ checkout sạch: [`docs/E2E.md`](./docs/E2E.md).

## Trạng thái release

Semantic snapshot hiện tại đã hoàn tất Member 4 M4.1-M4.4 và được kiểm chứng bằng final integration ngày 2026-10-07. Historical `coverage.json` của collector không có trong workspace hiện tại; M4.4 không chạy lại collection và không tạo claim coverage thay thế.

| Hạng mục | Kết quả đã kiểm chứng |
|---|---:|
| Canonical records | `1,111` |
| Ontology triples | `350` |
| Asserted triples | `13,577` |
| Inferred delta | `713,894` |
| Verified external links | `222` |
| Metadata triples | `1,526` |
| Final public graph | `729,567` |
| SPARQL competency questions | `10/10 PASS` |
| Cypher competency questions | `10/10 PASS` |
| SPARQL/Cypher parity | `10/10 PASS` |
| Final integration | `PASS` |
| Demo smoke | `8/8 PASS` |
| Focused M4.4 regression | `24 passed` |

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
make app-up
make app-smoke
make verify RUN_MODE=full
make demo-smoke
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
make app-up
make app-smoke
make verify RUN_MODE=full
make demo-smoke
```

`make pipeline RUN_MODE=full` gọi network tới registry chính thức, Wikipedia và các endpoint external theo cấu hình. Với golden fixture offline, dùng `make pipeline-sample` rồi các target service/query tương ứng.

> **Cảnh báo artifact:** `pipeline-sample` và một số test collector ghi vào cùng `data/raw`, `data/processed`, `data/rdf` và `data/linking` với full run. Không chạy sample/test trên checkout đang giữ snapshot full nếu chưa sao lưu hoặc dùng checkout/worktree riêng; sau regression, cần chạy lại full pipeline trước khi staging dữ liệu.

## Services và endpoint

- Web Explorer: `http://localhost:3030`
- Read-only API docs: `http://localhost:3030/docs`
- OpenAPI JSON: `http://localhost:3030/openapi.json`
- Linked-data resource: `http://localhost:3030/vietheritage/resource/{entity_id}`
- Fuseki SPARQL: `http://localhost:3031/vietheritage/sparql`
- Fuseki service/UI: `http://localhost:3031`
- Neo4j Browser: `http://localhost:7474`
- Neo4j Bolt: `bolt://localhost:7687`

Các port Docker chỉ bind loopback theo `docker-compose.yml`. Không dùng password mặc định trong môi trường chia sẻ; `.env` luôn local-only và không được commit.

## Dữ liệu và reproducibility

Raw full snapshot được commit theo yêu cầu release. Các file raw chính gồm:

- `data/raw/registry_records.jsonl` — official registry source records for the active snapshot.
- `data/raw/registry_failures.jsonl` — registry collection failure manifest.
- `data/raw/pages.jsonl` — Wikipedia enrichment input.
- `data/raw/enrichment_failures.jsonl` — các registry label không có exact Wikipedia match; đây là manifest thiếu enrichment, không xóa registry entity.
- Wikidata manifests: `wikidata_exact_enrichment.jsonl`, `wikidata_exact_missing.jsonl`, `wikidata_sparql_exact_enrichment.jsonl`.
- DBpedia manifests: `dbpedia_lookup_candidates.jsonl`, `dbpedia_exact_candidates.jsonl`, `dbpedia_wikidata_candidates.jsonl`.

Full raw audit không phát hiện credential/private-key/API-key pattern. Không commit `.env`, credentials, user files hoặc các file chẩn đoán untracked được bảo vệ. Xem quy trình và inventory tại [`docs/RELEASE.md`](./docs/RELEASE.md).

## Acceptance và requirements

Pipeline đã bao phủ các phần blocking của `PROJECT_SPEC.md`: official collection, raw validation, normalization, deterministic identity/collision check, ontology mapping, RDF generation/validation, SHACL public-graph validation, OWL reasoning, Wikidata/DBpedia verified linking, Fuseki, 10 SPARQL CQ, Neo4j LPG, Cypher/RDF parity, read-only Linked Data API, dereferenceable Turtle/JSON-LD resources, browser explorer, reports và CLI Make targets. Các commit implementation gần nhất:

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
- [`docs/E2E.md`](./docs/E2E.md) — end-to-end setup and execution.
- [`docs/API.md`](./docs/API.md) — read-only Semantic Web API contract.
- [`docs/USER_GUIDE.md`](./docs/USER_GUIDE.md) — browser explorer guide for non-SPARQL users.
- [`docs/DEMO.md`](./docs/DEMO.md) — reproducible offline Semantic Web demo runbook.
- [`docs/UX_DESIGN.md`](./docs/UX_DESIGN.md) — URI, RDF, provenance, and UX design.
- [`docs/RELEASE.md`](./docs/RELEASE.md) — release inventory, validation và post-release checklist.
- Section 9 của `PROJECT_SPEC.md` — repository structure đầy đủ.
