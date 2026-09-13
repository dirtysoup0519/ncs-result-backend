"""Generic staging writer for validated delivery rows."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from ncs_backend.shared.domain.identifiers import BatchId

ConnectionFactory = Callable[[], Any]


class StagingConflictError(RuntimeError):
    """Raised when the same batch is loaded with different row content."""


class StagingWriter(Protocol):
    def write(self, batch_id: BatchId, rows: Iterable[Mapping[str, Any]]) -> int: ...

    def read(self, batch_id: BatchId) -> tuple[dict[str, Any], ...]: ...


class DbApiStagingWriter:
    """Idempotent DB-API writer for the schema-neutral ``stg_import_row`` table."""

    def __init__(self, connection_factory: ConnectionFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._connection_factory = connection_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def write(self, batch_id: BatchId, rows: Iterable[Mapping[str, Any]]) -> int:
        materialized = tuple(dict(row) for row in rows)
        encoded = tuple(_encode_row(row) for row in materialized)
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT row_number, payload_json, row_sha256
                FROM stg_import_row
                WHERE batch_id = ?
                ORDER BY row_number
                """,
                (str(batch_id),),
            )
            existing = cursor.fetchall()
            if existing:
                if len(existing) != len(encoded) or any(
                    (int(row[0]), row[1], row[2]) != (index, payload, digest)
                    for index, (payload, digest) in enumerate(encoded, start=1)
                    for row in existing[index - 1 : index]
                ):
                    raise StagingConflictError("staging batch already exists with different row content")
                connection.commit()
                return len(existing)

            loaded_at = self._clock().isoformat()
            cursor.executemany(
                """
                INSERT INTO stg_import_row (
                    batch_id, row_number, payload_json, row_sha256, loaded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [(str(batch_id), index, payload, digest, loaded_at) for index, (payload, digest) in enumerate(encoded, start=1)],
            )
            connection.commit()
            return len(encoded)
        except StagingConflictError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise RuntimeError("could not write staging rows") from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def read(self, batch_id: BatchId) -> tuple[dict[str, Any], ...]:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT payload_json
                FROM stg_import_row
                WHERE batch_id = ?
                ORDER BY row_number
                """,
                (str(batch_id),),
            )
            return tuple(json.loads(row[0]) for row in cursor.fetchall())
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()


def _encode_row(row: Mapping[str, Any]) -> tuple[str, str]:
    try:
        payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("staging rows must be JSON-serializable") from exc
    return payload, sha256(payload.encode("utf-8")).hexdigest()
