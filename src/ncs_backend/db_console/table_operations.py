"""Direct table data operations for the local database console.

Provides SQL-free data management: browse, insert, update, delete, truncate
and drop. All identifiers are validated and quoted, all values are bound as
parameters. Destructive operations require an explicit confirm flag.
"""

from __future__ import annotations

from typing import Any, Callable

from ncs_backend.db_console.sql_identifiers import (
    quote_identifier,
    quote_qualified,
    validate_identifier,
    validate_identifier_list,
)
from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT

ConnectionFactory = Callable[[], Any]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

CONFIRM_REQUIRED = "DB_DESTRUCTIVE_CONFIRM_REQUIRED"


class TableOperationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class TableOperations:
    def __init__(self, connection_factory: ConnectionFactory, *, dialect: DatabaseDialect) -> None:
        self._factory = connection_factory
        self._dialect = dialect

    # ------------------------------------------------------------------ read

    def browse(
        self,
        table: str,
        *,
        schema: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
        column: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        validate_identifier(table, kind="table name")
        if limit < 1:
            limit = DEFAULT_PAGE_SIZE
        limit = min(limit, MAX_PAGE_SIZE)
        if offset < 0:
            offset = 0

        where_sql = ""
        parameters: list[Any] = []
        if column is not None:
            validate_identifier(column, kind="column name")
            if search is None:
                raise TableOperationError("DB_FILTER_REQUIRED", "column filter requires a search value")
            where_sql = f" WHERE {quote_identifier(column, self._dialect)} = {self._dialect.placeholder}"
            parameters.append(search)
        elif search is not None:
            raise TableOperationError("DB_FILTER_REQUIRED", "search value requires a column name")

        order_sql = ""
        if order_by is not None:
            validate_identifier(order_by, kind="order column")
            direction = "DESC" if descending else "ASC"
            order_sql = f" ORDER BY {quote_identifier(order_by, self._dialect)} {direction}"

        connection = self._factory()
        try:
            cursor = connection.cursor()
            target = quote_qualified(schema, table, self._dialect)
            cursor.execute(f"SELECT COUNT(*) FROM {target}{where_sql}", parameters)
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT * FROM {target}{where_sql}{order_sql} "
                f"LIMIT {self._limit_clause(limit, offset)}",
                parameters,
            )
            columns = [description[0] for description in cursor.description or []]
            rows = [tuple(row) for row in cursor.fetchall()]
            cursor.close()
            return {"table": table, "total": total, "columns": columns, "rows": rows}
        finally:
            connection.close()

    # ----------------------------------------------------------------- write

    def insert(self, table: str, values: dict[str, Any], *, schema: str | None = None) -> int:
        validate_identifier(table, kind="table name")
        if not values:
            raise TableOperationError("DB_VALUES_REQUIRED", "insert requires at least one column value")
        columns = validate_identifier_list(values.keys(), kind="column name")
        connection = self._factory()
        try:
            cursor = connection.cursor()
            column_sql = ", ".join(quote_identifier(name, self._dialect) for name in columns)
            placeholder_sql = ", ".join([self._dialect.placeholder] * len(columns))
            cursor.execute(
                f"INSERT INTO {quote_qualified(schema, table, self._dialect)} ({column_sql}) "
                f"VALUES ({placeholder_sql})",
                [values[name] for name in columns],
            )
            affected = cursor.rowcount
            connection.commit()
            cursor.close()
            return affected
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update(
        self,
        table: str,
        keys: dict[str, Any],
        values: dict[str, Any],
        *,
        schema: str | None = None,
    ) -> int:
        validate_identifier(table, kind="table name")
        key_names = validate_identifier_list(keys.keys(), kind="key column")
        if not key_names:
            raise TableOperationError("DB_KEYS_REQUIRED", "update requires at least one key column")
        if not values:
            raise TableOperationError("DB_VALUES_REQUIRED", "update requires at least one column value")
        value_names = validate_identifier_list(values.keys(), kind="column name")

        set_sql = ", ".join(
            f"{quote_identifier(name, self._dialect)} = {self._dialect.placeholder}" for name in value_names
        )
        where_sql = " AND ".join(
            f"{quote_identifier(name, self._dialect)} = {self._dialect.placeholder}" for name in key_names
        )
        parameters = [values[name] for name in value_names] + [keys[name] for name in key_names]

        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"UPDATE {quote_qualified(schema, table, self._dialect)} SET {set_sql} WHERE {where_sql}",
                parameters,
            )
            affected = cursor.rowcount
            connection.commit()
            cursor.close()
            return affected
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def delete(self, table: str, keys: dict[str, Any], *, schema: str | None = None) -> int:
        validate_identifier(table, kind="table name")
        key_names = validate_identifier_list(keys.keys(), kind="key column")
        if not key_names:
            raise TableOperationError("DB_KEYS_REQUIRED", "delete requires at least one key column")
        where_sql = " AND ".join(
            f"{quote_identifier(name, self._dialect)} = {self._dialect.placeholder}" for name in key_names
        )
        parameters = [keys[name] for name in key_names]

        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"DELETE FROM {quote_qualified(schema, table, self._dialect)} WHERE {where_sql}",
                parameters,
            )
            affected = cursor.rowcount
            connection.commit()
            cursor.close()
            return affected
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ------------------------------------------------------------ destructive

    def truncate(self, table: str, *, schema: str | None = None, confirm: bool = False) -> str:
        validate_identifier(table, kind="table name")
        self._require_confirm(confirm)
        connection = self._factory()
        try:
            cursor = connection.cursor()
            target = quote_qualified(schema, table, self._dialect)
            if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
                cursor.execute(f"TRUNCATE TABLE {target}")
            else:
                cursor.execute(f"DELETE FROM {target}")
                if table_has_sqlite_sequence(cursor, table):
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
            connection.commit()
            cursor.close()
            return "truncated"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def drop(self, table: str, *, schema: str | None = None, confirm: bool = False) -> str:
        validate_identifier(table, kind="table name")
        self._require_confirm(confirm)
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(f"DROP TABLE {quote_qualified(schema, table, self._dialect)}")
            connection.commit()
            cursor.close()
            return "dropped"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ---------------------------------------------------------------- helpers

    def _require_confirm(self, confirm: bool) -> None:
        if confirm is not True:
            raise TableOperationError(
                CONFIRM_REQUIRED,
                "destructive operation requires confirm=true in the request body",
            )

    def _limit_clause(self, limit: int, offset: int) -> str:
        if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
            return f"{limit} OFFSET {offset}" if offset else f"{limit}"
        return f"{limit} OFFSET {offset}"


def table_has_sqlite_sequence(cursor: Any, table: str) -> bool:
    try:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
        )
        return cursor.fetchone() is not None
    except Exception:
        return False
