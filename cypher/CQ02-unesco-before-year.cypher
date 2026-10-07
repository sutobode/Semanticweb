MATCH (site:UNESCOHeritageSite)
WHERE site.recognitionYear < 2000
RETURN site.entityId AS entityId, site.uri AS site, site.labelVi AS label, site.recognitionYear AS year
ORDER BY year
