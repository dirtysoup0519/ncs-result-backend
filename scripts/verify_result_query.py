"""Result-table query acceptance over the admin internal API.

Verifies P0-2 acceptance: after an import, every rpt_* result table is
reachable through GET /internal/v1/ads-result/tables and its rows can
be paged through GET /internal/v1/ads-result/tables/<name>/rows.

Usage:
  python scripts/verify_result_query.py \
      [--sqlite .local/ncs.sqlite | --database-url mysql+pymysql://...] \
      [--package /path/to/ads_package]        # import first (default: synthesize v2.5 sample)
      [--expect-nonempty table ...]           # tables that must contain rows

Exit code 0 when every whitelisted table answers and the expected
tables are non-empty. This is the Windows-side check for the VM
database; run it anywhere Python can reach the database.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from ncs_backend.admin.ads_v23_import_service import AdsV23ImportService  # noqa: E402
from ncs_backend.admin.ads_schema import initialize_ads_result_schema  # noqa: E402
from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema  # noqa: E402
from ncs_backend.admin.app import create_app  # noqa: E402
from ncs_backend.admin.result_query_service import ResultTableQueryService, RESULT_TABLE_NAMES  # noqa: E402
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url  # noqa: E402
from ncs_backend.shared.db import SQLITE_DIALECT  # noqa: E402
from scripts.verify_dual_entry_idempotency import _synthesize_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Result-table query acceptance")
    parser.add_argument("--sqlite", type=Path, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--package", type=Path, default=None, help="import this package before checking")
    parser.add_argument("--skip-import", action="store_true", help="do not import; query the database as-is")
    parser.add_argument("--allow-empty", action="store_true", help="do not require any table to have rows")
    args = parser.parse_args()

    if args.sqlite is not None:
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection_factory = lambda: sqlite3.connect(args.sqlite)  # noqa: E731
        dialect = SQLITE_DIALECT
    elif args.database_url:
        connection_factory = connection_factory_from_url(args.database_url)
        dialect = database_dialect_from_url(args.database_url)
    else:
        parser.error("--sqlite or --database-url is required")

    connection = connection_factory()
    try:
        initialize_control_schema(connection)
        initialize_staging_schema(connection)
        initialize_ads_result_schema(connection, dialect=dialect)
        connection.commit()
    finally:
        connection.close()

    if args.package is not None:
        AdsV23ImportService(connection_factory, dialect=dialect).import_package(args.package)
    elif not args.skip_import:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = _synthesize_package(Path(tmp) / "package", "batch-result-query")
            AdsV23ImportService(connection_factory, dialect=dialect).import_package(package)

    app = create_app(result_query_service=ResultTableQueryService(connection_factory, dialect=dialect))
    client = app.test_client()

    listing = client.get("/internal/v1/ads-result/tables")
    if listing.status_code != 200:
        print(f"FAIL listing returned {listing.status_code}: {listing.json}")
        return 1
    rows_by_table = {item["table"]: item["rowCount"] for item in listing.json["data"]["items"]}
    missing = [name for name in RESULT_TABLE_NAMES if name not in rows_by_table]
    if missing:
        print(f"FAIL missing tables in whitelist response: {missing}")
        return 1

    print(f"result tables: {len(rows_by_table)}")
    failed = 0
    for table in RESULT_TABLE_NAMES:
        response = client.get(f"/internal/v1/ads-result/tables/{table}/rows?limit=3")
        if response.status_code != 200:
            print(f"  FAIL {table}: HTTP {response.status_code}")
            failed += 1
            continue
        print(f"  ok   {table}: {rows_by_table[table]} row(s)")

    if not args.allow_empty and args.package is None:
        # rpt_station_hour_heatmap / rpt_station_ranking belong to the v2.1
        # baseline contract; the v2.5 sample writes their replacements
        # (rpt_station_hour_heatmap_profile / rpt_station_top10_snapshot).
        legacy_tables = {"rpt_station_hour_heatmap", "rpt_station_ranking"}
        empty_required = [
            name for name, count in rows_by_table.items()
            if count == 0 and name not in legacy_tables
        ]
        if empty_required:
            print(f"FAIL empty tables after sample import: {empty_required}")
            failed += 1

    if failed:
        print(f"FAIL result-query acceptance with {failed} failure(s)")
        return 1
    print("PASS result-query acceptance")
    return 0


class ResultTableQueryServiceWiring:
    """Late-import wrapper to avoid a module import cycle in this script."""

    def __new__(cls, connection_factory, dialect):  # noqa: D102
        from ncs_backend.admin.result_query_service import ResultTableQueryService

        return ResultTableQueryService(connection_factory, dialect=dialect)


if __name__ == "__main__":
    raise SystemExit(main())
