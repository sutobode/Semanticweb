MATCH (site:UNESCOHeritageSite)
RETURN site.entityId AS site, site.label AS label
ORDER BY site
