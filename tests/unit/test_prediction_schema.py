import sqlite3

from ncs_backend.admin.prediction_schema import initialize_prediction_schema


def test_prediction_schema_is_idempotent_and_exposes_contract_view():
    connection = sqlite3.connect(":memory:")
    first = initialize_prediction_schema(connection)
    second = initialize_prediction_schema(connection)

    assert first.applied is True
    assert second.applied is False
    assert set(first.tables) == {"ctl_model_version", "ctl_prediction_run", "rpt_load_prediction"}
    assert connection.execute("SELECT * FROM api_v1_load_prediction").description


def test_prediction_view_exposes_only_published_runs():
    connection = sqlite3.connect(":memory:")
    initialize_prediction_schema(connection)
    connection.execute(
        "INSERT INTO ctl_prediction_run (prediction_run_id, model_code, model_version, source_batch_id, cutoff_time, lookback, horizon, dataset_profile_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "global_load_forecast", "v1", "batch-1", "2015-12-28 17:00:00", 512, 24, "{}", "CREATED"),
    )
    connection.execute(
        "INSERT INTO rpt_load_prediction (prediction_run_id, series_type, target_time, charging_energy, prediction_date, cutoff_hour, forecast_start_at, model_version, source_batch_id, data_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "FORECAST", "2015-12-28 18:00:00", 1.5, "2015-12-28", 17, "2015-12-28 18:00:00", "v1", "batch-1", "2.2.0"),
    )
    assert connection.execute("SELECT COUNT(*) FROM api_v1_load_prediction").fetchone()[0] == 0
    connection.execute("UPDATE ctl_prediction_run SET status = 'PUBLISHED' WHERE prediction_run_id = 'run-1'")
    assert connection.execute("SELECT COUNT(*) FROM api_v1_load_prediction").fetchone()[0] == 1
