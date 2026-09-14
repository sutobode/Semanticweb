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



## Runtime endpoint discovery

The Explorer reads `/api/config` for the canonical resource template, ontology base, public SPARQL endpoint, and read-only Graph Store URL. This prevents UI components from inventing a second URI namespace or linking the home page to a different Fuseki port. The local defaults remain documented as `localhost:3030` for Explorer and `localhost:3031` for public Fuseki.

## Semantic entity presentation

Direct HTML resources expose the same semantic identity as their RDF representations. The page links to the canonical URI, Turtle, and JSON-LD; displays ontology types as ontology links; labels source and derivation links; marks verified `owl:sameAs` links; and separates asserted triples, novel inferred triples, and closure triples. Each triple displays its named graph identifier.

## Accessibility and responsive evidence

The Explorer uses a skip link, semantic landmarks, explicit form labels, visible keyboard focus, live regions for loading/results/errors, accessible button names, reduced-motion handling, and a 320px-safe responsive layout. `make ux-audit` checks these static contracts and records the result. Keyboard and screen-reader checks remain manual evidence activities and must be recorded separately before claiming a full WCAG 2.2 AA audit.

## Demo and resilience

The reproducible offline journey is documented in [`DEMO.md`](./DEMO.md). `make ux-audit` exercises local search, entity detail, canonical HTML/Turtle/JSON-LD, allowlisted CQ, public read-only Fuseki behavior, API mutation rejection, missing-resource behavior, and timing samples. It writes snapshot-bound evidence under `reports/<run_id>/` without contacting external data sources.



The pinned Chromium audit at `tools/browser_ux_audit.cjs` checks four viewport sizes, horizontal overflow, accessible control names, keyboard activation from navigation through entity detail, canonical/RDF representation links, and simulated API failure. The current evidence is `browser-ux-audit: PASS (6/6)`. A human screen-reader audit remains a separate follow-up and is not claimed by the automated result.
