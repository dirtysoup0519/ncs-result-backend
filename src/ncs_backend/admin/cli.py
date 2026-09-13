"""Internal CLI for validating a dataset delivery before database import."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema
from ncs_backend.admin.importers import DeliveryValidator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NCS data administration utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-delivery", help="validate schema, manifest and JSON/CSV/TSV rows")
    validate.add_argument("--schema", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--data", type=Path, required=True)
    initialize = subparsers.add_parser("init-control-schema", help="initialize the local control-plane schema")
    initialize.add_argument("--sqlite", type=Path, required=True, help="SQLite database file for local development")
    staging = subparsers.add_parser("init-staging-schema", help="initialize the local staging schema")
    staging.add_argument("--sqlite", type=Path, required=True, help="SQLite database file for local development")
    return parser


def validate_delivery(schema_path: Path, manifest_path: Path, data_path: Path) -> dict[str, Any]:
    result = DeliveryValidator().validate_files(schema_path, manifest_path, data_path)
    return {
        "passed": result.passed,
        "datasetCode": result.dataset_code,
        "schemaVersion": result.schema_version,
        "rowCount": result.row_count,
        "issues": list(result.issues),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-control-schema":
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(args.sqlite)
        try:
            tables = initialize_control_schema(connection)
        finally:
            connection.close()
        print(json.dumps({"initialized": True, "database": str(args.sqlite), "tables": list(tables)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "init-staging-schema":
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(args.sqlite)
        try:
            tables = initialize_staging_schema(connection)
        finally:
            connection.close()
        print(json.dumps({"initialized": True, "database": str(args.sqlite), "tables": list(tables)}, ensure_ascii=False, indent=2))
        return 0

    result = validate_delivery(args.schema, args.manifest, args.data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
