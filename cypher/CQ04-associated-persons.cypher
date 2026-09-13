MATCH (entity)-[:ASSOCIATED_WITH_PERSON]->(person)
RETURN entity.entityId AS entity, person.entityId AS person, entity.label AS label
ORDER BY entity
