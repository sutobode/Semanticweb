# External Link Evaluation — VietHeritageLOD (Thành viên 3, COMP-007)

Kết quả sửa chính sách xuất bản liên kết trên canonical snapshot
`20260925T034421Z`, gồm 1.068 bản ghi. Chỉ chạy linker với các đầu vào cục bộ;
không thu thập dữ liệu, không chạy lại normalization/mapping/RDF generation
hoặc reasoning. `PROJECT_SPEC.md` 1.6.2 §16, §22–23 là chuẩn authoritative.

## 1. Kết quả từ các artifact hiện tại

| Chỉ số | Trước sửa | Sau sửa |
|---|---:|---:|
| Dòng review | 281 | 281 |
| `verified` / `owl:sameAs` được xuất bản | 281 | **221** |
| Wikidata được xuất bản | 256 | **221** |
| DBpedia được xuất bản | 25 | **0** |
| `manual_review` | 0 | **18** |
| `rejected` | 0 | **42** |

Nguồn số liệu: `data/rdf/external-links.ttl`, `data/linking/link_review.csv`,
`data/linking/link-review.jsonl`, `data/linking/dbpedia_candidates.csv`.
221 liên kết còn xuất bản vẫn vượt ngưỡng MUST ≥100 của MET-008.
Không thêm liên kết giả để giữ số lượng cũ.

42 dòng bị từ chối gồm:

- 40 dòng thuộc thành phần identity xung đột: 35 Wikidata và 5 DBpedia,
  liên quan 35 resource nội bộ. Bản trước sửa có 23 cặp resource disjoint,
  dùng chung 12 QID và thêm một URI DBpedia trong một nhóm đã xung đột.
- 2 DBpedia có bằng chứng QID cũ không còn khớp canonical.

18 DBpedia còn lại ở `manual_review`. Cả 25 ứng viên DBpedia đều thiếu
`distance_km`; không ứng viên nào có review độc lập hợp lệ trong manifest cũ.

## 2. An toàn identity trước khi xuất bản

`link_records()` đọc ontology và asserted A-Box hiện tại.
`_reject_identity_conflicts()` tái sử dụng `validation.semantic.Contract`:

1. Lập đồ thị vô hướng từ các ứng viên chưa bị từ chối và các assertion
   `owl:sameAs` đã có trong A-Box; ứng viên đang chờ review cũng tham gia.
2. Duyệt toàn bộ thành phần liên thông. Không chỉ kiểm tra từng resource
   hoặc từng cặp cùng đích: identity có thể nối gián tiếp qua nhiều đích.
3. Hợp các type đã biết, gồm ancestry `rdfs:subClassOf`; lấy các cặp disjoint
   từ `owl:disjointWith`, `owl:AllDisjointClasses`, `owl:disjointUnionOf`.
4. Nếu thành phần chứa type disjoint, từ chối toàn bộ ứng viên trong thành
   phần. Không tự chọn một resource làm bên thắng.
5. Giữ bằng chứng gốc trong `reason`, thêm `IDENTITY_TYPE_CONFLICT`, mã axiom,
   class và resource làm chứng. Các thành phần tương thích vẫn được xuất bản.

Ví dụ cũ `registry-7d309bea2919` và `registry-2dc9c151de83` cùng nối tới
`Q2397005`/`dbpedia:Space_of_gong_culture` bị từ chối do AX-008.
Không thay đổi ontology hoặc type trong A-Box để cho phép đồng nhất này.

## 3. DBpedia: ứng viên không phải phê duyệt

`review_dbpedia_candidate()` giữ nguyên các ngưỡng hiện hành:

| Điều kiện | Trạng thái ứng viên |
|---|---|
| Type không tương thích hoặc score < 0.70 | `rejected` |
| Khoảng cách > 20 km | `rejected` |
| Score ≥ 0.90 và khoảng cách ≤ 5 km | `auto_candidate` |
| Score ≥ 0.90 và thiếu khoảng cách | `manual_review` |
| Score ≥ 0.70 và khoảng cách ≤ 20 km, ngoài nhánh auto | `manual_review` |
| Tổ hợp không có quyết định trong §22.2 | Dừng với `LINK_POLICY_UNCOVERED` |

Theo §22.4, `auto_candidate` chuyển thành `manual_review` khi vào manifest
review. Chỉ review tường minh của reviewer hoặc fixture verification mới cho
phép `verified`. Linker đọc lại `link_review.csv`, yêu cầu đúng cặp URI,
dataset, score, distance, type compatibility, cùng reviewer/thời điểm/lý do.
Các dòng `automated:vietheritage-linker/0.1.0` cũ không phải phê duyệt độc lập.

Thiếu khoảng cách không tự động thành `verified`. Trường hợp này chỉ có thể
được xuất bản sau review tường minh hợp lệ; review cũng không vượt qua được
lỗi type, ngưỡng từ chối, bằng chứng QID cũ hoặc xung đột identity.

`dbpedia_candidates.csv` giữ trạng thái ứng viên (`auto_candidate`,
`manual_review`, `rejected`); `link_review.csv`/JSONL giữ trạng thái review
(`verified`, `manual_review`, `rejected`). Schema manifest không thay đổi.

## 4. QID bridge và bằng chứng cũ

Không có ngoại lệ QID-bridge trong §22–23 cho phép bỏ qua review DBpedia.
Ứng viên `method=dbpedia-wikidata-sameas` hoặc có `wikidata_id` phải có QID
hợp lệ, bằng đúng `external_ids.wikidata` của canonical hiện tại.

Nếu thiếu hoặc khác QID, dòng đó bị `rejected` với `STALE_QID_BRIDGE`;
`reason` giữ QID trong bằng chứng và QID canonical để truy vết. Một đường
bằng chứng độc lập khác chỉ được xuất bản nếu tự thỏa chính sách hiện hành.

| Resource | Đích | QID trong bằng chứng | QID canonical |
|---|---|---|---|
| `registry-5c00a7907df2` | `dbpedia:Cauldron` | `Q1317634` | Không có |
| `registry-5988642e341f` | `dbpedia:Cannon` | `Q81103` | Không có |

Hai liên kết này không còn xuất hiện trong RDF. Các file raw bằng chứng
được giữ nguyên; quyết định mới nằm trong review manifest.

## 5. Kiểm chứng và tái sinh riêng Member 3

`tests/unit/test_linker.py`: **29 test PASS**, bao gồm thành phần tương thích,
AX-008, subclass/disjointness, identity nhiều bước, thiếu khoảng cách,
review cũ tự động, bridge hợp lệ/cũ, đường bằng chứng độc lập và chạy riêng
linking không đổi đầu vào/metadata.

Kiểm tra trực tiếp trên các artifact sau sửa:

- Turtle parse PASS; 221 triple và 221 subject có trong A-Box.
- 0 assertion trùng, 0 self-link, 0 QID xuất bản lệch canonical.
- CSV/JSONL khớp nhau; toàn bộ 281 dòng đạt schema review.
- 202 thành phần identity được xuất bản; 0 xung đột type disjoint/AX-008.
- Tập liên kết xuất bản bằng đúng tập dòng review `verified`.

Lần sửa này tái sinh bằng `linker.run("full", refresh_metadata=False)` để
chỉ ghi bốn artifact linking. Mặc định của `run()` vẫn giữ hành vi cập nhật
metadata cho pipeline thông thường; tùy chọn trên tắt riêng tác dụng phụ đó.
`dataset-metadata.ttl` không được cập nhật trong phạm vi Member 3 này, nên
metric `verified_external_links=281` trong file đó chưa phản ánh số mới 221.
