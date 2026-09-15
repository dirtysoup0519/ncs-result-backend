"""Initialize the MySQL ADS schema through the single configured connection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.mysql_setup import initialize_mysql_ads
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument(
        "--url",
        default=os.getenv("NCS_DATABASE_URL"),
        help="single MySQL recovery-mode URL; defaults to NCS_DATABASE_URL",
    )
    args = parser.parse_args(argv)
    if not args.initialize:
        parser.error("--initialize is required")
    if not args.url:
        parser.error("--url or NCS_DATABASE_URL is required")
    if database_dialect_from_url(args.url).name != "mysql":
        parser.error("--url must use MySQL")

    applied = initialize_mysql_ads(connection_factory_from_url(args.url))
    print(json.dumps({"schemaApplied": applied}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
