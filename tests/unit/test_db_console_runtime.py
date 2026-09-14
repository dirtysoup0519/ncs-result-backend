import subprocess

import pytest

from ncs_backend.db_console.runtime import (
    DatabaseRuntimeError,
    UnmanagedDatabaseRuntime,
    WindowsServiceDatabaseRuntime,
)


def test_unmanaged_runtime_rejects_actions():
    runtime = UnmanagedDatabaseRuntime()
    assert runtime.status() == "UNKNOWN"
    with pytest.raises(DatabaseRuntimeError) as error:
        runtime.start()
    assert error.value.code == "DB_RUNTIME_NOT_MANAGED"


def test_windows_runtime_parses_status_and_uses_fixed_service_name():
    calls = []

    def runner(args, timeout):
        calls.append((list(args), timeout))
        return subprocess.CompletedProcess(args, 0, "STATE : 4  RUNNING\r\n", "")

    runtime = WindowsServiceDatabaseRuntime("MySQL80", runner=runner, sleeper=lambda _: None)

    assert runtime.status() == "RUNNING"
    assert runtime.start() == "RUNNING"
    assert all(call[0] == ["sc.exe", "query", "MySQL80"] for call in calls)


def test_windows_runtime_rejects_service_names_with_spaces():
    with pytest.raises(ValueError):
        WindowsServiceDatabaseRuntime("My SQL")
