"""Transactional multi-statement script execution for the database console.

All statements run inside one transaction: either every statement commits
or the whole script rolls back. This is the managed way to run multi-step
changes; the single-statement endpoint stays available for quick edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from ncs_backend.db_console.log_store import ConsoleLogStore
from ncs_backend.db_console.sql_executor import _statement_type, _safe_error_message
from ncs_backend.shared.db import DatabaseDialect

ConnectionFactory = Callable[[], Any]

MAX_SCRIPT_STATEMENTS = 50


@dataclass(frozen=True, slots=True)
class ScriptStatementResult:
    index: int
    statement_type: str
    affected_rows: int | None


@dataclass(frozen=True, slots=True)
class ScriptResult:
    script_id: str
    committed: bool
    statements: tuple[ScriptStatementResult, ...]
    duration_ms: int
    error: str | None = None


class ScriptRunner:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        logs: ConsoleLogStore,
        *,
        dialect: DatabaseDialect,
    ) -> None:
        self._factory = connection_factory
        self._logs = logs
        self._dialect = dialect

    def run(self, statements: list[str]) -> ScriptResult:
        if not statements or not any(statement.strip() for statement in statements):
            raise ValueError("script requires at least one SQL statement")
        cleaned = [statement for statement in statements if statement.strip()]
        if len(cleaned) > MAX_SCRIPT_STATEMENTS:
            raise ValueError(f"script supports at most {MAX_SCRIPT_STATEMENTS} statements")

        started = monotonic()
        results: list[ScriptStatementResult] = []
        error: str | None = None
        connection = self._factory()
        try:
            cursor = connection.cursor()
            for index, statement in enumerate(cleaned, start=1):
                statement_type = _statement_type(statement)
                cursor.execute(statement)
                affected = cursor.rowcount if statement_type in {"INSERT", "UPDATE", "DELETE"} else None
                results.append(
                    ScriptStatementResult(index=index, statement_type=statement_type, affected_rows=affected)
                )
                self._logs.append(
                    category="SCRIPT",
                    level="INFO",
                    action=statement_type,
                    message=f"statement {index}/{len(cleaned)} ok",
                )
            connection.commit()
            committed = True
        except Exception as exc:
            committed = False
            error = _safe_error_message(exc)
            try:
                connection.rollback()
            except Exception:
                pass
            self._logs.append(category="SCRIPT", level="ERROR", action="SCRIPT", message=f"rolled back: {error}")
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            connection.close()

        result = ScriptResult(
            script_id=f"script-{uuid4().hex}",
            committed=committed,
            statements=tuple(results),
            duration_ms=max(0, int((monotonic() - started) * 1000)),
            error=error,
        )
        return result
