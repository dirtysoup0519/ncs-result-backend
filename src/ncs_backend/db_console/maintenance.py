"""Server-level maintenance operations for the local database console.

MySQL: server info, processlist, kill query, ANALYZE/OPTIMIZE, variables.
SQLite: version, vacuum, wal checkpoint, integrity check.
Destructive actions (kill) require an explicit confirm flag.
"""

from __future__ import annotations

from typing import Any, Callable

from ncs_backend.db_console.sql_identifiers import quote_identifier, validate_identifier
from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT

ConnectionFactory = Callable[[], Any]

CONFIRM_REQUIRED = "DB_DESTRUCTIVE_CONFIRM_REQUIRED"


class MaintenanceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class MaintenanceOperations:
    def __init__(self, connection_factory: ConnectionFactory, *, dialect: DatabaseDialect) -> None:
        self._factory = connection_factory
        self._dialect = dialect

    def server_info(self) -> dict[str, Any]:
        if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
            return self._mysql_info()
        return self._sqlite_info()

    def processlist(self) -> dict[str, Any]:
        self._require_mysql("processlist")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute("SHOW FULL PROCESSLIST")
            columns = [description[0] for description in cursor.description or []]
            rows = [tuple(row) for row in cursor.fetchall()]
            cursor.close()
            return {"columns": columns, "rows": rows}
        finally:
            connection.close()

    def kill_query(self, query_id: int, *, confirm: bool = False) -> str:
        self._require_mysql("kill-query")
        if not isinstance(query_id, int) or query_id < 1:
            raise MaintenanceError("DB_QUERY_ID_INVALID", "query id must be a positive integer")
        if confirm is not True:
            raise MaintenanceError(
                CONFIRM_REQUIRED,
                "killing a running query requires confirm=true in the request body",
            )
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(f"KILL {int(query_id)}")
            connection.commit()
            cursor.close()
            return f"kill issued for connection {query_id}"
        finally:
            connection.close()

    def variables(self, pattern: str | None = None) -> dict[str, Any]:
        self._require_mysql("variables")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            if pattern:
                cursor.execute("SHOW VARIABLES LIKE %s", (pattern,))
            else:
                cursor.execute("SHOW VARIABLES")
            rows = [(str(name), str(value)) for name, value in cursor.fetchall()]
            cursor.close()
            return {"variables": dict(rows)}
        finally:
            connection.close()

    def optimize(self, table: str | None = None, *, schema: str | None = None) -> str:
        self._require_mysql("optimize")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            if table:
                validate_identifier(table, kind="table name")
                target = quote_identifier(table, self._dialect)
                if schema:
                    target = f"{quote_identifier(schema, self._dialect)}.{target}"
            else:
                cursor.execute("SHOW TABLES")
                target = ", ".join(quote_identifier(row[0], self._dialect) for row in cursor.fetchall())
            cursor.execute(f"OPTIMIZE TABLE {target}")
            connection.commit()
            cursor.close()
            return f"optimize issued for {table or 'all tables'}"
        finally:
            connection.close()

    def analyze(self, table: str | None = None, *, schema: str | None = None) -> str:
        self._require_mysql("analyze")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            if table:
                validate_identifier(table, kind="table name")
                target = quote_identifier(table, self._dialect)
                if schema:
                    target = f"{quote_identifier(schema, self._dialect)}.{target}"
            else:
                cursor.execute("SHOW TABLES")
                target = ", ".join(quote_identifier(row[0], self._dialect) for row in cursor.fetchall())
            cursor.execute(f"ANALYZE TABLE {target}")
            connection.commit()
            cursor.close()
            return f"analyze issued for {table or 'all tables'}"
        finally:
            connection.close()

    def vacuum(self, *, confirm: bool = False) -> str:
        self._require_sqlite("vacuum")
        if confirm is not True:
            raise MaintenanceError(
                CONFIRM_REQUIRED,
                "VACUUM rewrites the whole database file and requires confirm=true",
            )
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute("VACUUM")
            connection.commit()
            cursor.close()
            return "vacuum completed"
        finally:
            connection.close()

    def checkpoint(self) -> str:
        self._require_sqlite("checkpoint")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cursor.fetchall()
            connection.commit()
            cursor.close()
            return "wal checkpoint completed"
        finally:
            connection.close()

    def integrity_check(self) -> dict[str, Any]:
        self._require_sqlite("integrity-check")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA integrity_check")
            results = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            return {"results": results}
        finally:
            connection.close()

    # ---------------------------------------------------------------- helpers

    def _require_mysql(self, action: str) -> None:
        if not (self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql"):
            raise MaintenanceError("DB_MYSQL_ONLY", f"{action} is only available on MySQL")

    def _require_sqlite(self, action: str) -> None:
        if self._dialect.name != "sqlite":
            raise MaintenanceError("DB_SQLITE_ONLY", f"{action} is only available on SQLite")

    def _mysql_info(self) -> dict[str, Any]:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            info: dict[str, Any] = {}
            cursor.execute("SELECT VERSION()")
            info["version"] = str(cursor.fetchone()[0])
            cursor.execute("SELECT CURRENT_USER()")
            info["current_user"] = str(cursor.fetchone()[0])
            cursor.execute("SELECT DATABASE()")
            row = cursor.fetchone()
            info["database"] = str(row[0]) if row and row[0] else None
            cursor.execute("SHOW VARIABLES LIKE 'character_set_server'")
            match = cursor.fetchone()
            if match:
                info["character_set_server"] = str(match[1])
            cursor.close()
            return info
        finally:
            connection.close()

    def _sqlite_info(self) -> dict[str, Any]:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = str(cursor.fetchone()[0])
            cursor.execute("PRAGMA database_list")
            database = None
            for _, name, _file in cursor.fetchall():
                database = str(name)
                break
            cursor.close()
            return {"version": version, "database": database}
        finally:
            connection.close()
