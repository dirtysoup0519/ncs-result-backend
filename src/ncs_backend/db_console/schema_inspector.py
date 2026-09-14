"""Read-only metadata inspection for the local database console.

Dialect-aware introspection over plain DB-API connections:
MySQL uses information_schema, SQLite uses pragma statements.
No business data is read here beyond lightweight row counts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from ncs_backend.db_console.sql_identifiers import quote_qualified, quote_identifier, validate_identifier
from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT

ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class TableSummary:
    name: str
    kind: str  # "table" or "view"
    column_count: int
    row_count: int | None  # None when an estimate is unavailable or too costly


@dataclass(frozen=True, slots=True)
class ColumnDetail:
    name: str
    data_type: str
    nullable: bool
    default: str | None
    key: str | None


@dataclass(frozen=True, slots=True)
class IndexDetail:
    name: str
    columns: tuple[str, ...]
    unique: bool


class SchemaInspector:
    def __init__(self, connection_factory: ConnectionFactory, *, dialect: DatabaseDialect) -> None:
        self._factory = connection_factory
        self._dialect = dialect

    def list_tables(self, *, schema: str | None = None) -> tuple[TableSummary, ...]:
        if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
            return self._list_tables_mysql(schema)
        return self._list_tables_sqlite()

    def table_detail(self, table: str, *, schema: str | None = None) -> dict[str, Any]:
        validate_identifier(table, kind="table name")
        columns = self._columns(table, schema=schema)
        return {
            "table": table,
            "columns": [asdict(column) for column in columns],
            "indexes": [asdict(index) for index in self._indexes(table, schema=schema)],
            "row_count": self._row_count(table, schema=schema),
        }

    def _list_tables_mysql(self, schema: str | None) -> tuple[TableSummary, ...]:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT table_name, table_type, COALESCE(table_rows, 0) "
                "FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
                (schema or self._current_schema(cursor),),
            )
            summaries: list[TableSummary] = []
            for name, kind, rows in cursor.fetchall():
                summaries.append(
                    TableSummary(
                        name=name,
                        kind=kind.lower(),
                        column_count=self._mysql_column_count(connection, name),
                        row_count=int(rows),
                    )
                )
            return tuple(summaries)
        finally:
            connection.close()

    def _list_tables_sqlite(self) -> tuple[TableSummary, ...]:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            entries = cursor.fetchall()
            summaries: list[TableSummary] = []
            for name, kind in entries:
                count_cursor = connection.cursor()
                count_cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(name, self._dialect)}")
                total = int(count_cursor.fetchone()[0])
                count_cursor.close()
                summaries.append(
                    TableSummary(
                        name=name,
                        kind="table" if kind == "table" else "view",
                        column_count=len(self._sqlite_columns(connection, name)),
                        row_count=total,
                    )
                )
            return tuple(summaries)
        finally:
            connection.close()

    def _columns(self, table: str, *, schema: str | None = None) -> tuple[ColumnDetail, ...]:
        if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
            return self._mysql_columns(table, schema=schema)
        connection = self._factory()
        try:
            return self._sqlite_columns(connection, table)
        finally:
            connection.close()

    def _mysql_columns(self, table: str, *, schema: str | None = None) -> tuple[ColumnDetail, ...]:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT column_name, column_type, is_nullable, column_default, column_key "
                "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema or self._current_schema(cursor), table),
            )
            return tuple(
                ColumnDetail(
                    name=name,
                    data_type=column_type,
                    nullable=nullable == "YES",
                    default=default,
                    key=key or None,
                )
                for name, column_type, nullable, default, key in cursor.fetchall()
            )
        finally:
            connection.close()

    def _sqlite_columns(self, connection: Any, table: str) -> tuple[ColumnDetail, ...]:
        cursor = connection.cursor()
        cursor.execute(f"PRAGMA table_info({quote_identifier(table, self._dialect)})")
        details: list[ColumnDetail] = []
        for _cid, name, column_type, not_null, default, pk in cursor.fetchall():
            details.append(
                ColumnDetail(
                    name=name,
                    data_type=column_type or "",
                    nullable=not int(not_null),
                    default=str(default) if default is not None else None,
                    key="PRI" if pk else None,
                )
            )
        return tuple(details)

    def _indexes(self, table: str, *, schema: str | None = None) -> tuple[IndexDetail, ...]:
        if self._dialect is MYSQL_DIALECT or self._dialect.name == "mysql":
            connection = self._factory()
            try:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT index_name, column_name, non_unique FROM information_schema.statistics "
                    "WHERE table_schema = %s AND table_name = %s ORDER BY index_name, seq_in_index",
                    (schema or self._current_schema(cursor), table),
                )
                return self._group_indexes(cursor.fetchall())
            finally:
                connection.close()
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(f"PRAGMA index_list({quote_identifier(table, self._dialect)})")
            index_rows = cursor.fetchall()
            indexes: list[IndexDetail] = []
            for row in index_rows:
                name = row[1]
                unique = not int(row[2])
                column_cursor = connection.cursor()
                column_cursor.execute(f"PRAGMA index_info({quote_identifier(name, self._dialect)})")
                columns = tuple(str(info[2]) for info in column_cursor.fetchall())
                column_cursor.close()
                indexes.append(IndexDetail(name=name, columns=columns, unique=unique))
            return tuple(indexes)
        finally:
            connection.close()

    def _group_indexes(self, rows) -> tuple[IndexDetail, ...]:
        grouped: dict[str, dict[str, Any]] = {}
        for index_name, column_name, non_unique in rows:
            entry = grouped.setdefault(index_name, {"columns": [], "unique": int(non_unique) == 0})
            entry["columns"].append(column_name)
        return tuple(
            IndexDetail(name=name, columns=tuple(entry["columns"]), unique=entry["unique"])
            for name, entry in grouped.items()
        )

    def _row_count(self, table: str, *, schema: str | None = None) -> int:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {quote_qualified(schema, table, self._dialect)}")
            return int(cursor.fetchone()[0])
        finally:
            connection.close()

    def _mysql_column_count(self, connection: Any, table: str) -> int:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table,),
        )
        return int(cursor.fetchone()[0])

    def _current_schema(self, cursor: Any) -> str:
        cursor.execute("SELECT DATABASE()")
        value = cursor.fetchone()[0]
        return value or ""
