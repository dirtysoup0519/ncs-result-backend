"""Small DB-API dialect boundary without an ORM dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DatabaseDialect:
    name: str
    placeholder: str

    def prepare(self, sql: str) -> str:
        """Translate qmark templates while preserving quoted question marks."""

        if self.placeholder == "?":
            return sql
        output: list[str] = []
        quote: str | None = None
        index = 0
        while index < len(sql):
            char = sql[index]
            if quote:
                output.append(char)
                if char == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        output.append(sql[index + 1])
                        index += 1
                    else:
                        quote = None
            elif char in {"'", '"', "`"}:
                quote = char
                output.append(char)
            elif char == "?":
                output.append(self.placeholder)
            else:
                output.append(char)
            index += 1
        return "".join(output)

    def cursor(self, connection: Any) -> "DialectCursor":
        return DialectCursor(connection.cursor(), self)


class DialectCursor:
    """Delegate a DB-API cursor while adapting SQL parameter markers."""

    def __init__(self, cursor: Any, dialect: DatabaseDialect) -> None:
        self._cursor = cursor
        self._dialect = dialect

    def execute(self, sql: str, parameters: Any = None):
        prepared = self._dialect.prepare(sql)
        if parameters is None:
            self._cursor.execute(prepared)
        else:
            self._cursor.execute(prepared, parameters)
        return self

    def executemany(self, sql: str, parameter_rows: Any):
        self._cursor.executemany(self._dialect.prepare(sql), parameter_rows)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def close(self) -> None:
        self._cursor.close()
