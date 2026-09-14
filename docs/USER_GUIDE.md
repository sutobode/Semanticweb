# VietHeritageLOD User Guide

## Start the local experience

From a prepared checkout with full RDF artifacts and Fuseki loaded:

```powershell
make fuseki-up
make fuseki-load RUN_MODE=full
make app-up
make app-smoke
```

Open:

```text
http://localhost:8000
```

If the full data has not been built yet, follow [`E2E.md`](./E2E.md) first.

## Explore without SPARQL

1. Open the home page and choose **Bắt đầu tìm kiếm**.
2. Search for `Huế`, `Hội An`, or `Vịnh Hạ Long`.
3. Filter by ontology entity type, registry category, or recognition year.
4. Open a result to see its stable URI, ontology types, description, sources, categories, and verified external links.
5. Open the HTML resource, Turtle representation, or JSON-LD representation from the entity page.
6. Use **Competency Questions** to run one of the ten read-only SPARQL templates without writing a query.

## Advanced Semantic Web access

- SPARQL 1.1: `http://localhost:3031/vietheritage/sparql`
- API documentation: `http://localhost:3030/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Resource URI: `http://localhost:3030/vietheritage/resource/{entity_id}`

Use SPARQL directly when you need graph patterns, aggregation, paths, inference-aware analysis, or a custom research query. The explorer is intended to make the same linked data approachable to people who do not know SPARQL.

## Stop the explorer

```powershell
make app-down
make fuseki-down
```
