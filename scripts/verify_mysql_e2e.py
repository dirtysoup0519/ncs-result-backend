"""Run the full ADS v2.1 acceptance flow against a configured test MySQL DB."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.mysql_acceptance import run_mysql_acceptance
from ncs_backend.db_console.connections import database_dialect_from_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run ADS v2.1 end-to-end acceptance on a test MySQL database")
    parser.add_argument("--package", type=Path, default=os.getenv("NCS_ADS_V21_PACKAGE"))
    parser.add_argument("--migrator-url", default=os.getenv("NCS_MYSQL_MIGRATOR_URL"))
    parser.add_argument("--admin-url", default=os.getenv("NCS_MYSQL_ADMIN_URL"))
    parser.add_argument("--reader-url", default=os.getenv("NCS_MYSQL_READER_URL"))
    args = parser.parse_args(argv)
    if not args.package:
        parser.error("--package or NCS_ADS_V21_PACKAGE is required")
    urls = (args.migrator_url, args.admin_url, args.reader_url)
    if any(not value for value in urls):
        parser.error("migrator, admin and reader URLs are required")
    if any(database_dialect_from_url(value).name != "mysql" for value in urls):
        parser.error("all acceptance URLs must use MySQL")
    targets = {_target(value) for value in urls}
    if len(targets) != 1:
        parser.error("all acceptance URLs must target the same MySQL database")
    report = run_mysql_acceptance(
        args.package,
        migrator_url=args.migrator_url,
        admin_url=args.admin_url,
        reader_url=args.reader_url,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


def _target(url: str) -> tuple[str | None, int, str]:
    parsed = urlsplit(url)
    return parsed.hostname, parsed.port or 3306, parsed.path.strip("/")


if __name__ == "__main__":
    raise SystemExit(main())
