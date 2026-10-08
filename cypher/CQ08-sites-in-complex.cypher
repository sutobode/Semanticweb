MATCH (:HeritageComplex)-[:HAS_MEMBER*1..]->(site:HeritageSite)
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS label
ORDER BY label
