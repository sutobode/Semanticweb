MATCH (site:HeritageSite)-[:SAME_AS]->(external:ExternalResource)
WHERE site.uri <> external.uri
RETURN site.entityId AS entityId, site.uri AS site, site.labelVi AS label, external.uri AS externalResource
ORDER BY site, externalResource
LIMIT 50
