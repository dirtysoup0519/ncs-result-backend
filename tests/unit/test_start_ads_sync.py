"""Scenario tests for scripts/shell/start_ads_sync.sh (zero-config bootstrap)."""

import os
import signal
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "scripts" / "shell" / "start_ads_sync.sh"

STUB_PYTHON = (
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "args = sys.argv[1:]\n"
    "if args and args[0] == '-c':\n"
    "    sys.exit(0)\n"
    "sys.exit(0)\n"
)


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
    return values


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


def test_fresh_machine_honors_db_url(env):
    env_file = Path(env["env_file"])

    result = _run(env, "--env", str(env_file), "--db-url", "mysql+pymysql://root@10.0.0.5:3306/ncs_analytics", "--once")

    assert result.returncode == 0
    assert "NCS_DATABASE_URL='mysql+pymysql://root@10.0.0.5:3306/ncs_analytics'" in env_file.read_text(encoding="utf-8")


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

    duplicate = _run(env, "--env", str(env["env_file"]), "--detach")
    assert duplicate.returncode == 1
    assert "already running" in duplicate.stdout

    stop = _run(env, "--env", str(env["env_file"]), "--stop")
    assert stop.returncode == 0
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)
        pytest.fail("watcher did not stop")
    assert not pid_file.exists()
