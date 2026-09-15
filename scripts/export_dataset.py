"""Export VM MySQL datasets to the repository data exchange directory."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.export_ml_dataset import DATASETS, main as export_main
from ncs_backend.shared.local_config import load_local_config


def main(argv: list[str] | None = None) -> int:
    load_local_config(REPO_ROOT / ".local" / "ncs.env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=(*DATASETS, "all"), default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--station-id")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args(argv)

    output = args.output or (
        REPO_ROOT / "data_exchange" / "exports" / f"dataset-{datetime.now():%Y%m%d-%H%M%S}"
    )
    command = ["--dataset", args.dataset, "--output", str(output)]
    if args.start_date:
        command.extend(("--start-date", args.start_date))
    if args.end_date:
        command.extend(("--end-date", args.end_date))
    if args.station_id:
        command.extend(("--station-id", args.station_id))
    if not args.no_zip:
        command.append("--zip")
    return export_main(command)


if __name__ == "__main__":
    raise SystemExit(main())
