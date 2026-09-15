$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepoRoot ".local\ncs.env"
$BackendDir = $RepoRoot
$FrontendCandidates = @(
    (Join-Path $RepoRoot "..\ncs-dashboard\ncs-dashboard"),
    (Join-Path $RepoRoot "ncs-dashboard\ncs-dashboard")
)
$FrontendDir = $FrontendCandidates | Where-Object { Test-Path (Join-Path $_ "package.json") } | Select-Object -First 1

if (-not (Test-Path $ConfigPath)) {
    Write-Host "[ERROR] Missing $ConfigPath" -ForegroundColor Red
    Write-Host "Run .\scripts\setup_new_machine.ps1 first."
    exit 1
}
Get-Content -LiteralPath $ConfigPath | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
}
if (-not $env:NCS_DATABASE_URL) { Write-Host "[ERROR] NCS_DATABASE_URL is missing in $ConfigPath" -ForegroundColor Red; exit 1 }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "[ERROR] Python was not found in PATH." -ForegroundColor Red; exit 1 }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "[ERROR] npm was not found in PATH." -ForegroundColor Red; exit 1 }
if (-not $FrontendDir) { Write-Host "[ERROR] Vue frontend package.json was not found beside the backend." -ForegroundColor Red; exit 1 }

function ListeningPid([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) { return $connection.OwningProcess }
    return $null
}

$backendPid = ListeningPid 5000
if ($backendPid) {
    Write-Host "[SKIP] Port 5000 is already used by PID $backendPid. Stop it manually before restarting."
} else {
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-Command", "Set-Location -LiteralPath '$BackendDir'; python scripts/run_query.py") -WorkingDirectory $BackendDir
    Write-Host "[START] Query API: http://127.0.0.1:5000"
}
$frontendPid = ListeningPid 5173
if ($frontendPid) {
    Write-Host "[SKIP] Port 5173 is already used by PID $frontendPid. Stop it manually before restarting."
} else {
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-Command", "Set-Location -LiteralPath '$FrontendDir'; npm run dev") -WorkingDirectory $FrontendDir
    Write-Host "[START] Dashboard: http://localhost:5173"
}
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173/"
