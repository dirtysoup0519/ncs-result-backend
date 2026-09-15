"""Scenario tests for scripts/shell/sync_ads_once.sh.

A stub Python interpreter replaces the real import/prediction commands so the
exit-code contract (30/40/50), marker selection, retry counting, and the
_SUCCESS directory mode can be exercised end to end in a sandbox.
"""

import os
import shutil
import stat
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "scripts" / "shell" / "sync_ads_once.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("flock") is None,
    reason="sync_ads_once.sh takes a flock lock; run on Linux (util-linux) to exercise these",
)

STUB_PYTHON = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import os
    import sys

    args = sys.argv[1:]
    if args and args[0] == "-c":
        sys.exit(0)  # version preflight call

    is_prediction = "--model-package" in args
    call_log = os.environ["STUB_CALL_LOG"]
    with open(call_log, "a", encoding="utf-8") as fh:
        fh.write("predict\\n" if is_prediction else "import\\n")

    if is_prediction:
        fail_times = int(os.environ.get("STUB_PREDICT_FAIL_TIMES", "0"))
        done = sum(1 for line in open(call_log, encoding="utf-8") if line.strip() == "predict")
        sys.exit(50 if done <= fail_times else 0)
    sys.exit(int(os.environ.get("STUB_IMPORT_EXIT", "0")))
    """
)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "ads_exchange"
    for sub in ("ready", "archive", "rejected", "logs", "locks"):
        (root / sub).mkdir(parents=True)
    stub = tmp_path / "stub_python"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    values = {
        "NCS_REPO": str(fake_repo),
        "NCS_DATABASE_URL": "mysql+pymysql://root@127.0.0.1:3306/ncs_analytics",
        "NCS_ADS_EXCHANGE_ROOT": str(root),
        "NCS_PYTHON_BIN": str(stub),
        "NCS_ADS_SYNC_MAX_ATTEMPTS": "3",
        "STUB_CALL_LOG": str(tmp_path / "calls.log"),
        "STUB_IMPORT_EXIT": "0",
        "STUB_PREDICT_FAIL_TIMES": "0",
        "NCS_LOG_TZ": "UTC",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    values["root"] = root
    return values


def _make_zip(root: Path, name: str, mtime: float | None = None) -> Path:
    """A real (minimal) zip archive with one manifest.json inside."""
    import zipfile

    package = root / "ready" / name
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("contract_v2/manifest.json", "{}")
    if mtime is not None:
        os.utime(package, (mtime, mtime))
    return package


def _run_sync(env) -> int:
    run_env = dict(os.environ)
    for key, value in env.items():
        if key != "root":
            run_env[key] = str(value)
    result = subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
        env=run_env,
    )
    return result.returncode


def _calls(env) -> list[str]:
    log = Path(env["STUB_CALL_LOG"])
    if not log.exists():
        return []
    return [line.strip() for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_unfinished_oldest_package_does_not_block(env):
    root = env["root"]
    now = time.time()
    _make_zip(root, "old.zip", mtime=now - 600)  # no marker, still uploading
    _make_zip(root, "new.zip", mtime=now - 60).with_name("new.zip.ready").write_text("")

    code = _run_sync(env)

    assert code == 0
    assert (root / "archive" / "new.zip").exists()
    assert (root / "archive" / "new.zip.ready").exists()
    assert (root / "ready" / "old.zip").exists()  # untouched, still waiting


def test_import_exit_30_rejects_immediately(env):
    root = env["root"]
    _make_zip(root, "bad.zip").with_name("bad.zip.ready").write_text("")
    env["STUB_IMPORT_EXIT"] = "30"

    code = _run_sync(env)

    assert code == 30
    assert (root / "rejected" / "bad.zip").exists()
    assert (root / "rejected" / "bad.zip.ready").exists()
    assert not (root / "ready" / "bad.zip").exists()


def test_import_exit_40_retries_then_rejects(env):
    root = env["root"]
    env["STUB_IMPORT_EXIT"] = "40"
    _make_zip(root, "pkg.zip").with_name("pkg.zip.ready").write_text("")

    first = _run_sync(env)
    assert first == 40
    assert (root / "ready" / "pkg.zip").exists()  # stays for retry
    assert (root / "ready" / "pkg.zip.attempts").read_text().strip() == "1"

    second = _run_sync(env)
    assert second == 40  # attempts=2 < 3, still retrying
    assert (root / "ready" / "pkg.zip").exists()
    assert (root / "ready" / "pkg.zip.attempts").read_text().strip() == "2"

    third = _run_sync(env)
    assert third == 40
    assert (root / "rejected" / "pkg.zip").exists()  # limit reached
    assert not (root / "ready" / "pkg.zip.attempts").exists()


def test_prediction_failure_retries_prediction_only(env):
    root = env["root"]
    env["NCS_MODEL_PACKAGE"] = str(Path(env["NCS_REPO"]) / "model")
    env["STUB_PREDICT_FAIL_TIMES"] = "2"  # fail twice, succeed on 3rd
    _make_zip(root, "pkg.zip").with_name("pkg.zip.ready").write_text("")

    first = _run_sync(env)
    assert first == 50
    assert (root / "ready" / "pkg.zip").exists()  # kept for retry
    assert (root / "ready" / "pkg.zip.ready.predict").exists()
    assert _calls(env).count("import") == 1
    assert _calls(env).count("predict") == 1

    second = _run_sync(env)
    assert second == 50
    assert _calls(env).count("import") == 1  # import NOT re-run after publish
    assert _calls(env).count("predict") == 2

    third = _run_sync(env)
    assert third == 0  # prediction recovered
    assert (root / "archive" / "pkg.zip").exists()
    assert (root / "archive" / "pkg.zip.ready").exists()
    assert not (root / "ready" / "pkg.zip.attempts").exists()


def test_prediction_retry_limit_archives_not_rejects(env):
    root = env["root"]
    env["NCS_MODEL_PACKAGE"] = str(Path(env["NCS_REPO"]) / "model")
    env["STUB_PREDICT_FAIL_TIMES"] = "99"  # always fail
    env["NCS_ADS_SYNC_MAX_ATTEMPTS"] = "2"
    _make_zip(root, "pkg.zip").with_name("pkg.zip.ready").write_text("")

    assert _run_sync(env) == 50
    assert (root / "ready" / "pkg.zip.ready.predict").exists()

    final = _run_sync(env)
    assert final == 50
    assert (root / "archive" / "pkg.zip").exists()  # ADS published, so archive
    assert not (root / "rejected" / "pkg.zip").exists()


def test_success_directory_mode(env):
    root = env["root"]
    batch = root / "ready" / "batch-001"
    (batch / "contract_v2").mkdir(parents=True)
    (batch / "contract_v2" / "manifest.json").write_text("{}", encoding="utf-8")
    (batch / "_SUCCESS").write_text("", encoding="utf-8")

    code = _run_sync(env)

    assert code == 0
    assert (root / "archive" / "batch-001" / "_SUCCESS").exists()
    assert _calls(env) == ["import"]


def test_success_zip_flow_archives_and_clears_attempts(env):
    root = env["root"]
    _make_zip(root, "ok.zip").with_name("ok.zip.ready").write_text("")
    (root / "ready" / "ok.zip.attempts").write_text("2", encoding="utf-8")

    code = _run_sync(env)

    assert code == 0
    assert (root / "archive" / "ok.zip").exists()
    assert not (root / "ready" / "ok.zip.attempts").exists()
    assert _calls(env) == ["import"]
