# VietHeritageLOD

Đồ thị tri thức Linked Open Data về Di sản Văn hóa Việt Nam.

Nguồn có thẩm quyền duy nhất để triển khai: [`PROJECT_SPEC.md`](./PROJECT_SPEC.md).
Phân công theo vai trò và trình tự công việc: [`PLAN.md`](./PLAN.md).

## Quick start

```bash
cp .env.example .env
make setup
make test
make pipeline-sample
make fuseki-up
make fuseki-load
make cq-test
make neo4j-up
make neo4j-load
make cypher-test
make verify
```

## Yêu cầu môi trường

- Python `>=3.12,<3.14` (xem `DEC-046` trong `PROJECT_SPEC.md` Phụ lục A)
- Docker (Fuseki + Neo4j)
- GNU Make

## Cấu trúc

Xem Section 9 (Repository Structure) của `PROJECT_SPEC.md`.
