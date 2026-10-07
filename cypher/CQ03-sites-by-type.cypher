MATCH (site:ArchaeologicalSite)
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS label
ORDER BY label
