param(
    [int]$ChunkSize = 100
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "dbpedia-runner-console.out"
$errLog = Join-Path $logDir "dbpedia-runner-console.err"
$proc = Start-Process -FilePath "python" -ArgumentList @("-u", "tools/dbpedia_exact_candidates.py", "$ChunkSize") -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
[IO.File]::WriteAllText((Join-Path $logDir "dbpedia-parent.pid"), "$($proc.Id)`n", [Text.UTF8Encoding]::new($false))
Write-Output "STARTED pid=$($proc.Id) chunk_size=$ChunkSize"
Write-Output "LIVE_LOG=$(Join-Path $logDir 'dbpedia-enrichment-utf8.log')"
Write-Output "STATUS=$(Join-Path $logDir 'dbpedia-enrichment-status.txt')"
