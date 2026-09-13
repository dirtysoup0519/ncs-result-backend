"""DB-API repositories for the control-plane batch and publication records.

The repository deliberately exposes business operations instead of accepting
arbitrary table names or SQL from callers.  The first adapter targets the
standard ``qmark`` DB-API style used by SQLite; a later MySQL adapter can keep
the same port and only change the connection/placeholder details.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
import json
from typing import Any, Protocol
from uuid import uuid4

from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId, DatasetCode, SchemaVersion

ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class ImportBatchRecord:
    batch_id: BatchId
    dataset_code: DatasetCode
    schema_version: SchemaVersion
    source_batch_id: str
    source_uri: str
    source_sha256: str
    data_date: date
    row_count: int
    status: BatchStatus
    error_summary: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_code: DatasetCode
    display_name: str
    owner: str
    current_schema_version: SchemaVersion | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SchemaVersionRecord:
    dataset_code: DatasetCode
    schema_version: SchemaVersion
    schema_json: str
    schema_checksum: str
    compatibility: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    publication_id: str
    dataset_code: DatasetCode
    batch_id: BatchId
    schema_version: SchemaVersion
    status: str
    supersedes_publication_id: str | None
    published_at: datetime
    retracted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class QualityResultRecord:
    result_id: str
    batch_id: BatchId
    rule_code: str
    severity: str
    passed: bool
    checked_row_count: int
    failure_count: int
    details_json: str | None
    created_at: datetime


class ControlRepository(Protocol):
    def get_dataset(self, dataset_code: DatasetCode) -> DatasetRecord | None: ...

    def insert_dataset(self, dataset: DatasetRecord) -> DatasetRecord: ...

    def update_dataset_schema(
        self,
        dataset_code: DatasetCode,
        schema_version: SchemaVersion,
        *,
        updated_at: datetime,
    ) -> DatasetRecord: ...

    def get_schema_version(
        self,
        dataset_code: DatasetCode,
        schema_version: SchemaVersion,
    ) -> SchemaVersionRecord | None: ...

    def insert_schema_version(self, schema: SchemaVersionRecord) -> SchemaVersionRecord: ...

    def find_batch_by_source(self, dataset_code: DatasetCode, source_batch_id: str) -> ImportBatchRecord | None: ...

    def get_batch(self, batch_id: BatchId) -> ImportBatchRecord | None: ...

    def insert_batch(self, batch: ImportBatchRecord) -> ImportBatchRecord: ...

    def update_batch_status(
        self,
        batch_id: BatchId,
        expected_status: BatchStatus,
        target_status: BatchStatus,
        *,
        updated_at: datetime,
        error_summary: str | None = None,
    ) -> ImportBatchRecord: ...

    def publish_batch(
        self,
        batch_id: BatchId,
        *,
        publication_id: str,
        published_at: datetime,
        actor: str,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> PublicationRecord: ...

    def rollback_to(
        self,
        dataset_code: DatasetCode,
        target_batch_id: BatchId,
        *,
        rolled_back_at: datetime,
        actor: str,
        request_id: str | None = None,
        reason: str,
    ) -> PublicationRecord: ...

    def insert_quality_result(self, result: QualityResultRecord) -> QualityResultRecord: ...

    def list_quality_results(self, batch_id: BatchId) -> tuple[QualityResultRecord, ...]: ...

    def has_blocking_quality_failure(self, batch_id: BatchId) -> bool: ...


class ControlRepositoryError(RuntimeError):
    """Raised when a persistence operation cannot be completed safely."""


class DbApiControlRepository:
    """Control-plane repository backed by a DB-API 2.0 connection factory."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get_dataset(self, dataset_code: DatasetCode) -> DatasetRecord | None:
        rows = self._query(
            """
            SELECT dataset_code, display_name, owner, current_schema_version,
                   status, created_at, updated_at
            FROM ctl_dataset
            WHERE dataset_code = ?
            """,
            (str(dataset_code),),
        )
        return _dataset_from_row(rows[0]) if rows else None

    def insert_dataset(self, dataset: DatasetRecord) -> DatasetRecord:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ctl_dataset (
                    dataset_code, display_name, owner, current_schema_version,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(dataset.dataset_code),
                    dataset.display_name,
                    dataset.owner,
                    str(dataset.current_schema_version) if dataset.current_schema_version else None,
                    dataset.status,
                    _datetime_text(dataset.created_at),
                    _datetime_text(dataset.updated_at),
                ),
            )
            connection.commit()
            return dataset
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not insert dataset") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def update_dataset_schema(
        self,
        dataset_code: DatasetCode,
        schema_version: SchemaVersion,
        *,
        updated_at: datetime,
    ) -> DatasetRecord:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE ctl_dataset
                SET current_schema_version = ?, updated_at = ?
                WHERE dataset_code = ?
                """,
                (str(schema_version), _datetime_text(updated_at), str(dataset_code)),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ControlRepositoryError("dataset does not exist")
            connection.commit()
        except ControlRepositoryError:
            raise
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not update dataset schema") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
        dataset = self.get_dataset(dataset_code)
        if dataset is None:
            raise ControlRepositoryError("updated dataset disappeared")
        return dataset

    def get_schema_version(
        self,
        dataset_code: DatasetCode,
        schema_version: SchemaVersion,
    ) -> SchemaVersionRecord | None:
        rows = self._query(
            """
            SELECT dataset_code, schema_version, schema_json, schema_checksum,
                   compatibility, created_at
            FROM ctl_schema_version
            WHERE dataset_code = ? AND schema_version = ?
            """,
            (str(dataset_code), str(schema_version)),
        )
        return _schema_version_from_row(rows[0]) if rows else None

    def insert_schema_version(self, schema: SchemaVersionRecord) -> SchemaVersionRecord:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ctl_schema_version (
                    dataset_code, schema_version, schema_json, schema_checksum,
                    compatibility, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(schema.dataset_code),
                    str(schema.schema_version),
                    schema.schema_json,
                    schema.schema_checksum,
                    schema.compatibility,
                    _datetime_text(schema.created_at),
                ),
            )
            connection.commit()
            return schema
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not insert schema version") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def find_batch_by_source(self, dataset_code: DatasetCode, source_batch_id: str) -> ImportBatchRecord | None:
        rows = self._query(
            """
            SELECT batch_id, dataset_code, schema_version, source_batch_id,
                   source_uri, source_sha256, data_date, row_count, status, error_summary,
                   created_at, updated_at, published_at
            FROM ctl_import_batch
            WHERE dataset_code = ? AND source_batch_id = ?
            """,
            (str(dataset_code), source_batch_id),
        )
        return _batch_from_row(rows[0]) if rows else None

    def get_batch(self, batch_id: BatchId) -> ImportBatchRecord | None:
        rows = self._query(
            """
            SELECT batch_id, dataset_code, schema_version, source_batch_id,
                   source_uri, source_sha256, data_date, row_count, status, error_summary,
                   created_at, updated_at, published_at
            FROM ctl_import_batch
            WHERE batch_id = ?
            """,
            (str(batch_id),),
        )
        return _batch_from_row(rows[0]) if rows else None

    def insert_batch(self, batch: ImportBatchRecord) -> ImportBatchRecord:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ctl_import_batch (
                    batch_id, dataset_code, schema_version, source_batch_id,
                    source_uri, source_sha256, data_date, row_count, status, error_summary,
                    created_at, updated_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(batch.batch_id),
                    str(batch.dataset_code),
                    str(batch.schema_version),
                    batch.source_batch_id,
                    batch.source_uri,
                    batch.source_sha256,
                    batch.data_date.isoformat(),
                    batch.row_count,
                    batch.status.value,
                    batch.error_summary,
                    _datetime_text(batch.created_at),
                    _datetime_text(batch.updated_at),
                    _datetime_text(batch.published_at),
                ),
            )
            connection.commit()
            return batch
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not insert import batch") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def update_batch_status(
        self,
        batch_id: BatchId,
        expected_status: BatchStatus,
        target_status: BatchStatus,
        *,
        updated_at: datetime,
        error_summary: str | None = None,
    ) -> ImportBatchRecord:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE ctl_import_batch
                SET status = ?, error_summary = ?, updated_at = ?
                WHERE batch_id = ? AND status = ?
                """,
                (
                    target_status.value,
                    error_summary,
                    _datetime_text(updated_at),
                    str(batch_id),
                    expected_status.value,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ControlRepositoryError("batch was changed by another operation")
            connection.commit()
        except ControlRepositoryError:
            raise
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not update import batch status") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
        updated = self.get_batch(batch_id)
        if updated is None:
            raise ControlRepositoryError("updated import batch disappeared")
        return updated

    def publish_batch(
        self,
        batch_id: BatchId,
        *,
        publication_id: str,
        published_at: datetime,
        actor: str,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> PublicationRecord:
        """Publish a READY batch and move the previous pointer atomically."""

        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            batch_row = _fetch_one(
                cursor,
                """
                SELECT batch_id, dataset_code, schema_version, source_batch_id,
                       source_uri, source_sha256, data_date, row_count, status, error_summary,
                       created_at, updated_at, published_at
                FROM ctl_import_batch
                WHERE batch_id = ?
                """,
                (str(batch_id),),
            )
            if batch_row is None:
                raise ControlRepositoryError("import batch does not exist")
            if batch_row["status"] == BatchStatus.PUBLISHED.value:
                existing = _fetch_one(
                    cursor,
                    """
                    SELECT publication_id, dataset_code, batch_id, schema_version,
                           status, supersedes_publication_id, published_at, retracted_at
                    FROM ctl_publication
                    WHERE dataset_code = ? AND batch_id = ?
                    """,
                    (batch_row["dataset_code"], batch_row["batch_id"]),
                )
                if existing is None:
                    raise ControlRepositoryError("published batch has no publication record")
                connection.commit()
                return _publication_from_row(existing)
            if batch_row["status"] != BatchStatus.READY.value:
                raise ControlRepositoryError("only READY batches can be published")

            previous = _fetch_one(
                cursor,
                """
                SELECT publication_id, dataset_code, batch_id, schema_version,
                       status, supersedes_publication_id, published_at, retracted_at
                FROM ctl_publication
                WHERE dataset_code = ? AND status = 'PUBLISHED'
                ORDER BY published_at DESC
                LIMIT 1
                """,
                (batch_row["dataset_code"],),
            )
            supersedes_id = previous["publication_id"] if previous else None
            if previous:
                cursor.execute(
                    """
                    UPDATE ctl_publication
                    SET status = 'SUPERSEDED', retracted_at = ?
                    WHERE publication_id = ? AND status = 'PUBLISHED'
                    """,
                    (_datetime_text(published_at), previous["publication_id"]),
                )
            cursor.execute(
                """
                INSERT INTO ctl_publication (
                    publication_id, dataset_code, batch_id, schema_version,
                    status, supersedes_publication_id, published_at, retracted_at
                ) VALUES (?, ?, ?, ?, 'PUBLISHED', ?, ?, NULL)
                """,
                (
                    publication_id,
                    batch_row["dataset_code"],
                    batch_row["batch_id"],
                    batch_row["schema_version"],
                    supersedes_id,
                    _datetime_text(published_at),
                ),
            )
            cursor.execute(
                """
                UPDATE ctl_import_batch
                SET status = 'PUBLISHED', published_at = ?, updated_at = ?
                WHERE batch_id = ? AND status = 'READY'
                """,
                (_datetime_text(published_at), _datetime_text(published_at), str(batch_id)),
            )
            if cursor.rowcount != 1:
                raise ControlRepositoryError("batch was changed before publication")
            cursor.execute(
                """
                INSERT INTO ctl_audit_log (
                    audit_id, action, actor, resource_type, resource_id,
                    request_id, details_json, created_at
                ) VALUES (?, 'PUBLISH_BATCH', ?, 'IMPORT_BATCH', ?, ?, ?, ?)
                """,
                (
                    _new_id("audit"),
                    actor,
                    str(batch_id),
                    request_id,
                    _audit_details(reason),
                    _datetime_text(published_at),
                ),
            )
            connection.commit()
            publication_row = _fetch_one(
                cursor,
                """
                SELECT publication_id, dataset_code, batch_id, schema_version,
                       status, supersedes_publication_id, published_at, retracted_at
                FROM ctl_publication
                WHERE publication_id = ?
                """,
                (publication_id,),
            )
            if publication_row is None:
                raise ControlRepositoryError("publication record was not written")
            return _publication_from_row(publication_row)
        except ControlRepositoryError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not publish import batch") from exc
        finally:
            cursor.close()
            connection.close()

    def rollback_to(
        self,
        dataset_code: DatasetCode,
        target_batch_id: BatchId,
        *,
        rolled_back_at: datetime,
        actor: str,
        request_id: str | None = None,
        reason: str,
    ) -> PublicationRecord:
        """Move the dataset pointer to an existing historical publication."""

        connection = self._connection_factory()
        cursor = connection.cursor()
        try:
            current = _fetch_one(
                cursor,
                """
                SELECT publication_id, dataset_code, batch_id, schema_version,
                       status, supersedes_publication_id, published_at, retracted_at
                FROM ctl_publication
                WHERE dataset_code = ? AND status = 'PUBLISHED'
                ORDER BY published_at DESC
                LIMIT 1
                """,
                (str(dataset_code),),
            )
            target = _fetch_one(
                cursor,
                """
                SELECT publication_id, dataset_code, batch_id, schema_version,
                       status, supersedes_publication_id, published_at, retracted_at
                FROM ctl_publication
                WHERE dataset_code = ? AND batch_id = ?
                """,
                (str(dataset_code), str(target_batch_id)),
            )
            if target is None:
                raise ControlRepositoryError("target batch has no publication record")
            if target["status"] == "PUBLISHED":
                connection.commit()
                return _publication_from_row(target)
            if target["status"] != "SUPERSEDED":
                raise ControlRepositoryError("target publication is not available for rollback")
            if current is None:
                raise ControlRepositoryError("dataset has no active publication")

            now = _datetime_text(rolled_back_at)
            cursor.execute(
                """
                UPDATE ctl_publication
                SET status = 'ROLLED_BACK', retracted_at = ?
                WHERE publication_id = ? AND status = 'PUBLISHED'
                """,
                (now, current["publication_id"]),
            )
            if cursor.rowcount != 1:
                raise ControlRepositoryError("active publication changed before rollback")
            cursor.execute(
                """
                UPDATE ctl_publication
                SET status = 'PUBLISHED', retracted_at = NULL
                WHERE publication_id = ? AND status = 'SUPERSEDED'
                """,
                (target["publication_id"],),
            )
            if cursor.rowcount != 1:
                raise ControlRepositoryError("target publication changed before rollback")
            cursor.execute(
                """
                INSERT INTO ctl_audit_log (
                    audit_id, action, actor, resource_type, resource_id,
                    request_id, details_json, created_at
                ) VALUES (?, 'ROLLBACK_PUBLICATION', ?, 'DATASET', ?, ?, ?, ?)
                """,
                (
                    _new_id("audit"),
                    actor,
                    str(dataset_code),
                    request_id,
                    _audit_details(reason),
                    now,
                ),
            )
            connection.commit()
            target_row = _fetch_one(
                cursor,
                """
                SELECT publication_id, dataset_code, batch_id, schema_version,
                       status, supersedes_publication_id, published_at, retracted_at
                FROM ctl_publication
                WHERE publication_id = ?
                """,
                (target["publication_id"],),
            )
            if target_row is None:
                raise ControlRepositoryError("rollback target disappeared")
            return _publication_from_row(target_row)
        except ControlRepositoryError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not rollback publication") from exc
        finally:
            cursor.close()
            connection.close()

    def insert_quality_result(self, result: QualityResultRecord) -> QualityResultRecord:
        existing = self._query(
            """
            SELECT result_id, batch_id, rule_code, severity, passed,
                   checked_row_count, failure_count, details_json, created_at
            FROM ctl_quality_result
            WHERE batch_id = ? AND rule_code = ?
            """,
            (str(result.batch_id), result.rule_code),
        )
        if existing:
            current = _quality_result_from_row(existing[0])
            if _same_quality_content(current, result):
                return current
            raise ControlRepositoryError("quality result already exists with different content")

        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ctl_quality_result (
                    result_id, batch_id, rule_code, severity, passed,
                    checked_row_count, failure_count, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    str(result.batch_id),
                    result.rule_code,
                    result.severity,
                    int(result.passed),
                    result.checked_row_count,
                    result.failure_count,
                    result.details_json,
                    _datetime_text(result.created_at),
                ),
            )
            connection.commit()
            return result
        except Exception as exc:
            connection.rollback()
            raise ControlRepositoryError("could not insert quality result") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def list_quality_results(self, batch_id: BatchId) -> tuple[QualityResultRecord, ...]:
        rows = self._query(
            """
            SELECT result_id, batch_id, rule_code, severity, passed,
                   checked_row_count, failure_count, details_json, created_at
            FROM ctl_quality_result
            WHERE batch_id = ?
            ORDER BY rule_code
            """,
            (str(batch_id),),
        )
        return tuple(_quality_result_from_row(row) for row in rows)

    def has_blocking_quality_failure(self, batch_id: BatchId) -> bool:
        rows = self._query(
            """
            SELECT 1 AS blocked
            FROM ctl_quality_result
            WHERE batch_id = ?
              AND severity IN ('BLOCKER', 'ERROR')
              AND passed = 0
            LIMIT 1
            """,
            (str(batch_id),),
        )
        return bool(rows)

    def _query(self, sql: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, parameters)
            columns = [column[0] for column in cursor.description or ()]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()
            connection.close()


def _fetch_one(cursor: Any, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
    cursor.execute(sql, parameters)
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description or ()]
    return dict(zip(columns, row))


def _batch_from_row(row: dict[str, Any]) -> ImportBatchRecord:
    return ImportBatchRecord(
        batch_id=BatchId(str(row["batch_id"])),
        dataset_code=DatasetCode(str(row["dataset_code"])),
        schema_version=SchemaVersion(str(row["schema_version"])),
        source_batch_id=str(row["source_batch_id"]),
        source_uri=str(row["source_uri"]),
        source_sha256=str(row["source_sha256"]),
        data_date=_date_value(row["data_date"]),
        row_count=int(row["row_count"]),
        status=BatchStatus(str(row["status"])),
        error_summary=row.get("error_summary"),
        created_at=_datetime_value(row["created_at"]),
        updated_at=_datetime_value(row["updated_at"]),
        published_at=_datetime_value(row.get("published_at")),
    )


def _dataset_from_row(row: dict[str, Any]) -> DatasetRecord:
    return DatasetRecord(
        dataset_code=DatasetCode(str(row["dataset_code"])),
        display_name=str(row["display_name"]),
        owner=str(row["owner"]),
        current_schema_version=SchemaVersion(str(row["current_schema_version"]))
        if row.get("current_schema_version")
        else None,
        status=str(row["status"]),
        created_at=_datetime_value(row["created_at"]),
        updated_at=_datetime_value(row["updated_at"]),
    )


def _schema_version_from_row(row: dict[str, Any]) -> SchemaVersionRecord:
    return SchemaVersionRecord(
        dataset_code=DatasetCode(str(row["dataset_code"])),
        schema_version=SchemaVersion(str(row["schema_version"])),
        schema_json=str(row["schema_json"]),
        schema_checksum=str(row["schema_checksum"]),
        compatibility=str(row["compatibility"]),
        created_at=_datetime_value(row["created_at"]),
    )


def _publication_from_row(row: dict[str, Any]) -> PublicationRecord:
    return PublicationRecord(
        publication_id=str(row["publication_id"]),
        dataset_code=DatasetCode(str(row["dataset_code"])),
        batch_id=BatchId(str(row["batch_id"])),
        schema_version=SchemaVersion(str(row["schema_version"])),
        status=str(row["status"]),
        supersedes_publication_id=row.get("supersedes_publication_id"),
        published_at=_datetime_value(row["published_at"]),
        retracted_at=_datetime_value(row.get("retracted_at")),
    )


def _quality_result_from_row(row: dict[str, Any]) -> QualityResultRecord:
    return QualityResultRecord(
        result_id=str(row["result_id"]),
        batch_id=BatchId(str(row["batch_id"])),
        rule_code=str(row["rule_code"]),
        severity=str(row["severity"]),
        passed=bool(row["passed"]),
        checked_row_count=int(row["checked_row_count"]),
        failure_count=int(row["failure_count"]),
        details_json=row.get("details_json"),
        created_at=_datetime_value(row["created_at"]),
    )


def _same_quality_content(left: QualityResultRecord, right: QualityResultRecord) -> bool:
    return (
        left.batch_id == right.batch_id
        and left.rule_code == right.rule_code
        and left.severity == right.severity
        and left.passed == right.passed
        and left.checked_row_count == right.checked_row_count
        and left.failure_count == right.failure_count
        and left.details_json == right.details_json
    )


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _audit_details(reason: str | None) -> str | None:
    return json.dumps({"reason": reason}, ensure_ascii=False) if reason else None
