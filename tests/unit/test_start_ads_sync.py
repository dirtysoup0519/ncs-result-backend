"""Scenario tests for scripts/shell/start_ads_sync.sh."""

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "scripts" / "shell" / "start_ads_sync.sh"

STUB_PYTHON = (
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "args = sys.argv[1:]\n"
    "sys.exit(0)  # preflight and any import/prediction call succeed\n"
)


def _write_env(root: Path, **overrides) -> Path:
    env_file = root / "ads-sync.env"
    values = {
        "NCS_REPO": str(root / "repo"),
        "NCS_DATABASE_URL": "mysql+pymysql://root@127.0.0.1:3306/ncs_analytics",
        "NCS_ADS_EXCHANGE_ROOT": str(root / "exchange"),
        "NCS_PYTHON_BIN": str(root / "stub-python"),
        "NCS_ADS_SYNC_INTERVAL_SECONDS": "1",
    }
    values.update(overrides)
    lines = [f"export {key}='{value}'" for key, value in values.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_file


@pytest.fixture()
def env(tmp_path, monkeypatch):
    (tmp_path / "repo").mkdir()
    (tmp_path / "exchange").mkdir()
    stub = tmp_path / "stub-python"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    env_file = _write_env(tmp_path)
    values = {
        "root": tmp_path,
        "env_file": str(env_file),
    }
    return values


def _run(env, *args):
    result = subprocess.run(
        ["bash", str(START_SCRIPT), "--env", env["env_file"], *args],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result


def test_missing_env_file_is_rejected(tmp_path):
    result = subprocess.run(
        ["bash", str(START_SCRIPT), "--env", str(tmp_path / "nope.env"), "--once"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert "env file not found" in result.stderr


def test_missing_required_variable_is_rejected(tmp_path):
    env_file = tmp_path / "ads-sync.env"
    env_file.write_text("export NCS_ADS_EXCHANGE_ROOT='/tmp/x'\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(START_SCRIPT), "--env", str(env_file), "--once"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "NCS_REPO" in result.stderr


def test_once_runs_single_round_and_creates_directories(env):
    result = _run(env, "--once")

    assert result.returncode == 0
    assert "sync_ads_once exit=0" in result.stdout
    exchange = Path(env["env_file"]).parent / "exchange"
    for name in ("ready", "archive", "rejected", "logs", "locks"):
        assert (exchange / name).is_dir()


def test_detach_start_twice_and_stop(env):
    result = _run(env, "--detach")
    assert result.returncode == 0

    exchange = Path(env["env_file"]).parent / "exchange"
    pid_file = exchange / "locks" / "watch_ads.pid"
    deadline = time.time() + 5
    while time.time() < deadline and not pid_file.exists():
        time.sleep(0.1)
    assert pid_file.exists()
    pid = int(pid_file.read_text().strip())

    # Second detach must refuse to start a duplicate watcher.
    duplicate = _run(env, "--detach")
    assert duplicate.returncode == 1
    assert "already running" in duplicate.stderr

    stop = _run(env, "--stop")
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
