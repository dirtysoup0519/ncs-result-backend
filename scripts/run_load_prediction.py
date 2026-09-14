"""Run and publish one load prediction from the current published dataset."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.prediction.model_registry import ModelPackage
from ncs_backend.prediction.runner import PredictionRunner


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-package", type=Path, required=True)
    parser.add_argument("--database-url", default=os.getenv("NCS_MYSQL_ADMIN_URL") or os.getenv("NCS_DATABASE_URL"))
    parser.add_argument("--cutoff-time")
    parser.add_argument("--horizon", type=int, default=24)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or NCS_MYSQL_ADMIN_URL is required")
    connection = connection_factory_from_url(args.database_url)()
    try:
        package = ModelPackage.open(args.model_package)
        run_id = PredictionRunner(dialect=database_dialect_from_url(args.database_url)).run(connection, package, cutoff_time=args.cutoff_time, horizon=args.horizon)
    finally:
        connection.close()
    print(json.dumps({"predictionRunId": run_id}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
