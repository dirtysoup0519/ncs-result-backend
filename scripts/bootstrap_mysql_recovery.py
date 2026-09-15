"""Prepare the NCS database on a MySQL server in recovery mode."""

from __future__ import annotations

import argparse
import re

try:
    import pymysql
except ImportError as exc:  # pragma: no cover - exercised by setup script
    raise SystemExit("PyMySQL is required; install the [mysql] project extra first") from exc


IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", default="ncs_analytics")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    _identifier(args.database, "database")

    connection = _connect(args.host, args.port)
    try:
        version, recovery_mode = _server_state(connection)
        print(f"MYSQL_CONNECTION_OK version={version} skipGrantTables={str(recovery_mode).lower()}")
        if not recovery_mode:
            raise SystemExit(
                "MYSQL_RECOVERY_MODE_REQUIRED: this lab configuration requires "
                "skip_grant_tables=ON"
            )
        if not args.check_only:
            _initialize_database(connection, args.database)
    finally:
        connection.close()

    if not args.check_only:
        print(f"RECOVERY_DATABASE_READY database={args.database}")
    return 0


def _connect(host: str, port: int):
    try:
        return pymysql.connect(
            host=host,
            port=port,
            user="root",
            password="",
            charset="utf8mb4",
            autocommit=False,
        )
    except pymysql.MySQLError as exc:
        raise SystemExit(f"MYSQL_CONNECTION_FAILED user=root: {exc}") from exc


def _server_state(connection) -> tuple[str, bool]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = str(cursor.fetchone()[0])
        try:
            cursor.execute("SHOW GRANTS")
            recovery_mode = False
        except pymysql.MySQLError as exc:
            recovery_mode = exc.args[0] == 1290 and "skip-grant-tables" in str(exc).lower()
            if not recovery_mode:
                raise
    return version, recovery_mode


def _initialize_database(connection, database: str) -> None:
    quoted_database = f"`{database}`"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {quoted_database} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise SystemExit(f"invalid {label}: {value}")
    return value


def connection_url(host: str, port: int, database: str) -> str:
    return f"mysql+pymysql://root@{host}:{port}/{database}"


if __name__ == "__main__":
    raise SystemExit(main())
