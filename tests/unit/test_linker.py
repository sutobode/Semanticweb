import csv
import json
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

import vietheritage.linking.linker as linker_module
from vietheritage.linking.linker import dbpedia_score, link_records, review_dbpedia_candidate
from vietheritage.validation.semantic import identity_component_fingerprint


ROOT = Path(__file__).resolve().parents[2]
VH = Namespace("http://localhost:3030/vietheritage/ontology/")
VHR = Namespace("http://localhost:3030/vietheritage/resource/")
NOW = "2026-10-03T00:00:00Z"
DBPEDIA = "http://dbpedia.org/resource/Ha_Long_Bay"


@pytest.fixture
def ontology():
    return Graph().parse(ROOT / "ontology" / "vietheritage.ttl", format="turtle")


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(linker_module, "_now", lambda: NOW)


def _record(name, qid=None, candidates=()):
    return {"entity_id": f"registry-{name}", "label_vi": name,
            "external_ids": {"wikidata": qid} if qid else {},
            "dbpedia_candidates": list(candidates),
            "identity_profile": {"granularity": "entity", "scope": "entity"}}


def _assertions(records, types=None):
    graph = Graph()
    for record in records:
        entity_id = record["entity_id"]
        graph.add((VHR[entity_id], RDF.type, VH[(types or {}).get(entity_id, "HeritageSite")]))
    return graph


def _link(records, ontology, *, types=None, link_reviews=()):
    return link_records(records, ontology=ontology, assertions=_assertions(records, types),
                        link_reviews=list(link_reviews))


def _bridge(distance=2):
    return {"uri": DBPEDIA, "score": 1.0, "distance_km": distance,
            "type_compatible": True, "same_entity": True,
            "granularity_compatible": True, "scope_compatible": True,
            "location_compatible": distance is not None, "method": "dbpedia-wikidata-sameas",
            "wikidata_id": "Q123", "evidence": "local explicit owl:sameAs to canonical Q123"}


def _approval(distance=2):
    return {"source_uri": str(VHR["registry-a"]), "target_uri": DBPEDIA,
            "target_dataset": "dbpedia", "method": "silk", "score": 1.0,
            "distance_km": distance, "type_compatible": True, "same_entity": True,
            "granularity_compatible": True, "scope_compatible": True,
            "location_compatible": distance is not None, "status": "verified",
            "reviewer": "fixture:test_linker", "reviewed_at": NOW,
            "reason": "Fixture identity and current candidate evidence independently checked"}


def _multiple_local_approval(records):
    fingerprint = identity_component_fingerprint(
        {VHR[record["entity_id"]] for record in records},
        {str(VHR[record["entity_id"]]): record for record in records},
    )
    return [
        {
            **_approval(),
            "source_uri": str(VHR[record["entity_id"]]),
            "target_dataset": "wikidata",
            "target_uri": "https://www.wikidata.org/entity/Q123",
            "multiple_local_approved": True,
            "component_fingerprint": fingerprint,
            "reason": "Reviewed duplicate local records represent the same active entity",
        }
        for record in records
    ]


def test_qid_is_verified_and_invalid_qid_rejected(ontology) -> None:
    reviews, verified = _link([
        {"entity_id": "registry-a", "label_vi": "A", "external_ids": {"wikidata": "Q123"}},
        {"entity_id": "registry-b", "label_vi": "B", "external_ids": {"wikidata": "Q-1"}},
    ], ontology)
    assert len(verified) == 1
    assert verified[0]["target_uri"].endswith("Q123")
    assert any(row["status"] == "rejected" for row in reviews)


def test_dbpedia_thresholds_are_fixed_and_type_safe() -> None:
    assert dbpedia_score("Vịnh Hạ Long", "Vịnh Hạ Long") == 1.0
    assert review_dbpedia_candidate(0.95, 3, True) == "auto_candidate"
    assert review_dbpedia_candidate(0.80, 10, True) == "manual_review"
    assert review_dbpedia_candidate(0.99, 1, False) == "rejected"


def test_dbpedia_candidate_only_verified_candidate_enters_verified_links(ontology) -> None:
    records = [{
        "entity_id": "registry-a",
        "label_vi": "Vịnh Hạ Long",
        "external_ids": {},
        "dbpedia_candidates": [
            {"uri": "http://dbpedia.org/resource/Ha_Long_Bay", "label": "Vịnh Hạ Long", "distance_km": 2,
             "type_compatible": True, "same_entity": True, "granularity_compatible": True,
             "scope_compatible": True, "location_compatible": True},
            {"uri": "http://dbpedia.org/resource/Other", "label": "Other", "distance_km": 100},
        ],
        "identity_profile": {"granularity": "entity", "scope": "entity"},
    }]
    queued, unpublished = _link(records, ontology)
    assert not unpublished
    assert {row["status"] for row in queued} == {"manual_review", "rejected"}
    reviews, verified = _link(records, ontology, link_reviews=[_approval()])
    assert len(reviews) == 2
    assert len(verified) == 1
    assert verified[0]["target_uri"].endswith("Ha_Long_Bay")



def test_loader_reads_explicit_dbpedia_wikidata_manifest(tmp_path, monkeypatch) -> None:
    import json
    import vietheritage.linking.linker as linker_module

    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    (raw / "dbpedia_wikidata_candidates.jsonl").write_text(
        json.dumps({"entity_id": "registry-a", "uri": "http://dbpedia.org/resource/A"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(linker_module, "REPO_ROOT", tmp_path)
    candidates = linker_module._load_dbpedia_candidates()
    assert candidates["registry-a"][0]["uri"].endswith("/A")


def test_local_english_labels_are_attached_only_to_verified_targets(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    rows = [
        {"wikidata_id": "Q123", "uri": "http://dbpedia.org/resource/English_Title"},
        {"wikidata_id": "Q456", "uri": "http://dbpedia.org/resource/Rejected_Title"},
        {"wikidata_id": "invalid", "uri": "http://dbpedia.org/resource/Ignored"},
    ]
    (raw / "dbpedia_wikidata_candidates.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )
    monkeypatch.setattr(linker_module, "REPO_ROOT", tmp_path)
    reviews = [
        {"target_uri": "https://www.wikidata.org/entity/Q123", "status": "verified"},
        {"target_uri": "https://www.wikidata.org/entity/Q456", "status": "rejected"},
    ]

    assert linker_module.attach_local_english_labels(reviews) == 1
    assert reviews[0]["label_en"] == "English Title"
    assert reviews[1]["label_en"] is None


def test_external_link_turtle_materializes_english_label(tmp_path) -> None:
    output = tmp_path / "external-links.ttl"
    linker_module._write_turtle([{
        "source_uri": str(VHR["registry-a"]),
        "target_uri": "https://www.wikidata.org/entity/Q123",
        "label_en": "English Title",
    }], output)

    graph = Graph().parse(output, format="turtle")
    target = URIRef("https://www.wikidata.org/entity/Q123")
    assert (VHR["registry-a"], OWL.sameAs, target) in graph
    assert (target, RDFS.label, Literal("English Title", lang="en")) in graph


def test_shared_identity_with_compatible_site_subclasses_requires_reviewed_exception(ontology):
    records = [_record("a", "Q123"), _record("b", "Q123")]
    reviews, verified = _link(records, ontology, types={
        "registry-a": "HistoricalSite", "registry-b": "ReligiousSite",
    })
    assert not verified
    assert all("SECOND_ACTIVE_LOCAL_ENTITY" in row["reason"] for row in reviews)

    reviews, verified = _link(records, ontology, types={
        "registry-a": "HistoricalSite", "registry-b": "ReligiousSite",
    }, link_reviews=_multiple_local_approval(records))
    assert len(verified) == 2
    assert all(row["status"] == "verified" for row in reviews)
    assert all(row["multiple_local_approved"] is True for row in reviews)
    assert all(row["reviewer"] == "fixture:test_linker" for row in reviews)
    assert {row["target_uri"] for row in verified} == {"https://www.wikidata.org/entity/Q123"}


@pytest.mark.parametrize(("left_profile", "right_profile", "reason"), [
    ({"granularity": "whole", "scope": "entity"},
     {"granularity": "component", "scope": "entity"}, "WHOLE_COMPONENT_CONFLICT"),
    ({"granularity": "entity", "scope": "broad"},
     {"granularity": "entity", "scope": "localized"}, "BROAD_LOCALIZED_CONFLICT"),
    ({"granularity": "entity", "scope": "entity", "locations": ["Hà Nội"]},
     {"granularity": "entity", "scope": "entity", "locations": ["Huế"]}, "INCOMPATIBLE_LOCATION"),
    ({"granularity": "entity", "scope": "entity", "communities": ["Kinh"]},
     {"granularity": "entity", "scope": "entity", "communities": ["Chăm"]}, "INCOMPATIBLE_COMMUNITY"),
])
def test_reviewed_exception_cannot_override_intrinsic_identity_conflicts(
    ontology, left_profile, right_profile, reason,
):
    records = [_record("a", "Q123"), _record("b", "Q123")]
    records[0]["identity_profile"] = left_profile
    records[1]["identity_profile"] = right_profile
    reviews, verified = _link(records, ontology, link_reviews=_multiple_local_approval(records))
    assert not verified
    assert all(reason in row["reason"] for row in reviews)


@pytest.mark.parametrize("left,right", [
    ("RepresentativeIntangibleHeritage", "NationalIntangibleHeritage"),
    ("RepresentativeIntangibleHeritage", "UrgentSafeguardingIntangibleHeritage"),
    ("UrgentSafeguardingIntangibleHeritage", "NationalIntangibleHeritage"),
])
def test_ax008_shared_identity_is_rejected_with_evidence(ontology, left, right):
    records = [_record("a", "Q123"), _record("b", "Q123")]
    reviews, verified = _link(records, ontology, types={"registry-a": left, "registry-b": right})
    assert not verified
    assert len(reviews) == 2
    for row in reviews:
        assert row["status"] == "rejected"
        assert "IDENTITY_TYPE_CONFLICT" in row["reason"]
        assert "AX-008" in row["reason"]
        assert "registry-a" in row["reason"] and "registry-b" in row["reason"]
        assert "normalized deterministic QID" in row["reason"]


@pytest.mark.parametrize("other", ["AdministrativeArea", "Museum"])
def test_subclass_ancestry_and_both_disjoint_constructs_are_respected(ontology, other):
    records = [_record("a", "Q123"), _record("b", "Q123")]
    reviews, verified = _link(records, ontology, types={"registry-a": "HistoricalSite", "registry-b": other})
    assert not verified
    assert all(row["status"] == "rejected" and "AX-004" in row["reason"] for row in reviews)
    assert all(str(VH.HeritageSite) in row["reason"] for row in reviews)


def test_identity_safety_checks_connected_components_not_only_shared_targets(ontology):
    # Each direct shared-target group is compatible; the complete component is not:
    # representative a -- Q123 -- generic b -- DBpedia -- national c -- Q456.
    candidate = {"uri": DBPEDIA, "score": 1.0, "distance_km": 2,
                 "type_compatible": True, "same_entity": True,
                 "granularity_compatible": True, "scope_compatible": True,
                 "location_compatible": True}
    records = [_record("a", "Q123"), _record("b", "Q123", [candidate]),
               _record("c", "Q456", [candidate])]
    types = {"registry-a": "RepresentativeIntangibleHeritage", "registry-b": "IntangibleHeritage",
             "registry-c": "NationalIntangibleHeritage"}
    reviews, verified = _link(records, ontology, types=types)
    assert not verified
    assert len(reviews) == 5
    assert all(row["status"] == "rejected" and "AX-008" in row["reason"] for row in reviews)
    assert _link(list(reversed(records)), ontology, types=types) == (reviews, verified)


def test_existing_same_as_edges_participate_in_identity_components(ontology):
    records = [_record("a", "Q123"), _record("b", "Q456")]
    data = _assertions(records, {"registry-a": "HistoricalSite", "registry-b": "Museum"})
    from rdflib import URIRef

    data.add((URIRef("https://www.wikidata.org/entity/Q123"), OWL.sameAs,
              URIRef("https://www.wikidata.org/entity/Q456")))
    reviews, verified = link_records(records, assertions=data, ontology=ontology)
    assert not verified
    assert all("IDENTITY_TYPE_CONFLICT" in row["reason"] for row in reviews)


@pytest.mark.parametrize("score,distance,compatible,expected", [
    (0.90, 5, True, "auto_candidate"),
    (0.90, 5.01, True, "manual_review"),
    (0.70, 20, True, "manual_review"),
    (0.69, 1, True, "rejected"),
    (0.99, 20.01, True, "rejected"),
    (1.0, None, True, "manual_review"),
    (1.0, None, False, "rejected"),
])
def test_dbpedia_decision_table_boundaries(score, distance, compatible, expected):
    assert review_dbpedia_candidate(score, distance, compatible) == expected


def test_uncovered_policy_combination_fails_closed():
    with pytest.raises(ValueError, match="LINK_POLICY_UNCOVERED"):
        review_dbpedia_candidate(0.80, None, True)


def test_missing_geo_and_legacy_automated_review_cannot_verify_qid_bridge(ontology):
    records = [_record("a", "Q123", [_bridge(None)])]
    legacy = _approval(None) | {"reviewer": "automated:vietheritage-linker/0.1.0"}
    reviews, verified = _link(records, ontology, link_reviews=[legacy])
    assert len(verified) == 1 and verified[0]["target_dataset"] == "wikidata"
    dbpedia = next(row for row in reviews if row["target_dataset"] == "dbpedia")
    assert dbpedia["status"] == "rejected"
    assert dbpedia["reviewer"] is None and dbpedia["reviewed_at"] is None
    assert "INCOMPATIBLE_LOCATION" in dbpedia["reason"]


@pytest.mark.parametrize("qid", [None, "Q456"])
def test_stale_bridge_overrides_even_an_explicit_review_and_valid_geo(ontology, qid):
    records = [_record("a", qid, [_bridge()])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval()])
    assert all(row["target_dataset"] != "dbpedia" for row in verified)
    dbpedia = next(row for row in reviews if row["target_dataset"] == "dbpedia")
    assert dbpedia["status"] == "rejected"
    assert "STALE_QID_BRIDGE" in dbpedia["reason"]
    assert "evidence_qid=Q123" in dbpedia["reason"]
    assert f"canonical_qid={qid}" in dbpedia["reason"]


def test_current_bridge_with_valid_geo_and_explicit_review_is_publishable(ontology):
    records = [_record("a", "Q123", [_bridge()])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval()])
    assert len(verified) == 2
    assert {row["target_dataset"] for row in verified} == {"wikidata", "dbpedia"}
    dbpedia = next(row for row in reviews if row["target_dataset"] == "dbpedia")
    assert dbpedia["reviewer"] == _approval()["reviewer"]
    assert dbpedia["reason"] == _approval()["reason"]


def test_type_only_candidate_rejection_has_specific_reason(ontology):
    candidate = _bridge() | {"type_compatible": False}
    reviews, verified = _link([_record("a", "Q123", [candidate])], ontology)
    assert len(verified) == 1
    dbpedia = next(row for row in reviews if row["target_dataset"] == "dbpedia")
    assert "INCOMPATIBLE_TYPE" in dbpedia["reason"]


def test_missing_geo_cannot_be_published_after_explicit_review(ontology):
    records = [_record("a", "Q123", [_bridge(None)])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval(None)])
    assert len(verified) == 1
    assert next(row for row in reviews if row["target_dataset"] == "dbpedia")["status"] == "rejected"


def test_review_of_different_geographic_evidence_is_not_reused(ontology):
    records = [_record("a", "Q123", [_bridge()])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval(3)])
    assert len(verified) == 1
    assert next(row for row in reviews if row["target_dataset"] == "dbpedia")["status"] == "manual_review"


def test_explicit_review_cannot_override_policy_rejection(ontology):
    records = [_record("a", "Q123", [_bridge(21)])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval(21)])
    assert len(verified) == 1
    assert next(row for row in reviews if row["target_dataset"] == "dbpedia")["status"] == "rejected"


def test_independent_valid_path_survives_a_stale_bridge_for_the_same_pair(ontology):
    independent = {"uri": DBPEDIA, "score": 1.0, "distance_km": 2,
                   "type_compatible": True, "same_entity": True,
                   "granularity_compatible": True, "scope_compatible": True,
                   "location_compatible": True, "evidence": "independent reviewed local identity"}
    records = [_record("a", candidates=[_bridge(), independent])]
    reviews, verified = _link(records, ontology, link_reviews=[_approval()])
    assert len(reviews) == 2 and len(verified) == 1
    assert verified[0]["target_uri"] == DBPEDIA
    assert any(row["status"] == "rejected" and "STALE_QID_BRIDGE" in row["reason"] for row in reviews)


def test_linking_only_run_keeps_protected_inputs_and_review_decisions(tmp_path, monkeypatch, ontology):
    raw = tmp_path / "data" / "raw"
    processed = tmp_path / "data" / "processed"
    rdf = tmp_path / "data" / "rdf"
    linking = tmp_path / "data" / "linking"
    ontology_dir = tmp_path / "ontology"
    for directory in (raw, processed, rdf, linking, ontology_dir):
        directory.mkdir(parents=True)
    records = [_record("a", "Q123")]
    canonical = processed / "canonical.jsonl"
    canonical.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    asserted = rdf / "vietheritage.ttl"
    _assertions(records).serialize(destination=asserted, format="turtle")
    ontology_path = ontology_dir / "vietheritage.ttl"
    ontology.serialize(destination=ontology_path, format="turtle")
    evidence = raw / "dbpedia_wikidata_candidates.jsonl"
    evidence.write_text(json.dumps(_bridge() | {"entity_id": "registry-a"}) + "\n", encoding="utf-8")
    metadata = rdf / "dataset-metadata.ttl"
    metadata.write_text("metadata must not be refreshed", encoding="utf-8")
    with (linking / "link_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_approval()))
        writer.writeheader()
        writer.writerow(_approval())
    protected = {path: path.read_bytes() for path in (canonical, asserted, ontology_path, evidence, metadata)}
    monkeypatch.setattr(linker_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(linker_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(linker_module, "RDF_DIR", rdf)
    monkeypatch.setattr(linker_module, "LINKING_DIR", linking)

    assert linker_module.run("full", refresh_metadata=False) == 0
    outputs = {path: path.read_bytes() for path in (
        rdf / "external-links.ttl", linking / "link_review.csv",
        linking / "link-review.jsonl", linking / "dbpedia_candidates.csv",
    )}
    graph = Graph().parse(rdf / "external-links.ttl", format="turtle")
    assert len(graph) == 3
    assert (URIRef("https://www.wikidata.org/entity/Q123"), RDFS.label,
            Literal("Ha Long Bay", lang="en")) in graph
    candidates = list(csv.DictReader((linking / "dbpedia_candidates.csv").open(encoding="utf-8")))
    assert candidates[0]["status"] == "auto_candidate"
    reviews = [json.loads(line) for line in (linking / "link-review.jsonl").read_text(encoding="utf-8").splitlines()]
    assert next(row for row in reviews if row["target_dataset"] == "dbpedia")["status"] == "verified"
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(json.loads((ROOT / "schema" / "link-review.schema.json").read_text(encoding="utf-8")))
    assert not [error for row in reviews for error in validator.iter_errors(row)]
    assert linker_module.run("full", refresh_metadata=False) == 0
    assert all(path.read_bytes() == contents for path, contents in protected.items())
    assert all(path.read_bytes() == contents for path, contents in outputs.items())
