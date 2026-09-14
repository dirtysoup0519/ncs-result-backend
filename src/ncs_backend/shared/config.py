"""Environment-backed configuration with no external side effects."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str | None = None
    db_console_host: str = "127.0.0.1"
    db_console_port: int = 5002
    db_console_max_rows: int = 500
    db_runtime_mode: str = "unmanaged"
    db_service_name: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("NCS_DATABASE_URL") or None
        return cls(
            environment=os.getenv("NCS_ENV", "development"),
            log_level=os.getenv("NCS_LOG_LEVEL", "INFO").upper(),
            database_url=database_url,
            db_console_host=os.getenv("NCS_DB_CONSOLE_HOST", "127.0.0.1"),
            db_console_port=int(os.getenv("NCS_DB_CONSOLE_PORT", "5002")),
            db_console_max_rows=int(os.getenv("NCS_DB_CONSOLE_MAX_ROWS", "500")),
            db_runtime_mode=os.getenv("NCS_DB_RUNTIME_MODE", "unmanaged"),
            db_service_name=os.getenv("NCS_DB_SERVICE_NAME", ""),
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)
