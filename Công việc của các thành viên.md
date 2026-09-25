PHÂN CÔNG CÔNG VIỆC NHÓM 4 NGƯỜI
Capstone Project: VietHeritageLOD	5
1. Nguyên tắc phân công	5
2. Thành viên 1 — Ontology & Knowledge Modeling Lead	5
2.1. Mục tiêu chính	5
2.2. Công việc cụ thể	6
A. Xây dựng competency questions	6
B. Xây terminology glossary	6
C. Thiết kế class hierarchy	7
D. Thiết kế object properties	8
E. Thiết kế datatype properties	8
F. Triển khai RDFS	9
G. Triển khai OWL / OWL2	9
H. Reasoning	9
I. Ontology documentation	10
2.3. Deliverables chính	10
2.4. Phối hợp	10
3. Thành viên 2 — Data Acquisition & Normalization Lead	11
3.1. Mục tiêu chính	11
3.2. Công việc cụ thể	11
A. Khảo sát nguồn dữ liệu	11
B. Chọn tập entity ban đầu	12
C. Xây data collector	12
D. Thiết kế intermediate schema	12
E. Data cleaning	13
F. Chuẩn hóa dữ liệu	13
G. Xử lý missing data	14
H. Entity deduplication	14
I. Provenance metadata	15
J. Data statistics	15
3.3. Deliverables chính	15
3.4. Phối hợp	16
4. Thành viên 3 — RDF & Linked Data Lead	16
4.1. Mục tiêu chính	16
4.2. Công việc cụ thể	16
A. Thiết kế URI	16
B. Thiết kế RDF mapping	17
C. Implement RDFLib transformation	17
D. Sinh RDF dataset	18
E. Vocabulary reuse	18
F. Provenance RDF	19
G. Wikidata linking	19
H. DBpedia linking	19
I. Silk Framework	20
J. Validate owl:sameAs	20
K. RDF validation	20
4.3. Deliverables chính	21
4.4. Phối hợp	21
5. Thành viên 4 — SPARQL, Triple Store & Deployment Lead	21
5.1. Mục tiêu chính	21
5.2. Công việc cụ thể	22
A. Cài đặt Apache Jena Fuseki	22
B. Docker hóa	22
C. Load và kiểm tra RDF graph	22
D. Implement 10 SPARQL queries	23
E. Expected-result testing	23
F. Linked Data publication	24
G. SPARQL endpoint	24
H. Federated query	24
I. Deployment	25
J. Final demo environment	25
5.3. Deliverables chính	25
5.4. Phối hợp	26
6. Công việc chung của cả nhóm	26
7. Phân công theo 7 tuần	27
Tuần 1 — Project Definition	27
Thành viên 1	27
Thành viên 2	27
Thành viên 3	27
Thành viên 4	27
Output chung	27
8. Tuần 2 — RDF Prototype	28
Thành viên 1	28
Thành viên 2	28
Thành viên 3	28
Thành viên 4	28
Output chung	28
9. Tuần 3 — RDFS	29
Thành viên 1	29
Thành viên 2	29
Thành viên 3	29
Thành viên 4	29
Output chung	29
10. Tuần 4 — Linked Open Data	29
Thành viên 1	29
Thành viên 2	30
Thành viên 3	30
Thành viên 4	30
Output chung	30
11. Tuần 5 — OWL & Reasoning	30
Thành viên 1	30
Thành viên 2	30
Thành viên 3	31
Thành viên 4	31
Output chung	31
12. Tuần 6 — 5-star Completion	31
Thành viên 1	31
Thành viên 2	31
Thành viên 3	31
Thành viên 4	31
Output chung	32
13. Tuần 7 — Finalization	32
Thành viên 1	32
Thành viên 2	32
Thành viên 3	32
Thành viên 4	33
14. Phân công viết báo cáo	33
15. Phân công slide và thuyết trình	34
16. Phân công video 3–5 phút	34
17. Quy tắc Git và quản lý công việc	35
18. Quy tắc họp nhóm	36
Buổi đầu tuần	36
Buổi cuối tuần	36
19. Definition of Done cho từng thành viên	36
Thành viên 1 hoàn thành khi	37
Thành viên 2 hoàn thành khi	37
Thành viên 3 hoàn thành khi	37
Thành viên 4 hoàn thành khi	37
20. Tiêu chí đảm bảo khối lượng công việc cân bằng	37
21. Ma trận trách nhiệm tổng hợp	38
22. Mục tiêu chung cuối cùng	39
Capstone Project: VietHeritageLOD
Tên đề tài: VietHeritageLOD – A Linked Open Data Knowledge Graph for Vietnamese Cultural Heritage
Số thành viên: 4
Thời gian thực hiện: 7 tuần
Thời gian dự kiến: 23/08/2026 – 09/10/2026
Ngày trình bày: 10/10/2026

1. Nguyên tắc phân công
Dự án được chia thành bốn mảng công việc chính:
Thành viên
Vai trò chính
Mảng phụ trách
Thành viên 1
Ontology & Knowledge Modeling Lead
Ontology, RDFS, OWL/OWL2, competency questions, reasoning
Thành viên 2
Data Acquisition & Normalization Lead
Thu thập, làm sạch, chuẩn hóa và quản lý dữ liệu nguồn
Thành viên 3
RDF & Linked Data Lead
RDF transformation, URI, provenance, Wikidata/DBpedia linking, Silk
Thành viên 4
SPARQL, Triple Store & Deployment Lead
Fuseki, SPARQL, Linked Data publication, deployment, testing

Mỗi thành viên chịu trách nhiệm chính đối với output của mảng mình, nhưng không làm việc hoàn toàn độc lập. Các phần có liên quan trực tiếp phải được review chéo giữa các thành viên.

2. Thành viên 1 — Ontology & Knowledge Modeling Lead
2.1. Mục tiêu chính
Chịu trách nhiệm thiết kế mô hình tri thức của toàn bộ dự án, đảm bảo ontology đủ khả năng biểu diễn dữ liệu thu thập được và trả lời các competency questions đã đề ra.
Đây là người chịu trách nhiệm chính về phần semantic modeling của VietHeritageLOD.

2.2. Công việc cụ thể
A. Xây dựng competency questions
Phối hợp với cả nhóm để chốt 10 competency questions, ví dụ:
tìm di sản theo địa phương;
tìm di sản UNESCO theo năm công nhận;
tìm di sản liên quan tới nhân vật lịch sử;
tìm địa phương có nhiều di sản nhất;
tìm các entity có external links;
truy vấn kết hợp với DBpedia.
Với mỗi competency question cần xác định:
Natural-language question
        ↓
Các concepts cần biểu diễn
        ↓
Các properties cần có
        ↓
Dữ liệu cần thu thập
        ↓
SPARQL query dự kiến


B. Xây terminology glossary
Xây danh sách các khái niệm chính của domain, ví dụ:
HeritageSite
HistoricalSite
ReligiousSite
ArchaeologicalSite
ArchitecturalSite
UNESCOHeritageSite
HeritageComplex
HistoricalPerson
HistoricalEvent
HistoricalPeriod
AdministrativeArea
Organization

Với mỗi term cần ghi:
tên;
định nghĩa;
ví dụ;
quan hệ với term khác;
có sử dụng vocabulary bên ngoài hay không.

C. Thiết kế class hierarchy
Thiết kế ontology sơ bộ trong Protégé.
Ví dụ:
CulturalHeritageEntity
│
├── HeritageSite
│   ├── HistoricalSite
│   ├── ReligiousSite
│   ├── ArchaeologicalSite
│   ├── ArchitecturalSite
│   └── UNESCOHeritageSite
│
├── HeritageComplex
└── Museum

Phải xác định rõ:
rdfs:subClassOf;
các class có thể overlap;
các class cần owl:disjointWith;
class nào dùng trực tiếp;
class nào được suy luận.

D. Thiết kế object properties
Ví dụ:
vh:locatedIn
vh:partOf
vh:hasPart
vh:associatedWithPerson
vh:associatedWithEvent
vh:belongsToPeriod
vh:builtBy
vh:recognizedBy
vh:hasArchitecturalStyle

Với mỗi property phải xác định:
property name
domain
range
inverse property nếu có
subPropertyOf nếu có
transitive/symmetric/functional nếu phù hợp


E. Thiết kế datatype properties
Ví dụ:
vh:constructionYear
vh:recognitionYear
vh:address

Đồng thời xác định các property có thể reuse:
rdfs:label
rdfs:comment
geo:lat
geo:long
dcterms:source
dcterms:license


F. Triển khai RDFS
Sau bài RDFS:
khai báo class;
subclass;
property;
domain;
range;
label;
comment;
property hierarchy nếu cần.
Ví dụ:
vh:UNESCOHeritageSite
    rdfs:subClassOf vh:HeritageSite .


G. Triển khai OWL / OWL2
Sau các buổi OWL và OWL2, bổ sung các axiom thực sự có ý nghĩa.
Ví dụ:
partOf inverseOf hasPart

HistoricalPerson
    disjointWith HeritageSite

UNESCOHeritageSite
    equivalentTo
    HeritageSite
    AND recognizedBy value UNESCO

Không thêm axiom chỉ để tăng số lượng.

H. Reasoning
Chuẩn bị ít nhất 1–2 reasoning scenarios.
Ví dụ:
siteA rdf:type HeritageSite
siteA recognizedBy UNESCO

Reasoner suy ra:
siteA rdf:type UNESCOHeritageSite

Phải ghi lại:
knowledge trước reasoning;
ontology axiom;
inferred knowledge;
screenshot hoặc demo từ Protégé.

I. Ontology documentation
Chuẩn bị phần tài liệu gồm:
ontology diagram;
danh sách classes;
danh sách properties;
domain/range;
vocabulary reuse;
OWL axioms;
reasoning examples.

2.3. Deliverables chính
ontology/vietheritage.ttl
ontology/diagrams/
docs/competency-questions.md
docs/ontology-specification.md
docs/reasoning-examples.md


2.4. Phối hợp
Với Thành viên 2: kiểm tra ontology có phù hợp dữ liệu thực tế hay không.
Với Thành viên 3: kiểm tra RDF mapping có đúng semantics của ontology hay không.
Với Thành viên 4: kiểm tra 10 competency questions có thể chuyển thành SPARQL query và trả lời được hay không.

3. Thành viên 2 — Data Acquisition & Normalization Lead
3.1. Mục tiêu chính
Chịu trách nhiệm xây dựng dataset đầu vào sạch, nhất quán và có nguồn gốc rõ ràng để RDF pipeline có thể sử dụng ổn định.
Không chỉ thu thập nhiều dữ liệu mà phải đảm bảo dữ liệu thực sự phục vụ ontology và competency questions.

3.2. Công việc cụ thể
A. Khảo sát nguồn dữ liệu
Nguồn chính:
Vietnamese Wikipedia

Khảo sát:
Wikipedia categories;
loại bài viết;
infobox thường gặp;
API response;
coordinates;
Wikidata QID;
page ID;
title;
links;
categories.

B. Chọn tập entity ban đầu
Giai đoạn thử nghiệm:
20–30 heritage sites

Sau khi pipeline ổn định:
100–150 sites

Mục tiêu cuối:
150–250 primary heritage sites

Không thu thập hàng loạt ngay từ đầu.

C. Xây data collector
Triển khai Python collector sử dụng MediaWiki API.
Collector cần lấy tối thiểu:
page_id
title
URL
Wikidata ID
coordinates
categories
short description
selected infobox fields

Output raw:
data/raw/


D. Thiết kế intermediate schema
Phối hợp với Thành viên 1 và Thành viên 3 để thống nhất cấu trúc JSON trung gian.
Ví dụ:
{
  "id": "viwiki-123456",
  "page_id": 123456,
  "name_vi": "...",
  "wikidata_id": "Q...",
  "source_url": "...",
  "categories": [],
  "coordinates": {
    "lat": null,
    "long": null
  },
  "location": {},
  "construction_year": null,
  "recognition_year": null,
  "persons": [],
  "events": []
}


E. Data cleaning
Xử lý:
HTML markup;
Wikipedia markup;
dư thừa khoảng trắng;
ký tự đặc biệt;
duplicate;
redirect;
null values;
inconsistent field names.

F. Chuẩn hóa dữ liệu
Chuẩn hóa:
Tên
Văn Miếu - Quốc Tử Giám
Văn Miếu – Quốc Tử Giám

về một representation thống nhất.
Năm
1070
"năm 1070"
"1070 (thời Lý)"

→
1070

nếu có thể xác định chắc chắn.
Coordinate
Chuẩn hóa latitude/longitude thành dạng numeric thống nhất.

G. Xử lý missing data
Không tự suy đoán dữ liệu.
Nếu source không có:
constructionYear

thì giữ:
null

hoặc không tạo triple tương ứng.
Điều này phù hợp với Open World Assumption.

H. Entity deduplication
Phát hiện các record có thể là cùng một entity.
Ưu tiên:
Wikipedia page ID
Wikidata QID
canonical URL

làm identifier.

I. Provenance metadata
Mỗi record cần giữ:
source URL
retrieval date
source page ID
source dataset

để Thành viên 3 sinh provenance RDF.

J. Data statistics
Cuối pipeline phải thống kê được:
number of collected pages
number of valid entities
number of discarded records
number with Wikidata QID
number with coordinates
number with historical persons
number with recognition year


3.3. Deliverables chính
src/collector/
src/normalization/
data/raw/
data/processed/
docs/data-sources.md
docs/data-schema.md
docs/data-statistics.md


3.4. Phối hợp
Với Thành viên 1: xác nhận property ontology có dữ liệu hỗ trợ.
Với Thành viên 3: thống nhất normalized JSON schema và mapping sang RDF.
Với Thành viên 4: cung cấp dataset ổn định để kiểm thử SPARQL.

4. Thành viên 3 — RDF & Linked Data Lead
4.1. Mục tiêu chính
Chịu trách nhiệm chuyển dữ liệu đã chuẩn hóa thành RDF knowledge graph hợp lệ, đồng thời thực hiện phần quan trọng nhất để đạt 5-star LOD: liên kết entity với các dataset bên ngoài.

4.2. Công việc cụ thể
A. Thiết kế URI
Phối hợp với Thành viên 1 để xây URI convention.
Ví dụ:
/ontology/HeritageSite
/ontology/locatedIn

/resource/site/viwiki-123456
/resource/person/wikidata-Q123
/resource/place/wikidata-Q456

Yêu cầu:
unique;
stable;
không phụ thuộc quá nhiều vào label;
có thể publish qua HTTP.

B. Thiết kế RDF mapping
Map normalized data sang ontology.
Ví dụ:
name_vi
    ↓
rdfs:label "... "@vi

latitude
    ↓
geo:lat

historical_person
    ↓
vh:associatedWithPerson

Mapping phải được document rõ.

C. Implement RDFLib transformation
Viết Python code:
JSON
 ↓
RDFLib Graph
 ↓
Turtle

Phải xử lý:
URIRef;
Literal;
language tags;
XSD datatypes;
RDF type;
ontology properties;
external vocabularies.

D. Sinh RDF dataset
Output chính:
data/rdf/vietheritage.ttl

Có thể tách thành:
entities.ttl
ontology.ttl
provenance.ttl
external-links.ttl

nếu cần.

E. Vocabulary reuse
Triển khai:
RDF
RDFS
OWL
DCTerms
WGS84
PROV-O
FOAF / schema.org nếu cần

Không tạo property mới nếu vocabulary phổ biến đã có term phù hợp.

F. Provenance RDF
Ví dụ:
vh:site123
    prov:wasDerivedFrom
    <https://vi.wikipedia.org/wiki/...> .

Thêm:
retrieval metadata;
source;
license;
dataset metadata.

G. Wikidata linking
Ưu tiên deterministic linking.
Nếu record có:
wikidata_id = Q12345

sinh:
vh:site123
    owl:sameAs
    wd:Q12345 .

Sau đó thống kê:
number of Wikidata links
percentage of resources linked


H. DBpedia linking
Xây candidate links tới DBpedia thông qua:
English Wikipedia correspondence;
labels;
coordinates;
Wikidata;
Silk Framework.

I. Silk Framework
Thiết kế linkage rules.
Ví dụ:
label similarity
AND
geographic proximity
AND
type compatibility

Thiết lập threshold cho:
accept
verify
reject


J. Validate owl:sameAs
Không chấp nhận tất cả candidate tự động.
Chuẩn bị bảng:
Local resource
External resource
Method
Confidence
Verified
...
...
Wikidata ID
1.0
Yes
...
...
Silk
0.92
Yes


K. RDF validation
Kiểm tra:
Turtle parse;
datatype;
URI format;
language tag;
orphan node;
invalid external links.
Phải đảm bảo final RDF load được vào Fuseki.

4.3. Deliverables chính
src/rdf/
src/linking/
data/rdf/vietheritage.ttl
data/rdf/external-links.ttl
silk/linkage-rules.xml
docs/rdf-mapping.md
docs/link-evaluation.md


4.4. Phối hợp
Với Thành viên 1: kiểm tra RDF semantics và ontology mapping.
Với Thành viên 2: kiểm tra normalized source data.
Với Thành viên 4: đảm bảo RDF load và query đúng trên Fuseki.

5. Thành viên 4 — SPARQL, Triple Store & Deployment Lead
5.1. Mục tiêu chính
Chịu trách nhiệm biến RDF dataset thành hệ thống có thể truy vấn và demo thực tế, bao gồm triple store, SPARQL endpoint, Linked Data access và deployment.

5.2. Công việc cụ thể
A. Cài đặt Apache Jena Fuseki
Thiết lập môi trường local trước.
Cần thực hiện:
Fuseki installation
dataset creation
RDF upload
SPARQL query endpoint
SPARQL update nếu cần


B. Docker hóa
Nếu thời gian cho phép, tạo:
docker-compose.yml

để nhóm có thể chạy:
docker compose up

và khởi động hệ thống.
Mục tiêu là giảm phụ thuộc vào máy cá nhân của một thành viên.

C. Load và kiểm tra RDF graph
Kiểm tra:
số triples;
graph load thành công;
namespace;
query đơn giản;
query với datatype;
query với language tags.

D. Implement 10 SPARQL queries
Mỗi competency question có một file:
sparql/CQ01.rq
sparql/CQ02.rq
...
sparql/CQ10.rq

Các query cần thể hiện đa dạng kỹ thuật:
basic graph pattern
FILTER
OPTIONAL
property path
GROUP BY
COUNT
ORDER BY
HAVING
owl:sameAs
SERVICE


E. Expected-result testing
Với mỗi query ghi:
Input
Expected output
Actual output
Pass / Fail

Phối hợp với Thành viên 1 để đánh giá competency questions.

F. Linked Data publication
Khảo sát Pubby hoặc giải pháp tương đương.
Mục tiêu:
Khi truy cập URI:
/resource/site/viwiki-123456

người dùng có thể xem thông tin resource.
Nếu có thể:
Browser → HTML
Machine client → RDF


G. SPARQL endpoint
Endpoint dự kiến:
https://<host>/sparql

Hoặc local demo:
http://localhost:3030/vietheritage/sparql


H. Federated query
Chuẩn bị CQ10 kết nối DBpedia.
Ví dụ:
SERVICE <https://dbpedia.org/sparql> {
    ...
}

Phải có local fallback nếu remote endpoint lỗi.

I. Deployment
Chuẩn bị một trong hai phương án:
Phương án A
Cloud deployment

nếu đủ thời gian.
Phương án B
Dockerized local deployment

đảm bảo demo ổn định.
Không để cloud deployment trở thành blocker.

J. Final demo environment
Chuẩn bị demo flow:
1. Open one heritage resource
2. Run basic semantic query
3. Run aggregate query
4. Show external links
5. Optional federated DBpedia query

Demo phải được rehearsal và chạy trong khoảng 3–4 phút.

5.3. Deliverables chính
deployment/
docker-compose.yml
sparql/CQ01.rq ... CQ10.rq
tests/competency-questions/
docs/deployment.md
docs/query-results.md


5.4. Phối hợp
Với Thành viên 1: competency questions và ontology reasoning.
Với Thành viên 3: RDF loading, URI, external linking.
Với Thành viên 2: kiểm tra kết quả query có khớp raw/processed data.

6. Công việc chung của cả nhóm
Ngoài phần phụ trách riêng, một số công việc phải có sự tham gia của cả 4 thành viên.
Công việc
M1
M2
M3
M4
Chốt scope
✓
✓
✓
✓
Competency questions
Lead
Review
Review
Review
Ontology
Lead
Review
Review
Review
Data schema
Review
Lead
Lead
Review
RDF mapping
Review
Review
Lead
Review
SPARQL
Review
Review
Review
Lead
External linking
Review
Support
Lead
Support
Testing
✓
✓
✓
✓
Report
✓
✓
✓
✓
Slides
✓
✓
✓
✓
Video
✓
✓
✓
✓
Presentation rehearsal
✓
✓
✓
✓


7. Phân công theo 7 tuần
Tuần 1 — Project Definition
Thành viên 1
xây terminology glossary;
draft 10 competency questions;
ontology sketch v0.1;
danh sách classes/properties ban đầu.
Thành viên 2
khảo sát Wikipedia;
tìm categories phù hợp;
lấy 20–30 sample entities;
kiểm tra MediaWiki API;
thống kê field có thể lấy được.
Thành viên 3
nghiên cứu URI strategy;
thiết kế RDF namespace;
đề xuất vocabulary reuse;
xác định external linking targets.
Thành viên 4
khảo sát Fuseki;
chạy Fuseki local;
thử load một RDF sample;
thiết kế cấu trúc thư mục SPARQL/deployment.
Output chung
Proposal v1
Ontology v0.1
10 competency questions
20–30 sample entities
GitHub repository


8. Tuần 2 — RDF Prototype
Thành viên 1
review ontology theo nội dung RDF;
xác định resource/literal;
datatype;
language tag.
Thành viên 2
hoàn thiện collector prototype;
raw JSON;
normalized JSON;
20–30 entities.
Thành viên 3
RDFLib generator;
RDF mapping;
sinh Turtle đầu tiên;
provenance prototype.
Thành viên 4
load Turtle vào Fuseki;
chạy query cơ bản;
kiểm tra endpoint.
Output chung
Wikipedia
    ↓
JSON
    ↓
RDF
    ↓
Fuseki
    ↓
SPARQL

phải chạy end-to-end.

9. Tuần 3 — RDFS
Thành viên 1
ontology v1;
class hierarchy;
domain/range;
property hierarchy;
labels/comments.
Thành viên 2
mở rộng collection lên 50–100 sites;
cải thiện normalization;
deduplication.
Thành viên 3
cập nhật RDF generator theo ontology v1;
vocabulary reuse;
provenance.
Thành viên 4
implement CQ1–CQ5;
expected-result testing;
Fuseki configuration.
Output chung
Ontology v1 frozen
50–100 sites
CQ1–CQ5 working


10. Tuần 4 — Linked Open Data
Thành viên 1
review ontology theo LOD best practices;
ontology documentation.
Thành viên 2
mở rộng dataset;
đảm bảo QID/source metadata đầy đủ.
Thành viên 3
Wikidata linking;
URI finalization;
dataset metadata;
4-star RDF.
Thành viên 4
SPARQL endpoint;
Pubby prototype;
resource dereferencing;
deployment prototype.
Output chung
4-star dataset
SPARQL endpoint
LOD publication prototype


11. Tuần 5 — OWL & Reasoning
Thành viên 1
OWL axioms;
disjointness;
inverse property;
reasoning demo.
Thành viên 2
hoàn thiện dataset gần mục tiêu;
kiểm tra problematic records.
Thành viên 3
cập nhật RDF theo ontology v2;
bắt đầu Silk/DBpedia linking.
Thành viên 4
CQ6–CQ8;
reasoning-related query;
regression test toàn bộ queries.
Output chung
Ontology v2
Reasoning demo
CQ1–CQ8 working


12. Tuần 6 — 5-star Completion
Thành viên 1
ontology consistency check;
review OWL2 nếu cần;
đóng băng ontology.
Thành viên 2
freeze processed dataset;
final data statistics.
Thành viên 3
Silk linking;
DBpedia links;
link verification;
100+ external links;
freeze RDF.
Thành viên 4
CQ9–CQ10;
federated query;
deployment stabilization;
complete query tests.
Output chung
Final ontology
Final RDF
5-star Linked Data
10 SPARQL queries
100+ external links


13. Tuần 7 — Finalization
Thành viên 1
Phụ trách chính phần report:
Ontology Design
Knowledge Modeling
Reasoning

Thành viên 2
Phụ trách chính phần report:
Data Sources
Data Collection
Normalization
Dataset Statistics

Thành viên 3
Phụ trách chính phần report:
RDF Transformation
URI Design
Linked Open Data
External Linking

Thành viên 4
Phụ trách chính phần report:
Triple Store
SPARQL
System Deployment
Evaluation

Cả nhóm:
review report;
thống nhất terminology;
làm slides;
record video;
rehearsal;
chuẩn bị backup demo.

14. Phân công viết báo cáo
Phần report
Người viết chính
Người review
Introduction
M1
M2, M3, M4
Problem & Scope
M1
M2
Competency Questions
M1
M4
Ontology Design
M1
M3
Data Sources
M2
M3
Collection & Normalization
M2
M3
RDF Transformation
M3
M1
URI & Vocabulary
M3
M1
External Linking
M3
M4
SPARQL Endpoint
M4
M3
SPARQL Queries
M4
M1
Evaluation
M4
M1, M2, M3
Conclusion
Cả nhóm
Cả nhóm

Một người nên được giao nhiệm vụ editor cuối, chịu trách nhiệm thống nhất cách viết, terminology, hình ảnh, numbering và references trước khi nộp.

15. Phân công slide và thuyết trình
Có thể chia phần trình bày như sau:
Người
Nội dung
Thời lượng
M1
Problem, objectives, scope, competency questions
3 phút
M1 hoặc M2
Ontology & reasoning
3 phút
M2 + M3
Data pipeline, RDF, 5-star LOD, linking
3 phút
M4
SPARQL + technical demo
4 phút
Cả nhóm
Evaluation + conclusion + Q&A
2 phút

Không bắt buộc mỗi người phải nói thời lượng hoàn toàn bằng nhau. Quan trọng hơn là mỗi thành viên trình bày phần mình hiểu sâu nhất.

16. Phân công video 3–5 phút
Video có thể chia thành:
0:00–0:30
Problem + project overview
→ M1

0:30–1:20
Ontology
→ M1

1:20–2:00
Data collection
→ M2

2:00–2:50
RDF + external linking
→ M3

2:50–4:10
SPARQL demo
→ M4

4:10–4:30
Conclusion
→ cả nhóm hoặc M1

Một thành viên có kỹ năng editing tốt nhất chịu trách nhiệm ghép video cuối.

17. Quy tắc Git và quản lý công việc
Mỗi feature/task nên làm trên branch riêng, ví dụ:
feature/ontology-v1
feature/wiki-collector
feature/rdf-generator
feature/wikidata-linking
feature/fuseki
feature/sparql-cq01

Không commit trực tiếp vào main đối với thay đổi lớn.
Pull Request phải có ít nhất một người khác review với các phần quan trọng:
Ontology PR
→ M3 review

Data schema PR
→ M3 review

RDF mapping PR
→ M1 review

SPARQL PR
→ M1 review

Deployment PR
→ M3 review


18. Quy tắc họp nhóm
Nên có ít nhất 2 lần sync ngắn mỗi tuần.
Buổi đầu tuần
Mục tiêu:
Review milestone tuần trước
Chốt task tuần này
Xác định dependency/blocker

Buổi cuối tuần
Mục tiêu:
Demo phần đã làm
Merge integration
Test end-to-end
Chốt milestone

Không chỉ báo cáo bằng lời; mỗi thành viên nên demo artifact thực tế.

19. Definition of Done cho từng thành viên
Thành viên 1 hoàn thành khi
10 CQs ổn định
Ontology hoàn chỉnh
RDFS/OWL hợp lệ
Reasoning demo chạy được
Ontology documentation hoàn thiện

Thành viên 2 hoàn thành khi
Collector reproducible
Dataset sạch
150–250 sites mục tiêu
Provenance/source đầy đủ
Processed dataset freeze

Thành viên 3 hoàn thành khi
RDF generator chạy end-to-end
Turtle hợp lệ
URI ổn định
External vocabularies được reuse
100+ external links được xác thực

Thành viên 4 hoàn thành khi
Fuseki chạy ổn định
Final RDF load thành công
10 CQs có SPARQL query
Query tests pass
Demo/deployment hoạt động


20. Tiêu chí đảm bảo khối lượng công việc cân bằng
Không nên đánh giá khối lượng bằng số file hoặc số dòng code.
Bốn mảng có dạng công việc khác nhau:
M1 → Modeling-heavy
M2 → Data-heavy
M3 → Integration-heavy
M4 → Query/Infrastructure-heavy

Do đó cần đánh giá theo responsibility + deliverables + integration dependency, không phải số lượng code.
Trong hai tuần cuối, thành viên nào hoàn thiện mảng chính sớm phải hỗ trợ các phần đang chậm, đặc biệt:
data cleaning
link verification
query testing
documentation
report
presentation


21. Ma trận trách nhiệm tổng hợp
Ký hiệu:
P = Phụ trách chính
S = Hỗ trợ / Review

Hạng mục
M1
M2
M3
M4
Scope
P
S
S
S
Competency Questions
P
S
S
S
Ontology
P
S
S
S
RDFS
P


S


OWL/OWL2
P


S
S
Reasoning
P


S
S
Data source
S
P
S


Collector


P
S


Cleaning
S
P
S


Normalization
S
P
S


RDF Mapping
S
S
P
S
RDF Generation
S
S
P
S
URI Design
S


P
S
Provenance RDF
S
S
P


Wikidata Linking


S
P
S
DBpedia Linking




P
S
Silk Framework




P
S
Fuseki




S
P
SPARQL
S


S
P
CQ Testing
S
S
S
P
Deployment




S
P
Report
P
P
P
P
Slides
P
S
S
S
Video
S
S
S
P/S
Presentation
P
P
P
P


22. Mục tiêu chung cuối cùng
Dù phân chia theo 4 vai trò, sản phẩm cuối cùng phải là một pipeline thống nhất:
                M1
         Ontology & Semantics
                 │
                 ▼
M2 ───────► Data Model ◄─────── M3
Data                           RDF
Collection                    Linking
                 │
                 ▼
                M4
       Fuseki + SPARQL + Demo

Không thành viên nào chỉ chịu trách nhiệm một file hoặc một công đoạn biệt lập.
Đến cuối dự án, cả bốn thành viên đều phải có khả năng giải thích được:
Dữ liệu lấy từ đâu?
        ↓
Dữ liệu được chuẩn hóa thế nào?
        ↓
Ontology biểu diễn điều gì?
        ↓
RDF triples được sinh như thế nào?
        ↓
Vì sao dataset đạt 4-star?
        ↓
External linking giúp đạt 5-star ra sao?
        ↓
SPARQL trả lời competency questions như thế nào?
        ↓
OWL reasoning tạo thêm tri thức gì?

Đây cũng chính là luồng mà nhóm nên sử dụng để kể câu chuyện của VietHeritageLOD trong buổi capstone presentation.

