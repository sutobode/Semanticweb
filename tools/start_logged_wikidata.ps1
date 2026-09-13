param(
    [int]$MaxQueries = 400
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "wikidata-runner-console.out"
$errLog = Join-Path $logDir "wikidata-runner-console.err"
$proc = Start-Process -FilePath "python" -ArgumentList @("-u", "tools/wikidata_exact_enrich.py", "$MaxQueries") -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
[IO.File]::WriteAllText((Join-Path $logDir "wikidata-parent.pid"), "$($proc.Id)`n", [Text.UTF8Encoding]::new($false))
Write-Output "STARTED pid=$($proc.Id) max_queries=$MaxQueries"
Write-Output "LIVE_LOG=$(Join-Path $logDir 'wikidata-enrichment-utf8.log')"
Write-Output "STATUS=$(Join-Path $logDir 'wikidata-enrichment-status.txt')"
