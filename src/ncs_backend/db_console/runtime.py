"""Database runtime adapters used by the local database console."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import re
import subprocess
from time import monotonic, sleep
from typing import Protocol


class DatabaseRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DatabaseRuntime(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def start_stop_supported(self) -> bool: ...

    def status(self) -> str: ...

    def start(self) -> str: ...

    def stop(self) -> str: ...

    def restart(self) -> str: ...


class UnmanagedDatabaseRuntime:
    mode = "unmanaged"
    start_stop_supported = False

    def status(self) -> str:
        return "UNKNOWN"

    def start(self) -> str:
        raise DatabaseRuntimeError("DB_RUNTIME_NOT_MANAGED", "当前数据库由外部环境管理，不能从本工具启停")

    stop = start
    restart = start


CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


class WindowsServiceDatabaseRuntime:
    mode = "windows_service"
    start_stop_supported = True

    def __init__(
        self,
        service_name: str,
        *,
        runner: CommandRunner | None = None,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
        timeout_seconds: float = 20.0,
        poll_interval: float = 0.5,
    ) -> None:
        if not service_name or any(char.isspace() for char in service_name):
            raise ValueError("service_name must be a single non-empty token")
        self.service_name = service_name
        self._runner = runner or _run_command
        self._sleeper = sleeper
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._poll_interval = poll_interval

    def status(self) -> str:
        result = self._run(["sc.exe", "query", self.service_name])
        if result.returncode != 0:
            return "UNKNOWN"
        match = re.search(r"STATE\s*:\s*\d+\s+(\w+)", result.stdout.upper())
        return {
            "RUNNING": "RUNNING",
            "STOPPED": "STOPPED",
            "START_PENDING": "STARTING",
            "STOP_PENDING": "STOPPING",
        }.get(match.group(1), "UNKNOWN") if match else "UNKNOWN"

    def start(self) -> str:
        return self._change("start", "RUNNING", "STARTING")

    def stop(self) -> str:
        return self._change("stop", "STOPPED", "STOPPING")

    def restart(self) -> str:
        if self.status() == "RUNNING":
            self.stop()
        return self.start()

    def _change(self, command: str, expected: str, pending: str) -> str:
        current = self.status()
        if current == expected:
            return current
        result = self._run(["sc.exe", command, self.service_name])
        if result.returncode != 0:
            raise DatabaseRuntimeError("DB_RUNTIME_COMMAND_FAILED", _command_message(result))
        deadline = self._clock() + self._timeout_seconds
        while self._clock() <= deadline:
            current = self.status()
            if current == expected:
                return current
            self._sleeper(self._poll_interval)
        raise DatabaseRuntimeError("DB_RUNTIME_TIMEOUT", f"数据库服务未在 {self._timeout_seconds:g} 秒内进入 {expected}")

    def _run(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(args, self._timeout_seconds)
        except FileNotFoundError as exc:
            raise DatabaseRuntimeError("DB_RUNTIME_UNAVAILABLE", "找不到 sc.exe") from exc
        except subprocess.TimeoutExpired as exc:
            raise DatabaseRuntimeError("DB_RUNTIME_TIMEOUT", "数据库服务命令执行超时") from exc


def _run_command(args: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _command_message(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "service command failed").strip()
    return output[:300]
