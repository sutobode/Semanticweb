# Member 2 — Coverage Enrichment (06/10/2026)

Báo cáo vòng bổ sung dữ liệu theo `member2_coverage_enrichment_prompt.md` và lần kiểm tra trên Docker sau đó.

- **Commit:** `29f8207`, nhánh `feat/update_map_record`
- **Ontology:** 1.7.1. Không sửa ontology, axiom, reasoner hay validator.
- **Trạng thái:** phần dữ liệu đã xong và kiểm chứng; `verify` tổng vẫn FAIL vì 3 lỗi có sẵn (mục 7).

---

## 1. Tóm tắt

| Hạng mục | Trước | Sau | Mục tiêu | Trạng thái |
|---|---:|---:|---|---|
| HeritageComplex | 1 | 5 | 3–5 | ✅ |
| ArchitecturalStyle | 2 | 6 | 5–10 | ✅ |
| HistoricalPeriod | 1 | 5 | 5–10 | ✅ |
| ReligiousSite | 1 | 30 | 10–30 | ✅ |
| HistoricalEvent | 6 | 17 | 10–20 | ✅ |
| hasRelatedSite (asserted) | 1 | 6 | 5–10 | ✅ |
| hasHistoricalSuccessor | 1 | 2 | 3–5 | ⚠️ dừng theo stop condition B |
| hasMember | 3 | 16 | — | |
| hasArchitecturalStyle | 2 | 11 | — | |
| belongsToPeriod | 1 | 10 | — | |
| associatedWithEvent | 4 | 14 | — | |

| Số liệu | Trước | Sau |
|---|---:|---:|
| Canonical records | 1.088 | 1.111 |
| Asserted triples | 13.277 | 13.577 |
| Inferred delta | — | 713.580 |
| Closure (ontology + asserted) | — | 727.499 |
| External links | 222 | 222 (không chạy lại linking) |
| Final graph | — | 729.247 |

`hasHistoricalSuccessor` dừng ở 2: các ứng viên còn lại chỉ có thể suy ra từ thứ tự năm, điều mà prompt cấm.

---

## 2. Chuẩn bị môi trường

Máy chưa có Python, Java, Make. Đã cài bản portable, không cần quyền admin:

| Công cụ | Vị trí |
|---|---|
| Python 3.12.10 | `%LOCALAPPDATA%\vh-tools\python312` |
| Temurin JDK 17 | `%LOCALAPPDATA%\vh-tools\jdk\jdk-17.0.20.1+1` |
| Apache Jena 4.10.0 | `%LOCALAPPDATA%\vh-tools\apache-jena-4.10.0` |
| Virtualenv | `.venv` (đã nằm trong `.gitignore`) |

Bước suy luận cần đặt hai biến môi trường `JAVA_HOME` và `JENA_HOME`.

> **Lưu ý khi tái tạo dữ liệu.** `data/raw/holder_locations.jsonl` bị git bỏ qua nhưng bước `map` cần nó. Thiếu file này, 44 bảo vật quốc gia mất `locatedIn` và số triple thấp hơn bản đã commit. Tạo lại bằng `vietheritage.registry.holder_locations.run_holder_locations()`. Sau khi tạo lại, pipeline khớp hoàn toàn bản đã commit (1.088 record, 13.277 triple).

---

## 3. Dữ liệu đã bổ sung

### 3.1 HeritageComplex (4 mới)

Mỗi quần thể là một complex cha riêng; thành viên là các HeritageSite **đã có** trong canonical. Không retype site nào, không assert `partOf`/`hasPart` thủ công.

| Complex | Thành viên | Nguồn |
|---|---|---|
| Quần thể di tích và danh thắng Yên Tử - Vĩnh Nghiêm, Côn Sơn, Kiếp Bạc | Yên Tử, Khu nhà Trần Đông Triều, Chùa Vĩnh Nghiêm, Chùa Bổ Đà, Côn Sơn - Kiếp Bạc, complex An Phụ | [dsvh 22230](https://dsvh.gov.vn/quan-the-di-tich-va-danh-thang-yen-tu-vinh-nghiem-con-son-kiep-bac-duoc-unesco-ghi-vao-danh-muc-di-san-the-gioi-22230) |
| Di tích lịch sử, danh lam thắng cảnh An Phụ - Kính Chủ - Nhẫm Dương (lồng trong complex trên) | Đền Cao An Phụ, Động Kính Chủ | [dsvh 3218](https://dsvh.gov.vn/di-tich-lich-su-danh-lam-thang-canh-an-phu-kinh-chu-nham-duong-tinh-hai-duong-3218) |
| Di tích lịch sử và kiến trúc nghệ thuật Đền Xưa - Chùa Giám - Đền Bia | Đền Xưa, Chùa Giám, Đền Bia | [dsvh 1487](https://dsvh.gov.vn/thu-tuong-chinh-phu-ky-quyet-dinh-xep-hang-di-tich-quoc-gia-dac-biet-nam-2017-1487) |
| Di tích lịch sử và danh lam thắng cảnh hồ Hoàn Kiếm và đền Ngọc Sơn | Hồ Hoàn Kiếm, Đền Ngọc Sơn | [dsvh 2978](https://dsvh.gov.vn/di-tich-lich-su-va-danh-lam-thang-canh-ho-hoan-kiem-va-den-ngoc-son-2978) |

Không gắn `recognizedBy` cho complex: domain của nó là HeritageSite, gắn vào sẽ vi phạm disjointness.

### 3.2 ArchitecturalStyle (4 mới, tái sử dụng 2 cũ)

Theo phân loại của P. Stern trong [bài Khu đền tháp Mỹ Sơn](https://dsvh.gov.vn/di-tich-kien-truc-nghe-thuat-khu-den-thap-my-son-2943):

| Phong cách | Gắn cho |
|---|---|
| Mỹ Sơn E1 (mới) | Mỹ Sơn, Tháp Hòa Lai |
| Hòa Lai (mới) | Mỹ Sơn, Tháp Hòa Lai |
| Đồng Dương (mới) | Mỹ Sơn, Phật viện Đồng Dương |
| Muộn (mới) | Tháp Pô Klong Garai |
| Mỹ Sơn A1 (cũ) | Tháp Nhạn, Mỹ Sơn |
| Bình Định (cũ) | Tháp Nhạn, Mỹ Sơn |

### 3.3 HistoricalPeriod (4 mới, dùng chung)

| Thời kỳ | Di tích |
|---|---|
| Nhà Lý | Khu lăng mộ và đền thờ các vua triều Lý, Chùa Phật Tích |
| Nhà Trần | Khu lăng mộ vua Trần (Thái Bình), Khu nhà Trần Đông Triều, Đền Trần - Chùa Phổ Minh, Chùa Vĩnh Nghiêm, Chùa Thái Lạc |
| Nhà Hậu Lê | Lam Kinh |
| Nhà Tây Sơn | Khu đền thờ Tây Sơn Tam Kiệt |

### 3.4 HistoricalEvent (11 mới)

| Sự kiện | Di tích gắn |
|---|---|
| Chiến dịch Điện Biên Phủ | Chiến trường Điện Biên Phủ |
| Đợt III Chiến dịch Điện Biên Phủ | — (successor của Đợt II) |
| Chiến thắng Bạch Đằng năm 1288 | Bạch Đằng |
| Khởi nghĩa Yên Thế | Những địa điểm Khởi nghĩa Yên Thế |
| Khởi nghĩa Bắc Sơn | Khởi nghĩa Bắc Sơn |
| Phong trào Đồng Khởi | Đồng Khởi Bến Tre |
| Chiến thắng Rạch Gầm - Xoài Mút | Rạch Gầm - Xoài Mút |
| Sự kiện 81 ngày đêm Thành cổ Quảng Trị năm 1972 | Thành cổ Quảng Trị |
| Chiến dịch Đăk Tô I | Chiến thắng Đăk Tô - Tân Cảnh |
| Đại hội đại biểu toàn quốc lần thứ II của Đảng | Địa điểm tổ chức Đại hội II |
| Chiến dịch Ngọc Hồi - Đống Đa | Gò Đống Đa |

Cạnh successor mới: **Đợt II → Đợt III**, theo câu phân đợt của [Bảo tàng Lịch sử Quốc gia](https://baotanglichsu.vn/vi/Articles/2002/67980/tran-quyet-chien-chien-luoc-tieu-diet-tap-djoan-cu-djiem-djien-bien-phu-13-3-7-5-1954-djot-i-chien-dich-djien-bien-phu-djon-phu-djau.html). Không thêm cạnh tắt Đợt I → Đợt III.

### 3.5 ReligiousSite (29 di tích mới)

Chỉ gắn khi bài chính thức nêu rõ chức năng thờ tự. Các loại hình cũ được giữ nguyên.

- **Tháp Chăm:** Mỹ Sơn, Hòa Lai, Pô Klong Garai, Phật viện Đồng Dương
- **Chùa:** Bút Tháp, Dâu, Keo, Keo Hành Thiện, Tây Phương, Phật Tích, Vĩnh Nghiêm, Bổ Đà, Thái Lạc, Chùa Thầy, Tháp Bình Sơn
- **Đền:** Sóc, Hùng, Trần - Phổ Minh, Hai Bà Trưng, Hát Môn, Cửa Ông, Trần Thương, Tây Sơn Tam Kiệt
- **Khu di tích:** Yên Tử, Côn Sơn - Kiếp Bạc, Khu nhà Trần Đông Triều, Lăng mộ vua Lý, Lăng mộ vua Trần, Văn Miếu - Quốc Tử Giám

### 3.6 hasRelatedSite (5 cặp mới)

Mỗi cặp chỉ khai báo một chiều; chiều ngược do AX-006 suy ra.

| Cặp | Bằng chứng |
|---|---|
| Chùa Keo Hành Thiện → Chùa Keo | Hai chùa dựng lại từ cùng chùa Keo cũ |
| Lăng mộ vua Trần (Thái Bình) → Khu nhà Trần Đông Triều | Từ năm 1320 các vua Trần an táng ở An Sinh |
| Chùa Vĩnh Nghiêm → Yên Tử | Chốn tổ của Thiền phái Trúc Lâm Yên Tử |
| Chùa Bổ Đà → Chùa Vĩnh Nghiêm | Trung tâm Phật giáo thứ hai, cùng ảnh hưởng Thiền phái |
| Tháp Hòa Lai → Tháp Pô Klong Garai | Hai giai đoạn kiến trúc gần như nối tiếp |

---

## 4. Cách thực hiện

- **Nguồn:** chủ yếu bài giới thiệu di tích quốc gia đặc biệt của Cục Di sản văn hóa, cộng một bài của Bảo tàng Lịch sử Quốc gia. Không dùng Wikipedia, blog hay trang du lịch.
- **Bằng chứng:** script đối chiếu **nguyên văn** từng câu trích mới lấy từ dsvh với bài gốc trước khi ghi. Mỗi bằng chứng ghi URL, câu trích và thời điểm truy xuất.
- **Quy ước lưu trữ** (theo tiền lệ Tháp Nhạn):

  | Loại dữ kiện | Nơi lưu |
  |---|---|
  | Loại hình, phong cách, thời kỳ của từng di tích | `registry_fields` trong `data/raw/registry_records.jsonl`, kèm `*_evidence_url`, `*_evidence_quote`, `*_evidence_retrieved_at` |
  | Entity dùng chung (complex, phong cách, thời kỳ, sự kiện) | `derived_entities` trong `config/mapping.yaml` |
  | Quan hệ giữa hai di tích | `curated_relations` trong `config/mapping.yaml` |

- **ID:** tính bằng hàm có sẵn (`style_entity_id`, `period_entity_id`, `event_entity_id`); hash của complex tái tạo đúng ID cũ của Thành Nhà Hồ.
- **Code:** một thay đổi nhỏ trong `src/vietheritage/mapping/mapper.py`. `attach` nhận thêm `registry_ids` để một khái niệm gắn cho nhiều di tích, và nhận `license` riêng cho từng mục.
- **Pipeline:** `normalize → resolve → map → generate-rdf`, sau đó chạy Jena **một lần**, rồi `generate-rdf` lại để cập nhật metadata, cuối cùng `validate`.

---

## 5. Kiểm tra dữ liệu

| Kiểm tra | Kết quả |
|---|---|
| Unit + contract + semantic tests | ✅ 576 passed (gồm 8 test mới) |
| Jena OWL Mini 4.10.0 | ✅ AX-001 … AX-011, AX-017 PASS |
| AX-017 | ✅ không còn rỗng (2 cạnh successor) |
| SHACL | ✅ `conforms: true` |
| Semantic validation | ✅ 0 lỗi domain/range, 0 lỗi disjointness, 0 `owl:Nothing` |
| Nhiễm bẩn fixture | ✅ không có |
| `git diff --check` | ✅ sạch trên file không sinh tự động |

`git diff --check` còn báo trong RDF do generator sinh: 54 dòng trailing whitespace trong literal Wikipedia (giống hệt HEAD) và một dòng trống cuối `dataset-metadata.ttl`. Không vá tay artifact sinh tự động.

**Suy luận trên dữ liệu thật:**

- **hasMember → hasPart → partOf:** 18 `partOf` được suy ra. Có tính bắc cầu: Đền Cao An Phụ `partOf` cả complex An Phụ lẫn complex Yên Tử.
- **hasRelatedSite đối xứng:** 6 cạnh ngược được suy ra (6 → 12).
- **Chồng loại hình:** 28/30 ReligiousSite đồng thời là HistoricalSite, ArchitecturalSite hoặc ArchaeologicalSite.

---

## 6. Kiểm tra trên Docker

| Bước | Kết quả |
|---|---|
| Fuseki: nạp 5 named graph | ✅ |
| 10 câu SPARQL trên bộ dữ liệu mẫu (golden fixture) | ✅ 10/10 |
| Neo4j: nạp node | ✅ 1.111 node |
| Explorer `app-smoke` | ✅ 16/16 |
| `linked-data-test` | ✅ |
| `verify --run-mode full` | ❌ `FINAL STATUS: FAIL` (xem mục 7) |

Trên service đang chạy: URI complex Yên Tử trả Turtle (200), SPARQL đếm được 30 ReligiousSite, truy vấn `partOf` bắc cầu trả `true`.

`.env` local được tạo với mật khẩu ngẫu nhiên, đã nằm trong `.gitignore`.

---

## 7. Ba mục làm `verify` FAIL

Cả ba không do enrichment gây ra.

| Check | Nguyên nhân | Phạm vi |
|---|---|---|
| `cq` | Lệnh so với `data/fixtures/expected/`, chứa ID chỉ có trong dữ liệu mẫu (`site-…`). Không thể pass trên dữ liệu full. | Thiết kế của `query_runner` |
| `cypher_parity` | Commit `6e76bac` đổi tên và nội dung file `.rq` sau commit parity `61e9d30`. Chỉ 3/10 cặp còn trùng tên, và cả 3 đều lệch. Có cả trên `master`. | Member 4 |
| `coverage` | Thiếu `reports/20260925T034421Z/coverage.json`. File này được tạo khi cào toàn bộ registry và không được commit. | Môi trường |

---

## 8. Ứng viên bị loại hoặc hoãn

| Ứng viên | Lý do |
|---|---|
| Complex Cố đô Huế | Đã có 2 HeritageSite đại diện cả khu; identity và mức chi tiết mơ hồ |
| ReligiousSite cho Đền Ngọc Sơn | Dùng chung `registry_fields` với Hồ Hoàn Kiếm, sẽ gắn nhầm cho hồ |
| ReligiousSite cho Đền Xưa / Chùa Giám / Đền Bia | Cổng thông tin tỉnh không truy cập được |
| ReligiousSite cho Đền Phù Đổng | Bài chỉ nói về tín ngưỡng trong lễ hội |
| ReligiousSite cho Lam Kinh | Chỉ có Thái miếu là thành phần thờ tự |
| Thời kỳ Vijaya (Tháp Dương Long) | Bài chỉ nêu ngầm |
| "Thời Lý" cho Chùa Bổ Đà | Nguồn chỉ ghi "tương truyền" |
| Successor Bạch Đằng 938 / 981 / 1288 | Bài chỉ nói trận 1288 |
| Successor Đăk Tô I → II | Bài không nhắc "Đăk Tô II" |
| Successor trong chuỗi sự kiện Bắc Sơn | Chỉ là danh sách theo thời gian |
| Đền Hai Bà Trưng ↔ Đền Hát Môn | Không nguồn nào nối trực tiếp hai đền |
| Chùa Dâu ↔ Chùa Thái Lạc | Nguồn chỉ nhắc "vùng Dâu" và so sánh kiến trúc |

Trang UNESCO WHC (lỗi 403) và cổng thông tin Hải Dương không truy cập được nên không dùng làm bằng chứng.

---

## 9. File thay đổi

- `config/mapping.yaml`
- `src/vietheritage/mapping/mapper.py`
- `tests/unit/test_m2_data_quality.py`
- `data/raw/registry_records.jsonl` (30 dòng)
- `data/processed/{normalized,entities,canonical}.jsonl`
- `data/rdf/{vietheritage.ttl, dataset-metadata.ttl, reasoning-report.json}`

## 10. Việc còn lại

- [ ] Member 4: ghép lại 10 cặp Cypher ↔ SPARQL để `cypher_parity` chạy được.
- [ ] Cho `cq` trong `verify` chạy trên bộ dữ liệu mẫu thay vì dữ liệu đang nạp.
- [ ] Bổ sung selector theo từng phần của bản ghi registry đã tách, để gắn loại hình riêng (ví dụ Đền Ngọc Sơn).
- [ ] Tắt container khi không dùng: `docker compose stop`.
