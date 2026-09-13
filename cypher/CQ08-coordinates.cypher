MATCH (entity:Entity)
WHERE entity.lat IS NOT NULL AND entity.lon IS NOT NULL
RETURN entity.entityId AS entity, entity.label AS label, entity.lat AS lat, entity.lon AS lon
ORDER BY entity
