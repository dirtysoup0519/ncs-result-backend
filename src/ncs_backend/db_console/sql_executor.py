"""Transactional DB-API SQL execution for the local database console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from ncs_backend.db_console.log_store import ConsoleLogStore

ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class SqlExecutionResult:
    query_id: str
    statement_type: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    affected_rows: int | None
    truncated: bool
    duration_ms: int


class SqlExecutionError(RuntimeError):
    def __init__(self, query_id: str, statement_type: str, cause: Exception) -> None:
        self.query_id = query_id
        self.statement_type = statement_type
        self.cause = cause
        super().__init__(str(cause))


class SqlExecutor:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        log_store: ConsoleLogStore,
        *,
        max_rows: int = 500,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be positive")
        self._connection_factory = connection_factory
        self._log_store = log_store
        self._max_rows = max_rows

    def execute(self, statement: str) -> SqlExecutionResult:
        normalized = _normalize_statement(statement)
        statement_type = _statement_type(normalized)
        query_id = f"sql-{uuid4().hex}"
        started = monotonic()
        connection = None
        cursor = None
        try:
            connection = self._connection_factory()
            cursor = connection.cursor()
            cursor.execute(normalized)
            duration_ms = _elapsed_ms(started)
            if cursor.description:
                columns = tuple(str(column[0]) for column in cursor.description)
                values = tuple(tuple(row) for row in cursor.fetchmany(self._max_rows + 1))
                truncated = len(values) > self._max_rows
                rows = values[: self._max_rows]
                connection.commit()
                result = SqlExecutionResult(
                    query_id=query_id,
                    statement_type=statement_type,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    affected_rows=None,
                    truncated=truncated,
                    duration_ms=duration_ms,
                )
                self._log_store.append(
                    category="SQL",
                    level="INFO",
                    action=statement_type,
                    message=f"执行成功，返回 {len(rows)} 行",
                    duration_ms=duration_ms,
                )
                return result

            affected_rows = cursor.rowcount if cursor.rowcount >= 0 else 0
            connection.commit()
            result = SqlExecutionResult(
                query_id=query_id,
                statement_type=statement_type,
                columns=(),
                rows=(),
                row_count=0,
                affected_rows=affected_rows,
                truncated=False,
                duration_ms=duration_ms,
            )
            self._log_store.append(
                category="SQL",
                level="INFO",
                action=statement_type,
                message=f"执行成功，影响 {affected_rows} 行",
                duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
            duration_ms = _elapsed_ms(started)
            self._log_store.append(
                category="SQL",
                level="ERROR",
                action=statement_type,
                message=f"执行失败：{_safe_error_message(exc)}",
                duration_ms=duration_ms,
            )
            raise SqlExecutionError(query_id, statement_type, exc) from exc
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()


def _normalize_statement(statement: str) -> str:
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("SQL statement is required")
    value = statement.strip()
    if _has_non_terminal_semicolon(value):
        raise ValueError("only one SQL statement is allowed")
    return value.rstrip(";").rstrip()


def _has_non_terminal_semicolon(value: str) -> bool:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == ";" and value[index + 1 :].strip():
            return True
    return False


def _statement_type(statement: str) -> str:
    without_comments = re.sub(r"^\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/\s*)*", "", statement, flags=re.DOTALL)
    match = re.match(r"([A-Za-z]+)", without_comments)
    return match.group(1).upper() if match else "UNKNOWN"


def _elapsed_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))


def _safe_error_message(error: Exception) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ")
    return message[:300] or error.__class__.__name__


def json_value(value: Any) -> Any:
    """Convert common DB-API scalar values to JSON-compatible values."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
