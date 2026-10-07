MATCH (site:HeritageSite)-[:LOCATED_IN]->(area:AdministrativeArea)
RETURN area.entityId AS entityId, area.uri AS area, area.labelVi AS areaLabel, count(DISTINCT site) AS siteCount
ORDER BY siteCount DESC, areaLabel
LIMIT 10
