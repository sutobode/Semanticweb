MATCH (entity:Entity)
UNWIND labels(entity) AS class
WITH class, count(entity) AS count
WHERE class IN [
  'CulturalHeritageEntity',
  'HeritageSite',
  'IntangibleHeritage',
  'NationalTreasure',
  'UNESCOHeritageSite',
  'Organization'
]
RETURN class, count
ORDER BY count DESC
