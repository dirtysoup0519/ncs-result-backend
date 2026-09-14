"""Validate and register a trained prediction model package."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.prediction.management import register_model
from ncs_backend.prediction.model_registry import ModelPackage


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-package", type=Path, required=True)
    parser.add_argument("--database-url", default=os.getenv("NCS_MYSQL_ADMIN_URL") or os.getenv("NCS_DATABASE_URL"))
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or NCS_MYSQL_ADMIN_URL is required")
    package = ModelPackage.open(args.model_package)
    connection = connection_factory_from_url(args.database_url)()
    try:
        result = register_model(connection, package, dialect=database_dialect_from_url(args.database_url))
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
