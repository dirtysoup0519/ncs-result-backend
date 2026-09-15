"""Ensure the configured database contains a published dashboard batch."""

from __future__ import annotations

import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.import_data_package import main as import_package_main
from ncs_backend.db_console.connections import connection_factory_from_url
from ncs_backend.shared.local_config import load_local_config


NO_PACKAGE_EXIT = 3


def main() -> int:
    load_local_config(REPO_ROOT / ".local" / "ncs.env")
    database_url = os.getenv("NCS_DATABASE_URL")
    if not database_url:
        print("DATABASE_URL_MISSING: run setup_new_machine.cmd first", file=sys.stderr)
        return 2
    if _dashboard_ready(database_url):
        print("DASHBOARD_DATA_READY")
        return 0

    print("DASHBOARD_DATA_EMPTY: importing the newest package from data_exchange/packages")
    try:
        result = import_package_main([])
    except SystemExit as exc:
        message = str(exc)
        if message.startswith("NO_PACKAGE:"):
            print(message, file=sys.stderr)
            return NO_PACKAGE_EXIT
        raise
    if result != 0 or not _dashboard_ready(database_url):
        print("DASHBOARD_DATA_IMPORT_FAILED: dashboard_overview was not published", file=sys.stderr)
        return 4
    print("DASHBOARD_DATA_IMPORTED")
    return 0


def _dashboard_ready(database_url: str) -> bool:
    connection = connection_factory_from_url(database_url)()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM ctl_publication "
            "WHERE dataset_code = 'dashboard_overview' AND status = 'PUBLISHED'"
        )
        row = cursor.fetchone()
        return bool(row and int(row[0]) > 0)
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
