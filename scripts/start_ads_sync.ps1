param(
    [string]$Action = "help",
    [string]$Package = "",
    [string]$Vm = ""
)

# Windows-side driver for the VM ADS sync watcher (README section 3.11).
# Requires Windows OpenSSH client and the VM SSH account.
#
#   start_ads_sync.cmd                       show status and help
#   start_ads_sync.cmd once                  run one sync round on the VM
#   start_ads_sync.cmd start                 start the watcher in background
#   start_ads_sync.cmd stop                  stop the watcher
#   start_ads_sync.cmd log                   tail the sync log
#   start_ads_sync.cmd put <zip路径>          上传包到 ready/ 并自动创建 .ready 标记
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
        $Vm = Read-Host "VM SSH 地址（格式 用户@IP，如 hadoop@192.168.176.100）"
        if ([string]::IsNullOrWhiteSpace($Vm)) { Fail "VM 地址不能为空" }
        $dir = Split-Path -Parent $ConfigPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        Set-Content -LiteralPath $ConfigPath -Value $Vm -Encoding ASCII
        Write-Host "[OK] 已保存 VM 地址到 $ConfigPath" -ForegroundColor Green
    }
}
if ($Vm -notmatch "^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$") {
    Fail "VM 地址格式应为 用户@IP，当前为: $Vm"
}

function Invoke-OnVm([string]$RemoteCommand) {
    ssh $Vm $RemoteCommand
    if ($LASTEXITCODE -ne 0) { Fail "远程命令失败（退出码 $LASTEXITCODE）: $RemoteCommand" }
}

$RepoDir = "~/ncs-result-backend"
$Runner = "$RepoDir/scripts/shell/start_ads_sync.sh"
$Exchange = "~/ncs-ads-exchange"

switch ($Action.ToLower()) {
    "help" {
        ssh $Vm "echo '=== VM 连接 OK ==='; test -d $RepoDir && echo '=== 仓库副本存在 ===' || echo '!!! VM 上还没有仓库副本，请先按 README 3.11 传送'; test -f $Runner && echo '=== 同步脚本就绪 ===' || echo '!!! 仓库副本缺同步脚本，需要 git pull 最新 main'" 2>$null
        if ($LASTEXITCODE -ne 0) { Fail "无法连接 $Vm（检查网络、sshd、地址格式）" }
        Write-Host ""
        Write-Host "用法: start_ads_sync.cmd <action> [-Vm 用户@IP]"
        Write-Host "  once    在 VM 上跑一轮同步"
        Write-Host "  start   后台启动监听（防双实例）"
        Write-Host "  stop    停止监听"
        Write-Host "  status  查看监听进程与最近日志"
        Write-Host "  log     查看最近 30 行同步日志"
        Write-Host "  put     上传数据包: start_ads_sync.cmd put D:\path\包.zip"
    }
    "once"  { Invoke-OnVm "$Runner --once" }
    "start" { Invoke-OnVm "$Runner --detach" }
    "stop"  { Invoke-OnVm "$Runner --stop" }
    "log"   { Invoke-OnVm "tail -n 30 $Exchange/logs/sync_ads.log" }
    "status" {
        Invoke-OnVm "pgrep -af watch_ads.sh || echo '(watcher 未运行)'"
        Invoke-OnVm "tail -n 10 $Exchange/logs/sync_ads.log 2>/dev/null || echo '(暂无日志)'"
    }
    "put" {
        if ($Package -eq "" -or -not (Test-Path $Package)) { Fail "put 需要一个存在的包路径，例如: start_ads_sync.cmd put D:\SHIJIAN\SPARK\ads-v32.zip" }
        $name = Split-Path -Leaf $Package
        if ($name -notmatch "\.(zip|tar\.gz)$") { Fail "只支持 .zip / .tar.gz 包: $name" }
        Invoke-OnVm "mkdir -p $Exchange/ready $Exchange/logs $Exchange/locks"
        Write-Host "上传 $name ..." -ForegroundColor Cyan
        scp $Package "${Vm}:$Exchange/ready/"
        if ($LASTEXITCODE -ne 0) { Fail "scp 上传失败" }
        Invoke-OnVm "touch $Exchange/ready/'$name'.ready && ls -lh $Exchange/ready/"
        Write-Host "[OK] 包已就位并带 .ready 标记。执行 start_ads_sync.cmd once 立即处理" -ForegroundColor Green
    }
    default { Fail "未知 action: $Action（可选 help/once/start/stop/log/status/put）" }
}
