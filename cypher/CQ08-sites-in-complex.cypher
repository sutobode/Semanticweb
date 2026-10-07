MATCH (site:HeritageSite)-[:PART_OF*1..]->(:HeritageComplex {entityId: "complex-thang-long"})
RETURN DISTINCT site.entityId AS entityId, site.uri AS site, site.labelVi AS label
ORDER BY label
