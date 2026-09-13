from vietheritage.lpg.loader import load_records


class FakeSession:
    def __init__(self):
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))


def test_loader_uses_merge_and_maps_relations() -> None:
    session = FakeSession()
    count = load_records(session, [{
        "entity_id": "registry-a",
        "entity_type": "HeritageSite",
        "label_vi": "A",
        "relations": {"located_in": ["area-a"]},
    }])
    assert count == 1
    assert session.calls[0][0].startswith("MERGE")
    assert any(":HeritageSite" in query for query, _ in session.calls)
    assert any(":LOCATED_IN" in query for query, _ in session.calls)



def test_loader_projects_inferred_cultural_and_unesco_labels() -> None:
    session = FakeSession()
    load_records(session, [{
        "entity_id": "registry-world",
        "entity_type": "HeritageSite",
        "registry_category": "world_heritage",
        "label_vi": "World",
    }])
    queries = [query for query, _ in session.calls]
    assert any("SET n:CulturalHeritageEntity" in query for query in queries)
    assert any("SET n:UNESCOHeritageSite" in query for query in queries)
