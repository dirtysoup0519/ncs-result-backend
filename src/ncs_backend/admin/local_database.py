"""Bootstrap and inspect the persistent SQLite database used for local development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from ncs_backend.admin.migrations import (
    CONTROL_TABLES,
    DEFAULT_MIGRATIONS,
    MIGRATION_TABLE,
    STAGING_TABLES,
    MigrationRunner,
)

REQUIRED_TABLES = (MIGRATION_TABLE, *CONTROL_TABLES, *STAGING_TABLES)
EXPECTED_VERSIONS = tuple(migration.version for migration in DEFAULT_MIGRATIONS)


@dataclass(frozen=True, slots=True)
class LocalDatabaseStatus:
    database: Path
    valid: bool
    tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    applied_versions: tuple[int, ...]
    expected_versions: tuple[int, ...] = EXPECTED_VERSIONS

    def to_dict(self) -> dict[str, object]:
        return {
            "database": str(self.database),
            "valid": self.valid,
            "tables": list(self.tables),
            "missingTables": list(self.missing_tables),
            "appliedVersions": list(self.applied_versions),
            "expectedVersions": list(self.expected_versions),
        }


def initialize_local_database(database: Path) -> LocalDatabaseStatus:
    path = Path(database).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        MigrationRunner().apply(connection)
    finally:
        connection.close()
    return inspect_local_database(path)


def inspect_local_database(database: Path) -> LocalDatabaseStatus:
    path = Path(database).resolve()
    if not path.is_file():
        return LocalDatabaseStatus(path, False, (), REQUIRED_TABLES, ())

    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        tables = tuple(str(row[0]) for row in table_rows if not str(row[0]).startswith("sqlite_"))
        versions: tuple[int, ...] = ()
        if MIGRATION_TABLE in tables:
            versions = tuple(
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM ctl_schema_migration ORDER BY version"
                ).fetchall()
            )
    finally:
        connection.close()

    missing = tuple(table for table in REQUIRED_TABLES if table not in tables)
    valid = not missing and versions == EXPECTED_VERSIONS
    return LocalDatabaseStatus(path, valid, tables, missing, versions)
