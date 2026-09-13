MATCH (part)-[:PART_OF*1..]->(whole)
RETURN part.entityId AS part, whole.entityId AS whole
ORDER BY part, whole
