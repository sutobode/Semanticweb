# M2 — Ghi chú triển khai (Data Acquisition & Normalization)

So sánh với nhánh `dev` ban đầu (commit `6e76bac`, snapshot `20260914T040348Z`). Phạm vi: COMP-000…COMP-004 (`PLAN.md` §2.2).

## 1. Kết quả

| Chỉ số | `dev` ban đầu | Bản này (`20260925T034421Z`) |
|---|---:|---:|
| Registry record | 860 | **1006** |
| Coverage claim | FAIL (10 `REGISTRY_EMPTY_SOURCE`) | `100% of selected official registry snapshot` |
| Canonical record (registry + phái sinh) | 860 + 0 | 1009 + 59 |
| HeritageSite | 122 | 271 |
| Record có Wikipedia / page Wikipedia | 50 / 42 | 204 / 158 |
| Record có QID | 89 | 232 |
| `recognition_year` sai (lấy nhầm số quyết định) | 597 | 0 |
| `registry_url` là trang chủ dsvh | 712 | 0 |
| AdministrativeArea / triple `vh:locatedIn` | 0 / 0 | 34 / 803 |
| Quan hệ khác | 0 | `recognized_by` 9, `built_by` 3, `associated_persons` 23, `associated_events` 4 |
| HeritageSite có `site_types` | 9 | 241 |
| Triple RDF | 8 679 | 12 786 |
| Verified external links (`make link`) | 114 | 281 |
| Unit test | 192 passed | 426 passed |

## 2. Cải tiến chính

**Registry collector (COMP-000)**
- Thêm nguồn bài viết "Di tích quốc gia" (`registry/articles.py`, `article_sources`): `national_monuments` 6 → 152 (DEC-M2-002).
- `registry_id` ổn định: `sha256(category_url | category | label_key)[:12]`, khi trùng tên thì thêm địa điểm → quyết định → STT. Không phụ thuộc href hay thứ tự dòng.
- Sửa `registry_url`: `http` → `https`, bỏ URL trang chủ hoặc URL dùng chung, percent-encode theo RFC 3986.
- Retry đúng NFR-007 (3 lần, 2/4/8 giây), pagination có fingerprint, chống lặp, tùy chọn lưu HTML.
- Category nguồn rỗng không còn làm FAIL coverage (DEC-M2-001). Lỗi mạng, HTTP hoặc parse vẫn chặn pipeline.

**Wikipedia collector (COMP-001)** — so khớp chuỗi chính xác sau chuẩn hóa, không fuzzy (DEC-007)
- Thứ tự thử: override tay (`wikipedia_overrides.yaml`) → luật alias (bỏ viết tắt DTLS…, ngoặc, "ở/tại…", tên tỉnh, "của người…") → `prefixsearch` cho khác biệt hoa/thường → mở rộng trang định hướng → tách di tích gộp.
- Bằng chứng tỉnh theo nhóm tỉnh sau sáp nhập. Xung đột tỉnh thì loại, kể cả khi tiêu đề khớp chính xác. Di sản phi vật thể có chính sách bằng chứng riêng (DEC-M2-003).
- Loại page sai theo thể loại (xã, sông, người, sự kiện…), bảo vật phải thuộc thể loại bảo vật, bỏ page bị gán cho nhiều nhãn khác nhau.
- Parser infobox mới. Quan hệ lấy từ infobox chỉ được nhận khi Wikidata P31 của page đích đúng lớp.

**Normalizer / Resolver / Mapper (COMP-002…004)**
- `parse_recognition_year` bỏ qua số hiệu quyết định. Có kiểm tra raw schema (`RAW_SCHEMA_INVALID`).
- `normalization/areas.py` + `config/areas.yaml`: khớp địa điểm theo 63 tỉnh cũ, công bố theo 34 tỉnh/thành sau sắp xếp 2025 (DEC-M2-004).
- Resolver gộp bản ghi "(bổ sung …)" vào bản gốc, ghi vào `identity_map.jsonl`.
- Mapper đọc toàn bộ từ `mapping.yaml` (`required_fields`, `registry_field_roles`, `infobox_fields`, `derived_entities`):
  - `world_heritage` → `recognized_by organization-unesco`;
  - `site_types` lấy từ tiền tố viết tắt trong tên;
  - cột nơi lưu giữ của bảo vật → `current_holder`;
  - di tích gộp có ≥ 2 bài Wikipedia → tách thành nhiều entity cùng `registry_id`.

**Công cụ và test**
- `tools/m2_quality_check.py` (quality gate), `m2_registry_probe.py`, `m2_replay_snapshot.py`, `m2_wiki_match_report.py`.
- 6 file test `test_m2_*` và golden fixture `data/fixtures/canonical.jsonl` (26 record, tái tạo đúng CQ01/03–08).
- MediaWiki giả lập (`tests/fixtures/fake_viwiki.py`) và HTML thật của 17 trang registry cùng 15 bài viết, dùng làm fixture.

## 3. Quyết định đề xuất đưa vào `PROJECT_SPEC.md` Phụ lục A

| Mã | Quyết định |
|---|---|
| DEC-M2-001 | Giữ 17 category. 10 category có trang chính thức chưa công bố dòng dữ liệu nào (bảo tàng, nghệ nhân, di vật, di sản tư liệu) ghi 0/0 (`allow_empty_source`). Tự thu thập khi nguồn có dữ liệu. |
| DEC-M2-002 | Thêm nguồn bài viết `dsvh.gov.vn/di-tich-quoc-gia-130` vào `national_monuments`. Coverage của category này là các di tích có bài giới thiệu, không phải toàn bộ danh mục di tích quốc gia. |
| DEC-M2-003 | Bằng chứng khớp Wikipedia cho di sản phi vật thể phụ thuộc luật alias đã áp: tỉnh, dân tộc, vùng, hoặc không cần. `national_intangible` khớp 44 → 74. |
| DEC-M2-004 | `located_in` / AdministrativeArea công bố theo 34 tỉnh/thành sau NQ 202/2025/QH15. Ô địa điểm gốc giữ ở `address`. Đặt `publish_level: source` để quay lại 63 tên cũ. |

Ngoài ra cần ghi: tách di tích gộp làm `canonical_registry_derived_entities` khác `registry_valid_records` về số lượng. Vì vậy coverage đếm **dòng registry được biểu diễn** (§12.4.2).

## 4. Ảnh hưởng tới thành viên khác

| Ai | Thay đổi | Cần làm |
|---|---|---|
| Cả nhóm | Toàn bộ `entity_id` registry đổi (URI công bố đổi một lần) | Chạy lại pipeline từ `normalize` |
| M3 | `entity_id` mới, số link tăng lên 281 | Chạy lại `make link` |
| M4 | `reporting/verify.py`: coverage đếm `registry_id` duy nhất cộng bản gộp | Review diff |
| M4 | `canonical.jsonl` có entity phái sinh (34 tỉnh, UNESCO, người, sự kiện) đặt đầu file; Neo4j sẽ có `LOCATED_IN`, `RECOGNIZED_BY`. CQ06 trên dữ liệu thật đổi theo tỉnh mới | Kiểm tra lại expected |
| M4 | Chỉ CQ01/09/10 có tên file `.cypher` trùng `.rq`. `CQ01.cypher` không lọc "Hà Nội" như `.rq` → sẽ `LPG_RDF_MISMATCH` | Sửa 10 file `.cypher` cho khớp 1:1 (Phụ lục C.5) |
| M1 | `generator._metadata_counts` đếm `registry_records = len(records)` (gồm cả entity phái sinh) | Đếm record có `registry_id` |

## 5. Việc còn mở

- **Nguồn QID:** một phần QID lấy từ truy vấn Wikidata exact-label của M3, không phải từ page Wikipedia. Nhóm cần quyết định có tính phần này vào MET-008 không (DEC-008).
- **Lớp Wikidata cho quan hệ** (`collector.yaml > relations.target_classes`): cần M1 xác nhận.
- **Spot-check độc lập** kết quả khớp Wikipedia: một thành viên khác M2 chấm mẫu.

## 6. Cách chạy

```bash
make test
make normalize resolve map RUN_MODE=full     # không cần mạng, dùng data/raw có sẵn
python tools/m2_quality_check.py             # kỳ vọng: m2-quality: PASS

make collect                                 # crawl lại dsvh + Wikipedia (cần mạng)
```

`data/raw/*`, `data/processed/*` và `reports/` nằm trong `.gitignore` (§9.1). Snapshot dữ liệu được phân phối bằng zip riêng, hoặc `git add -f` khi release. `reports/<snapshot>/coverage.json` cần có để `make verify RUN_MODE=full` chạy được.
