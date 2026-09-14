import sqlite3

import pytest

from ncs_backend.db_console.log_store import ConsoleLogStore
from ncs_backend.db_console.sql_executor import SqlExecutionError, SqlExecutor


def _executor(tmp_path, *, max_rows=500):
    database = tmp_path / "console.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    connection.executemany("INSERT INTO items (name) VALUES (?)", [(f"item-{i}",) for i in range(3)])
    connection.commit()
    connection.close()
    logs = ConsoleLogStore()
    return SqlExecutor(lambda: sqlite3.connect(database), logs, max_rows=max_rows), logs, database


def test_select_returns_columns_rows_and_log(tmp_path):
    executor, logs, _ = _executor(tmp_path)

    result = executor.execute("SELECT id, name FROM items ORDER BY id")

    assert result.statement_type == "SELECT"
    assert result.columns == ("id", "name")
    assert result.rows == ((1, "item-0"), (2, "item-1"), (3, "item-2"))
    assert result.affected_rows is None
    assert logs.last_sequence == 1
    assert logs.list()[0].action == "SELECT"


def test_write_commits_and_returns_affected_rows(tmp_path):
    executor, _, database = _executor(tmp_path)

    result = executor.execute("UPDATE items SET name = 'changed' WHERE id = 2")

    assert result.affected_rows == 1
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT name FROM items WHERE id = 2").fetchone() == ("changed",)
    connection.close()


def test_failed_sql_rolls_back_and_logs_error(tmp_path):
    executor, logs, database = _executor(tmp_path)

    with pytest.raises(SqlExecutionError):
        executor.execute("UPDATE items SET missing_column = 'changed'")

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT COUNT(*) FROM items WHERE name = 'changed'").fetchone() == (0,)
    connection.close()
    assert logs.list()[0].level == "ERROR"


def test_select_is_limited_and_multiple_statements_are_rejected(tmp_path):
    executor, _, _ = _executor(tmp_path, max_rows=2)

    result = executor.execute("SELECT id FROM items ORDER BY id")
    assert result.row_count == 2
    assert result.truncated is True

    with pytest.raises(ValueError, match="one SQL statement"):
        executor.execute("SELECT 1; SELECT 2")


def test_log_store_keeps_incremental_cursor_and_bounded_history():
    store = ConsoleLogStore(max_entries=2)
    store.append(category="SQL", level="INFO", action="SELECT", message="one")
    store.append(category="SQL", level="INFO", action="SELECT", message="two")
    store.append(category="SQL", level="INFO", action="SELECT", message="three")

    assert [item.sequence for item in store.list()] == [2, 3]
    assert [item.message for item in store.list(after=2)] == ["three"]
