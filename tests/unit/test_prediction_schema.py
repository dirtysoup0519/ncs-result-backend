import sqlite3

from ncs_backend.admin.prediction_schema import initialize_prediction_schema


def _database():
    """An empty database carrying the ADS control table the prediction view reads.

    The real deployment applies the ADS result schema first, so ctl_publication
    already exists by the time the prediction view is created.
    """
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE ctl_publication (publication_id TEXT, dataset_code TEXT, batch_id TEXT, schema_version TEXT, status TEXT, published_at TEXT)"
    )
    return connection


def _publish(connection, batch_id, status="PUBLISHED"):
    connection.execute(
        "INSERT INTO ctl_publication VALUES (?, 'load_hourly', ?, '2.2.0', ?, CURRENT_TIMESTAMP)",
        (f"pub-{batch_id}-{status}", batch_id, status),
    )


def _insert_run(connection, run_id, source_batch_id, prediction_date, cutoff_hour, status="PUBLISHED"):
    connection.execute(
        "INSERT INTO ctl_prediction_run (prediction_run_id, model_code, model_version, source_batch_id, cutoff_time, lookback, horizon, dataset_profile_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "global_load_forecast", "v1", source_batch_id, f"{prediction_date} {cutoff_hour:02d}:00:00", 512, 24, "{}", status),
    )
    connection.execute(
        "INSERT INTO rpt_load_prediction (prediction_run_id, series_type, target_time, charging_energy, prediction_date, cutoff_hour, forecast_start_at, model_version, source_batch_id, data_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "FORECAST", f"{prediction_date} {cutoff_hour + 1:02d}:00:00", 1.5, prediction_date, cutoff_hour, f"{prediction_date} {cutoff_hour + 1:02d}:00:00", "v1", source_batch_id, "2.2.0"),
    )


def test_prediction_schema_is_idempotent_and_exposes_contract_view():
    connection = _database()
    first = initialize_prediction_schema(connection)
    second = initialize_prediction_schema(connection)

    assert first.applied is True
    assert second.applied is False
    assert set(first.tables) == {"ctl_model_version", "ctl_prediction_run", "rpt_load_prediction"}
    assert connection.execute("SELECT * FROM api_v1_load_prediction").description


def test_prediction_view_exposes_only_published_runs():
    connection = _database()
    initialize_prediction_schema(connection)
    _publish(connection, "batch-1")
    _insert_run(connection, "run-1", "batch-1", "2015-12-28", 17, status="CREATED")
    assert connection.execute("SELECT COUNT(*) FROM api_v1_load_prediction").fetchone()[0] == 0
    connection.execute("UPDATE ctl_prediction_run SET status = 'PUBLISHED' WHERE prediction_run_id = 'run-1'")
    assert connection.execute("SELECT COUNT(*) FROM api_v1_load_prediction").fetchone()[0] == 1


def test_prediction_view_hides_runs_whose_source_batch_is_no_longer_published():
    """A superseded hourly batch takes its forecasts out of the read contract.

    The read path orders by business date, so a stale run for a later date would
    otherwise outrank a fresh run for an earlier one and the dashboard would keep
    serving a curve derived from data that is no longer published -- reporting the
    old batch's dataVersion and tripping the dashboard's batch warning.
    """
    connection = _database()
    initialize_prediction_schema(connection)
    _insert_run(connection, "run-stale", "batch-old", "2026-09-16", 1)
    _insert_run(connection, "run-current", "batch-new", "2026-09-15", 22)
    _publish(connection, "batch-old", status="SUPERSEDED")
    _publish(connection, "batch-new")

    visible = connection.execute(
        "SELECT DISTINCT prediction_run_id FROM api_v1_load_prediction"
    ).fetchall()

    assert visible == [("run-current",)]
