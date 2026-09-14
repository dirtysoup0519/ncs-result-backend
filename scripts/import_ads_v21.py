import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer, AdsV21WaveBImporter
from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageReader


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and publish A0 datasets from an ADS v2.1 package")
    parser.add_argument("--package", type=Path, required=True, help="extracted ADS v2.1 package directory")
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--wave-b", action="store_true", help="publish Wave B duration/profile/heatmap datasets")
    args = parser.parse_args(argv)
    package = AdsV21PackageReader().read(args.package)
    args.sqlite.parent.mkdir(parents=True, exist_ok=True)
    connection_factory = lambda: sqlite3.connect(args.sqlite)
    importer = AdsV21WaveBImporter if args.wave_b else AdsV21A0Importer
    result = importer(connection_factory).import_package(package)
    print(json.dumps({"sourceBatchId": package.source_batch_id, "publishedDatasets": list(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
