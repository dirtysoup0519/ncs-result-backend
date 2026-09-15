param(
    [string]$VmHost,
    [string]$FrontendDir
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepoRoot ".local\ncs.env"
$ProjectPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$BackendDir = $RepoRoot

function Fail([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Import-LocalConfig {
    if (-not (Test-Path $ConfigPath)) { return }
    Get-Content -LiteralPath $ConfigPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

function Set-LocalConfigValue([string]$Name, [string]$Value) {
    $lines = @(Get-Content -LiteralPath $ConfigPath)
    $updated = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^$([regex]::Escape($Name))=") {
            $lines[$index] = "$Name=$Value"
            $updated = $true
        }
    }
    if (-not $updated) { $lines += "$Name=$Value" }
    [IO.File]::WriteAllLines($ConfigPath, $lines, [Text.UTF8Encoding]::new($false))
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Resolve-FrontendDirectory([string]$RequestedPath) {
    $candidatePaths = @()
    if ($RequestedPath) { $candidatePaths += $RequestedPath }
    if ($env:NCS_FRONTEND_DIR) { $candidatePaths += $env:NCS_FRONTEND_DIR }
    $candidatePaths += @(
        (Join-Path $RepoRoot "..\ncs-dashboard\ncs-dashboard"),
        (Join-Path $RepoRoot "..\ncs-dashboard"),
        (Join-Path $RepoRoot "ncs-dashboard\ncs-dashboard"),
        (Join-Path $RepoRoot "ncs-dashboard")
    )
    foreach ($candidate in $candidatePaths) {
        if (-not [IO.Path]::IsPathRooted($candidate)) { $candidate = Join-Path $RepoRoot $candidate }
        $resolved = [IO.Path]::GetFullPath($candidate)
        if (Test-Path (Join-Path $resolved "package.json")) { return $resolved }
    }
    $entered = (Read-Host "Frontend project directory containing package.json").Trim('"').Trim()
    if (-not $entered) { return $null }
    if (-not [IO.Path]::IsPathRooted($entered)) { $entered = Join-Path $RepoRoot $entered }
    $resolved = [IO.Path]::GetFullPath($entered)
    if (-not (Test-Path (Join-Path $resolved "package.json"))) { return $null }
    return $resolved
}

function Find-CompatiblePython {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $version = & $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -in @("3.11", "3.12")) {
            return [PSCustomObject]@{ Executable = $pythonCommand.Source; Prefix = @(); Version = $version }
        }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        foreach ($selector in @("-3.12", "-3.11")) {
            $version = & $pyCommand.Source $selector -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -in @("3.11", "3.12")) {
                return [PSCustomObject]@{ Executable = $pyCommand.Source; Prefix = @($selector); Version = $version }
            }
        }
    }

    Fail "Python 3.11 or 3.12 was not found. Install one of these versions and run start_project.cmd again."
}

function Ensure-ProjectRuntime {
    Push-Location $RepoRoot
    try {
        if (-not (Test-Path $ProjectPython)) {
            $basePython = Find-CompatiblePython
            Write-Host "[SETUP] Creating ./.venv with Python $($basePython.Version)"
            $arguments = @($basePython.Prefix) + @("-m", "venv", (Join-Path $RepoRoot ".venv"))
            & $basePython.Executable @arguments
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ProjectPython)) {
                Fail "Failed to create the project virtual environment."
            }
        }

        $projectVersion = & $ProjectPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -ne 0 -or $projectVersion -notin @("3.11", "3.12")) {
            Fail "./.venv must use Python 3.11 or 3.12. Recreate it with a supported Python version."
        }

        & $ProjectPython -c "import flask, pymysql, numpy, torch, ncs_backend" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[SETUP] Installing Flask, PyMySQL, NumPy, PyTorch and backend dependencies"
            & $ProjectPython -m pip install -e ".[mysql,prediction]"
            if ($LASTEXITCODE -ne 0) { Fail "Failed to install backend dependencies." }
        }

        & $ProjectPython -c "import flask, pymysql, numpy, torch, ncs_backend" 2>$null
        if ($LASTEXITCODE -ne 0) { Fail "Backend dependencies are still unavailable after installation." }
        Write-Host "[READY] Backend runtime: ./.venv (Python $projectVersion)"
    }
    finally {
        Pop-Location
    }
}

Ensure-ProjectRuntime

Import-LocalConfig

if (-not (Test-Path $ConfigPath)) {
    Write-Host "[SETUP] Missing ./.local/ncs.env; initializing recovery-mode MySQL automatically."
    $setupArguments = @{ SkipDependencyInstall = $true }
    if ($VmHost) { $setupArguments.VmHost = $VmHost }
    if ($FrontendDir) { $setupArguments.FrontendDir = $FrontendDir }
    & (Join-Path $PSScriptRoot "setup_new_machine.ps1") @setupArguments
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ConfigPath)) {
        Fail "Automatic MySQL initialization did not create ./.local/ncs.env."
    }
    Import-LocalConfig
}
if (-not $env:NCS_DATABASE_URL) { Write-Host "[ERROR] NCS_DATABASE_URL is missing in $ConfigPath" -ForegroundColor Red; exit 1 }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "[ERROR] npm was not found in PATH." -ForegroundColor Red; exit 1 }
$FrontendDir = Resolve-FrontendDirectory $FrontendDir
if (-not $FrontendDir) { Fail "Frontend package.json was not found. Pass -FrontendDir or set NCS_FRONTEND_DIR in ./.local/ncs.env." }
if ($env:NCS_FRONTEND_DIR -ne $FrontendDir) { Set-LocalConfigValue "NCS_FRONTEND_DIR" $FrontendDir }
$queryPort = if ($env:NCS_QUERY_PORT) { [int]$env:NCS_QUERY_PORT } else { 5000 }
$frontendPort = if ($env:NCS_FRONTEND_PORT) { [int]$env:NCS_FRONTEND_PORT } else { 5173 }

Write-Host "[DATA] Checking published dashboard data"
& $ProjectPython (Join-Path $RepoRoot "scripts\ensure_dashboard_data.py")
if ($LASTEXITCODE -eq 3) {
    Fail "No published ADS data. Put the latest ADS v2.5 directory or archive in ./data_exchange/packages and run start_project.cmd again."
}
if ($LASTEXITCODE -ne 0) { Fail "Dashboard data check or automatic import failed." }

Write-Host "[MODEL] Checking published AI prediction"
& $ProjectPython (Join-Path $RepoRoot "scripts\ensure_prediction_data.py")
if ($LASTEXITCODE -eq 3) {
    Write-Host "[WARN] No model package found. Put a model directory, ZIP or PTH in ./data_exchange/models to enable AI prediction." -ForegroundColor Yellow
} elseif ($LASTEXITCODE -ne 0) {
    Fail "AI model validation or prediction failed. ADS data remains published."
}

function ListeningPid([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) { return $connection.OwningProcess }
    return $null
}

$backendPid = ListeningPid $queryPort
if ($backendPid) {
    Write-Host "[SKIP] Port $queryPort is already used by PID $backendPid. Stop it manually before restarting."
} else {
    $escapedPython = $ProjectPython.Replace("'", "''")
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-Command", "Set-Location -LiteralPath '$BackendDir'; & '$escapedPython' '.\scripts\run_query.py'") -WorkingDirectory $BackendDir
    Write-Host "[START] Query API: http://127.0.0.1:$queryPort"
}
$frontendPid = ListeningPid $frontendPort
if ($frontendPid) {
    Write-Host "[SKIP] Port $frontendPort is already used by PID $frontendPid. Stop it manually before restarting."
} else {
    $escapedFrontend = $FrontendDir.Replace("'", "''")
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-Command", "Set-Location -LiteralPath '$escapedFrontend'; npm run dev -- --port $frontendPort") -WorkingDirectory $FrontendDir
    Write-Host "[START] Dashboard: http://localhost:$frontendPort"
}
Start-Sleep -Seconds 3
Start-Process "http://localhost:$frontendPort/"
