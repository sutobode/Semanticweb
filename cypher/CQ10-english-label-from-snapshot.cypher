MATCH (site:HeritageSite)-[:SAME_AS]->(external:ExternalResource)
WHERE site.uri <> external.uri AND external.labelEn IS NOT NULL
RETURN site.entityId AS entityId, site.uri AS site, site.labelVi AS viLabel,
       external.uri AS externalResource, external.labelEn AS enLabel
ORDER BY site
