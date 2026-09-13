MATCH (entity:Entity)
WHERE entity.recognitionYear IS NOT NULL
RETURN entity.entityId AS entity, entity.label AS label, entity.recognitionYear AS year
ORDER BY year, entity
