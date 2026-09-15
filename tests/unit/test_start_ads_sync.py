"""Scenario tests for scripts/shell/start_ads_sync.sh (zero-config bootstrap)."""

import os
import shutil
import signal
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "scripts" / "shell" / "start_ads_sync.sh"
IS_WINDOWS = os.name == "nt"

# The --once path runs sync_ads_once.sh, which needs a real flock(1).
requires_flock = pytest.mark.skipif(
    shutil.which("flock") is None,
    reason="sync_ads_once.sh takes a flock lock; run on Linux (util-linux) to exercise these",
)

# Every test here drives start_ads_sync.sh through bash.  Without it on PATH the
# spawn dies with FileNotFoundError, which reads as a regression rather than as a
# missing prerequisite -- and on Windows bash is present only when Git Bash's
# bin directory happens to be on PATH.
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="these tests drive scripts/shell/*.sh through bash, which is not on PATH",
)

STUB_PYTHON = (
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "args = sys.argv[1:]\n"
    "if args and args[0] == '-c':\n"
    "    sys.exit(0)\n"
    "sys.exit(0)\n"
)


def _watcher_pid(exchange: Path) -> int | None:
    try:
        return int((exchange / "locks" / "watch_ads.pid").read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    """Liveness probe for a pid that came from `echo $!` inside a shell script.

    On Windows that pid lives in the MSYS pid space, not the Windows one
    (`ps -W` shows e.g. bash pid 1381 -> winpid 37856), so os.kill cannot be
    used on it at all: os.kill(pid, 0) on Windows *terminates* whichever
    process owns that Windows pid, and only CTRL_C_EVENT/CTRL_BREAK_EVENT are
    special-cased. Probe with the shell that owns the pid instead.
    """
    if IS_WINDOWS:
        result = subprocess.run(["bash", "-c", f"kill -0 {pid}"], capture_output=True, text=True)
        return result.returncode == 0
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _force_kill(pid: int, timeout: float = 5.0) -> None:
    """Stop a watcher: TERM first so its own trap can take the per-round
    `sleep` child down with it, then force. Cleaning up the child from here
    is not enough on its own -- seeing it die makes the watcher advance to the
    next round and spawn a fresh one before we get to the parent."""
    if IS_WINDOWS:
        subprocess.run(["bash", "-c", f"kill -TERM {pid}"], capture_output=True, text=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

    deadline = time.time() + timeout
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    if not _pid_alive(pid):
        return

    if IS_WINDOWS:
        # SIGKILL cannot be trapped, so the child has to be reaped from here.
        # Children first: MSYS re-parents them the moment the parent dies.
        # `taskkill /T` does not work for this -- the Windows parent recorded
        # for an MSYS child is not the watcher's pid.
        subprocess.run(
            ["bash", "-c", f"ps -W | awk '$2=={pid} {{print $1}}' | xargs -r kill -9"],
            capture_output=True,
            text=True,
        )
        subprocess.run(["bash", "-c", f"kill -9 {pid}"], capture_output=True, text=True)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# Watchers a test started, kept so teardown can still reap their children
# after the script's own --stop has already removed the pid file.
STARTED_WATCHERS: list[int] = []


def _kill_watcher(exchange: Path, timeout: float = 10.0) -> None:
    pids = [*STARTED_WATCHERS]
    pid = _watcher_pid(exchange)
    if pid is not None:
        pids.append(pid)
    STARTED_WATCHERS.clear()
    for pid in pids:
        _force_kill(pid, timeout)  # no-op for a pid that already exited


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path
    exchange = root / "exchange"
    env_file = root / "ads-sync.env"
    stub = root / "stub-python"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | 0o111)

    values = {
        "env_file": str(env_file),
        "root": exchange,
        "NCS_PIP_INSTALL": "0",
        "NCS_ADS_EXCHANGE_ROOT": str(exchange),  # never touch the network from tests
    }
    for key, value in values.items():
        if key.startswith("NCS_"):
            monkeypatch.setenv(key, value)
    yield values
    # The detached watcher outlives the pytest process: if a test fails before
    # running --stop, it would keep looping every 30s forever, recreating the
    # exchange tree under the temp dir (or, when the root is mangled, inside
    # the repo). Never let one escape.
    _kill_watcher(exchange)


def _make_env_file(env, extra: dict[str, str] | None = None) -> Path:
    lines = [
        f"export NCS_REPO='{REPO_ROOT}'",
        "export NCS_DATABASE_URL='mysql+pymysql://root@127.0.0.1:3306/ncs_analytics'",
        f"export NCS_ADS_EXCHANGE_ROOT='{Path(env['env_file']).parent / 'exchange'}'",
        f"export NCS_PYTHON_BIN='{Path(env['env_file']).parent / 'stub-python'}'",
        "export NCS_LOG_TZ='Asia/Shanghai'",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"export {key}='{value}'")
    path = Path(env["env_file"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(env, *args) -> subprocess.CompletedProcess:
    run_env = {k: str(v) for k, v in os.environ.items()}
    for key, value in env.items():
        if key.startswith("NCS_"):
            run_env[key] = str(value)
    return subprocess.run(
        ["bash", str(START_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=run_env,
    )


def _dirs_exist(exchange: Path) -> bool:
    return all((exchange / name).is_dir() for name in ("ready", "processing", "archive", "rejected", "logs", "locks"))


@requires_flock
def test_fresh_machine_generates_env_and_runs_once(env):
    env_file = Path(env["env_file"])
    assert not env_file.exists()

    result = _run(env, "--env", str(env_file), "--once")

    assert result.returncode == 0, result.stderr
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert f"NCS_REPO='{REPO_ROOT}'" in content
    assert "NCS_DATABASE_URL='mysql+pymysql://root@127.0.0.1:3306/ncs_analytics'" in content
    assert "NCS_PYTHON_BIN=" in content
    assert "NCS_LOG_TZ='Asia/Shanghai'" in content
    assert _dirs_exist(Path(env["root"]))
    assert "sync_ads_once exit=0" in result.stdout


@requires_flock
def test_fresh_machine_honors_db_url(env):
    env_file = Path(env["env_file"])

    result = _run(env, "--env", str(env_file), "--db-url", "mysql+pymysql://root@10.0.0.5:3306/ncs_analytics", "--once")

    assert result.returncode == 0
    assert "NCS_DATABASE_URL='mysql+pymysql://root@10.0.0.5:3306/ncs_analytics'" in env_file.read_text(encoding="utf-8")


@requires_flock
def test_existing_env_with_stub_python_once(env):
    _make_env_file(env)

    result = _run(env, "--env", str(env["env_file"]), "--once")

    assert result.returncode == 0
    assert _dirs_exist(Path(env["root"]))


def test_stop_without_watcher_fails_cleanly(env):
    _make_env_file(env)

    result = _run(env, "--env", str(env["env_file"]), "--stop")

    assert result.returncode == 1
    assert "not running" in result.stdout


def test_detach_start_twice_and_stop(env):
    _make_env_file(env)

    result = _run(env, "--env", str(env["env_file"]), "--detach")
    assert result.returncode == 0

    pid_file = Path(env["root"]) / "locks" / "watch_ads.pid"
    deadline = time.time() + 5
    while time.time() < deadline and not pid_file.exists():
        time.sleep(0.1)
    assert pid_file.exists()
    pid = int(pid_file.read_text().strip())
    STARTED_WATCHERS.append(pid)

    duplicate = _run(env, "--env", str(env["env_file"]), "--detach")
    assert duplicate.returncode == 1
    assert "already running" in duplicate.stdout

    stop = _run(env, "--env", str(env["env_file"]), "--stop")
    assert stop.returncode == 0
    deadline = time.time() + 5
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    if _pid_alive(pid):
        pytest.fail("watcher did not stop")  # teardown reaps it
    assert not pid_file.exists()
