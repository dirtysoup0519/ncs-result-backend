"""Import and publish one versioned ADS Spark contract package (v2.3/v2.5)."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.adapters.ads_v23_import import AdsV23Importer
from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageReader
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.shared.db import SQLITE_DIALECT


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and publish an ADS Spark contract package")
    parser.add_argument("--package", type=Path, required=True, help="extracted package directory or its parent directory")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--sqlite", type=Path, help="SQLite database path (local development only)")
    target.add_argument("--database-url", default=os.getenv("NCS_DATABASE_URL"), help="MySQL URL; prefer NCS_DATABASE_URL")
    parser.add_argument("--skip-initialize", action="store_true", help="use an already migrated schema")
    args = parser.parse_args(argv)
    if args.sqlite is None and not args.database_url:
        parser.error("--sqlite, --database-url, or NCS_DATABASE_URL is required")

    package = AdsV23PackageReader().read(args.package)
    if args.sqlite is not None:
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection_factory = lambda: sqlite3.connect(args.sqlite)
        dialect = SQLITE_DIALECT
    else:
        connection_factory = connection_factory_from_url(args.database_url)
        dialect = database_dialect_from_url(args.database_url)
    result = AdsV23Importer(
        connection_factory,
        dialect=dialect,
        initialize_schema=not args.skip_initialize,
    ).import_package(package)
    print(json.dumps({
        "sourceBatchId": package.source_batch_id,
        "schemaVersion": package.schema_version,
        "metricVersion": package.metric_version,
        "publishedDatasets": list(result),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
