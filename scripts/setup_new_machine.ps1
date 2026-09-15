param(
    [string]$VmHost = "192.168.176.100",
    [int]$MysqlPort = 3306,
    [string]$Database = "ncs_analytics",
    [string]$AccountHost = "%",
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

Write-Host "[1/6] Checking VM network: $VmHost`:$MysqlPort"
$tcp = Test-NetConnection -ComputerName $VmHost -Port $MysqlPort -InformationLevel Quiet
if (-not $tcp) { Fail "VM MySQL port is unreachable. Start the VM and check its network address." }

Write-Host "[2/6] Checking Python 3.11/3.12"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { Fail "Python was not found in PATH." }
$pythonVersion = & $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($pythonVersion -notin @("3.11", "3.12")) { Fail "Python 3.11 or 3.12 is required; found $pythonVersion." }

if (-not (Test-Path $Python)) {
    Write-Host "[3/6] Creating project virtual environment"
    & $pythonCommand.Source -m venv (Join-Path $RepoRoot ".venv")
}
if (-not $SkipDependencyInstall) {
    Write-Host "[3/6] Installing MySQL and project dependencies"
    & $Python -m pip install -e ".[mysql]"
}
if (-not (Test-Path $Python)) { Fail "Project Python environment was not created." }

Write-Host "[4/6] Enter passwords (input is hidden and never committed)"
$rootSecure = Read-Host "MySQL root password" -AsSecureString
$migratorSecure = Read-Host "ncs_ads_migrator password" -AsSecureString
$adminSecure = Read-Host "ncs_ads_admin password" -AsSecureString
$readerSecure = Read-Host "ncs_ads_reader password" -AsSecureString
function Plain([Security.SecureString]$Value) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
$env:NCS_BOOTSTRAP_ROOT_PASSWORD = Plain $rootSecure
$env:NCS_BOOTSTRAP_MIGRATOR_PASSWORD = Plain $migratorSecure
$env:NCS_BOOTSTRAP_ADMIN_PASSWORD = Plain $adminSecure
$env:NCS_BOOTSTRAP_READER_PASSWORD = Plain $readerSecure

try {
    Write-Host "[5/6] Checking MySQL login before any database change"
    & $Python (Join-Path $RepoRoot "scripts\bootstrap_mysql_users.py") --host $VmHost --port $MysqlPort --database $Database --account-host $AccountHost --check-only
    if ($LASTEXITCODE -ne 0) { Fail "MySQL root login check failed." }

    Write-Host "[6/6] Creating database, users, schema, grants and local config"
    & $Python (Join-Path $RepoRoot "scripts\bootstrap_mysql_users.py") --host $VmHost --port $MysqlPort --database $Database --account-host $AccountHost
    if ($LASTEXITCODE -ne 0) { Fail "Database or account creation failed." }

    $rootUrl = & $Python -c "from scripts.bootstrap_mysql_users import connection_url; import os; print(connection_url('root', os.environ['NCS_BOOTSTRAP_ROOT_PASSWORD'], '$VmHost', $MysqlPort, '$Database'))"
    $migratorUrl = & $Python -c "from scripts.bootstrap_mysql_users import connection_url; import os; print(connection_url('ncs_ads_migrator', os.environ['NCS_BOOTSTRAP_MIGRATOR_PASSWORD'], '$VmHost', $MysqlPort, '$Database'))"
    $adminUrl = & $Python -c "from scripts.bootstrap_mysql_users import connection_url; import os; print(connection_url('ncs_ads_admin', os.environ['NCS_BOOTSTRAP_ADMIN_PASSWORD'], '$VmHost', $MysqlPort, '$Database'))"
    $readerUrl = & $Python -c "from scripts.bootstrap_mysql_users import connection_url; import os; print(connection_url('ncs_ads_reader', os.environ['NCS_BOOTSTRAP_READER_PASSWORD'], '$VmHost', $MysqlPort, '$Database'))"

    $env:NCS_MYSQL_MIGRATOR_URL = $migratorUrl
    $env:NCS_MYSQL_ADMIN_URL = $adminUrl
    $env:NCS_MYSQL_READER_URL = $readerUrl
    & $Python (Join-Path $RepoRoot "scripts\setup_mysql_ads.py") --initialize --migrator-url $migratorUrl
    if ($LASTEXITCODE -ne 0) { Fail "Schema initialization failed." }
    & $Python (Join-Path $RepoRoot "scripts\setup_mysql_ads.py") --grant-reader --privileged-url $rootUrl --reader-host $AccountHost --reader-account ncs_ads_reader
    if ($LASTEXITCODE -ne 0) { Fail "Reader view grants failed." }
    & $Python (Join-Path $RepoRoot "scripts\setup_mysql_ads.py") --verify --migrator-url $migratorUrl --admin-url $adminUrl --reader-url $readerUrl
    if ($LASTEXITCODE -ne 0) { Fail "Account permission verification failed." }

    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
    $lines = @(
        "NCS_DATABASE_URL=$readerUrl",
        "NCS_MYSQL_MIGRATOR_URL=$migratorUrl",
        "NCS_MYSQL_ADMIN_URL=$adminUrl",
        "NCS_MYSQL_READER_URL=$readerUrl",
        "NCS_QUERY_HOST=127.0.0.1",
        "NCS_QUERY_PORT=5000",
        "NCS_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173"
    )
    Set-Content -LiteralPath $ConfigPath -Value $lines -Encoding utf8
    Write-Host "READY: MySQL schema, accounts and grants are ready." -ForegroundColor Green
    Write-Host "Local config written to $ConfigPath (Git ignored)."
}
finally {
    Remove-Item Env:NCS_BOOTSTRAP_ROOT_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_BOOTSTRAP_MIGRATOR_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_BOOTSTRAP_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_BOOTSTRAP_READER_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_MYSQL_MIGRATOR_URL -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_MYSQL_ADMIN_URL -ErrorAction SilentlyContinue
    Remove-Item Env:NCS_MYSQL_READER_URL -ErrorAction SilentlyContinue
    Pop-Location
}
