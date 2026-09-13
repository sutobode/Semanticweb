MATCH (entity:HeritageSite)
RETURN entity.entityId AS entity, entity.label AS label
ORDER BY label
