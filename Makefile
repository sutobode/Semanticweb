SHELL := cmd
PYTHON ?= python
RUN_MODE ?= sample

.PHONY: setup test collect-sample collect normalize resolve map generate-rdf link \
        validate reason fuseki-up fuseki-down fuseki-reset fuseki-load \
        linked-data-test app-up app-down app-test app-smoke api-docs neo4j-up neo4j-down neo4j-reset neo4j-load cypher-test \
        traceability-check query cq-test pipeline-sample pipeline verify

## make setup — Python/Docker -> venv, dependencies
setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

## make test — source + fixtures -> test reports
test:
	$(PYTHON) -m pytest tests/unit tests/contract tests/integration tests/semantic -v

## make collect-sample — registry + enrichment fixtures -> raw fixture + coverage report
collect-sample:
	$(PYTHON) -m vietheritage.cli collect-sample

## make collect — Official registry + Wikipedia enrichment -> full raw + coverage report
collect:
	$(PYTHON) -m vietheritage.cli collect

## make normalize — raw -> normalized JSONL
normalize:
	$(PYTHON) -m vietheritage.cli normalize --run-mode $(RUN_MODE)

## make resolve — normalized -> entities/identity map
resolve:
	$(PYTHON) -m vietheritage.cli resolve --run-mode $(RUN_MODE)

## make map — entities + mapping -> canonical JSONL
map:
	$(PYTHON) -m vietheritage.cli map --run-mode $(RUN_MODE)

## make generate-rdf — canonical + ontology -> Turtle
generate-rdf:
	$(PYTHON) -m vietheritage.cli generate-rdf --run-mode $(RUN_MODE)

## make link — RDF + candidates -> links/review
link:
	$(PYTHON) -m vietheritage.cli link --run-mode $(RUN_MODE)

## make validate — RDF + ontology -> validation report
validate:
	$(PYTHON) -m vietheritage.cli validate --run-mode $(RUN_MODE)

## make reason — ontology + RDF -> inferred Turtle
reason:
	$(PYTHON) -m vietheritage.cli reason --run-mode $(RUN_MODE)

## make fuseki-up — Docker -> running Fuseki
fuseki-up:
	docker compose up -d --build fuseki
	$(PYTHON) -m vietheritage.cli wait-fuseki

## make fuseki-down — running Fuseki -> stopped Fuseki
fuseki-down:
	docker compose stop fuseki

## make fuseki-reset — Fuseki volume -> empty dataset
fuseki-reset:
	docker compose down -v fuseki

## make fuseki-load — RDF artifacts -> loaded dataset
fuseki-load:
	$(PYTHON) -m vietheritage.cli fuseki-load --run-mode $(RUN_MODE)

## make linked-data-test — running Fuseki + site URI -> HTTP RDF response
linked-data-test:
	$(PYTHON) -m vietheritage.cli linked-data-test

## make app-up — Docker -> running read-only explorer
app-up:
	docker compose up -d --build --no-deps explorer

## make app-down — running explorer -> stopped explorer
app-down:
	docker compose stop explorer

## make app-test — web API/server tests
app-test:
	$(PYTHON) -m pytest tests/unit/test_web_api.py tests/unit/test_web_server.py -q

## make app-smoke — running explorer -> HTTP smoke checks
app-smoke:
	$(PYTHON) -m vietheritage.web.smoke

## make api-docs — print local API documentation URL
api-docs:
	@echo http://localhost:8000/docs

## make neo4j-up — Docker -> running Neo4j
neo4j-up:
	docker compose up -d --build neo4j
	$(PYTHON) -m vietheritage.cli wait-neo4j

## make neo4j-down — running Neo4j -> stopped Neo4j
neo4j-down:
	docker compose stop neo4j

## make neo4j-reset — Neo4j volume -> empty database
neo4j-reset:
	docker compose down -v neo4j

## make neo4j-load — canonical.jsonl -> LPG nodes/relationships
neo4j-load:
	$(PYTHON) -m vietheritage.cli neo4j-load --run-mode $(RUN_MODE)

## make cypher-test — 10 .cypher files -> Cypher report
cypher-test:
	$(PYTHON) -m vietheritage.cli cypher-test

## make traceability-check — config/requirements.yaml + tests -> traceability report
traceability-check:
	$(PYTHON) -m vietheritage.cli traceability-check

## make query — QUERY=... -> query output
query:
	$(PYTHON) -m vietheritage.cli query --query "$(QUERY)"

## make cq-test — 10 .rq -> CQ report
cq-test:
	$(PYTHON) -m vietheritage.cli cq-test

## make pipeline-sample — all sample inputs -> all sample artifacts
pipeline-sample:
	$(MAKE) collect-sample
	$(MAKE) normalize RUN_MODE=sample
	$(MAKE) resolve RUN_MODE=sample
	$(MAKE) map RUN_MODE=sample
	$(MAKE) generate-rdf RUN_MODE=sample
	$(MAKE) validate RUN_MODE=sample
	$(MAKE) link RUN_MODE=sample
	$(MAKE) reason RUN_MODE=sample

## make pipeline — full source -> full artifacts
pipeline:
	$(MAKE) collect
	$(MAKE) normalize RUN_MODE=full
	$(MAKE) resolve RUN_MODE=full
	$(MAKE) map RUN_MODE=full
	$(MAKE) generate-rdf RUN_MODE=full
	$(MAKE) validate RUN_MODE=full
	$(MAKE) link RUN_MODE=full
	$(MAKE) reason RUN_MODE=full

## make verify — repository + services -> final report (FINAL STATUS PASS)
verify:
	$(PYTHON) -m vietheritage.cli verify --run-mode $(RUN_MODE)
