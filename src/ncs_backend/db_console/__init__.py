"""Small local database console for development and student demonstrations."""

from ncs_backend.db_console.log_store import ConsoleLogEntry, ConsoleLogStore
from ncs_backend.db_console.sql_executor import (
    SqlExecutionError,
    SqlExecutionResult,
    SqlExecutor,
)

__all__ = [
    "ConsoleLogEntry",
    "ConsoleLogStore",
    "SqlExecutionError",
    "SqlExecutionResult",
    "SqlExecutor",
]
