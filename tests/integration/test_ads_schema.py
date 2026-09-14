import sqlite3

import pytest

from ncs_backend.admin.ads_schema import (
    ADS_MIGRATION_TABLE,
    ADS_RESULT_TABLES,
    ADS_VIEW_NAMES,
    AdsSchemaMigrationError,
    initialize_ads_result_schema,
)
from ncs_backend.admin.local_database import initialize_local_database
from ncs_backend.query.view_contract import inspect_view_contracts


def test_ads_result_schema_is_idempotent_and_satisfies_view_contract(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    connection = sqlite3.connect(database)
    try:
        first = initialize_ads_result_schema(connection)
        second = initialize_ads_result_schema(connection)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        views = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        contracts = tuple(item for item in inspect_view_contracts(lambda: sqlite3.connect(database)) if item.view_name in ADS_VIEW_NAMES)
    finally:
        connection.close()

    assert first.applied is True
    assert second.applied is False
    assert set(ADS_RESULT_TABLES).issubset(tables)
    assert set(ADS_VIEW_NAMES).issubset(views)
    assert all(item.compatible for item in contracts)


def test_ads_result_schema_rejects_changed_definition(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    connection = sqlite3.connect(database)
    try:
        initialize_ads_result_schema(connection)
        with pytest.raises(AdsSchemaMigrationError, match="checksum"):
            initialize_ads_result_schema(connection, schema_sql=("CREATE TABLE changed (id INTEGER)",))
    finally:
        connection.close()


def test_published_views_do_not_expose_unpublished_rows(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    connection = sqlite3.connect(database)
    try:
        initialize_ads_result_schema(connection)
        connection.execute(
            "INSERT INTO rpt_dashboard_overview (batch_id, metric_code, display_name, metric_value, unit, precision_value, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("batch-a", "total_order_count", "总订单", 5000, "count", 0, "v2.1"),
        )
        connection.commit()
        hidden = connection.execute("SELECT COUNT(*) FROM api_v1_dashboard_overview").fetchone()[0]
        connection.execute(
            "INSERT INTO ctl_import_batch (batch_id, dataset_code, schema_version, source_batch_id, source_uri, source_sha256, data_date, row_count, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("batch-a", "dashboard_overview", "v2.1", "source-a", "ads://a", "a" * 64, "2019-01-01", 1, "PUBLISHED"),
        )
        connection.execute(
            "INSERT INTO ctl_publication (publication_id, dataset_code, batch_id, schema_version, status, published_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("pub-a", "dashboard_overview", "batch-a", "v2.1", "PUBLISHED"),
        )
        connection.commit()
        visible = connection.execute("SELECT COUNT(*) FROM api_v1_dashboard_overview").fetchone()[0]
    finally:
        connection.close()

    assert hidden == 0
    assert visible == 1


def test_station_daily_ranking_uses_full_period_and_common_end_date(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    connection = sqlite3.connect(database)
    try:
        initialize_ads_result_schema(connection)
        rows = [
            ("station-batch", "2019-01-01", "S1", "站点1", "L1", 2, "10", "2", "v2.3"),
            ("station-batch", "2019-02-01", "S1", "站点1", "L1", 3, "15", "3", "v2.3"),
            ("station-batch", "2019-01-01", "S2", "站点2", "L2", 4, "20", "4", "v2.3"),
        ]
        connection.executemany(
            "INSERT INTO rpt_station_daily (batch_id, data_date, station_id, station_name, location_id, order_count, total_kwh, total_fees, data_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.execute(
            "INSERT INTO ctl_import_batch (batch_id, dataset_code, schema_version, source_batch_id, source_uri, source_sha256, data_date, row_count, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("station-batch", "station_daily", "2.0.0", "source", "ads://source", "b" * 64, "2019-02-01", 3, "PUBLISHED"),
        )
        connection.execute(
            "INSERT INTO ctl_publication (publication_id, dataset_code, batch_id, schema_version, status, published_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("station-pub", "station_daily", "station-batch", "2.0.0", "PUBLISHED"),
        )
        connection.commit()
        ranking = connection.execute(
            "SELECT station_id, order_count, total_fees, data_date FROM api_v1_station_ranking ORDER BY total_fees DESC"
        ).fetchall()
    finally:
        connection.close()

    assert ranking == [("S1", 5, 5, "2019-02-01"), ("S2", 4, 4, "2019-02-01")]
