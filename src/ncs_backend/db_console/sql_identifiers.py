"""Strict identifier validation and quoting shared by console management modules.

Console management endpoints build SQL from user-supplied table and column names.
Names are never interpolated raw: they must match a conservative whitelist and are
then quoted with the target dialect. Values are always bound as parameters.
"""

from __future__ import annotations

import re

from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MAX_IDENTIFIER_LENGTH = 64


class IdentifierError(ValueError):
    """Raised when a table or column name is not a safe simple identifier."""


def validate_identifier(name: str, *, kind: str = "identifier") -> str:
    if not isinstance(name, str):
        raise IdentifierError(f"{kind} must be a string")
    value = name.strip()
    if not value or not IDENTIFIER_PATTERN.match(value):
        raise IdentifierError(f"invalid {kind}: only [A-Za-z_][A-Za-z0-9_]* is allowed")
    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise IdentifierError(f"{kind} exceeds {MAX_IDENTIFIER_LENGTH} characters")
    return value


def validate_identifier_list(names, *, kind: str = "identifier") -> tuple[str, ...]:
    validated = tuple(validate_identifier(name, kind=kind) for name in names)
    if len(set(validated)) != len(validated):
        raise IdentifierError(f"duplicate {kind} names are not allowed")
    return validated


def quote_identifier(name: str, dialect: DatabaseDialect) -> str:
    """Quote a *validated* identifier for the target dialect."""

    validate_identifier(name)
    if dialect is MYSQL_DIALECT or dialect.name == "mysql":
        return f"`{name}`"
    return f'"{name}"'


def quote_qualified(schema: str | None, name: str, dialect: DatabaseDialect) -> str:
    quoted = quote_identifier(name, dialect)
    if schema:
        return f"{quote_identifier(schema, dialect)}.{quoted}"
    return quoted
