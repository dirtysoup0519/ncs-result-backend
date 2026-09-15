import sqlite3

from ncs_backend.db_console.app import create_app
from ncs_backend.db_console.log_store import ConsoleLogStore
from ncs_backend.db_console.runtime import UnmanagedDatabaseRuntime


def _app(tmp_path):
    database = tmp_path / "console.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO items (name) VALUES ('demo')")
    connection.commit()
    connection.close()
    return create_app(
        connection_factory=lambda: sqlite3.connect(database),
        runtime=UnmanagedDatabaseRuntime(),
        log_store=ConsoleLogStore(),
    )


def test_status_sql_and_logs_endpoints(tmp_path):
    client = _app(tmp_path).test_client()

    status = client.get("/internal/db-console/status")
    assert status.status_code == 200
    assert status.json["data"]["connectionStatus"] == "CONNECTED"
    assert status.json["data"]["startStopSupported"] is False

    result = client.post("/internal/db-console/sql", json={"statement": "SELECT * FROM items"})
    assert result.status_code == 200
    assert result.json["data"]["rows"] == [[1, "demo"]]

    logs = client.get("/internal/db-console/logs?after=0&limit=10")
    assert logs.status_code == 200
    assert logs.json["data"]["items"][0]["action"] == "SELECT"


def test_runtime_and_sql_validation_errors_are_stable(tmp_path):
    client = _app(tmp_path).test_client()

    runtime = client.post("/internal/db-console/runtime", json={"action": "STOP"})
    assert runtime.status_code == 409
    assert runtime.json["code"] == "DB_RUNTIME_NOT_MANAGED"

    invalid = client.post("/internal/db-console/sql", json={"statement": ""})
    assert invalid.status_code == 400
    assert invalid.json["code"] == "SQL_STATEMENT_REQUIRED"


def test_sync_activity_panel(tmp_path):
    database = tmp_path / "sync.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE ctl_import_batch (batch_id TEXT, dataset_code TEXT, schema_version TEXT,"
        " source_batch_id TEXT, source_uri TEXT, source_sha256 TEXT, data_date TEXT,"
        " row_count INTEGER, status TEXT, error_summary TEXT,"
        " created_at TEXT DEFAULT '2026-09-15T20:59:02', updated_at TEXT, published_at TEXT)"
    )
    connection.execute(
        "INSERT INTO ctl_import_batch (batch_id, dataset_code, schema_version, source_batch_id,"
        " source_uri, source_sha256, data_date, row_count, status)"
        " VALUES ('b1', 'dashboard_overview', '2.2.0', 'ncs_sim', 'u', 'h', '2026-09-14', 6, 'PUBLISHED')"
    )
    connection.commit()
    connection.close()
    client = create_app(
        connection_factory=lambda: sqlite3.connect(database),
        runtime=UnmanagedDatabaseRuntime(),
        log_store=ConsoleLogStore(),
    ).test_client()

    result = client.get("/internal/db-console/sync")
    assert result.status_code == 200
    data = result.json["data"]
    assert data["columns"] == ["created_at", "dataset_code", "source_batch_id", "row_count", "status", "error_summary"]
    assert data["rows"][0][:5] == ["2026-09-15T20:59:02", "dashboard_overview", "ncs_sim", 6, "PUBLISHED"]
    assert data["summary"] == {"total": 1, "published": 1, "pendingOrFailed": 0}

    bad_limit = client.get("/internal/db-console/sync?limit=abc")
    assert bad_limit.status_code == 400
    assert bad_limit.json["code"] == "DB_PAGE_INVALID"


def test_sync_activity_reports_missing_table(tmp_path):
    database = tmp_path / "empty.sqlite"
    sqlite3.connect(database).close()
    client = create_app(
        connection_factory=lambda: sqlite3.connect(database),
        runtime=UnmanagedDatabaseRuntime(),
        log_store=ConsoleLogStore(),
    ).test_client()

    result = client.get("/internal/db-console/sync")
    assert result.status_code == 409
    assert result.json["code"] == "SYNC_HISTORY_UNAVAILABLE"


def test_page_is_available(tmp_path):
    client = _app(tmp_path).test_client()
    response = client.get("/db-console")
    assert response.status_code == 200
    assert "NCS 数据库工具" in response.text
    assert "执行中" in response.text
    assert client.get("/internal/db-console/static/db_console.css").status_code == 200
