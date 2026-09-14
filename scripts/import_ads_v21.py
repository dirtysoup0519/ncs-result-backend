import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer
from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageReader


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and publish A0 datasets from an ADS v2.1 package")
    parser.add_argument("--package", type=Path, required=True, help="extracted ADS v2.1 package directory")
    parser.add_argument("--sqlite", type=Path, required=True)
    args = parser.parse_args(argv)
    package = AdsV21PackageReader().read(args.package)
    args.sqlite.parent.mkdir(parents=True, exist_ok=True)
    connection_factory = lambda: sqlite3.connect(args.sqlite)
    result = AdsV21A0Importer(connection_factory).import_package(package)
    print(json.dumps({"sourceBatchId": package.source_batch_id, "publishedDatasets": list(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
