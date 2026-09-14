# VietHeritageLOD API

Base URL: `http://localhost:8000`

The API is read-only and Fuseki-backed. RDF remains authoritative; JSON responses are convenience projections with `@id`, `@type`, and `@context`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Fuseki/service health |
| GET | `/api/stats` | Graph entity/class/category/link counts |
| GET | `/api/search` | Paginated RDF search |
| GET | `/api/entities/{entity_id}` | Semantic entity detail |
| GET | `/resource/{entity_id}` | Content-negotiated linked-data resource |
| GET | `/api/queries` | Allowlisted CQ catalogue |
| GET | `/api/queries/{CQ01..CQ10}/run` | Read-only competency query |
| GET | `/openapi.json` | Machine-readable API description |
| GET | `/docs` | Human-readable API links |

## Search

Example:

```text
GET /api/search?q=Huế&entity_type=HeritageSite&page=1&page_size=25
```

Supported filters: `q`, `entity_type`, `registry_category`, `location`, `year`, `page`, `page_size`. `page_size` is limited to 100. Results include RDF `@id`, ontology `@type`, language-aware label, category URI, sources, and verified external links.

## Entity and content negotiation

```powershell
curl http://localhost:8000/api/entities/registry-b043193f37c5
curl -H "Accept: text/turtle" http://localhost:8000/resource/registry-b043193f37c5
curl -H "Accept: application/ld+json" http://localhost:8000/resource/registry-b043193f37c5
```

Supported representations:

- `text/html` — human-readable detail page.
- `text/turtle` — RDF 1.1 Turtle.
- `application/ld+json` — JSON-LD with explicit VietHeritage context.
- `application/json` — convenience detail projection.

The resource response sets `Vary: Accept` and includes a canonical `Link` header.

## Semantic fields

JSON-LD context maps convenience fields to RDF vocabulary. Entity detail distinguishes `asserted_triples` from `inferred_triples`, preserves named graph provenance, exposes `dcterms:source`/`prov:wasDerivedFrom`, and exposes only verified `owl:sameAs` links as external identity links.

## Competency questions

The API exposes only the existing ten read-only SPARQL files. It does not accept arbitrary update queries. The canonical power-user endpoint remains:

```text
http://localhost:3030/vietheritage/sparql
```
