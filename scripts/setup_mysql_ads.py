"""Manage the MySQL ADS schema and fixed account boundary without storing secrets."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.mysql_setup import grant_reader_views, initialize_mysql_ads, verify_mysql_accounts
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Initialize and verify the MySQL ADS result database")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--grant-reader", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--migrator-url", default=os.getenv("NCS_MYSQL_MIGRATOR_URL"))
    parser.add_argument("--privileged-url", default=os.getenv("NCS_MYSQL_PRIVILEGED_URL"))
    parser.add_argument("--admin-url", default=os.getenv("NCS_MYSQL_ADMIN_URL"))
    parser.add_argument("--reader-url", default=os.getenv("NCS_MYSQL_READER_URL"))
    parser.add_argument("--reader-account", default="ncs_ads_reader")
    parser.add_argument("--reader-host", default="localhost")
    args = parser.parse_args(argv)
    if not any((args.initialize, args.grant_reader, args.verify)):
        parser.error("select at least one action: --initialize, --grant-reader, or --verify")

    output = {}
    if args.initialize:
        _require_mysql_url(parser, args.migrator_url, "--migrator-url or NCS_MYSQL_MIGRATOR_URL")
        output["schemaApplied"] = initialize_mysql_ads(connection_factory_from_url(args.migrator_url))
    if args.grant_reader:
        _require_mysql_url(parser, args.privileged_url, "--privileged-url or NCS_MYSQL_PRIVILEGED_URL")
        database = urlsplit(args.privileged_url).path.strip("/")
        output["grantedViews"] = list(grant_reader_views(
            connection_factory_from_url(args.privileged_url),
            database=database,
            reader_account=args.reader_account,
            reader_host=args.reader_host,
        ))
    if args.verify:
        for value, label in (
            (args.migrator_url, "--migrator-url or NCS_MYSQL_MIGRATOR_URL"),
            (args.admin_url, "--admin-url or NCS_MYSQL_ADMIN_URL"),
            (args.reader_url, "--reader-url or NCS_MYSQL_READER_URL"),
        ):
            _require_mysql_url(parser, value, label)
        report = verify_mysql_accounts(
            connection_factory_from_url(args.migrator_url),
            connection_factory_from_url(args.admin_url),
            connection_factory_from_url(args.reader_url),
        )
        output["verification"] = asdict(report)
        if not all((report.reader_physical_tables_denied, report.admin_dml_only, report.migrator_can_manage_schema)):
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _require_mysql_url(parser, value, label):
    if not value:
        parser.error(f"{label} is required")
    if database_dialect_from_url(value).name != "mysql":
        parser.error(f"{label} must use a MySQL URL")


if __name__ == "__main__":
    raise SystemExit(main())
