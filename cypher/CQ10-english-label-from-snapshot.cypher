MATCH (entity:Entity)
WHERE entity.labelEn IS NOT NULL
RETURN entity.entityId AS entity, entity.labelEn AS label
ORDER BY entity
