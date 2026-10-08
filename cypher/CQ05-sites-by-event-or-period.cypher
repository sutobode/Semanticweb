MATCH (site:HeritageSite)-[relation:ASSOCIATED_WITH_EVENT|BELONGS_TO_PERIOD]->(context:Resource)
WHERE (type(relation) = "ASSOCIATED_WITH_EVENT" AND context:HistoricalEvent)
   OR (type(relation) = "BELONGS_TO_PERIOD" AND context:HistoricalPeriod)
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS label
ORDER BY label
