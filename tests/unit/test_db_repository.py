import sqlite3

from ncs_backend.query.db_repository import DbApiDashboardRepository


def _repository(tmp_path):
    database = tmp_path / "views.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE api_v1_dashboard_overview (
            metric_code TEXT, display_name TEXT, metric_value TEXT, unit TEXT,
            precision INTEGER, data_date TEXT, region_id TEXT,
            data_version TEXT, generated_at TEXT, staleness TEXT
        );
        INSERT INTO api_v1_dashboard_overview VALUES
          ('total_order_count', '总订单数', '12', 'count', 0, '2019-09-13', NULL, 'overview:b1', '2026-09-13T06:00:00+08:00', 'FRESH'),
          ('total_charging_fee', '总充电费用', '30.50', 'CNY', 2, '2019-09-13', NULL, 'overview:b1', '2026-09-13T06:00:00+08:00', 'FRESH');
        CREATE TABLE api_v1_station_ranking (
            station_id TEXT, station_name TEXT, order_count INTEGER,
            total_fees TEXT, total_kwh TEXT, data_date TEXT,
            data_version TEXT, generated_at TEXT, staleness TEXT
        );
        INSERT INTO api_v1_station_ranking VALUES
          ('S1', '站点一', 3, '30.50', '100.00', '2019-09-13', 'rank:b1', '2026-09-13T06:00:00+08:00', 'FRESH');
        """
    )
    connection.commit()
    connection.close()
    return DbApiDashboardRepository(lambda: sqlite3.connect(database))


def test_db_repository_maps_canonical_view_columns(tmp_path):
    repository = _repository(tmp_path)

    result = repository.fetch("overview", {})

    assert result.empty is False
    assert result.data_version == "overview:b1"
    assert result.data["items"] == [
        {"metricCode": "total_charging_fee", "displayName": "总充电费用", "value": "30.50", "unit": "CNY", "precision": 2},
        {"metricCode": "total_order_count", "displayName": "总订单数", "value": 12, "unit": "count", "precision": 0},
    ]


def test_db_repository_applies_default_latest_ranking_and_limit(tmp_path):
    repository = _repository(tmp_path)

    result = repository.fetch("ranking", {})

    assert result.data["metricCode"] == "total_fees"
    assert result.data["items"][0]["rank"] == 1
    assert result.data["items"][0]["value"] == "30.50"
    assert repository.is_available("ranking") is True
