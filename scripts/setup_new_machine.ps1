param(
    [string]$VmHost,
    [int]$MysqlPort = 3306,
    [string]$Database = "ncs_analytics",
    [string]$FrontendDir,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $RepoRoot ".local"
$ConfigPath = Join-Path $LocalDir "ncs.env"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
Push-Location $RepoRoot

function Fail([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
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
    Fail "Python 3.11 or 3.12 was not found."
}

function Resolve-VmHost([string]$RequestedHost) {
    if ($RequestedHost) { return $RequestedHost.Trim() }
    if ($env:NCS_VM_HOST) { return $env:NCS_VM_HOST.Trim() }
    if ($env:NCS_DATABASE_URL -and $env:NCS_DATABASE_URL -match '@([^:/?#]+)(?::\d+)?/') {
        return $Matches[1]
    }
    if (Test-Path $ConfigPath) {
        $savedHost = Get-Content -LiteralPath $ConfigPath | Where-Object { $_ -match '^NCS_VM_HOST=(.+)$' } | Select-Object -Last 1
        if ($savedHost -and $savedHost -match '^NCS_VM_HOST=(.+)$') { return $Matches[1].Trim() }
        $savedUrl = Get-Content -LiteralPath $ConfigPath | Where-Object { $_ -match '^NCS_DATABASE_URL=(.+)$' } | Select-Object -Last 1
        if ($savedUrl -and $savedUrl -match '@([^:/?#]+)(?::\d+)?/') { return $Matches[1] }
    }
    return (Read-Host "VM MySQL host or IP (example: 192.168.x.x)").Trim()
}

function Resolve-FrontendDirectory([string]$RequestedPath) {
    $candidates = @()
    if ($RequestedPath) { $candidates += $RequestedPath }
    if ($env:NCS_FRONTEND_DIR) { $candidates += $env:NCS_FRONTEND_DIR }
    $candidates += @(
        (Join-Path $RepoRoot "..\ncs-dashboard\ncs-dashboard"),
        (Join-Path $RepoRoot "..\ncs-dashboard"),
        (Join-Path $RepoRoot "ncs-dashboard\ncs-dashboard"),
        (Join-Path $RepoRoot "ncs-dashboard")
    )
    foreach ($candidate in $candidates) {
        if (-not [IO.Path]::IsPathRooted($candidate)) { $candidate = Join-Path $RepoRoot $candidate }
        $resolved = [IO.Path]::GetFullPath($candidate)
        if (Test-Path (Join-Path $resolved "package.json")) { return $resolved }
    }
    $entered = (Read-Host "Frontend project directory containing package.json").Trim('"').Trim()
    if (-not $entered) { return $null }
    if (-not [IO.Path]::IsPathRooted($entered)) { $entered = Join-Path $RepoRoot $entered }
    $resolved = [IO.Path]::GetFullPath($entered)
    if (Test-Path (Join-Path $resolved "package.json")) { return $resolved }
    return $null
}

try {
    $VmHost = Resolve-VmHost $VmHost
    if (-not $VmHost) { Fail "VM MySQL host/IP is required." }
    Write-Host "[1/5] Checking VM network: $VmHost`:$MysqlPort"
    $tcp = Test-NetConnection -ComputerName $VmHost -Port $MysqlPort -InformationLevel Quiet
    if (-not $tcp) { Fail "VM MySQL port is unreachable. Start the VM and check its network address." }

    Write-Host "[2/5] Checking Python 3.11/3.12"
    $basePython = Find-CompatiblePython

    if (-not (Test-Path $Python)) {
        Write-Host "[3/5] Creating project virtual environment with Python $($basePython.Version)"
        $arguments = @($basePython.Prefix) + @("-m", "venv", (Join-Path $RepoRoot ".venv"))
        & $basePython.Executable @arguments
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Python)) {
            Fail "Project Python environment was not created."
        }
    }
    if (-not $SkipDependencyInstall) {
        Write-Host "[3/5] Installing Flask, PyMySQL and project dependencies"
        & $Python -m pip install -e ".[mysql,prediction]"
        if ($LASTEXITCODE -ne 0) { Fail "Project dependency installation failed." }
    }
    & $Python -c "import flask, pymysql, numpy, torch, ncs_backend" 2>$null
    if ($LASTEXITCODE -ne 0) { Fail "Flask, PyMySQL, NumPy, PyTorch or the backend package is unavailable in ./.venv." }

    $FrontendDir = Resolve-FrontendDirectory $FrontendDir
    if (-not $FrontendDir) { Fail "Frontend package.json was not found. Pass -FrontendDir or enter its directory." }
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) { $npmCommand = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $npmCommand) { Fail "Node.js/npm was not found. Install Node.js 23+ first." }
    Write-Host "[3/5] Installing frontend dependencies in $FrontendDir"
    Push-Location $FrontendDir
    try {
        $npmProcess = Start-Process -FilePath $npmCommand.Source -ArgumentList @("install") -WorkingDirectory $FrontendDir -NoNewWindow -Wait -PassThru
        if ($npmProcess.ExitCode -ne 0) { Fail "Frontend dependency installation failed." }
    }
    finally {
        Pop-Location
    }

    Write-Host "[4/5] Checking required MySQL recovery mode and creating database"
    & $Python (Join-Path $RepoRoot "scripts\bootstrap_mysql_recovery.py") --host $VmHost --port $MysqlPort --database $Database --check-only
    if ($LASTEXITCODE -ne 0) { Fail "MySQL recovery-mode connection check failed." }
    & $Python (Join-Path $RepoRoot "scripts\bootstrap_mysql_recovery.py") --host $VmHost --port $MysqlPort --database $Database
    if ($LASTEXITCODE -ne 0) { Fail "Database creation failed." }

    $databaseUrl = & $Python -c "from scripts.bootstrap_mysql_recovery import connection_url; print(connection_url('$VmHost', $MysqlPort, '$Database'))"
    if ($LASTEXITCODE -ne 0 -or -not $databaseUrl) { Fail "Failed to build the recovery-mode database URL." }

    Write-Host "[5/5] Applying schema and verifying stable views"
    & $Python (Join-Path $RepoRoot "scripts\setup_mysql_ads.py") --initialize --url $databaseUrl
    if ($LASTEXITCODE -ne 0) { Fail "Schema initialization failed." }
    & $Python (Join-Path $RepoRoot "scripts\verify_mysql_ads.py") --url $databaseUrl
    if ($LASTEXITCODE -ne 0) { Fail "MySQL schema or view verification failed." }

    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
    $lines = @(
        "NCS_VM_HOST=$VmHost",
        "NCS_FRONTEND_DIR=$FrontendDir",
        "NCS_DATABASE_URL=$databaseUrl",
        "NCS_MYSQL_SECURITY_MODE=recovery_root",
        "NCS_QUERY_HOST=127.0.0.1",
        "NCS_QUERY_PORT=5000",
        "NCS_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173"
    )
    [IO.File]::WriteAllLines($ConfigPath, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "READY: recovery-mode MySQL schema and views are ready." -ForegroundColor Green
    Write-Host "Local config written to $ConfigPath (Git ignored)."
}
finally {
    Pop-Location
}
