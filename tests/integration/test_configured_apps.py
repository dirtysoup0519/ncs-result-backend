import sqlite3

from ncs_backend.admin.local_database import initialize_local_database
from ncs_backend.bootstrap import configured_admin_app, configured_db_console_app, configured_query_app
from ncs_backend.shared.config import Settings


def _settings(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    return Settings(database_url=f"sqlite:///{database.as_posix()}"), database


def _schema():
    return {
        "datasetCode": "integration_dataset",
        "version": "v1",
        "grain": ["data_date"],
        "uniqueKey": ["data_date"],
        "fields": [
            {"name": "data_date", "type": "date", "nullable": False},
            {"name": "value", "type": "decimal", "nullable": False},
        ],
    }


def test_configured_admin_app_persists_dataset(tmp_path):
    settings, database = _settings(tmp_path)
    client = configured_admin_app(settings).test_client()

    ready = client.get("/health/ready")
    created = client.post(
        "/internal/v1/datasets",
        json={"schema": _schema(), "displayName": "Integration", "owner": "backend"},
    )
    listed = client.get("/internal/v1/datasets")

    assert ready.status_code == 200
    assert created.status_code == 201
    assert listed.json["data"]["items"][0]["dataset_code"] == "integration_dataset"
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM ctl_dataset").fetchone() == (1,)
    finally:
        connection.close()


def test_configured_console_reports_sql_failure_in_logs(tmp_path):
    settings, _ = _settings(tmp_path)
    client = configured_db_console_app(settings).test_client()

    failed = client.post("/internal/db-console/sql", json={"statement": "SELECT missing FROM ctl_dataset"})
    logs = client.get("/internal/db-console/logs")

    assert failed.status_code == 400
    assert logs.json["data"]["items"][-1]["level"] == "ERROR"
    assert client.get("/internal/db-console/status").json["data"]["connectionStatus"] == "CONNECTED"


def test_configured_query_app_degrades_capabilities_without_ads_views(tmp_path):
    settings, _ = _settings(tmp_path)
    client = configured_query_app(settings).test_client()

    response = client.get("/api/v1/meta/capabilities")

    assert response.status_code == 200
    assert all(item["available"] is False for item in response.json["data"]["items"])
