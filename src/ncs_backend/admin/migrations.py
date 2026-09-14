"""Idempotent control-plane schema for the data administration service."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from typing import Any

CONTROL_TABLES = (
    "ctl_dataset",
    "ctl_schema_version",
    "ctl_import_batch",
    "ctl_quality_result",
    "ctl_publication",
    "ctl_audit_log",
)

STAGING_TABLES = ("stg_import_row",)

MIGRATION_TABLE = "ctl_schema_migration"

MIGRATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ctl_schema_migration (
    version INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP NOT NULL
)
"""

CONTROL_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS ctl_dataset (
        dataset_code VARCHAR(128) PRIMARY KEY,
        display_name VARCHAR(255) NOT NULL,
        owner VARCHAR(128) NOT NULL,
        current_schema_version VARCHAR(32),
        status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_schema_version (
        dataset_code VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        schema_json TEXT NOT NULL,
        schema_checksum VARCHAR(64) NOT NULL,
        compatibility VARCHAR(32) NOT NULL DEFAULT 'BACKWARD',
        created_at TIMESTAMP NOT NULL,
        PRIMARY KEY (dataset_code, schema_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_import_batch (
        batch_id VARCHAR(128) PRIMARY KEY,
        dataset_code VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        source_batch_id VARCHAR(128) NOT NULL,
        source_uri TEXT NOT NULL,
        source_sha256 VARCHAR(64) NOT NULL,
        data_date DATE NOT NULL,
        row_count BIGINT NOT NULL DEFAULT 0,
        status VARCHAR(32) NOT NULL,
        error_summary TEXT,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        published_at TIMESTAMP,
        UNIQUE (dataset_code, source_batch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_quality_result (
        result_id VARCHAR(128) PRIMARY KEY,
        batch_id VARCHAR(128) NOT NULL,
        rule_code VARCHAR(128) NOT NULL,
        severity VARCHAR(32) NOT NULL,
        passed BOOLEAN NOT NULL,
        checked_row_count BIGINT NOT NULL DEFAULT 0,
        failure_count BIGINT NOT NULL DEFAULT 0,
        details_json TEXT,
        created_at TIMESTAMP NOT NULL,
        UNIQUE (batch_id, rule_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_publication (
        publication_id VARCHAR(128) PRIMARY KEY,
        dataset_code VARCHAR(128) NOT NULL,
        batch_id VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL,
        supersedes_publication_id VARCHAR(128),
        published_at TIMESTAMP NOT NULL,
        retracted_at TIMESTAMP,
        UNIQUE (dataset_code, batch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_audit_log (
        audit_id VARCHAR(128) PRIMARY KEY,
        action VARCHAR(128) NOT NULL,
        actor VARCHAR(255) NOT NULL,
        resource_type VARCHAR(128) NOT NULL,
        resource_id VARCHAR(128),
        request_id VARCHAR(128),
        details_json TEXT,
        created_at TIMESTAMP NOT NULL
    )
    """,
)

STAGING_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS stg_import_row (
        batch_id VARCHAR(128) NOT NULL,
        row_number BIGINT NOT NULL,
        payload_json TEXT NOT NULL,
        row_sha256 VARCHAR(64) NOT NULL,
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, row_number)
    )
    """,
)


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        payload = "\n".join(statement.strip() for statement in self.statements).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class MigrationResult:
    applied: tuple[int, ...]
    skipped: tuple[int, ...]


DEFAULT_MIGRATIONS = (
    Migration(1, "control-schema", tuple(CONTROL_SCHEMA_SQL)),
    Migration(2, "staging-schema", tuple(STAGING_SCHEMA_SQL)),
)


class MigrationError(RuntimeError):
    """Raised when migration history is inconsistent or cannot be applied."""


class MigrationRunner:
    """Apply ordered, checksummed DB-API migrations."""

    def __init__(self, migrations: Iterable[Migration] = DEFAULT_MIGRATIONS, *, placeholder: str = "?") -> None:
        ordered = tuple(sorted(migrations, key=lambda item: item.version))
        versions = [item.version for item in ordered]
        if len(set(versions)) != len(versions) or any(version <= 0 for version in versions):
            raise ValueError("migration versions must be unique positive integers")
        self._migrations = ordered
        self._placeholder = placeholder

    def apply(self, connection: Any) -> MigrationResult:
        cursor = connection.cursor()
        applied: list[int] = []
        skipped: list[int] = []
        try:
            cursor.execute(MIGRATION_SCHEMA_SQL)
            rows = cursor.execute(
                "SELECT version, checksum FROM ctl_schema_migration"
            ).fetchall()
            history = {int(version): checksum for version, checksum in rows}
            for migration in self._migrations:
                previous = history.get(migration.version)
                if previous is not None:
                    if previous != migration.checksum:
                        raise MigrationError(
                            f"migration checksum mismatch: v{migration.version} {migration.name}"
                        )
                    skipped.append(migration.version)
                    continue
                for statement in migration.statements:
                    cursor.execute(statement)
                cursor.execute(
                    "INSERT INTO ctl_schema_migration "
                    f"(version, name, checksum, applied_at) VALUES ({self._placeholder}, {self._placeholder}, {self._placeholder}, CURRENT_TIMESTAMP)",
                    (migration.version, migration.name, migration.checksum),
                )
                applied.append(migration.version)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
        return MigrationResult(tuple(applied), tuple(skipped))


def initialize_control_schema(connection: Any, statements: Iterable[str] = CONTROL_SCHEMA_SQL) -> tuple[str, ...]:
    """Create control tables atomically and return their logical names."""

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return CONTROL_TABLES


def initialize_staging_schema(connection: Any, statements: Iterable[str] = STAGING_SCHEMA_SQL) -> tuple[str, ...]:
    """Create local staging tables atomically and return their logical names."""

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return STAGING_TABLES
