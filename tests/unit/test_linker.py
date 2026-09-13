from vietheritage.linking.linker import dbpedia_score, link_records, review_dbpedia_candidate


def test_qid_is_verified_and_invalid_qid_rejected() -> None:
    reviews, verified = link_records([
        {"entity_id": "registry-a", "label_vi": "A", "external_ids": {"wikidata": "Q123"}},
        {"entity_id": "registry-b", "label_vi": "B", "external_ids": {"wikidata": "Q-1"}},
    ])
    assert len(verified) == 1
    assert verified[0]["target_uri"].endswith("Q123")
    assert any(row["status"] == "rejected" for row in reviews)


def test_dbpedia_thresholds_are_fixed_and_type_safe() -> None:
    assert dbpedia_score("Vịnh Hạ Long", "Vịnh Hạ Long") == 1.0
    assert review_dbpedia_candidate(0.95, 3, True) == "verified"
    assert review_dbpedia_candidate(0.80, 10, True) == "manual_review"
    assert review_dbpedia_candidate(0.99, 1, False) == "rejected"


def test_dbpedia_candidate_only_verified_candidate_enters_verified_links() -> None:
    reviews, verified = link_records([{
        "entity_id": "registry-a",
        "label_vi": "Vịnh Hạ Long",
        "external_ids": {},
        "dbpedia_candidates": [
            {"uri": "http://dbpedia.org/resource/Ha_Long_Bay", "label": "Vịnh Hạ Long", "distance_km": 2},
            {"uri": "http://dbpedia.org/resource/Other", "label": "Other", "distance_km": 100},
        ],
    }])
    assert len(reviews) == 2
    assert len(verified) == 1
    assert verified[0]["target_uri"].endswith("Ha_Long_Bay")
