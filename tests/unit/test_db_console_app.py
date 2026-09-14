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


def test_page_is_available(tmp_path):
    client = _app(tmp_path).test_client()
    response = client.get("/db-console")
    assert response.status_code == 200
    assert "NCS 数据库工具" in response.text
