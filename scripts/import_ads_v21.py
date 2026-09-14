import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer, AdsV21WaveBImporter
from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageReader
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.shared.db import SQLITE_DIALECT


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and publish A0 datasets from an ADS v2.1 package")
    parser.add_argument("--package", type=Path, required=True, help="extracted ADS v2.1 package directory")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--sqlite", type=Path, help="SQLite database path (local development only)")
    target.add_argument(
        "--database-url",
        default=os.getenv("NCS_DATABASE_URL"),
        help="MySQL URL; prefer passing it through NCS_DATABASE_URL",
    )
    parser.add_argument(
        "--skip-initialize",
        action="store_true",
        help="use an already migrated schema (required for the DML-only admin account)",
    )
    parser.add_argument("--wave-b", action="store_true", help="publish Wave B duration/profile/heatmap datasets")
    args = parser.parse_args(argv)
    if args.sqlite is None and not args.database_url:
        parser.error("--sqlite, --database-url, or NCS_DATABASE_URL is required")
    package = AdsV21PackageReader().read(args.package)
    if args.sqlite is not None:
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection_factory = lambda: sqlite3.connect(args.sqlite)
        dialect = SQLITE_DIALECT
    else:
        connection_factory = connection_factory_from_url(args.database_url)
        dialect = database_dialect_from_url(args.database_url)
    importer = AdsV21WaveBImporter if args.wave_b else AdsV21A0Importer
    result = importer(
        connection_factory,
        dialect=dialect,
        initialize_schema=not args.skip_initialize,
    ).import_package(package)
    print(json.dumps({"sourceBatchId": package.source_batch_id, "publishedDatasets": list(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
