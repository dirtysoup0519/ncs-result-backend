import sqlite3

from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.shared.db import MYSQL_DIALECT, SQLITE_DIALECT


def test_mysql_dialect_translates_parameters_but_not_quoted_question_marks():
    sql = "SELECT '?' AS literal, value FROM sample WHERE id = ? AND note = \"?\""

    assert MYSQL_DIALECT.prepare(sql) == (
        "SELECT '?' AS literal, value FROM sample WHERE id = %s AND note = \"?\""
    )


def test_sqlite_dialect_keeps_qmark_templates():
    sql = "SELECT value FROM sample WHERE id = ?"

    assert SQLITE_DIALECT.prepare(sql) == sql


def test_migration_runner_uses_dialect_cursor_with_sqlite(tmp_path):
    connection = sqlite3.connect(tmp_path / "control.sqlite")
    try:
        result = MigrationRunner(dialect=SQLITE_DIALECT).apply(connection)
    finally:
        connection.close()

    assert result.applied == (1, 2)
