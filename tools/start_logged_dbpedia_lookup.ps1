param(
    [int]$MaxQueries = 400
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "dbpedia-lookup-runner.out"
$errLog = Join-Path $logDir "dbpedia-lookup-runner.err"
$proc = Start-Process -FilePath "python" -ArgumentList @("-u", "tools/dbpedia_lookup_candidates.py", "$MaxQueries") -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
[IO.File]::WriteAllText((Join-Path $logDir "dbpedia-lookup-parent.pid"), "$($proc.Id)`n", [Text.UTF8Encoding]::new($false))
Write-Output "STARTED pid=$($proc.Id) max_queries=$MaxQueries"
Write-Output "LIVE_LOG=$(Join-Path $logDir 'dbpedia-lookup-utf8.log')"
Write-Output "STATUS=$(Join-Path $logDir 'dbpedia-lookup-status.txt')"
