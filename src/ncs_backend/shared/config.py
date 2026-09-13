"""Environment-backed configuration with no external side effects."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("NCS_DATABASE_URL") or None
        return cls(
            environment=os.getenv("NCS_ENV", "development"),
            log_level=os.getenv("NCS_LOG_LEVEL", "INFO").upper(),
            database_url=database_url,
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)
