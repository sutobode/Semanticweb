# Knowledge Graphs — Tài liệu tham chiếu

> Tài liệu này được tổng hợp từ các slide môn **IE650 Knowledge Graphs** trong thư mục `Course`. Dùng như một checklist và sổ tay khi làm bài tập/project. Khi triển khai thực tế, luôn kiểm tra lại version của vocabulary, reasoner, triple store và endpoint đang sử dụng.

## Mục lục

1. [Lộ trình môn học](#1-lộ-trình-môn-học)
2. [Tư duy cốt lõi](#2-tư-duy-cốt-lõi)
3. [RDF](#3-rdf)
4. [RDFS](#4-rdfs)
5. [OWL và OWL 2](#5-owl-và-owl-2)
6. [Reasoning và entailment](#6-reasoning-và-entailment)
7. [SPARQL](#7-sparql)
8. [Linked Open Data](#8-linked-open-data)
9. [Lập trình với Jena và RDFLib](#9-lập-trình-với-jena-và-rdflib)
10. [Ontology engineering](#10-ontology-engineering)
11. [RDF*, SPARQL*, LPG và Cypher](#11-rdf-sparql-lpg-và-cypher)
12. [Tích hợp dữ liệu và ứng dụng](#12-tích-hợp-dữ-liệu-và-ứng-dụng)
13. [Template project](#13-template-project)
14. [Checklist kiểm tra](#14-checklist-kiểm-tra)
15. [Lỗi thường gặp](#15-lỗi-thường-gặp)
16. [Cheat sheet nhanh](#16-cheat-sheet-nhanh)

---

## 1. Lộ trình môn học

```text
Semantic Web
    ↓
URI / XML / interoperability
    ↓
RDF: biểu diễn fact bằng triple
    ↓
RDFS: class, property, schema, domain/range
    ↓
OWL: ontology giàu biểu đạt và ràng buộc
    ↓
Reasoning: suy ra fact mới hoặc kiểm tra nhất quán
    ↓
SPARQL: truy vấn và biến đổi RDF graph
    ↓
LOD: xuất bản và liên kết dataset trên Web
    ↓
Ontology Engineering: thiết kế ontology có phương pháp
    ↓
Ứng dụng: public KG, data integration, LPG, mashup
```

### Mục tiêu sau khi học

Có thể:

- Mô hình hóa domain thành RDF graph.
- Thiết kế vocabulary/ontology bằng RDFS hoặc OWL.
- Viết và kiểm tra truy vấn SPARQL.
- Hiểu fact tường minh và fact suy diễn.
- Giải thích tác động của Open World Assumption (OWA) và Non-Unique Name Assumption (NUNA).
- Liên kết dữ liệu từ nhiều nguồn bằng URI và mapping.
- Chọn RDF/OWL/SPARQL hoặc LPG/Cypher phù hợp với bài toán.
- Đánh giá chất lượng ontology và Knowledge Graph.

---

## 2. Tư duy cốt lõi

### 2.1 Knowledge Graph là gì?

Knowledge Graph thường là một đồ thị có hướng, có nhãn và không đồng nhất:

- **Node/resource**: người, tổ chức, thành phố, tài liệu, sản phẩm…
- **Edge/property**: `worksFor`, `locatedIn`, `authorOf`…
- **Class/type**: `Person`, `City`, `Publication`…
- **Schema/ontology**: mô tả các class, property và ràng buộc.

Ví dụ:

```text
Heiko ──worksFor──> UniversityOfMannheim
```

### 2.2 “Things, not strings”

Không chỉ lưu chuỗi `"Mannheim"`, hãy định danh thực thể:

```turtle
ex:Heiko ex:worksFor ex:UniversityOfMannheim .
ex:UniversityOfMannheim a ex:University .
```

URI giúp phân biệt thực thể và nối dữ liệu giữa các nguồn.

### 2.3 OWA — Open World Assumption

> Không biết một fact không có nghĩa là fact đó sai.

Nếu biết:

```turtle
ex:Peter ex:hasChild ex:Julia, ex:Mary .
```

Không được kết luận Peter chỉ có hai người con. Có thể còn dữ liệu chưa được công bố.

Hệ quả:

- Không dùng thiếu dữ liệu để suy ra phủ định.
- `ASK` trả về `false` chỉ có nghĩa là không tìm thấy pattern phù hợp trong dữ liệu/reasoning hiện tại.
- Nếu cần “đây là toàn bộ danh sách”, phải mô hình hóa closed set rõ ràng, ví dụ bằng `owl:oneOf`, hoặc dùng validation riêng.

### 2.4 NUNA — Non-Unique Name Assumption

> Hai URI khác nhau không mặc nhiên là hai thực thể khác nhau.

```turtle
ex:Munich ex:capitalOf ex:Bavaria .
ex:Muenchen ex:capitalOf ex:Bayern .
```

Không thể tự động kết luận `ex:Munich` khác `ex:Muenchen`.

Dùng khi có đủ bằng chứng:

```turtle
ex:Munich owl:sameAs ex:Muenchen .
```

Hoặc:

```turtle
ex:Munich owl:differentFrom ex:Hamburg .
```

### 2.5 AAA — Anybody can say Anything about Anything

Một nguồn có thể bổ sung thông tin về resource do nguồn khác định nghĩa. Vì vậy:

- Không nên thiết kế ontology quá độc quyền cho một ngữ cảnh.
- Cần dùng namespace rõ ràng.
- Cần ghi provenance và source của assertion.

---

## 3. RDF

### 3.1 Triple

RDF biểu diễn fact bằng:

```text
Subject — Predicate — Object
```

Ví dụ:

```turtle
@prefix ex: <http://example.org/> .

ex:Heiko ex:worksFor ex:UniversityOfMannheim .
```

Đọc là: `Heiko worksFor UniversityOfMannheim`.

### 3.2 Resource và literal

| Thành phần | Ý nghĩa | Có thể làm subject? | Có thể làm object? |
|---|---|---:|---:|
| URI resource | Định danh thực thể | Có | Có |
| Blank node | Thực thể không có URI công khai | Có | Có |
| Literal | Giá trị nguyên tử | Không | Có |

Ví dụ:

```turtle
ex:Munich ex:name "München"@de .
ex:Munich ex:name "Munich"@en .
ex:Munich ex:population "1356594"^^xsd:integer .
ex:Munich ex:foundingDate "1158-01-01"^^xsd:date .
```

Một literal có thể có:

- Datatype: `^^xsd:integer`, `^^xsd:date`, `^^xsd:boolean`…
- Language tag: `@en`, `@vi`, `@de`…
- Không đồng thời có cả datatype và language tag.

> Không giả định mọi chuỗi đều tự động có datatype `xsd:string`; hãy kiểm tra dữ liệu thực tế và datatype của endpoint.

### 3.3 `rdf:type` và `a`

```turtle
ex:Heiko rdf:type ex:Person .
```

Turtle shorthand:

```turtle
ex:Heiko a ex:Person .
```

### 3.4 Namespace và prefix

Luôn khai báo prefix ở đầu file:

```turtle
@prefix ex:   <http://example.org/> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix dct:  <http://purl.org/dc/terms/> .
```

### 3.5 Turtle shorthand

```turtle
@prefix ex: <http://example.org/> .

ex:Book1
    a ex:Book ;
    ex:title "Knowledge Graphs"@en ;
    ex:author ex:Author1, ex:Author2 .
```

Quy tắc:

- Dấu `.` kết thúc một subject.
- Dấu `;` nối nhiều predicate của cùng subject.
- Dấu `,` nối nhiều object của cùng predicate.
- Literal dạng string phải đặt trong dấu nháy.
- URI đầy đủ có thể đặt trong `<...>`.

### 3.6 Blank node

Dùng khi không cần URI định danh công khai:

```turtle
ex:Recipe1 ex:hasIngredient [
    ex:ingredient ex:Sugar ;
    ex:amount [
        ex:value "100"^^xsd:integer ;
        ex:unit ex:Gram
    ]
] .
```

Blank node phù hợp cho:

- Địa chỉ trung gian.
- Thực thể phụ không cần liên kết toàn cục.
- Quan hệ nhiều ngôi/n-ary relation.
- Restriction trong OWL.

### 3.7 Quan hệ nhiều ngôi

RDF predicate là quan hệ hai ngôi. Với thông tin như:

```text
hasIngredient(Recipe, Sugar, 100g)
```

dùng node trung gian:

```turtle
ex:Recipe1 ex:hasIngredient [
    ex:ingredient ex:Sugar ;
    ex:amount "100g"
] .
```

### 3.8 Reification

Reification là mô hình hóa statement như một resource để nói về statement đó:

```turtle
ex:statement1
    a rdf:Statement ;
    rdf:subject ex:Rome ;
    rdf:predicate ex:capitalOf ;
    rdf:object ex:Spain .

ex:Peter ex:says ex:statement1 .
```

Hạn chế: verbose và khó query. Với annotation trên triple, cân nhắc RDF* hoặc mô hình n-ary rõ nghĩa.

### 3.9 RDF serialization

Các định dạng cần biết:

- **Turtle**: dễ viết và đọc.
- **N-Triples**: mỗi dòng một triple, phù hợp xử lý đơn giản.
- **RDF/XML**: XML-based, verbose.
- **JSON-LD**: phù hợp ứng dụng JSON/Web.
- **TriG/N-Quads**: hỗ trợ named graph.
- **RDFa/Microdata**: nhúng structured data vào HTML.

---

## 4. RDFS

RDFS dùng để mô tả schema/vocabulary cho RDF graph.

### 4.1 Class và subclass

```turtle
ex:Person a rdfs:Class .
ex:Student a rdfs:Class ;
    rdfs:subClassOf ex:Person .
```

Suy luận:

```text
Student(x) ⇒ Person(x)
```

### 4.2 Property và subproperty

```turtle
ex:capitalOf a rdf:Property .
ex:locatedIn a rdf:Property .
ex:capitalOf rdfs:subPropertyOf ex:locatedIn .
```

Nếu:

```turtle
ex:Madrid ex:capitalOf ex:Spain .
```

suy ra:

```turtle
ex:Madrid ex:locatedIn ex:Spain .
```

### 4.3 Domain và range

```turtle
ex:capitalOf
    rdfs:domain ex:City ;
    rdfs:range ex:Country .
```

Với:

```turtle
ex:Madrid ex:capitalOf ex:Spain .
```

suy ra:

```turtle
ex:Madrid a ex:City .
ex:Spain a ex:Country .
```

> `rdfs:domain` và `rdfs:range` là quy tắc suy luận toàn cục cho property, không chỉ là gợi ý kiểm tra dữ liệu.

### 4.4 Label, comment, seeAlso

```turtle
ex:Country
    a rdfs:Class ;
    rdfs:label "Country"@en ;
    rdfs:label "Quốc gia"@vi ;
    rdfs:comment "A political entity."@en ;
    rdfs:seeAlso <https://example.org/country-info> .
```

### 4.5 T-Box và A-Box

**T-Box** — schema/terminology:

```turtle
ex:City a rdfs:Class .
ex:capitalOf rdfs:domain ex:City .
```

**A-Box** — assertion/instance data:

```turtle
ex:Madrid a ex:City .
ex:Madrid ex:capitalOf ex:Spain .
```

### 4.6 RDFS reasoning cơ bản

Các quy tắc thường gặp:

```text
p rdfs:subPropertyOf q ∧ s p o
    ⇒ s q o

p rdfs:domain C ∧ s p o
    ⇒ s rdf:type C

p rdfs:range C ∧ s p o
    ⇒ o rdf:type C

x rdf:type C1 ∧ C1 rdfs:subClassOf C2
    ⇒ x rdf:type C2
```

### 4.7 Giới hạn của RDFS

RDFS không phù hợp để biểu diễn trực tiếp:

- Exactly one / at most one.
- Property functional/inverse functional.
- Class disjointness.
- Complement/negation.
- Restriction cục bộ theo từng class.
- Các biểu thức logic phức tạp.

Dùng OWL khi cần các khả năng trên.

---

## 5. OWL và OWL 2

### 5.1 Khi nào dùng OWL?

Dùng OWL khi cần:

- Mô tả class bằng restriction.
- Kiểm tra sự nhất quán.
- Khẳng định class disjoint/equivalent.
- Mô hình hóa cardinality.
- Mô tả đặc tính của property.
- Suy luận logic phức tạp hơn RDFS.

### 5.2 Các flavor/profile

- **OWL Lite**: hạn chế, reasoning đơn giản hơn.
- **OWL DL**: dựa trên Description Logic, decidable.
- **OWL Full**: tự do và biểu đạt mạnh hơn, reasoning khó hơn.
- **OWL 2 EL**: reasoning nhanh cho ontology lớn.
- **OWL 2 QL**: query answering gần mô hình relational database.
- **OWL 2 RL**: phù hợp triển khai dạng rule.

### 5.3 `owl:Class`, `owl:Thing`, `owl:Nothing`

```turtle
ex:Person a owl:Class .
```

- `owl:Thing`: superclass tổng quát.
- `owl:Nothing`: class rỗng.

### 5.4 ObjectProperty và DatatypeProperty

```turtle
ex:knows a owl:ObjectProperty .
ex:hasName a owl:DatatypeProperty .
```

- `ObjectProperty`: object là resource.
- `DatatypeProperty`: object là literal.

### 5.5 Equivalent và disjoint

```turtle
ex:Lecturer owl:equivalentClass ex:UniversityTeacher .
ex:teaches owl:equivalentProperty ex:lecturerFor .
ex:City owl:disjointWith ex:Country .
```

### 5.6 `owl:sameAs` và `owl:differentFrom`

```turtle
ex:Muenchen owl:sameAs ex:Munich .
ex:Munich owl:differentFrom ex:Hamburg .
```

Cẩn thận với `owl:sameAs`: nó mạnh hơn việc nói “có liên quan” hoặc “cùng trang Web”. Nếu hai resource chỉ liên quan, dùng property phù hợp như `rdfs:seeAlso` hoặc `foaf:homepage`.

### 5.7 Đặc tính của property

#### Symmetric

```turtle
ex:sitsOppositeOf a owl:SymmetricProperty .
```

```text
A sitsOppositeOf B ⇒ B sitsOppositeOf A
```

#### Inverse

```turtle
ex:supervises owl:inverseOf ex:supervisedBy .
```

#### Transitive

```turtle
ex:hasAncestor a owl:TransitiveProperty .
```

#### Reflexive, irreflexive, asymmetric — OWL 2

```turtle
ex:relativeOf a owl:ReflexiveProperty .
ex:parentOf a owl:IrreflexiveProperty .
ex:tallerThan a owl:AsymmetricProperty .
```

Chỉ dùng các đặc tính phù hợp với semantics thực tế. Đặc biệt, không gán `TransitiveProperty`, `SymmetricProperty` hoặc `InverseFunctionalProperty` một cách tùy tiện.

#### Functional

```turtle
ex:hasCapital a owl:FunctionalProperty .
```

Mỗi subject có tối đa một object khác nhau về mặt logic. Nếu dữ liệu khai báo hai object, reasoner có thể suy ra chúng là `owl:sameAs`.

#### Inverse functional

```turtle
ex:hasISBN a owl:InverseFunctionalProperty .
```

Dùng khi giá trị thực sự hoạt động như định danh duy nhất. Không nên dùng nếu dữ liệu không bảo đảm tính duy nhất.

### 5.8 Restrictions

#### `allValuesFrom`

Mọi giá trị của property phải thuộc class:

```turtle
ex:VeganRecipe rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:hasIngredient ;
    owl:allValuesFrom ex:Vegetable
] .
```

#### `someValuesFrom`

Phải tồn tại ít nhất một giá trị thuộc class:

```turtle
ex:BallSport rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:requires ;
    owl:someValuesFrom ex:Ball
] .
```

#### Cardinality

```turtle
ex:Human rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:hasMother ;
    owl:cardinality 1
] .
```

Các dạng:

- `owl:minCardinality`: tối thiểu `n`.
- `owl:maxCardinality`: tối đa `n`.
- `owl:cardinality`: chính xác `n`.

OWL 2 có qualified cardinality, ví dụ “đọc ít nhất 1000 cuốn sách”:

```turtle
ex:LiteratePerson rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:hasRead ;
    owl:minQualifiedCardinality 1000 ;
    owl:onClass ex:Book
] .
```

#### `hasValue`

```turtle
ex:AfricanCountry rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:locatedOnContinent ;
    owl:hasValue ex:Africa
] .
```

### 5.9 Subclass và equivalentClass khác nhau thế nào?

```turtle
ex:BallSport rdfs:subClassOf [ restriction ] .
```

Chỉ nói:

```text
BallSport ⊆ các thực thể thỏa restriction
```

Còn:

```turtle
ex:BallSport owl:equivalentClass [ restriction ] .
```

nói hai chiều:

```text
BallSport ⇔ các thực thể thỏa restriction
```

Với `equivalentClass`, một instance thỏa restriction có thể được suy ra là `BallSport`.

### 5.10 Set operators

```turtle
ex:FacultyMember owl:unionOf (ex:Student ex:Professor) .
ex:LivingThing owl:complementOf ex:InanimateThing .
ex:EdibleMushroom owl:disjointWith ex:PoisonousMushroom .
```

OWL 2 hỗ trợ disjoint union:

```turtle
ex:Wine owl:disjointUnionOf (
    ex:RedWine
    ex:RoseWine
    ex:WhiteWine
) .
```

### 5.11 Property chain — OWL 2

```turtle
ex:hasGrandparent owl:propertyChainAxiom (
    ex:hasParent
    ex:hasParent
) .
```

Suy luận:

```text
hasParent(X,Y) ∧ hasParent(Y,Z)
    ⇒ hasGrandparent(X,Z)
```

### 5.12 OWL không giải quyết mọi thứ

Một số luật dạng điều kiện cần rule language:

```text
daughterOf(X,Y) ← childOf(X,Y) ∧ Woman(X)
```

Có thể cần:

- SWRL.
- RIF.
- Rule engine riêng.
- SHACL cho validation.
- Logic ứng dụng trong code.

---

## 6. Reasoning và entailment

### 6.1 Fact tường minh và fact suy diễn

Fact tường minh:

```turtle
ex:Madrid ex:capitalOf ex:Spain .
```

Fact suy diễn từ RDFS:

```turtle
ex:Madrid a ex:City .
ex:Spain a ex:Country .
ex:Madrid ex:locatedIn ex:Spain .
```

Luôn phân biệt:

- Triple có trong file/dataset ban đầu.
- Triple do reasoner tạo ra.
- Triple chỉ đúng theo ontology nhưng chưa được materialize.

### 6.2 Forward chaining

Phù hợp với nhiều rule RDFS/RL:

```text
E := graph ban đầu
Lặp:
    áp dụng các rule lên E
    thêm consequence chưa có vào E
Dừng khi không thêm được fact mới
```

### 6.3 Tableau reasoning

OWL DL thường dùng tableau:

- Mở rộng các biểu thức logic.
- Tách nhánh với phép OR/union.
- Đóng nhánh khi có mâu thuẫn như `Person(x)` và `¬Person(x)`.
- Ontology consistent nếu còn ít nhất một nhánh không đóng.

### 6.4 Các câu hỏi reasoning thường gặp

- `C rdfs:subClassOf D` có suy ra được không?
- Hai class có equivalent không?
- Hai class có disjoint không?
- Class có thể có instance không?
- Instance `x` có thuộc class `C` không?
- Có những instance nào của `C`?
- Graph/ontology có mâu thuẫn không?

### 6.5 Reasoning không phải validation

- **Reasoning**: suy ra fact mới theo semantics.
- **Validation**: kiểm tra dữ liệu có tuân thủ constraint hay không.

Do OWA, OWL không mặc nhiên là ngôn ngữ validation kiểu database. Nếu cần báo lỗi dữ liệu thiếu/sai, cân nhắc SHACL hoặc quy tắc kiểm tra riêng.

---

## 7. SPARQL

### 7.1 Basic SELECT

```sparql
PREFIX ex: <http://example.org/>

SELECT ?person ?name
WHERE {
    ?person a ex:Person ;
            ex:name ?name .
}
```

### 7.2 Graph pattern nối tiếp

```sparql
SELECT ?person ?city
WHERE {
    ?person a ex:Person .
    ?person ex:livesIn ?city .
    ?city a ex:City .
}
```

Các pattern trong cùng một group mặc định là phép AND/join.

### 7.3 Biến không mặc nhiên khác nhau

```sparql
SELECT ?p ?c1 ?c2
WHERE {
    ?p ex:hasChild ?c1, ?c2 .
}
```

`?c1` và `?c2` có thể cùng bind vào một resource. Nếu cần hai binding khác nhau về mặt RDF term:

```sparql
SELECT ?p ?c1 ?c2
WHERE {
    ?p ex:hasChild ?c1, ?c2 .
    FILTER(?c1 != ?c2)
}
```

Nhưng điều này vẫn không vượt qua NUNA: hai URI khác nhau chưa chắc là hai người khác nhau.

### 7.4 FILTER

```sparql
SELECT ?person ?age
WHERE {
    ?person ex:age ?age .
    FILTER(?age >= 18 && ?age < 65)
}
```

Toán tử:

```text
=  !=  <  >  <=  >=
&& || !
```

### 7.5 String, datatype và language tag

```sparql
# Literal không có language tag
?country ex:name "Germany" .

# Literal có language tag
?country ex:name "Germany"@en .

# Datatype
?person ex:age 42 .
```

`"Germany"` và `"Germany"@en` là hai literal khác nhau.

Các hàm hữu ích:

```sparql
FILTER(regex(?name, "^Ann$"))
FILTER(str(?label) = "Tyskland")
FILTER(isURI(?x))
FILTER(isBLANK(?x))
FILTER(isLITERAL(?x))
FILTER(DATATYPE(?x) = xsd:string)
FILTER(LANG(?x) = "en")
```

### 7.6 UNION

```sparql
SELECT ?person ?phone
WHERE {
    {
        ?person ex:privatePhone ?phone
    }
    UNION
    {
        ?person ex:workPhone ?phone
    }
}
```

### 7.7 OPTIONAL

```sparql
SELECT ?person ?phone ?fax
WHERE {
    ?person ex:phone ?phone .
    OPTIONAL {
        ?person ex:fax ?fax .
    }
}
```

Biến `?fax` có thể không bound.

### 7.8 DISTINCT, ORDER BY, LIMIT, OFFSET

```sparql
SELECT DISTINCT ?city ?population
WHERE {
    ?city ex:population ?population .
}
ORDER BY DESC(?population)
LIMIT 100
OFFSET 0
```

Nên dùng `ORDER BY` nếu kết quả cần phân trang ổn định.

### 7.9 ASK

```sparql
ASK {
    ?person ex:hasSibling ?sibling .
}
```

Kết quả là boolean. `false` không có nghĩa là fact bị phủ định trong OWA.

### 7.10 DESCRIBE

```sparql
DESCRIBE <http://dbpedia.org/resource/Berlin>
```

Kết quả DESCRIBE có thể phụ thuộc implementation của endpoint.

### 7.11 CONSTRUCT

```sparql
CONSTRUCT {
    ?person ex:isInCountry ?country .
}
WHERE {
    ?person ex:livesIn ?city .
    ?city ex:locatedIn ?country .
}
```

CONSTRUCT trả về một RDF graph, phù hợp để:

- Tạo graph dẫn xuất.
- Chuyển đổi vocabulary.
- Trích xuất subgraph.
- Chuẩn bị dữ liệu cho ứng dụng khác.

### 7.12 Query có reasoning

Mặc định, query thường chỉ nhìn thấy triple đã có trong active graph. Nếu cần fact suy diễn:

**Cách 1: reasoning trước rồi query**

```text
schema + data → reasoning model → SPARQL query
```

**Cách 2: query explicit theo hierarchy**

```sparql
SELECT ?x
WHERE {
    ?x a ?type .
    ?type rdfs:subClassOf* ex:Building .
}
```

`rdfs:subClassOf*` là property path và tùy endpoint/configuration có thể được hỗ trợ.

### 7.13 Federation

```sparql
SELECT ?name ?lat ?long
WHERE {
    ?person a foaf:Person ;
            foaf:name ?name ;
            foaf:based_near ?city .
    ?city owl:sameAs ?remoteCity .

    SERVICE <https://example.org/sparql> {
        ?remoteCity geo:lat ?lat ;
                    geo:long ?long .
    }
}
```

Cần kiểm tra:

- Endpoint có cho phép `SERVICE` không.
- Prefix và URI mapping có đúng không.
- Timeout, rate limit và số lượng request.
- Kết quả có ổn định không.

### 7.14 Tối ưu SPARQL

- Lọc sớm bằng pattern cụ thể.
- Dùng `LIMIT` trong lúc thử nghiệm.
- Tránh `?s ?p ?o` trên dataset lớn nếu không cần.
- Chỉ `SELECT` biến cần dùng.
- Dùng `VALUES` để giới hạn input.
- Dùng `FILTER` sau khi có pattern cần thiết.
- Kiểm tra query plan nếu endpoint hỗ trợ.
- Cẩn thận với `OPTIONAL`, `UNION`, regex và federation.

---

## 8. Linked Open Data

### 8.1 Bốn nguyên tắc LOD

1. Dùng URI để định danh sự vật.
2. Dùng HTTP URI có thể dereference.
3. Cung cấp thông tin hữu ích ở format chuẩn khi truy cập URI.
4. Liên kết tới các URI/dataset khác.

### 8.2 Five Star Scheme

| Mức | Ý nghĩa |
|---|---|
| `*` | Trên Web, giấy phép mở |
| `**` | Có cấu trúc, máy đọc được |
| `***` | Format không độc quyền |
| `****` | Chuẩn mở của W3C |
| `*****` | Liên kết tới dataset khác |

### 8.3 `owl:sameAs` dùng cẩn thận

Dùng khi hai URI cùng định danh **một thực thể**:

```turtle
my:UK owl:sameAs dbpedia:United_Kingdom .
```

Không dùng thay cho:

- “Có liên quan đến”.
- “Trang chủ của”.
- “Cùng tên”.
- “Cùng công ty nhưng khác chi nhánh”.
- “Tòa nhà và tổ chức ở trong tòa nhà”.

Cân nhắc:

```turtle
resource rdfs:seeAlso otherResource .
resource foaf:homepage homepageURI .
```

### 8.4 Vocabulary phổ biến

- Dublin Core / DCTERMS: metadata.
- FOAF: Person, Organization, knows, homepage.
- WGS84: latitude, longitude, location.
- Schema.org: product, offer, person, organization, event, recipe.
- SDMX/Data Cube: dữ liệu thống kê.

### 8.5 Metadata và provenance

Nên ghi:

- Nguồn dữ liệu.
- Người/tổ chức tạo dữ liệu.
- Thời gian tạo/cập nhật.
- Quy trình biến đổi.
- License.
- Version dataset.
- Chất lượng và giới hạn.

Có thể dùng PROV-O hoặc vocabulary phù hợp.

---

## 9. Lập trình với Jena và RDFLib

### 9.1 Apache Jena — Java

Các khái niệm chính:

- `Model`: RDF graph.
- `Resource`: URI resource.
- `Property`: predicate.
- `Literal`: literal.
- `Statement`: triple.
- Iterator: duyệt dữ liệu lớn mà không nạp toàn bộ vào memory.

Ví dụ ý tưởng:

```java
Model model = ModelFactory.createDefaultModel();
model.read("data/example.ttl", "TURTLE");

Resource person = model.getResource("http://example.org/Heiko");
Property worksFor = model.createProperty("http://example.org/worksFor");

StmtIterator it = model.listStatements(person, worksFor, (RDFNode) null);
while (it.hasNext()) {
    Statement statement = it.next();
    System.out.println(statement.getObject());
}
```

Reasoning RDFS:

```java
Model schemaModel = ModelFactory.createDefaultModel();
schemaModel.read("data/schema.ttl", "TURTLE");

Model dataModel = ModelFactory.createDefaultModel();
dataModel.read("data/data.ttl", "TURTLE");

InfModel reasoningModel =
    ModelFactory.createRDFSModel(schemaModel, dataModel);
```

### 9.2 RDFLib — Python

```python
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS

EX = Namespace("http://example.org/")
g = Graph()

g.parse("data/example.ttl", format="turtle")

for s, p, o in g:
    print(s, p, o)
```

Thêm triple:

```python
g.add((EX.Munich, RDFS.label, Literal("Munich", lang="en")))
```

Tìm triple:

```python
for s, p, o in g.triples((None, RDF.type, EX.Person)):
    print(s)
```

Lấy value:

```python
value = g.value(EX.Munich, RDFS.label)
print(value)
```

Serialize:

```python
print(g.serialize(format="turtle"))
```

SPARQL:

```python
query = """
PREFIX ex: <http://example.org/>
SELECT ?person ?name
WHERE {
    ?person a ex:Person ;
            ex:name ?name .
}
"""

for row in g.query(query):
    print(row.person, row.name)
```

### 9.3 Lưu ý khi lập trình

- Không giả định mọi object là literal; kiểm tra node type.
- Không nạp toàn bộ dataset lớn vào list nếu có thể dùng iterator/stream.
- Kiểm tra encoding UTF-8.
- Xác định format khi parse.
- Không tin rằng endpoint luôn trả về thứ tự cố định.
- Ghi log query, endpoint, thời gian chạy và số kết quả.
- Tách schema, data, inferred graph và validation report nếu có thể.

---

## 10. Ontology Engineering

### 10.1 Quy trình đề xuất

1. Xác định mục tiêu và người dùng ontology.
2. Xác định phạm vi domain và ngoài phạm vi.
3. Viết competency questions.
4. Thu thập thuật ngữ và glossary.
5. Phân biệt class, instance và property.
6. Xây dựng taxonomy.
7. Định nghĩa object/data properties.
8. Định nghĩa domain/range.
9. Bổ sung restriction cần thiết.
10. Chọn vocabulary có sẵn để tái sử dụng.
11. Tạo dữ liệu mẫu.
12. Chạy reasoner và validation.
13. Viết query kiểm thử.
14. Đánh giá kết quả, sửa ontology và ghi lại quyết định.

### 10.2 Competency questions

Ví dụ domain thư viện:

- Có những cuốn sách nào do một tác giả viết?
- Những tác giả nào viết sách thuộc một thể loại?
- Cuốn sách nào được xuất bản trong một khoảng thời gian?
- Một người đã mượn sách nào?

Mỗi câu nên có:

- Câu hỏi tự nhiên.
- Query tương ứng.
- Kết quả mong đợi.
- Dataset test nhỏ.

### 10.3 Naming convention

Khuyến nghị:

```text
Class:    Person, University, ResearchPaper
Property: worksFor, hasAuthor, publishedIn
Instance: Alice, UniversityOfMannheim
```

Quy tắc:

- Class dùng danh từ số ít, viết hoa.
- Property viết thường đầu, hướng đọc rõ ràng.
- Không dùng tên mơ hồ như `relatedTo` nếu có thể cụ thể hơn.
- Cấp label đa ngôn ngữ.
- URI nên ổn định và có namespace riêng.

### 10.4 Phân biệt class và instance

Hỏi:

- “Mọi X đều là Y” có hợp lý không?
- Có thể có instance của X không?
- Câu “A là một X” có tự nhiên không?

Ví dụ:

```text
:Goethe a :Writer .
```

thường hợp lý hơn:

```turtle
:Goethe rdfs:subClassOf :Writer .
```

### 10.5 Rigidity, identity, unity

Trước khi dùng `rdfs:subClassOf`, kiểm tra:

- Class cha/con có cùng bản chất ổn định không?
- Hai class có cùng tiêu chí identity không?
- Class có cùng đặc tính whole/part không?
- Có nên dùng một property như `hasRole`, `hasDuration`, `contains` thay cho subclass không?

### 10.6 Design pattern cho quan hệ nhiều ngôi

Với quan hệ `r(X,Y,Z)`:

```turtle
ex:R a owl:Class .
ex:hasR a owl:ObjectProperty .
ex:hasComp1 a owl:ObjectProperty .
ex:hasComp2 a owl:ObjectProperty .

ex:X ex:hasR [
    a ex:R ;
    ex:hasComp1 ex:Y ;
    ex:hasComp2 ex:Z
] .
```

Dùng pattern này khi quan hệ có thuộc tính riêng như thời gian, nguồn, vai trò, mức độ, đơn vị.

### 10.7 Anti-pattern: exclusivity

Không nên mô hình hóa một khái niệm chỉ đúng trong một ngữ cảnh hẹp.

Ví dụ, nếu định nghĩa:

```text
CoastalCity ≡ City ∩ bordering some Ocean
```

tốt hơn là biểu diễn rõ intersection thay vì ngầm coi mọi thứ bordering Ocean đều là City. Một Country cũng có thể bordering Ocean.

### 10.8 Tái sử dụng ontology

Trước khi tạo class/property mới:

- Tìm vocabulary phổ biến.
- Kiểm tra nghĩa và domain/range.
- Kiểm tra license và trạng thái bảo trì.
- Dùng `rdfs:subClassOf`, `rdfs:subPropertyOf`, `owl:equivalentClass` hoặc mapping phù hợp.
- Không ép hai vocabulary là equivalent chỉ vì tên giống nhau.

---

## 11. RDF*, SPARQL*, LPG và Cypher

### 11.1 Khi RDF trở nên verbose

RDF thuần thường cần node trung gian để mô tả thuộc tính của một quan hệ:

```text
Dirk --careerStation--> CareerStation1
CareerStation1 --team--> Team
CareerStation1 --startYear--> 1994
CareerStation1 --endYear--> 1998
```

### 11.2 RDF*

```turtle
<<ex:Dirk ex:team ex:DJKWuerzburg>>
    ex:startYear 1994 ;
    ex:endYear 1998 .
```

Hoặc cú pháp annotation ngắn tùy implementation:

```turtle
ex:Dirk ex:team ex:DJKWuerzburg
    {| ex:startYear 1994 ; ex:endYear 1998 |} .
```

Phân biệt:

- **Quoted triple**: được nhắc đến nhưng không mặc nhiên asserted.
- **Asserted triple**: là fact trong graph.

RDF*/SPARQL* hỗ trợ không đồng nhất giữa các công cụ; cần kiểm tra implementation và version.

### 11.3 Labeled Property Graph

LPG có:

- Node với label.
- Node property key/value.
- Edge có type.
- Edge property key/value.

Ví dụ Cypher:

```cypher
CREATE (m:Movie {
    title: "The Matrix",
    released: 1999
})
CREATE (p:Person {
    name: "Hugo Weaving",
    born: 1960
})
CREATE (p)-[:ACTED_IN {roles: ["Agent Smith"]}]->(m)
```

### 11.4 Cypher pattern matching

```cypher
MATCH (n)
RETURN n
```

```cypher
MATCH (m:Movie {title: "The Matrix"})
RETURN m
```

```cypher
MATCH (m:Movie {title: "The Matrix"})
      <-[r:ACTED_IN]-(p:Person)
RETURN p, r
```

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= 1990 AND m.released < 2000
RETURN p, m
```

### 11.5 So sánh nhanh

| Khía cạnh | RDF/RDFS/OWL/SPARQL | LPG/Cypher |
|---|---|---|
| Semantics | Open-world, URI-centric | Thường closed-world hơn |
| Schema | Ontology và vocabulary | Label/type/property convention |
| Edge properties | RDF thuần cần pattern phụ; RDF* hỗ trợ | Tự nhiên |
| Reasoning | RDFS/OWL/rule | Thường cập nhật graph hoặc logic ứng dụng |
| Query | Triple/path pattern | Node-edge pattern |
| Interoperability | Mạnh với Web và LOD | Mạnh trong graph database/application |
| Phù hợp | Dữ liệu liên kết mở, semantic integration | Graph traversal, transaction, operational app |

Chọn công nghệ dựa trên yêu cầu, không dựa chỉ trên việc “graph nào nhanh hơn”.

---

## 12. Tích hợp dữ liệu và ứng dụng

### 12.1 Ba loại heterogeneity

1. **Syntactic heterogeneity**: CSV, JSON, XML, spreadsheet khác nhau.
2. **Semantic heterogeneity**: cùng khái niệm nhưng tên, URI, schema khác nhau.
3. **Access heterogeneity**: file dump, API, SPARQL endpoint, database, sensor khác nhau.

### 12.2 Pipeline tích hợp tổng quát

```text
Nguồn dữ liệu
    ↓
Phân tích schema và chất lượng
    ↓
Mapping sang RDF/vocabulary chung
    ↓
Chuẩn hóa URI, datatype, unit, time, location
    ↓
Entity matching / coreference
    ↓
Reasoning và validation
    ↓
SPARQL/API/application
```

### 12.3 Shared URI

Các dataset cùng dùng URI chung cho:

- Quốc gia/khu vực.
- Thời gian.
- Đơn vị đo.
- Chủ đề/chỉ số.
- Component của data cube.

Điều này giúp query rewriting và result integration dễ hơn.

### 12.4 Mapping

Có thể dùng:

- RML cho nguồn JSON/XML/CSV/spreadsheet.
- R2RML cho relational database.
- D2R hoặc virtual knowledge graph.
- Mapping thủ công.
- Entity linking/matching.

### 12.5 Virtual Knowledge Graph

Dữ liệu không nhất thiết phải được copy vào triple store. Một lớp mapping có thể cung cấp graph view trên database hiện có.

Ưu điểm:

- Dữ liệu gần real-time.
- Không duplicate toàn bộ dữ liệu.
- Có thể tích hợp nhiều nguồn.

Nhược điểm:

- Query phụ thuộc hệ thống nguồn.
- Performance và khả năng truy cập không ổn định.
- Mapping phải được bảo trì.

### 12.6 Provenance và quality

Mỗi nguồn nên có metadata:

- Nguồn gốc.
- Thời điểm cập nhật.
- Mapping version.
- Đơn vị đo.
- Độ tin cậy.
- License.
- Phạm vi bao phủ.
- Các giới hạn/ngoại lệ.

---

## 13. Template project

### 13.1 Cấu trúc thư mục đề xuất

```text
project/
├── README.md
├── ontology/
│   ├── domain.ttl
│   ├── constraints.ttl
│   └── mappings.ttl
├── data/
│   ├── raw/
│   ├── cleaned/
│   ├── instances.ttl
│   └── sample.ttl
├── queries/
│   ├── competency-questions.rq
│   ├── exploration.rq
│   └── reports.rq
├── validation/
│   ├── shapes.ttl
│   └── reports/
├── scripts/
│   ├── load_data.py
│   ├── transform.py
│   └── run_queries.py
├── tests/
│   ├── expected-results/
│   └── test_queries.py
└── docs/
    ├── modeling-decisions.md
    └── provenance.md
```

### 13.2 README tối thiểu

README nên trả lời:

- Project giải quyết bài toán gì?
- Domain và phạm vi là gì?
- Nguồn dữ liệu nào được dùng?
- License của dữ liệu là gì?
- Namespace chính là gì?
- Cách cài đặt/chạy project?
- Cách load ontology và data?
- Cách chạy reasoner?
- Cách chạy SPARQL query?
- Các competency questions là gì?
- Các giới hạn hiện tại?

### 13.3 Template modeling decision

```markdown
## Modeling decision: <Tên quyết định>

### Bối cảnh
Mô tả vấn đề cần mô hình hóa.

### Các phương án
1. ...
2. ...

### Quyết định
Chọn phương án ...

### Lý do
- ...
- ...

### Hệ quả
- ...

### Query/competency question bị ảnh hưởng
- ...
```

### 13.4 Template competency question

```markdown
## CQ-01: <Tên câu hỏi>

Câu hỏi tự nhiên:
> Những ... nào ...?

SPARQL:

```sparql
PREFIX ex: <http://example.org/>

SELECT ?x
WHERE {
    ...
}
```

Kết quả mong đợi:
- ...

Dataset test:
- ...
```

### 13.5 Template ontology tối thiểu

```turtle
@prefix ex:   <http://example.org/kg/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

ex:Ontology a owl:Ontology ;
    rdfs:label "Example Knowledge Graph Ontology"@en .

ex:Person a owl:Class .
ex:Organization a owl:Class .
ex:worksFor a owl:ObjectProperty ;
    rdfs:domain ex:Person ;
    rdfs:range ex:Organization .

ex:fullName a owl:DatatypeProperty ;
    rdfs:domain ex:Person ;
    rdfs:range xsd:string .
```

### 13.6 Template data

```turtle
@prefix ex: <http://example.org/kg/> .

ex:Alice a ex:Person ;
    ex:fullName "Alice"@en ;
    ex:worksFor ex:ExampleUniversity .

ex:ExampleUniversity a ex:Organization .
```

### 13.7 Template report

Báo cáo nên có:

1. Problem statement.
2. Domain và scope.
3. Data sources và license.
4. Ontology design.
5. URI/vocabulary strategy.
6. Mapping/transformation.
7. Reasoning strategy.
8. Competency questions và SPARQL.
9. Validation và quality evaluation.
10. Demo/application architecture.
11. Limitations.
12. Future work.

---

## 14. Checklist kiểm tra

### 14.1 Checklist RDF

- [ ] Mỗi fact có dạng subject-predicate-object hợp lệ.
- [ ] Subject là URI hoặc blank node, không phải literal.
- [ ] Predicate là URI.
- [ ] Literal có datatype/language tag đúng khi cần.
- [ ] URI resource không bị dùng lẫn với label người đọc.
- [ ] Namespace/prefix được khai báo rõ.
- [ ] Không dùng literal làm subject hoặc predicate.
- [ ] Quan hệ nhiều ngôi đã được mô hình hóa có chủ đích.
- [ ] Blank node chỉ dùng khi thực sự không cần URI công khai.

### 14.2 Checklist RDFS/OWL

- [ ] Class và instance được phân biệt.
- [ ] Property được phân loại object/data property nếu dùng OWL.
- [ ] Domain/range có ý nghĩa và không gây suy luận ngoài ý muốn.
- [ ] `subClassOf` dùng cho quan hệ “Every X is a Y”.
- [ ] `equivalentClass` chỉ dùng khi có quan hệ hai chiều.
- [ ] `sameAs` chỉ dùng khi hai URI cùng một entity.
- [ ] Functional/inverse functional property có cơ sở nghiệp vụ.
- [ ] Cardinality có phù hợp với OWA không.
- [ ] Có kiểm tra disjoint class nếu domain cần.
- [ ] Restriction là local cho class; range là global cho property.
- [ ] Đã chạy reasoner và xem inferred facts.
- [ ] Đã kiểm tra inconsistency.
- [ ] Không kỳ vọng OWL tự hoạt động như validation engine.

### 14.3 Checklist SPARQL

- [ ] Query có prefix đầy đủ.
- [ ] Pattern trong `WHERE` đúng hướng subject-predicate-object.
- [ ] Biết biến nào có thể unbound do `OPTIONAL`.
- [ ] Dùng `DISTINCT` khi cần loại binding trùng.
- [ ] Không nhầm binding khác nhau với entity khác nhau.
- [ ] Literal có language tag/datatype đúng.
- [ ] Có `ORDER BY` khi dùng phân trang.
- [ ] Không query `?s ?p ?o` trên graph lớn nếu không cần.
- [ ] Kiểm tra reasoning có được bật hay không.
- [ ] Kiểm tra active graph/default graph/named graph.
- [ ] Test query với dataset nhỏ trước.
- [ ] Kiểm tra timeout, endpoint limit và federation.

### 14.4 Checklist ontology engineering

- [ ] Đã xác định mục tiêu và scope.
- [ ] Đã viết competency questions.
- [ ] Có glossary/terminology.
- [ ] Có naming convention.
- [ ] Đã xem xét ontology/vocabulary có sẵn.
- [ ] Class hierarchy không chứa quan hệ vô lý.
- [ ] Đã kiểm tra rigidity, identity và unity.
- [ ] Không dùng subclass thay cho role/part/hasDuration khi không phù hợp.
- [ ] Có sample data để thử nghiệm.
- [ ] Mỗi quyết định khó có documentation.

### 14.5 Checklist data integration

- [ ] Đã kiểm tra schema và format từng nguồn.
- [ ] Đã chuẩn hóa encoding, datatype, unit và time.
- [ ] Có mapping table rõ ràng.
- [ ] Có chiến lược entity matching/coreference.
- [ ] Không dùng `owl:sameAs` chỉ vì label giống nhau.
- [ ] Có provenance cho dữ liệu đã biến đổi.
- [ ] Có license metadata.
- [ ] Đã kiểm tra duplicate, missing value và outlier.
- [ ] Query trên từng nguồn cho kết quả đúng trước khi tích hợp.
- [ ] Đã kiểm tra scale và đơn vị khi hợp nhất kết quả.

### 14.6 Checklist project/demo

- [ ] Project chạy lại được từ README.
- [ ] Có dữ liệu mẫu nhỏ để reviewer chạy nhanh.
- [ ] Có script load/transform/query.
- [ ] Có ontology và data tách riêng.
- [ ] Có ít nhất 3–5 competency questions.
- [ ] Có expected results hoặc automated tests.
- [ ] Có validation report.
- [ ] Có minh họa fact tường minh và fact suy diễn.
- [ ] Có nêu giới hạn của dữ liệu và mô hình.
- [ ] Không phụ thuộc không kiểm soát vào public endpoint.

---

## 15. Lỗi thường gặp

### Lỗi 1: Nghĩ rằng URI khác nhau luôn là hai entity khác nhau

Sai vì RDF dùng NUNA. Cần `owl:differentFrom` nếu muốn khẳng định khác nhau.

### Lỗi 2: Nghĩ rằng không có triple nghĩa là phủ định

Sai vì RDF dùng OWA. Thiếu dữ liệu không phải `false`.

### Lỗi 3: Dùng `owl:sameAs` quá rộng

`owl:sameAs` có nghĩa rất mạnh: hai URI cùng chỉ một thực thể.

### Lỗi 4: Nhầm `rdfs:domain` với kiểm tra input

`rdfs:domain` có thể làm phát sinh type mới. Nếu property được dùng trên resource, reasoner có thể suy ra resource thuộc domain.

### Lỗi 5: Dùng `rdfs:range` cho restriction cục bộ

Nếu chỉ muốn giới hạn property trong một class, dùng restriction:

```turtle
ex:ClassX rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:p ;
    owl:allValuesFrom ex:ClassY
] .
```

### Lỗi 6: Nghĩ SPARQL tự động suy luận

Mặc định SPARQL thường query graph hiện có. Phải bật reasoner, materialize graph hoặc viết query xét hierarchy.

### Lỗi 7: Nghĩ hai biến SPARQL khác nhau luôn là hai entity khác nhau

```sparql
?p ex:hasChild ?c1, ?c2
```

`?c1` và `?c2` có thể cùng binding. Dùng `FILTER(?c1 != ?c2)` nếu cần khác RDF term.

### Lỗi 8: Dùng subclass để biểu diễn mọi quan hệ

`Student`, `Person` có thể là subclass. Nhưng `Passenger`, `Employee`, `RoleAtTime` thường có thể là role/quan hệ tùy ngữ cảnh.

### Lỗi 9: Tạo class/property quá đặc thù

Ontology nên dùng được trong các context hợp lý khác nhau, theo nguyên tắc AAA.

### Lỗi 10: Không ghi provenance và license

Một graph có nhiều fact nhưng không biết nguồn, thời gian và license sẽ khó đánh giá và tái sử dụng.

### Lỗi 11: Chỉ test bằng một ví dụ

Cần test:

- Case đúng.
- Case thiếu dữ liệu.
- Case có nhiều giá trị.
- Case mâu thuẫn.
- Case khác ngữ cảnh.
- Case có blank node/language tag/datatype.

---

## 16. Cheat sheet nhanh

### RDF

```turtle
ex:s ex:p ex:o .
ex:s a ex:Class .
ex:s ex:name "value"@en .
ex:s ex:count 42 .
```

### RDFS

```turtle
ex:A rdfs:subClassOf ex:B .
ex:p rdfs:subPropertyOf ex:q .
ex:p rdfs:domain ex:C .
ex:p rdfs:range ex:D .
```

### OWL

```turtle
ex:A owl:equivalentClass ex:B .
ex:A owl:disjointWith ex:B .
ex:x owl:sameAs ex:y .
ex:p a owl:FunctionalProperty .
ex:p owl:inverseOf ex:q .
```

### Restriction

```turtle
ex:A rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty ex:p ;
    owl:someValuesFrom ex:B
] .
```

### SPARQL

```sparql
SELECT ?x
WHERE {
    ?x a ex:Class .
}
```

```sparql
ASK {
    ?x ex:p ex:o .
}
```

```sparql
CONSTRUCT {
    ?x ex:newProperty ?y .
}
WHERE {
    ?x ex:oldProperty ?y .
}
```

### Reasoning mental model

```text
RDF fact + RDFS/OWL axiom
    → inferred fact / consistency consequence
```

### Chọn công nghệ

| Nhu cầu | Công nghệ nên xem xét |
|---|---|
| Biểu diễn dữ liệu liên kết | RDF/Turtle |
| Schema đơn giản | RDFS |
| Constraint và logic ontology | OWL |
| Query RDF | SPARQL |
| Xuất bản Web và liên kết dataset | LOD |
| Xử lý Python | RDFLib |
| Xử lý Java/reasoning | Apache Jena |
| Edge property/transactional graph | LPG/Cypher |
| Validation dữ liệu | SHACL hoặc validation layer |
| Mapping nguồn dị biệt | RML/R2RML/D2R |

---

## Kết luận

Một bài Knowledge Graph tốt cần bảo đảm đồng thời:

```text
Mô hình đúng
+ URI/vocabulary rõ
+ Semantics phù hợp
+ Reasoning được kiểm tra
+ Query trả lời competency questions
+ Data có provenance/license
+ Project tái lập được
```

Khi gặp bài mới, hãy đi theo thứ tự:

1. Xác định domain và câu hỏi cần trả lời.
2. Viết competency questions.
3. Thiết kế class/property/URI.
4. Tạo sample RDF nhỏ.
5. Thêm RDFS/OWL vừa đủ.
6. Chạy reasoner và kiểm tra inferred facts.
7. Viết SPARQL query.
8. Kiểm tra OWA/NUNA và các edge case.
9. Bổ sung validation, provenance và documentation.
10. Chỉ sau đó mới mở rộng dữ liệu và xây dựng ứng dụng.
