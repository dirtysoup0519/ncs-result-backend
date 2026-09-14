"""Verify ADS result views against a configured MySQL database.

The script never reads credentials from repository files. Use
``NCS_MYSQL_TEST_URL`` or pass ``--url`` from a protected environment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.query.view_contract import inspect_view_contracts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify ADS views and metadata on MySQL")
    parser.add_argument("--url", default=os.getenv("NCS_MYSQL_TEST_URL") or os.getenv("NCS_DATABASE_URL"), help="MySQL URL; prefer NCS_MYSQL_TEST_URL")
    parser.add_argument("--initialize", action="store_true", help="apply control/result schema before verification")
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("--url or NCS_MYSQL_TEST_URL is required")
    dialect = database_dialect_from_url(args.url)
    if dialect.name != "mysql":
        parser.error("ADS-5 verification requires a mysql:// or mysql+pymysql:// URL")
    factory = connection_factory_from_url(args.url)
    connection = factory()
    try:
        if args.initialize:
            MigrationRunner(dialect=dialect).apply(connection)
            initialize_ads_result_schema(connection, dialect=dialect)
        cursor = dialect.cursor(connection)
        cursor.execute("SELECT VERSION(), @@character_set_database, @@time_zone, @@sql_mode")
        version, charset, timezone, sql_mode = cursor.fetchone()
        cursor.close()
    finally:
        connection.close()

    contracts = inspect_view_contracts(factory)
    print(json.dumps({
        "database": "mysql",
        "serverVersion": version,
        "characterSet": charset,
        "timeZone": timezone,
        "sqlMode": sql_mode,
        "views": [item.to_dict() for item in contracts],
        "compatible": all(item.compatible for item in contracts),
    }, ensure_ascii=False, indent=2))
    return 0 if all(item.compatible for item in contracts) else 2


if __name__ == "__main__":
    raise SystemExit(main())
