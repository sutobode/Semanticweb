MATCH (site:HeritageSite)-[relation:ASSOCIATED_WITH_EVENT|BELONGS_TO_PERIOD]->(context:Resource)
WHERE (type(relation) = "ASSOCIATED_WITH_EVENT" AND context.entityId = "event-example")
   OR (type(relation) = "BELONGS_TO_PERIOD" AND context.entityId = "period-example")
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS label
ORDER BY label
