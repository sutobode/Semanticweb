# Phase 4 Clean-Rebuild Staging and Rollback Runbook

This procedure is prepared for a later authorized rebuild. Do not run collection, promotion, reset, or database-load commands during pre-rebuild verification.

## Preconditions

1. Phase 1-4 changes are committed and the release commit SHA is recorded.
2. The full test suite, CQ fixtures, SHACL checks, RDF/LPG parity checks, and `git diff --check` pass.
3. The in-memory reconciliation gate reports `status=PASS`, `collisions=0`, and all reviewed distinct groups from `config/identity_reviews.yaml` are applied.
4. Production Fuseki and Neo4j credentials and endpoints are absent from the staging environment.
5. The operator records a run ID in UTC, for example `20261008T120000Z-clean-rebuild`.

## Immutable Snapshot

Run this only immediately before an authorized rebuild or promotion.

First freeze collectors, pipeline stages, loaders, and application traffic. Stop Fuseki and Neo4j before copying either filesystem artifacts or database volumes so every backup component represents the same point in time.

```powershell
$ErrorActionPreference = "Stop"
$RunId = "<UTC-RUN-ID>"
$Root = "C:\path\to\Semanticweb"
$Backup = "D:\vietheritage-backups\$RunId"
$ProductionDockerContext = "<APPROVED-PRODUCTION-CONTEXT>"
if ((docker context show) -ne $ProductionDockerContext) { throw "Wrong Docker context" }
function Assert-Native([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}
New-Item -ItemType Directory -Path $Backup

docker --context $ProductionDockerContext compose --project-directory "$Root" stop explorer fuseki neo4j
Assert-Native "stop production services"
$States = docker --context $ProductionDockerContext inspect `
  vietheritage-explorer vietheritage-fuseki vietheritage-neo4j `
  --format '{{.Name}}={{.State.Status}}'
Assert-Native "inspect stopped production services"
if ($States | Where-Object { $_ -notmatch '=exited$' }) { throw "A production container is still running" }
git -C $Root bundle create "$Backup\repository.bundle" --all
Assert-Native "create Git bundle"
Copy-Item "$Root\data" "$Backup\data" -Recurse -ErrorAction Stop
if (Test-Path "$Root\reports") {
  Copy-Item "$Root\reports" "$Backup\reports" -Recurse -ErrorAction Stop
}
Copy-Item "$Root\ontology" "$Backup\ontology" -Recurse -ErrorAction Stop
Copy-Item "$Root\config" "$Backup\config" -Recurse -ErrorAction Stop
Get-ChildItem $Backup -File -Recurse | Get-FileHash -Algorithm SHA256 |
  Export-Csv "$Backup\sha256.csv" -NoTypeInformation
```

Resolve volume names from the stopped containers, require each volume to exist, and archive it read-only. Never type a volume name manually and never run `fuseki-reset`, `neo4j-reset`, or `docker compose down -v`.

```powershell
$FusekiVolume = docker --context $ProductionDockerContext inspect vietheritage-fuseki --format '{{range .Mounts}}{{if eq .Destination "/fuseki/databases"}}{{.Name}}{{end}}{{end}}'
Assert-Native "inspect Fuseki mount"
$Neo4jVolume = docker --context $ProductionDockerContext inspect vietheritage-neo4j --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}'
Assert-Native "inspect Neo4j mount"
if (-not $FusekiVolume -or -not $Neo4jVolume) { throw "Production volume lookup failed" }
docker --context $ProductionDockerContext volume inspect $FusekiVolume | Out-Null
Assert-Native "verify Fuseki volume"
docker --context $ProductionDockerContext volume inspect $Neo4jVolume | Out-Null
Assert-Native "verify Neo4j volume"
docker --context $ProductionDockerContext run --rm --mount "type=volume,src=$FusekiVolume,dst=/source,readonly" `
  --mount "type=bind,src=$Backup,dst=/backup" alpine `
  tar -czf /backup/fuseki-volume.tgz -C /source .
Assert-Native "archive Fuseki volume"
docker --context $ProductionDockerContext run --rm --mount "type=volume,src=$Neo4jVolume,dst=/source,readonly" `
  --mount "type=bind,src=$Backup,dst=/backup" alpine `
  tar -czf /backup/neo4j-volume.tgz -C /source .
Assert-Native "archive Neo4j volume"
$FusekiArchive = tar -tzf "$Backup\fuseki-volume.tgz"
Assert-Native "list Fuseki archive"
$Neo4jArchive = tar -tzf "$Backup\neo4j-volume.tgz"
Assert-Native "list Neo4j archive"
if ((Get-Item "$Backup\fuseki-volume.tgz").Length -lt 1MB -or
    -not ($FusekiArchive | Select-String -Quiet "(^|/)vietheritage/Data-[^/]+/(GOSP|GSPO|POSG|SPOG)")) {
  throw "Fuseki archive lacks expected database files"
}
if ((Get-Item "$Backup\neo4j-volume.tgz").Length -lt 1MB -or
    -not ($Neo4jArchive | Select-String -Quiet "(^|/)databases/neo4j/(neostore|.*\.store)")) {
  throw "Neo4j archive lacks expected database files"
}
Get-ChildItem $Backup -File | Get-FileHash -Algorithm SHA256 |
  Export-Csv "$Backup\volume-sha256.csv" -NoTypeInformation
```

Upload the backup and an independently stored or signed hash manifest to WORM/object-lock storage and verify the upload before restarting services with `docker --context $ProductionDockerContext compose --project-directory "$Root" start fuseki neo4j explorer`; check `$LASTEXITCODE` and health afterward. This is a mandatory promotion gate; Windows read-only attributes are not an immutability control.

## Run-Scoped Staging

Use a separate worktree or clone whose `data`, `reports`, and logs are physically outside the production checkout. Execute the following commands inside an interactive session on the isolated candidate VM. The Compose ports bind to loopback, so a remote Docker context alone is not sufficient. Record `docker context show`, `docker info --format '{{.ID}}'`, and the VM identity in the run manifest.

```powershell
$ErrorActionPreference = "Stop"
$RunId = "<UTC-RUN-ID>"
$StageRoot = "D:\vietheritage-staging\$RunId"
function Assert-Native([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}
git clone <REPOSITORY-URL> "$StageRoot\repo"
Assert-Native "clone staging repository"
Set-Location "$StageRoot\repo"
git checkout --detach <VERIFIED-COMMIT-SHA>
Assert-Native "checkout verified release"
py -3.12 -m venv .venv-stage
Assert-Native "create staging virtual environment"
& ".\.venv-stage\Scripts\python.exe" -m pip install -r requirements.txt
Assert-Native "install staging dependencies"
& ".\.venv-stage\Scripts\python.exe" -m pip install -e .
Assert-Native "install staging package"
```

Download or mount the WORM snapshot inside the candidate VM before using it. Define a candidate-local path, verify the independently stored signed manifest, and reject missing or non-absolute paths:

```powershell
$Backup = "D:\verified-backups\$RunId"
if (-not [IO.Path]::IsPathRooted($Backup) -or -not (Test-Path "$Backup\sha256.csv") -or
    -not (Test-Path "$Backup\data\raw")) {
  throw "Verified candidate-local backup is unavailable"
}
# Verify the WORM/object-store signature and every downloaded backup hash here.
```

Do not copy the production `.env`; Python loaders do not automatically load a repository `.env`. Start from a sanitized process environment, set explicit staging endpoints and credentials, and reject accidental production values. `RUN_FUSEKI_INTEGRATION` must be absent during the test gate because that opt-in test performs a real load.

```powershell
"FUSEKI_URL", "FUSEKI_DATASET", "FUSEKI_LOAD_DATASET", "FUSEKI_USER", `
  "FUSEKI_ADMIN_PASSWORD", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", `
  "NEO4J_DATABASE", "RUN_FUSEKI_INTEGRATION" | ForEach-Object {
    Remove-Item "Env:$_" -ErrorAction SilentlyContinue
  }
$env:PYTHONNOUSERSITE = "1"
$env:FUSEKI_URL = "http://127.0.0.1:3031"
$env:FUSEKI_DATASET = "vietheritage"
$env:FUSEKI_LOAD_DATASET = "vietheritage-admin"
$env:FUSEKI_USER = "admin"
$env:FUSEKI_ADMIN_PASSWORD = "<STAGING-ONLY-PASSWORD>"
$env:NEO4J_URI = "bolt://127.0.0.1:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "<STAGING-ONLY-PASSWORD>"
$env:NEO4J_DATABASE = "neo4j"
if ((docker context show) -ne "<APPROVED-STAGING-CONTEXT>" -or
    $env:FUSEKI_URL -eq "<PRODUCTION-FUSEKI-URL>" -or
    $env:NEO4J_URI -eq "<PRODUCTION-NEO4J-URI>") {
  throw "Staging endpoint resolves to production"
}
$ModulePath = & ".\.venv-stage\Scripts\python.exe" -c "import pathlib,vietheritage; print(pathlib.Path(vietheritage.__file__).resolve())"
if (-not $ModulePath.StartsWith((Resolve-Path "$StageRoot\repo").Path)) {
  throw "vietheritage imports outside the staging worktree: $ModulePath"
}
```

If rebuilding from the currently approved source snapshot rather than collecting, replace only the staging raw directory and verify it against the backup manifest:

```powershell
if ((Resolve-Path "$StageRoot\repo").Path -notlike "$StageRoot*") { throw "Unsafe staging path" }
Remove-Item "$StageRoot\repo\data\raw" -Recurse -Force
New-Item -ItemType Directory -Path "$StageRoot\repo\data\raw"
Copy-Item "$Backup\data\raw\*" "$StageRoot\repo\data\raw" -Recurse -ErrorAction Stop
$ExpectedRaw = Import-Csv "$Backup\sha256.csv" | Where-Object { $_.Path -like "*\data\raw\*" }
$ExpectedRawMap = @{}
foreach ($Row in $ExpectedRaw) {
  $Marker = "\data\raw\"
  $Index = $Row.Path.ToLowerInvariant().LastIndexOf($Marker)
  if ($Index -lt 0) { throw "Invalid raw path in backup manifest: $($Row.Path)" }
  $ExpectedRawMap[$Row.Path.Substring($Index + $Marker.Length)] = $Row.Hash
}
$ActualRaw = Get-ChildItem "$StageRoot\repo\data\raw" -File -Recurse | ForEach-Object {
  [pscustomobject]@{
    RelativePath = $_.FullName.Substring((Resolve-Path "$StageRoot\repo\data\raw").Path.Length).TrimStart('\')
    Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  }
}
$ActualRawMap = @{}
foreach ($Row in $ActualRaw) { $ActualRawMap[$Row.RelativePath] = $Row.Hash }
if ($ActualRawMap.Count -ne $ExpectedRawMap.Count) { throw "Raw snapshot file count mismatch" }
foreach ($Path in $ExpectedRawMap.Keys) {
  if (-not $ActualRawMap.ContainsKey($Path) -or $ActualRawMap[$Path] -ne $ExpectedRawMap[$Path]) {
    throw "Raw snapshot mismatch: $Path"
  }
}
```

Run every file-producing stage from `$StageRoot\repo`. The hard-coded repository-relative paths then resolve inside the run-scoped worktree, not the production checkout.

```powershell
$Python = ".\.venv-stage\Scripts\python.exe"
& $Python -m pytest -q
Assert-Native "staging tests"
& $Python -m vietheritage.cli normalize --run-mode full
Assert-Native "normalize"
& $Python -m vietheritage.cli resolve --run-mode full
Assert-Native "resolve"
& $Python -m vietheritage.cli map --run-mode full
Assert-Native "map"
& $Python -m vietheritage.cli generate-rdf --run-mode full
Assert-Native "generate RDF"
& $Python -m vietheritage.cli link --run-mode full
Assert-Native "link"
& $Python -m vietheritage.cli reason --run-mode full
Assert-Native "reason"
& $Python -m vietheritage.cli validate --run-mode full
Assert-Native "validate"
```

Collection, if separately authorized, must also run only in this staging worktree before the stages above. Stop immediately if resolve reports any unreviewed blocker.

Use the isolated candidate VM for staging Fuseki/Neo4j because the repository compose file fixes container names and loopback ports. Before `docker compose up`, require that the fixed container names and the run-scoped `${COMPOSE_PROJECT_NAME}_fuseki-data` and `${COMPOSE_PROJECT_NAME}_neo4j-data` volumes do not exist. Set `COMPOSE_PROJECT_NAME` to a lowercase filesystem-safe run ID, create fresh volumes, and record their names. Before loading, query Fuseki with `ASK { ?s ?p ?o }` and Neo4j with `MATCH (n) RETURN count(n)`; require `false` and `0`. Load only the staging artifacts. Never reuse a prior staging volume and never point staging loaders at production endpoints.

```powershell
$env:COMPOSE_PROJECT_NAME = "<lowercase-run-id>"
$FusekiStageVolume = "$($env:COMPOSE_PROJECT_NAME)_fuseki-data"
$Neo4jStageVolume = "$($env:COMPOSE_PROJECT_NAME)_neo4j-data"
$ExistingContainers = docker ps -a --format '{{.Names}}'
Assert-Native "list staging containers"
if ($ExistingContainers -contains "vietheritage-fuseki" -or
    $ExistingContainers -contains "vietheritage-neo4j") { throw "Fixed staging container name already exists" }
$ExistingVolumes = docker volume ls --format '{{.Name}}'
Assert-Native "list staging volumes"
if ($ExistingVolumes -contains $FusekiStageVolume -or $ExistingVolumes -contains $Neo4jStageVolume) {
  throw "Run-scoped staging volume already exists"
}
docker compose up -d --build fuseki neo4j
Assert-Native "start staging databases"
& $Python -m vietheritage.cli wait-fuseki
Assert-Native "wait for staging Fuseki"
& $Python -m vietheritage.cli wait-neo4j
Assert-Native "wait for staging Neo4j"
$Ask = Invoke-RestMethod -Uri "$($env:FUSEKI_URL)/vietheritage/sparql" `
  -Method Get -Body @{ query = "ASK { ?s ?p ?o }" } -Headers @{ Accept = "application/sparql-results+json" }
if ($Ask.boolean) { throw "Staging Fuseki is not empty" }
$NeoCount = docker exec vietheritage-neo4j cypher-shell -u $env:NEO4J_USER `
  -p $env:NEO4J_PASSWORD "MATCH (n) RETURN count(n) AS count"
Assert-Native "check staging Neo4j emptiness"
if (($NeoCount -join "`n") -notmatch "(?m)^0$") { throw "Staging Neo4j is not empty" }
& $Python -m vietheritage.cli fuseki-load --run-mode full
Assert-Native "load staging Fuseki"
& $Python -m vietheritage.cli neo4j-load --run-mode full
Assert-Native "load staging Neo4j"
```

Create the candidate-results directory before running artifact gates:

```powershell
$Manifest = "$StageRoot\manifest"
New-Item -ItemType Directory -Path "$Manifest\candidate-results" -Force
```

The existing `cq-test` and `cypher-test` commands are golden-fixture regression gates; they do not validate rebuilt production artifacts. After those gates pass, execute each `sparql/CQ01`-`CQ10` file directly against the loaded candidate dataset and each `cypher/CQ01`-`CQ10` file directly against the loaded candidate Neo4j database, without fixture loaders or rollback transactions. Save normalized result rows under `$StageRoot\manifest\candidate-results` and compare primary canonical entity IDs for RDF/LPG parity. Check every Python, Docker, HTTP, and query client exit code with `Assert-Native` or an equivalent terminating check.

Create the staging manifest before promotion:

```powershell
$Package = "$StageRoot\package"
New-Item -ItemType Directory -Path $Package
New-Item -ItemType Directory -Path "$Package\data"
git rev-parse HEAD | Set-Content "$Manifest\release-sha.txt"
Assert-Native "record release SHA"
& $Python -m pip freeze | Set-Content "$Manifest\python-packages.txt"
Assert-Native "record Python packages"
docker image inspect vietheritage/fuseki:4.10.0 neo4j:5.26.0 --format '{{.RepoDigests}} {{.Id}}' |
  Set-Content "$Manifest\image-digests.txt"
Assert-Native "record image digests"
# Generate and human-review counts.json here before packaging.
if (-not (Test-Path "$Manifest\counts.json")) { throw "Reviewed counts.json is missing" }
Copy-Item data\processed,data\rdf,data\linking "$Package\data" -Recurse -ErrorAction Stop
Copy-Item reports "$Package\reports" -Recurse -ErrorAction Stop
Copy-Item "$Manifest\candidate-results" "$Package\candidate-results" -Recurse -ErrorAction Stop
Copy-Item "$Manifest\counts.json" "$Package\counts.json" -ErrorAction Stop
$PackageRoot = (Resolve-Path $Package).Path
Get-ChildItem $Package -File -Recurse | ForEach-Object {
  [pscustomobject]@{
    RelativePath = $_.FullName.Substring($PackageRoot.Length).TrimStart('\')
    Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    Bytes = $_.Length
  }
} | Export-Csv "$Manifest\package-sha256.csv" -NoTypeInformation
```

Add canonical row counts, RDF triple counts, link counts, collision-report status, and all gate report IDs to the reviewed `counts.json` before hashing the package. Copy the package to its promotion location and recompute relative-path hashes there; promotion requires exact relative paths, hashes, byte sizes, and file counts from `package-sha256.csv`.

## Staging Gates

Promotion is forbidden unless all gates pass:

- `collision_report.json`: `status=PASS`, `collisions=0`.
- Every configured internal review is present and schema-valid.
- Canonical and current v2 link-review schemas pass. The untouched pre-rebuild link manifest is explicitly legacy v1 and validates only against `schema/link-review-v1.schema.json`; it must not be republished.
- SHACL and final publication validation pass.
- SPARQL CQ01-CQ10 pass against staging Fuseki.
- Cypher CQ01-CQ10 and RDF/LPG parity pass against staging Neo4j.
- Artifact checksums and row/triple counts are recorded in `$StageRoot\manifest`.
- A human reviews identity-map deltas, canonical-ID changes, source-record counts, and all link-review decisions.

## Promotion

The repository's current Compose file is not blue/green capable and binds services to loopback. Promotion therefore requires an already provisioned host-local gateway/reverse proxy or a separately approved secure binding override on both prior and candidate hosts. DNS may switch only between those externally reachable gateway endpoints, never directly to Compose's loopback ports. If that routing control is unavailable, do not promote and do not mutate production volumes in place.

1. Freeze writes and stop production explorer/load jobs.
2. Verify the immutable backup hashes.
3. Package only approved staging artifacts: `data/processed`, `data/rdf`, `data/linking`, and run reports. Keep raw inputs with their source snapshot.
4. Verify the package hashes against the staging manifest.
5. Confirm the isolated candidate Fuseki and Neo4j services use the recorded image digests and staging-only volumes.
6. Run read-only smoke, artifact-specific CQ, SHACL, and parity checks against the candidate services.
7. Switch the external service endpoints from the prior host to the candidate host in one controlled change.
8. Keep the prior artifact directory and prior database volumes unchanged until the retention window expires.

## Rollback

1. Stop traffic to the candidate services.
2. Switch external endpoints back to the unchanged prior Fuseki and Neo4j host.
3. Verify and reuse the unchanged prior artifact directory. Restore it from the immutable backup only under a separate stopped-service recovery procedure if its integrity check fails.
4. Verify hashes against `sha256.csv` and `volume-sha256.csv`.
5. Restart the prior services and run read-only smoke checks plus CQ01-CQ10.
6. Preserve the failed candidate artifacts, manifests, and logs under the run ID for diagnosis; do not overwrite the backup.

Rollback must never use destructive Git commands or volume reset targets.
