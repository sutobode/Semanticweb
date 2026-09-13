MATCH (entity:Entity)
RETURN entity.entityType AS class, count(entity) AS count
ORDER BY count DESC
