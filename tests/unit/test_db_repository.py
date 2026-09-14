import sqlite3
from datetime import timezone

from ncs_backend.query.db_repository import DbApiDashboardRepository, _datetime_value, _monthly_trend_rows


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
        CREATE TABLE api_v1_station_hour_heatmap (
            station_id TEXT, station_name TEXT, hour INTEGER, value TEXT,
            is_observed INTEGER, metric TEXT, metric_code TEXT, unit TEXT,
            data_date TEXT, data_version TEXT, generated_at TEXT, staleness TEXT
        );
        INSERT INTO api_v1_station_hour_heatmap VALUES
          ('S1', '站点一', 8, '12.50', 1, 'kwh', 'charging_energy', 'kWh', '2019-09-13', 'heat:b1', '2026-09-13T06:00:00+08:00', 'FRESH');
        CREATE TABLE api_v1_weekday_weekend (
            day_type TEXT, metric_key TEXT, label TEXT, unit TEXT, metric_order INTEGER,
            max_value TEXT, raw_value TEXT, normalized_value TEXT,
            normalization_method TEXT, normalization_version TEXT,
            start_date TEXT, end_date TEXT, data_version TEXT,
            generated_at TEXT, staleness TEXT
        );
        INSERT INTO api_v1_weekday_weekend VALUES
          ('WEEKDAY', 'order_count', '订单量', 'count', 1, NULL, '10', NULL, NULL, NULL, '2019-09-01', '2019-09-13', 'profile:b1', '2026-09-13T06:00:00+08:00', 'FRESH'),
          ('WEEKEND', 'order_count', '订单量', 'count', 1, NULL, '4', NULL, NULL, NULL, '2019-09-01', '2019-09-13', 'profile:b1', '2026-09-13T06:00:00+08:00', 'FRESH');
        CREATE TABLE api_v1_fee_energy_trend (
            granularity TEXT, period TEXT, period_start TEXT, order_count INTEGER,
            total_fees TEXT, total_kwh TEXT, data_date TEXT, data_version TEXT,
            generated_at TEXT, staleness TEXT
        );
        INSERT INTO api_v1_fee_energy_trend VALUES
          ('DAY', '2019-09-12', '2019-09-12', 2, '3.00', '4.00', '2019-09-12', 'trend:b1', '2026-09-13T06:00:00+08:00', 'FRESH'),
          ('DAY', '2019-09-13', '2019-09-13', 5, '6.00', '7.00', '2019-09-13', 'trend:b1', '2026-09-13T06:00:00+08:00', 'FRESH');
        CREATE TABLE api_v1_load_prediction (
            series_type TEXT, target_time TEXT, order_count INTEGER, charging_energy TEXT,
            lower_bound TEXT, upper_bound TEXT, prediction_date TEXT, cutoff_hour INTEGER,
            forecast_start_at TEXT, interval_available INTEGER, confidence_level TEXT,
            model_version TEXT, prediction_run_id TEXT, generated_at TEXT,
            data_version TEXT, staleness TEXT
        );
        INSERT INTO api_v1_load_prediction VALUES
          ('ACTUAL', '2019-09-13T15:00:00+08:00', 8, '12.00', NULL, NULL, '2019-09-13', 16, '2019-09-13T16:00:00+08:00', 1, '0.95', 'model:b1', 'run:b1', '2026-09-13T06:00:00+08:00', 'pred:b1', 'FRESH'),
          ('ACTUAL', '2019-09-13T16:00:00+08:00', 9, '13.00', NULL, NULL, '2019-09-13', 16, '2019-09-13T16:00:00+08:00', 1, '0.95', 'model:b1', 'run:b1', '2026-09-13T06:00:00+08:00', 'pred:b1', 'FRESH'),
          ('FORECAST', '2019-09-13T16:00:00+08:00', NULL, '13.50', '11.00', '16.00', '2019-09-13', 16, '2019-09-13T16:00:00+08:00', 1, '0.95', 'model:b1', 'run:b1', '2026-09-13T06:00:00+08:00', 'pred:b1', 'FRESH');
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


def test_db_repository_fills_heatmap_hours_and_keeps_observation_flag(tmp_path):
    repository = _repository(tmp_path)

    result = repository.fetch("heatmap", {"metric": "kwh"})

    assert result.data["availability"] == "AVAILABLE"
    assert len(result.data["points"]) == 24
    assert result.data["points"][8] == {
        "stationId": "S1",
        "hour": 8,
        "value": "12.50",
        "isObserved": True,
    }
    assert result.data["points"][0]["isObserved"] is False
    assert result.data["metricCode"] == "kwh"
    assert result.data["valueRange"] == {"min": "0", "max": "12.50"}


def test_db_repository_aligns_profile_series_and_hides_future_actuals(tmp_path):
    repository = _repository(tmp_path)

    profile = repository.fetch("weekday_weekend", {})
    assert profile.data["series"][0]["rawValues"] == [10]
    assert profile.data["series"][1]["rawValues"] == [4]
    assert profile.data_date.isoformat() == "2019-09-13"

    prediction = repository.fetch("prediction", {"date": "2019-09-13", "cutoffHour": 16})
    assert len(prediction.data["actual"]) == 1
    assert prediction.data["actual"][0]["time"].endswith("15:00:00+08:00")
    assert len(prediction.data["forecast"]) == 1


def test_mysql_naive_timestamp_is_serialized_as_utc():
    value = _datetime_value("2026-09-14 09:06:27")

    assert value is not None
    assert value.tzinfo == timezone.utc
    assert value.isoformat() == "2026-09-14T09:06:27+00:00"


def test_daily_trend_rows_can_be_aggregated_for_month_view():
    rows = [
        {"period": "2026-08-31", "order_count": 2, "total_fees": "3.10", "total_kwh": "4.20"},
        {"period": "2026-09-01", "order_count": 5, "total_fees": "6.30", "total_kwh": "7.40"},
        {"period": "2026-09-02", "order_count": 7, "total_fees": "8.50", "total_kwh": "9.60"},
    ]

    monthly = _monthly_trend_rows(rows)

    assert [(item["period"], item["order_count"], str(item["total_fees"])) for item in monthly] == [
        ("2026-08", 2, "3.10"),
        ("2026-09", 12, "14.80"),
    ]


def test_trend_envelope_uses_latest_date_while_points_remain_chronological(tmp_path):
    result = _repository(tmp_path).fetch("fee_energy_trend", {"granularity": "DAY"})

    assert [point["period"] for point in result.data["points"]] == ["2019-09-12", "2019-09-13"]
    assert result.data_date.isoformat() == "2019-09-13"
