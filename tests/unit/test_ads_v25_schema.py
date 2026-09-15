from ncs_backend.admin.adapters.ads_v23_schema import (
    ADS_V23_DATASET_SPECS,
    ADS_V25_DATASET_SPECS,
    specs_for_schema_version,
)


def test_v25_contract_extends_v23_with_eighteen_datasets():
    assert len(ADS_V23_DATASET_SPECS) == 10
    assert len(ADS_V25_DATASET_SPECS) == 18
    assert specs_for_schema_version("2.2.0") == ADS_V25_DATASET_SPECS
    assert specs_for_schema_version("2.0.0") == ADS_V23_DATASET_SPECS


def test_import_switch_keeps_only_target_batch_published():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE ctl_publication (dataset_code TEXT, batch_id TEXT, status TEXT, retracted_at TEXT)"
    )
    connection.executemany(
        "INSERT INTO ctl_publication VALUES (?, ?, 'PUBLISHED', NULL)",
        (("station_daily", "old-a"), ("station_daily", "old-b"), ("station_daily", "new")),
    )

    AdsV23Importer._supersede_other_publications(
        connection.cursor(), "station_daily", "new", datetime(2026, 9, 14, tzinfo=timezone.utc)
    )

    assert connection.execute(
        "SELECT batch_id FROM ctl_publication WHERE status = 'PUBLISHED'"
    ).fetchall() == [("new",)]
import sqlite3
from datetime import datetime, timezone

from ncs_backend.admin.adapters.ads_v23_import import AdsV23Importer
