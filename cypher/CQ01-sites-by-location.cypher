MATCH (site:HeritageSite)-[:LOCATED_IN]->(location)
RETURN site.entityId AS entity, site.label AS label, location.entityId AS location
ORDER BY entity
