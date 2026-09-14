"""Small DB-API connection factories for the database console."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import unquote, urlsplit

ConnectionFactory = Callable[[], Any]


def connection_factory_from_url(database_url: str) -> ConnectionFactory:
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("database URL is required")
    parsed = urlsplit(database_url.strip())
    if parsed.scheme == "sqlite":
        path = _sqlite_path(parsed)

        def connect_sqlite():
            return sqlite3.connect(path)

        return connect_sqlite

    if parsed.scheme in {"mysql", "mysql+pymysql"}:
        if not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError("MySQL URL must include host and database")

        def connect_mysql():
            try:
                import pymysql
            except ImportError as exc:  # pragma: no cover - exercised only without optional driver
                raise RuntimeError("PyMySQL is required for MySQL connections") from exc
            return pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=unquote(parsed.username or ""),
                password=unquote(parsed.password or ""),
                database=parsed.path.strip("/"),
                autocommit=False,
                charset="utf8mb4",
            )

        return connect_mysql

    raise ValueError("supported database URLs are sqlite:/// and mysql+pymysql://")


def _sqlite_path(parsed) -> str:
    if parsed.netloc and parsed.netloc != "":
        return f"//{parsed.netloc}{parsed.path}"
    raw_path = parsed.path
    if raw_path == "/:memory:":
        return ":memory:"
    if raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return str(Path(raw_path))
