MATCH (entity:Entity)-[:SAME_AS]->(external)
RETURN entity.entityId AS entity, external.uri AS external
ORDER BY entity, external
