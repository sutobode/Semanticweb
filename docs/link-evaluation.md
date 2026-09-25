# External Link Evaluation — VietHeritageLOD (Thành viên 3, COMP-007)

Đánh giá link `owl:sameAs` sinh bởi `src/vietheritage/linking/linker.py`, dựa
trên lần chạy lại toàn bộ pipeline (`normalize → resolve → map → generate-rdf
→ link`, `RUN_MODE=full`) trên snapshot registry hiện có trong
`data/raw/registry_records.jsonl` (2026-09-25). Không gọi mạng trong bước
`link`; mọi input là manifest đã được thu thập trước (`data/raw/*candidates*`,
`external_ids.wikidata` trong canonical record).

## 1. Kết quả tổng hợp

| Metric | Giá trị | Ngưỡng yêu cầu (PROJECT_SPEC MET-008) |
|---|---:|---:|
| Canonical record đưa vào review | 1 068 | — |
| Candidate được review | 281 | — |
| Candidate `verified` (→ `owl:sameAs` trong `external-links.ttl`) | **281** | 100–250 (SHOULD), ≥100 (MUST) |
| — trong đó Wikidata | 256 | — |
| — trong đó DBpedia | 25 | — |
| Candidate `manual_review` chưa verify | 0 | — |
| Candidate `rejected` | 0 | — |
| `owl:sameAs` triples trong `data/rdf/external-links.ttl` | 281 | khớp verified |

281 vượt cả khoảng SHOULD (100–250) của spec. Không có candidate nào đang ở
trạng thái `manual_review` chờ xử lý ở snapshot này — chi tiết vì sao ở §3.2.

Nguồn số liệu: `data/linking/link_review.csv`, `data/linking/link-review.jsonl`
(sinh bởi `make link RUN_MODE=full`).

## 2. Wikidata linking — deterministic (PROJECT_SPEC §22.1)

**Phương pháp:** nếu canonical record có `external_ids.wikidata` khớp
`^Q[1-9][0-9]*$` (`linker.py:_QID_RE`), sinh trực tiếp:

```turtle
vhr:<entity_id> owl:sameAs <https://www.wikidata.org/entity/Q...> .
```

với `method=wikidata-qid`, `score=1.0`, `status=verified` ngay lập tức — **không
qua ngưỡng review**, vì QID trên record đã là kết quả của một bước xác định
danh tính độc lập trước đó (Wikipedia infobox/pageprops hoặc truy vấn Wikidata
exact-label của M2/M3), không phải suy luận từ label giống nhau (đúng NUNA,
PROJECT_SPEC §1.4.2). QID không hợp lệ (không khớp regex) bị `rejected` tường
minh, không bị âm thầm bỏ qua.

**Kết quả:** 256/1068 canonical record (24.0%) có QID hợp lệ và được verify.
Toàn bộ 256 record đều `status=verified`, không có `rejected` QID trong
snapshot hiện tại (đã qua chuẩn hóa ở COMP-001/COMP-004 trước khi tới đây).

## 3. DBpedia linking (PROJECT_SPEC §22.2–22.3)

Hai kênh candidate cùng đổ vào `link_records()`; kết quả review khác nhau vì
evidence khác nhau.

### 3.1 Kênh đã có dữ liệu: DBpedia↔Wikidata bridging

`data/raw/dbpedia_wikidata_candidates.jsonl` (25 dòng, `tools/dbpedia_wikidata_candidates.py`)
chứa candidate DBpedia được xác nhận qua chính DBpedia SPARQL endpoint: mỗi
dòng là một resource DBpedia có `owl:sameAs` **tường minh** trỏ ngược tới đúng
QID Wikidata mà record VietHeritageLOD đó đã verify ở §2 (`evidence: "DBpedia
HTTP SPARQL explicit owl:sameAs to the canonical Wikidata QID"`, `score: 1.0`,
`method: dbpedia-wikidata-sameas`). Đây là bằng chứng mạnh hơn label/geo
matching thuần túy — DBpedia tự công bố identity đó, không phải project suy
luận — nên cả 25/25 candidate đạt `status=verified` khi qua
`review_dbpedia_candidate()` (score 1.0 ≥ 0.90, không có toạ độ mâu thuẫn).

### 3.2 Kênh chưa có dữ liệu trong snapshot này: DBpedia Lookup / label search

`data/raw/dbpedia_lookup_candidates.jsonl` và `data/raw/dbpedia_exact_candidates.jsonl`
hiện **rỗng (0 dòng)** — công cụ thu thập (`tools/dbpedia_lookup_candidates.py`,
`tools/dbpedia_exact_candidates.py`) đã chạy nhưng DBpedia Lookup API không
trả candidate khớp cho phần lớn label tiếng Việt trong snapshot hiện tại. Vì
vậy nhánh đánh giá fuzzy — `dbpedia_score()` (Levenshtein-style
`difflib.SequenceMatcher` trên label) kết hợp `distance_km` (haversine) theo
bảng quyết định §22.2 — **có code, có unit test
(`tests/unit/test_linker.py`), nhưng chưa có candidate thật nào đi qua nhánh
`manual_review`/`rejected` trong lần chạy này**, vì không có input. Đây là hạn
chế của nguồn dữ liệu candidate ở bước thu thập (COMP-007 phần label-search),
không phải lỗi của bộ tính điểm hay ngưỡng review.

**Khuyến nghị cho vòng linking tiếp theo:** mở rộng `dbpedia_lookup_candidates.py`
sang tiếng Anh (dùng `title` Wikipedia tiếng Anh nếu có interwiki link) hoặc hạ
ngưỡng truy vấn Lookup API trước khi kết luận DBpedia không có candidate — với
1068 canonical record hiện tại (271 `HeritageSite`), 25 link qua kênh QID-bridge
là một lower bound, không phải giới hạn thật của DBpedia coverage.

## 4. Ngưỡng quyết định (Silk policy, PROJECT_SPEC §22.2, `silk/linkage-rules.xml`)

| Điều kiện | Kết quả |
|---|---|
| `type_compatible=false` | `rejected` |
| `score < 0.70` | `rejected` |
| `0.70 ≤ score < 0.90`, `distance_km ≤ 20` | `manual_review` |
| `score ≥ 0.90`, `distance_km ≤ 5`, có đủ toạ độ | `verified` (auto) |
| `score ≥ 0.90`, `5 < distance_km ≤ 20` | `manual_review` |
| `score ≥ 0.90`, thiếu một toạ độ | `manual_review` |
| `distance_km > 20` | `rejected` |

Cài đặt: `review_dbpedia_candidate()` (`linker.py:58-71`), đọc ngưỡng từ
`DBPEDIA_AUTO_ACCEPT_SCORE` (0.90), `DBPEDIA_REVIEW_SCORE` (0.70),
`DBPEDIA_AUTO_ACCEPT_DISTANCE_KM` (5), `DBPEDIA_REVIEW_DISTANCE_KM` (20) —
khớp `config/thresholds.yaml` và `silk/linkage-rules.xml`. `distance_km=None`
(record thiếu toạ độ nguồn hoặc đích) được coi là "không mâu thuẫn" chứ không
tự động reject, để không phạt các entity registry chưa có toạ độ.

`silk/linkage-rules.xml` là **policy source** đúng nghĩa đen theo
PROJECT_SPEC §22.3 (label similarity ≥ 0.90 AND geographic proximity ≤ 5 km);
project không đóng gói Silk Workbench/engine Java, executor thật là
`review_dbpedia_candidate()`/`dbpedia_score()` — cùng metric, cùng ngưỡng,
cùng phép kết hợp `AND`, chỉ khác runtime (Python thay vì Silk JVM). Điều kiện
`type_compatible` được lọc **trước** khi vào rule (không phải một `Compare`
trong Silk XML) vì đây là kiểm tra nhị phân từ `entity_type`/`registry_category`
đã biết, không phải một phép so khớp mờ cần metric riêng.

## 5. Bảng xác thực (mẫu, đầy đủ tại `data/linking/link_review.csv`)

Toàn bộ 281 dòng verified có đủ 4 cột yêu cầu (Local resource, External
resource, Method, Confidence) cộng metadata review (`reviewer`, `reviewed_at`,
`reason`) — không có dòng nào thiếu evidence.

| Local resource | External resource | Method | Confidence | Verified |
|---|---|---|---:|---|
| `vhr:registry-53caa1c3d5a1` (Vịnh Hạ Long) | `wd:Q190128` | `wikidata-qid` | 1.0 | Yes |
| `vhr:registry-53caa1c3d5a1` (Vịnh Hạ Long) | `dbpedia:Hạ_Long_Bay` | `dbpedia-wikidata-sameas` (label: `silk` trong CSV) | 1.0 | Yes |
| `vhr:registry-50e10d2b672f` (Phong Nha – Kẻ Bàng) | `dbpedia:Phong_Nha_–_Kẻ_Bàng_National_Park` | `silk` | 1.0 | Yes |
| `vhr:event-46f796e3c0a8` | `wd:Q7096923` | `wikidata-qid` | 1.0 | Yes |

Cột `method` trong `link_review.csv` ghi `silk` cho mọi candidate DBpedia
(kênh QID-bridge lẫn kênh label-search tương lai), để phân biệt với
`wikidata-qid` — đúng quy ước COMP-007 rằng mọi candidate không-deterministic
đều đi qua "Silk-style" scoring trước khi verify, bất kể nguồn candidate gốc.
`reviewer=automated:vietheritage-linker/0.1.0` cho toàn bộ 281 dòng: xác minh
hiện tại là **automated** (dựa trên evidence xác định — QID trùng khớp hoặc
DBpedia tự khai `owl:sameAs`), không phải human review thủ công; điều này
được ghi rõ trong `reason` của từng dòng, không giả vờ là review thủ công.

## 6. Validate `owl:sameAs` — không chấp nhận mù quáng

`owl:sameAs` chỉ được sinh khi (PROJECT_SPEC §23, thực thi bởi
`validation/policy.py` + `validation/semantic.py`, kiểm tra trong `validate`
stage khi `external-links.ttl` có mặt):

1. QID Wikidata hợp lệ trên chính record đó, HOẶC
2. DBpedia candidate `status=verified` trong `link_review.csv`; VÀ
3. Target URI là entity URI thật (không phải trang chủ tổ chức hay dataset
   container).

Không dùng `owl:sameAs` cho site↔thành phố, site↔website chính thức (dùng
`foaf:homepage` nếu cần), class↔instance, hoặc hai entity chỉ trùng label.
`tests/unit/test_validation.py::test_same_as_requires_approved_local_identity`
và `tests/unit/test_linker.py` giữ fixture âm cho từng vi phạm này.

## 7. Giới hạn đã biết

1. **DBpedia label-search chưa có candidate thật** (§3.2) — 25/25 link DBpedia
   hiện tại đều đến từ QID-bridge, không phải fuzzy Silk-style match; ngưỡng
   `manual_review`/`rejected` có code + test nhưng chưa được minh chứng trên
   dữ liệu thật của snapshot này.
2. **Reasoning-based validation chưa chạy được trong môi trường audit này**
   (thiếu Apache Jena/JDK cục bộ) — không ảnh hưởng tới linking, nhưng
   `make validate` cần `data/rdf/inferred.ttl` (từ `make reason`, thuộc
   Thành viên 1) trước khi có thể PASS toàn bộ. Xem `MEMBER3_WORK_HANDOFF.md`.
3. **256 Wikidata link phụ thuộc chất lượng QID upstream** (COMP-001/COMP-004,
   Thành viên 2) — linker không tự xác minh QID trỏ đúng entity, chỉ xác minh
   định dạng; sai QID ở nguồn sẽ tạo `owl:sameAs` sai mà linking stage không
   phát hiện được (nằm ngoài COMP-007, cần spot-check thủ công định kỳ — đã
   ghi trong `docs/M2_IMPLEMENTATION_NOTES.md` §5 "Việc còn mở").
