MATCH (site:HeritageSite)-[:ASSOCIATED_WITH_PERSON|BUILT_BY]->(person:HistoricalPerson)
WITH person, count(DISTINCT site) AS siteCount
WHERE siteCount > 1
RETURN person.entityId AS entityId, person.uri AS person, person.labelVi AS name, siteCount
ORDER BY siteCount DESC, name
