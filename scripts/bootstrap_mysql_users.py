"""Check a VM MySQL connection and create the NCS database accounts."""

from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import quote

try:
    import pymysql
except ImportError as exc:  # pragma: no cover - exercised by setup script
    raise SystemExit("PyMySQL is required; install the [mysql] project extra first") from exc


IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
ACCOUNT_HOST = re.compile(r"^[A-Za-z0-9_.:%-]+$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", default="ncs_analytics")
    parser.add_argument("--account-host", default="%")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    _identifier(args.database, "database")
    _account_host(args.account_host)

    root_password = os.environ.get("NCS_BOOTSTRAP_ROOT_PASSWORD")
    if root_password is None:
        raise SystemExit("NCS_BOOTSTRAP_ROOT_PASSWORD is required")
    connection = _connect(args.host, args.port, "root", root_password)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = str(cursor.fetchone()[0])
        print(f"MYSQL_CONNECTION_OK version={version}")
        if _grant_tables_disabled(connection):
            raise SystemExit(
                "MYSQL_GRANT_TABLES_DISABLED: the server was started with "
                "--skip-grant-tables; remove that option and restart mysqld before continuing"
            )
        if args.check_only:
            return 0
        _initialize(connection, args.database, args.account_host)
    finally:
        connection.close()

    print(f"DATABASE_AND_USERS_READY database={args.database} accountHost={args.account_host}")
    return 0


def _initialize(connection, database: str, account_host: str) -> None:
    passwords = {
        "ncs_ads_migrator": os.environ.get("NCS_BOOTSTRAP_MIGRATOR_PASSWORD"),
        "ncs_ads_admin": os.environ.get("NCS_BOOTSTRAP_ADMIN_PASSWORD"),
        "ncs_ads_reader": os.environ.get("NCS_BOOTSTRAP_READER_PASSWORD"),
    }
    missing = [name for name, password in passwords.items() if not password]
    if missing:
        raise SystemExit(f"missing account passwords: {', '.join(missing)}")

    quoted_database = f"`{database}`"
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {quoted_database} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            for account, password in passwords.items():
                account_sql = f"'{account}'@'{account_host}'"
                # PyMySQL uses ``%`` formatting whenever parameters are supplied.
                # The default MySQL account host is ``%`` (any host), so escape it
                # in statements that also contain the password placeholder. The
                # server receives the intended ``'user'@'%'`` after formatting.
                parameterized_account_sql = account_sql.replace("%", "%%")
                cursor.execute(
                    f"CREATE USER IF NOT EXISTS {parameterized_account_sql} IDENTIFIED BY %s",
                    (password,),
                )
                cursor.execute(f"ALTER USER {parameterized_account_sql} IDENTIFIED BY %s", (password,))
            cursor.execute(f"GRANT ALL PRIVILEGES ON {quoted_database}.* TO 'ncs_ads_migrator'@'{account_host}'")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {quoted_database}.* "
                f"TO 'ncs_ads_admin'@'{account_host}'"
            )
            cursor.execute(f"GRANT USAGE ON *.* TO 'ncs_ads_reader'@'{account_host}'")
            cursor.execute("FLUSH PRIVILEGES")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _connect(host: str, port: int, user: str, password: str):
    try:
        return pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
    except pymysql.MySQLError as exc:
        raise SystemExit(f"MYSQL_CONNECTION_FAILED user={user}: {exc}") from exc


def _grant_tables_disabled(connection) -> bool:
    """Return whether MySQL disabled privilege tables for recovery mode."""
    with connection.cursor() as cursor:
        cursor.execute("SHOW VARIABLES LIKE 'skip_grant_tables'")
        row = cursor.fetchone()
    return bool(row and len(row) > 1 and str(row[1]).strip().lower() in {"1", "on", "true"})


def _identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise SystemExit(f"invalid {label}: {value}")
    return value


def _account_host(value: str) -> str:
    if not ACCOUNT_HOST.fullmatch(value):
        raise SystemExit(f"invalid account host: {value}")
    return value


def connection_url(user: str, password: str, host: str, port: int, database: str) -> str:
    return f"mysql+pymysql://{user}:{quote(password, safe='')}@{host}:{port}/{database}"


if __name__ == "__main__":
    raise SystemExit(main())
