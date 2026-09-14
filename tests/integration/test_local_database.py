import sqlite3

from ncs_backend.admin.local_database import (
    EXPECTED_VERSIONS,
    REQUIRED_TABLES,
    initialize_local_database,
    inspect_local_database,
)
from ncs_backend.db_console.app import create_app
from ncs_backend.db_console.runtime import UnmanagedDatabaseRuntime
from ncs_backend.shared.config import Settings


def test_local_database_initialization_is_idempotent(tmp_path):
    database = tmp_path / "nested" / "ncs.sqlite"

    first = initialize_local_database(database)
    second = initialize_local_database(database)

    assert first.valid is True
    assert second.valid is True
    assert first.applied_versions == EXPECTED_VERSIONS
    assert set(REQUIRED_TABLES).issubset(second.tables)


def test_local_database_check_does_not_create_missing_file(tmp_path):
    database = tmp_path / "missing.sqlite"

    status = inspect_local_database(database)

    assert status.valid is False
    assert status.missing_tables == REQUIRED_TABLES
    assert database.exists() is False


def test_local_database_check_reports_incomplete_structure(tmp_path):
    database = tmp_path / "incomplete.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    connection.close()

    status = inspect_local_database(database)

    assert status.valid is False
    assert status.tables == ("unrelated",)
    assert status.missing_tables == REQUIRED_TABLES


def test_database_console_connects_to_initialized_database(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    settings = Settings(database_url=f"sqlite:///{database.as_posix()}")
    client = create_app(settings=settings, runtime=UnmanagedDatabaseRuntime()).test_client()

    status = client.get("/internal/db-console/status")
    result = client.post(
        "/internal/db-console/sql",
        json={"statement": "SELECT COUNT(*) AS table_count FROM ctl_schema_migration"},
    )

    assert status.json["data"]["connectionStatus"] == "CONNECTED"
    assert result.status_code == 200
    assert result.json["data"]["rows"] == [[len(EXPECTED_VERSIONS)]]
