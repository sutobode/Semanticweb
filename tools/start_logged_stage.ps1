param(
    [Parameter(Mandatory = $true)][string]$Stage,
    [string]$RunMode = "full"
)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$outLog = Join-Path $logDir "runner-console.out"
$errLog = Join-Path $logDir "runner-console.err"
$proc = Start-Process -FilePath "python" `
    -ArgumentList @("-u", "tools/run_logged_stage.py", $Stage, $RunMode) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru
$pidPath = Join-Path $logDir "full-pipeline.pid"
$status = @(
    "RUNNING",
    "stage=$Stage",
    "run_mode=$RunMode",
    "pid=$($proc.Id)",
    "started=$(Get-Date -Format o)",
    "live_log=$((Join-Path $logDir 'full-pipeline-utf8.log'))"
) -join "`n"
[IO.File]::WriteAllText((Join-Path $logDir "full-pipeline-status.txt"), $status + "`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($pidPath, "$($proc.Id)`n", [Text.UTF8Encoding]::new($false))
Write-Output "STARTED pid=$($proc.Id) stage=$Stage run_mode=$RunMode"
Write-Output "LIVE_LOG=$(Join-Path $logDir 'full-pipeline-utf8.log')"
Write-Output "STATUS=$(Join-Path $logDir 'full-pipeline-status.txt')"
