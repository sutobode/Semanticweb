MATCH (entity:HeritageSite)
WHERE entity.entityType = 'HeritageSite'
RETURN entity.entityId AS entity, entity.label AS label
ORDER BY entity
