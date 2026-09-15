"""Run the full ADS v2.1 acceptance flow against a configured test MySQL DB."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.mysql_acceptance import run_mysql_acceptance
from ncs_backend.db_console.connections import database_dialect_from_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run ADS v2.1 end-to-end acceptance on a test MySQL database")
    parser.add_argument("--package", type=Path, default=os.getenv("NCS_ADS_V21_PACKAGE"))
    parser.add_argument("--url", default=os.getenv("NCS_MYSQL_TEST_URL") or os.getenv("NCS_DATABASE_URL"))
    args = parser.parse_args(argv)
    if not args.package:
        parser.error("--package or NCS_ADS_V21_PACKAGE is required")
    if not args.url:
        parser.error("--url, NCS_MYSQL_TEST_URL, or NCS_DATABASE_URL is required")
    if database_dialect_from_url(args.url).name != "mysql":
        parser.error("the acceptance URL must use MySQL")
    report = run_mysql_acceptance(
        args.package,
        database_url=args.url,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
