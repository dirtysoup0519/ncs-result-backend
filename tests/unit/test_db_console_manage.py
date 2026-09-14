import sqlite3

import pytest

from ncs_backend.db_console.app import create_app
from ncs_backend.db_console.log_store import ConsoleLogStore
from ncs_backend.db_console.maintenance import MaintenanceError, MaintenanceOperations
from ncs_backend.db_console.runtime import UnmanagedDatabaseRuntime
from ncs_backend.db_console.schema_inspector import SchemaInspector
from ncs_backend.db_console.script_runner import ScriptRunner
from ncs_backend.db_console.sql_identifiers import IdentifierError, quote_identifier, validate_identifier
from ncs_backend.db_console.table_operations import TableOperationError, TableOperations
from ncs_backend.shared.db import SQLITE_DIALECT


def _database(tmp_path):
    database = tmp_path / "manage.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER)")
    connection.executemany("INSERT INTO items (name, qty) VALUES (?, ?)", [("a", 1), ("b", 2), ("c", 3)])
    connection.commit()
    connection.close()
    return database


def _operations(tmp_path):
    database = _database(tmp_path)
    factory = lambda: sqlite3.connect(database)  # noqa: E731
    logs = ConsoleLogStore()
    return (
        TableOperations(factory, dialect=SQLITE_DIALECT),
        SchemaInspector(factory, dialect=SQLITE_DIALECT),
        MaintenanceOperations(factory, dialect=SQLITE_DIALECT),
        ScriptRunner(factory, logs, dialect=SQLITE_DIALECT),
        logs,
    )


def test_validate_identifier_accepts_simple_names_and_rejects_injection():
    assert validate_identifier("ctl_import_batch", kind="table name") == "ctl_import_batch"

    for bad in ["items; DROP TABLE x", "items--", "1abc", "", "items;--", "it ems"]:
        with pytest.raises(IdentifierError):
            validate_identifier(bad, kind="table name")


def test_quote_identifier_uses_dialect_specific_quotes():
    assert quote_identifier("items", SQLITE_DIALECT) == '"items"'

    with pytest.raises(IdentifierError):
        quote_identifier("bad name", SQLITE_DIALECT)


def test_schema_inspector_lists_tables_and_details(tmp_path):
    _, inspector, _, _, _ = _operations(tmp_path)

    tables = inspector.list_tables()
    names = [table.name for table in tables]
    assert "items" in names

    detail = inspector.table_detail("items")
    column_names = [column["name"] for column in detail["columns"]]
    assert column_names == ["id", "name", "qty"]
    assert detail["row_count"] == 3

    with pytest.raises(IdentifierError):
        inspector.table_detail("items; DROP TABLE items")


def test_table_operations_browse_insert_update_delete(tmp_path):
    operations, _, _, _, _ = _operations(tmp_path)

    page = operations.browse("items", limit=2, offset=0, order_by="id")
    assert page["total"] == 3
    assert len(page["rows"]) == 2
    assert page["columns"] == ["id", "name", "qty"]

    affected = operations.insert("items", {"name": "d", "qty": 4})
    assert affected == 1

    affected = operations.update("items", {"id": 1}, {"qty": 100})
    assert affected == 1

    affected = operations.delete("items", {"id": 2})
    assert affected == 1

    with pytest.raises(IdentifierError):
        operations.browse("items; DROP TABLE items")

    with pytest.raises(IdentifierError):
        operations.insert("items", {"name; DROP TABLE items": "x"})


def test_destructive_operations_require_confirm(tmp_path):
    operations, _, _, _, _ = _operations(tmp_path)

    with pytest.raises(TableOperationError) as truncated:
        operations.truncate("items")
    assert truncated.value.code == "DB_DESTRUCTIVE_CONFIRM_REQUIRED"

    assert operations.truncate("items", confirm=True) == "truncated"
    assert operations.browse("items")["total"] == 0

    with pytest.raises(TableOperationError) as dropped:
        operations.drop("items")
    assert dropped.value.code == "DB_DESTRUCTIVE_CONFIRM_REQUIRED"

    assert operations.drop("items", confirm=True) == "dropped"


def test_maintenance_sqlite_capabilities(tmp_path):
    _, _, maintenance, _, _ = _operations(tmp_path)

    info = maintenance.server_info()
    assert "version" in info

    with pytest.raises(MaintenanceError) as vacuumed:
        maintenance.vacuum()
    assert vacuumed.value.code == "DB_DESTRUCTIVE_CONFIRM_REQUIRED"
    assert maintenance.vacuum(confirm=True) == "vacuum completed"
    assert maintenance.integrity_check()["results"][0] == "ok"

    with pytest.raises(MaintenanceError) as processlist:
        maintenance.processlist()
    assert processlist.value.code == "DB_MYSQL_ONLY"


def test_script_runner_commits_all_or_rolls_back(tmp_path):
    _, _, _, scripts, logs = _operations(tmp_path)

    result = scripts.run([
        "INSERT INTO items (name, qty) VALUES ('x', 9)",
        "UPDATE items SET qty = 10 WHERE name = 'x'",
    ])
    assert result.committed is True
    assert len(result.statements) == 2
    assert result.error is None

    failed = scripts.run([
        "INSERT INTO items (name, qty) VALUES ('y', 1)",
        "INSERT INTO items (missing_column) VALUES ('z')",
    ])
    assert failed.committed is False
    assert failed.error is not None
    # both statements of the failed script are rolled back
    assert scripts.run(["SELECT COUNT(*) FROM items WHERE name = 'y'"]).statements[0].affected_rows is None

    with pytest.raises(ValueError, match="at least one"):
        scripts.run([])

    actions = [entry.action for entry in logs.list()]
    assert "SCRIPT" in actions


def _client(tmp_path):
    database = _database(tmp_path)
    return create_app(
        connection_factory=lambda: sqlite3.connect(database),
        dialect=SQLITE_DIALECT,
        runtime=UnmanagedDatabaseRuntime(),
        log_store=ConsoleLogStore(),
    ).test_client()


def test_management_routes_end_to_end(tmp_path):
    client = _client(tmp_path)

    schema = client.get("/internal/db-console/schema")
    assert schema.status_code == 200
    assert any(item["name"] == "items" for item in schema.json["data"]["items"])

    detail = client.get("/internal/db-console/schema/tables/items")
    assert detail.status_code == 200
    assert detail.json["data"]["rowCount"] == 3

    rows = client.get("/internal/db-console/tables/items/rows?limit=2")
    assert rows.status_code == 200
    assert len(rows.json["data"]["rows"]) == 2
    assert rows.json["data"]["total"] == 3

    inserted = client.post("/internal/db-console/tables/items/rows", json={"values": {"name": "web", "qty": 7}})
    assert inserted.status_code == 200
    assert inserted.json["data"]["affectedRows"] == 1

    updated = client.patch("/internal/db-console/tables/items/rows", json={"keys": {"id": 1}, "values": {"qty": 42}})
    assert updated.status_code == 200

    deleted = client.delete("/internal/db-console/tables/items/rows", json={"keys": {"id": 3}})
    assert deleted.status_code == 200

    without_confirm = client.post("/internal/db-console/tables/items/truncate", json={})
    assert without_confirm.status_code == 409
    assert without_confirm.json["code"] == "DB_DESTRUCTIVE_CONFIRM_REQUIRED"

    truncated = client.post("/internal/db-console/tables/items/truncate", json={"confirm": True})
    assert truncated.status_code == 200

    info = client.get("/internal/db-console/maintenance/info")
    assert info.status_code == 200
    assert "version" in info.json["data"]

    integrity = client.get("/internal/db-console/maintenance/integrity-check")
    assert integrity.status_code == 200
    assert integrity.json["data"]["results"][0] == "ok"

    injected = client.get("/internal/db-console/schema/tables/items%3B%20DROP%20TABLE%20items")
    assert injected.status_code == 400
    assert injected.json["code"] == "DB_IDENTIFIER_INVALID"


def test_script_route_commits_and_rolls_back(tmp_path):
    client = _client(tmp_path)

    committed = client.post(
        "/internal/db-console/script",
        json={"statements": ["INSERT INTO items (name, qty) VALUES ('s1', 1)", "INSERT INTO items (name, qty) VALUES ('s2', 2)"]},
    )
    assert committed.status_code == 200
    assert committed.json["data"]["statements"][0]["statementType"] == "INSERT"

    rolled_back = client.post(
        "/internal/db-console/script",
        json={"statements": ["INSERT INTO items (name, qty) VALUES ('s3', 3)", "DELETE FROM missing_table"]},
    )
    assert rolled_back.status_code == 400
    assert rolled_back.json["code"] == "SCRIPT_ROLLED_BACK"

    verify = client.post("/internal/db-console/sql", json={"statement": "SELECT COUNT(*) FROM items WHERE name = 's3'"})
    assert verify.json["data"]["rows"] == [[0]]


def test_management_routes_without_database_return_503():
    client = create_app(
        runtime=UnmanagedDatabaseRuntime(),
        log_store=ConsoleLogStore(),
    ).test_client()

    response = client.get("/internal/db-console/schema")
    assert response.status_code == 503
    assert response.json["code"] == "DB_CONSOLE_NOT_CONFIGURED"
