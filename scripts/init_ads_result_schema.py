import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.prediction_schema import initialize_prediction_schema


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Initialize A0 ADS result tables and read-only views")
    parser.add_argument("--sqlite", type=Path, required=True)
    args = parser.parse_args(argv)
    args.sqlite.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.sqlite)
    try:
        result = initialize_ads_result_schema(connection)
        prediction = initialize_prediction_schema(connection)
    finally:
        connection.close()
    print(json.dumps({"initialized": result.applied, "predictionInitialized": prediction.applied, "database": str(args.sqlite), "tables": list(result.tables) + list(prediction.tables), "views": list(result.views) + list(prediction.views)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
