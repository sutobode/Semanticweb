# VietHeritageLOD UX Design

## Design principle

RDF/Turtle, the VietHeritage ontology, reasoning output, and Fuseki SPARQL remain the semantic source of truth. The HTTP API and browser explorer are read-only presentation layers over that graph; they do not create a second canonical JSON or SQL model.

## User flows

- **Visitor:** open `/`, search by Vietnamese label, filter by type/category/year, then open an entity detail page.
- **Researcher:** inspect the stable entity URI, provenance, asserted/inferred triples, Turtle and JSON-LD representations, and verified external links.
- **Power user:** use the 10 allowlisted competency questions or the Fuseki SPARQL 1.1 endpoint directly.

## URI and representations

Entity URIs use `VH_BASE_URI/resource/{entity_id}` and ontology terms use `VH_BASE_URI/ontology/{term}`. In the local Compose profile, the canonical base `http://localhost:3030/vietheritage` is served by the Explorer gateway; Fuseki public SPARQL is exposed at `http://localhost:3031/vietheritage/sparql`, while loader writes use the private admin service. The resource route returns HTML, Turtle, JSON-LD, or convenience JSON according to `Accept`; it sets `Vary: Accept`, preserves `@id`/`@type`, and links back to the canonical URI. HTML contains alternate links for RDF representations.

The local service uses direct HTTP 200 representations. This is documented as the local deployment choice instead of a 303 redirect because the same stable resource endpoint performs content negotiation.

## Graph semantics

Fuseki named graphs remain separate:

- ontology;
- asserted data;
- verified external links;
- inferred triples;
- dataset metadata.

Search uses the union/default graph, while entity detail reports source graph names and separates asserted from inferred triples. `owl:sameAs` is displayed only for verified identity links. Registry/Wikipedia sources are exposed using `dcterms:source` and `prov:wasDerivedFrom`.

## Query safety

The public service is GET-only and read-only. UI queries are generated from validated parameters and the competency-question route only runs allowlisted `CQ01`–`CQ10` files. No SPARQL Update, arbitrary filesystem path, credential, or unrestricted query body is accepted. Search uses page size 25 by default and 100 maximum.

## Accessibility and errors

The UI uses semantic HTML, labels, keyboard-friendly controls, responsive CSS, visible empty/loading/error states, and Vietnamese labels. Fuseki outage returns a safe 503 JSON error from the API and a human-readable browser error page.
