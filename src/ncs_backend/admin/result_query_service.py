"""Read-only inspection of the ADS result tables for the admin API.

Exposes the rpt_* result tables through a strict whitelist so that
imported batches can be verified and reconciled without direct
database access. Read-only by design: the service never issues
INSERT/UPDATE/DELETE/DDL statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Callable

from ncs_backend.admin.ads_schema import ADS_SCHEMA_STATEMENTS
from ncs_backend.db_console.sql_identifiers import quote_identifier, validate_identifier
from ncs_backend.shared.db import DatabaseDialect

ConnectionFactory = Callable[[], Any]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _result_table_names() -> tuple[str, ...]:
    tables = {
        match.group(1)
        for statement in ADS_SCHEMA_STATEMENTS
        for match in [re.match(r"\s*CREATE TABLE IF NOT EXISTS (\w+)", statement)]
        if match and match.group(1).startswith("rpt_")
    }
    return tuple(sorted(tables))


RESULT_TABLE_NAMES: tuple[str, ...] = _result_table_names()


@dataclass(frozen=True, slots=True)
class ResultTableSummary:
    name: str
    row_count: int


class ResultTableQueryService:
    def __init__(self, connection_factory: ConnectionFactory, *, dialect: DatabaseDialect) -> None:
        self._factory = connection_factory
        self._dialect = dialect

    def list_tables(self) -> tuple[ResultTableSummary, ...]:
        counts: list[ResultTableSummary] = []
        for table in RESULT_TABLE_NAMES:
            counts.append(ResultTableSummary(name=table, row_count=self._row_count(table)))
        return tuple(counts)

    def browse(
        self,
        table: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        if table not in RESULT_TABLE_NAMES:
            raise ValueError(f"unknown result table: {table}")
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        quoted = quote_identifier(table, self._dialect)
        order_clause = ""
        if order_by:
            validate_identifier(order_by, kind="column name")
            direction = "DESC" if descending else "ASC"
            order_clause = f" ORDER BY {quote_identifier(order_by, self._dialect)} {direction}"
        connection = self._factory()
        try:
            cursor = self._dialect.cursor(connection)
            cursor.execute(f"SELECT COUNT(*) FROM {quoted}")
            total = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT * FROM {quoted}{order_clause} LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            columns = tuple(column[0] for column in cursor.description or ())
            rows = cursor.fetchall()
            cursor.close()
            return {
                "table": table,
                "total": total,
                "columns": list(columns),
                "rows": [tuple(_json_safe(value) for value in row) for row in rows],
            }
        finally:
            connection.close()

    def _row_count(self, table: str) -> int:
        connection = self._factory()
        try:
            cursor = self._dialect.cursor(connection)
            cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(table, self._dialect)}")
            return int(cursor.fetchone()[0])
        finally:
            connection.close()


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
