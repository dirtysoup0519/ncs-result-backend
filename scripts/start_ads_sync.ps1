param(
    [string]$Action = "help",
    [string]$Package = "",
    [string]$Vm = ""
)

# Windows-side driver for the VM ADS sync watcher (README section 3.11).
# Requires the Windows OpenSSH client (ssh/scp) and the VM SSH account.
# IMPORTANT: keep this file ASCII-only; Windows PowerShell 5.1 misparses
# non-ASCII text in BOM-less files.
#
#   start_ads_sync.cmd                        connection check + help
#   start_ads_sync.cmd once                   run one sync round on the VM
#   start_ads_sync.cmd start                  start the watcher in background
#   start_ads_sync.cmd stop                   stop the watcher
#   start_ads_sync.cmd status                 watcher process + recent log
#   start_ads_sync.cmd log                    tail the sync log
#   start_ads_sync.cmd put <zip-path>         upload a package into ready/
#                                             and create its .ready marker
#
# The VM address (user@host) is saved to .local\vm_ads.env on first use;
# override per call with -Vm "hadoop@192.168.176.100".

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepoRoot ".local\vm_ads.env"

function Fail([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

if ($Vm -eq "") {
    if (Test-Path $ConfigPath) {
        $Vm = (Get-Content -LiteralPath $ConfigPath | Select-Object -First 1).Trim()
    } else {
        $Vm = Read-Host "VM SSH address (user@IP, e.g. hadoop@192.168.176.100)"
        if ([string]::IsNullOrWhiteSpace($Vm)) { Fail "VM address is required" }
        $dir = Split-Path -Parent $ConfigPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        Set-Content -LiteralPath $ConfigPath -Value $Vm -Encoding ASCII
        Write-Host "[OK] VM address saved to $ConfigPath" -ForegroundColor Green
    }
}
if ($Vm -notmatch "^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$") {
    Fail "VM address must look like user@IP, got: $Vm"
}

function Invoke-OnVm([string]$RemoteCommand) {
    ssh $Vm $RemoteCommand
    if ($LASTEXITCODE -ne 0) { Fail "remote command failed (exit $LASTEXITCODE): $RemoteCommand" }
}

$RepoDir = "~/ncs-result-backend"
$Runner = "$RepoDir/scripts/shell/start_ads_sync.sh"
$Exchange = "~/ncs-ads-exchange"

switch ($Action.ToLower()) {
    "help" {
        ssh $Vm "echo '=== VM connection OK ==='; test -d $RepoDir && echo '=== repo copy found ===' || echo '!!! repo copy missing on VM, transfer it first (README 3.11)'; test -f $Runner && echo '=== sync runner ready ===' || echo '!!! runner missing, git pull latest main'" 2>$null
        if ($LASTEXITCODE -ne 0) { Fail "cannot reach $Vm (check network, sshd, address format)" }
        Write-Host ""
        Write-Host "usage: start_ads_sync.cmd <action> [-Vm user@IP]"
        Write-Host "  once    run one sync round on the VM"
        Write-Host "  start   start the watcher in background (single-instance guarded)"
        Write-Host "  stop    stop the watcher"
        Write-Host "  status  show watcher process and recent log"
        Write-Host "  log     tail the last 30 sync log lines"
        Write-Host "  put     upload a package: start_ads_sync.cmd put D:\path\pkg.zip"
    }
    "once"  { Invoke-OnVm "$Runner --once" }
    "start" { Invoke-OnVm "$Runner --detach" }
    "stop"  { Invoke-OnVm "$Runner --stop" }
    "log"   { Invoke-OnVm "tail -n 30 $Exchange/logs/sync_ads.log" }
    "status" {
        Invoke-OnVm "pgrep -af watch_ads.sh || echo '(watcher not running)'"
        Invoke-OnVm "tail -n 10 $Exchange/logs/sync_ads.log 2>/dev/null || echo '(no log yet)'"
    }
    "put" {
        if ($Package -eq "" -or -not (Test-Path $Package)) { Fail "put needs an existing package path, e.g. start_ads_sync.cmd put D:\SHIJIAN\SPARK\ads-v32.zip" }
        $name = Split-Path -Leaf $Package
        if ($name -notmatch "\.(zip|tar\.gz)$") { Fail "only .zip / .tar.gz packages are supported: $name" }
        Invoke-OnVm "mkdir -p $Exchange/ready $Exchange/logs $Exchange/locks"
        Write-Host "uploading $name ..." -ForegroundColor Cyan
        scp $Package "${Vm}:$Exchange/ready/"
        if ($LASTEXITCODE -ne 0) { Fail "scp upload failed" }
        Invoke-OnVm "touch $Exchange/ready/'$name'.ready && ls -lh $Exchange/ready/"
        Write-Host "[OK] package staged with .ready marker. run: start_ads_sync.cmd once" -ForegroundColor Green
    }
    default { Fail "unknown action: $Action (help/once/start/stop/log/status/put)" }
}
