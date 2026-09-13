param(
    [int]$ChunkSize = 200
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "wikidata-sparql-runner-console.out"
$errLog = Join-Path $logDir "wikidata-sparql-runner-console.err"
$proc = Start-Process -FilePath "python" -ArgumentList @("-u", "tools/wikidata_sparql_exact_enrich.py", "$ChunkSize") -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
[IO.File]::WriteAllText((Join-Path $logDir "wikidata-sparql-parent.pid"), "$($proc.Id)`n", [Text.UTF8Encoding]::new($false))
Write-Output "STARTED pid=$($proc.Id) chunk_size=$ChunkSize"
Write-Output "LIVE_LOG=$(Join-Path $logDir 'wikidata-sparql-enrichment-utf8.log')"
Write-Output "STATUS=$(Join-Path $logDir 'wikidata-sparql-enrichment-status.txt')"
