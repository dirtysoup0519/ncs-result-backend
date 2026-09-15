import sqlite3

import pytest

from ncs_backend.admin.app import create_app
from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema
from ncs_backend.admin.result_query_service import RESULT_TABLE_NAMES, ResultTableQueryService
from ncs_backend.shared.db import SQLITE_DIALECT


def _service(tmp_path):
    database = tmp_path / "result_query.sqlite"
    connection = sqlite3.connect(database)
    initialize_control_schema(connection)
    initialize_staging_schema(connection)
    initialize_ads_result_schema(connection, dialect=SQLITE_DIALECT)
    connection.execute(
        "INSERT INTO rpt_dashboard_overview (batch_id, metric_code, display_name, metric_value, unit, precision_value, data_version) "
        "VALUES ('b1', 'total_order_count', '订单总数', 100, '单', 0, '2.2.0')"
    )
    connection.commit()
    connection.close()
    return ResultTableQueryService(lambda: sqlite3.connect(database), dialect=SQLITE_DIALECT)


def test_whitelist_covers_all_v25_result_tables():
    for expected in (
        "rpt_station_top10_snapshot",
        "rpt_station_hour_heatmap_profile",
        "rpt_revenue_monthly",
        "rpt_kpi_period_comparison",
        "rpt_weekday_hour_profile",
        "rpt_charge_type_distribution",
        "rpt_station_charge_type",
        "rpt_process_overview",
    ):
        assert expected in RESULT_TABLE_NAMES
    assert len(RESULT_TABLE_NAMES) == 20


def test_list_tables_reports_row_counts(tmp_path):
    service = _service(tmp_path)
    summaries = {item.name: item.row_count for item in service.list_tables()}
    assert summaries["rpt_dashboard_overview"] == 1
    assert summaries["rpt_station_top10_snapshot"] == 0


def test_browse_returns_rows_and_rejects_unknown_table(tmp_path):
    service = _service(tmp_path)
    page = service.browse("rpt_dashboard_overview", limit=10, offset=0)
    assert page["total"] == 1
    assert "metric_value" in page["columns"]
    assert page["rows"][0][page["columns"].index("metric_value")] == 100

    with pytest.raises(ValueError, match="unknown result table"):
        service.browse("ctl_publication", limit=10, offset=0)

    with pytest.raises(ValueError, match="invalid column name"):
        service.browse("rpt_dashboard_overview", limit=10, offset=0, order_by="; DROP TABLE x")


def test_internal_routes_serve_result_tables(tmp_path):
    service = _service(tmp_path)
    client = create_app(result_query_service=service).test_client()

    listing = client.get("/internal/v1/ads-result/tables")
    assert listing.status_code == 200
    tables = {item["table"]: item["rowCount"] for item in listing.json["data"]["items"]}
    assert tables["rpt_dashboard_overview"] == 1

    rows = client.get("/internal/v1/ads-result/tables/rpt_dashboard_overview/rows?limit=5")
    assert rows.status_code == 200
    assert rows.json["data"]["rows"][0][rows.json["data"]["columns"].index("metric_value")] == 100

    rejected = client.get("/internal/v1/ads-result/tables/ctl_publication/rows")
    assert rejected.status_code == 400
    assert rejected.json["code"] == "VALIDATION_INVALID_PARAMETER"

    missing = create_app().test_client().get("/internal/v1/ads-result/tables")
    assert missing.status_code == 503
    assert missing.json["code"] == "DEPENDENCY_NOT_READY"
