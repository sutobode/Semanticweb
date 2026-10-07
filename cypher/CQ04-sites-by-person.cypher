MATCH (site:HeritageSite)-[:ASSOCIATED_WITH_PERSON|BUILT_BY]->(:HistoricalPerson {entityId: "person-ly-thuong-kiet"})
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS siteLabel
ORDER BY siteLabel
