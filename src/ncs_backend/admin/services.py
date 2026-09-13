"""Application services for import-batch lifecycle and publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from ncs_backend.admin.repositories import ControlRepository, ImportBatchRecord, PublicationRecord
from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId
from ncs_backend.shared.domain.state_machine import batch_state_machine
from ncs_backend.shared.errors import AppError

Clock = Callable[[], datetime]


class BatchNotFoundError(AppError):
    def __init__(self, batch_id: BatchId) -> None:
        super().__init__("BATCH_NOT_FOUND", f"import batch {batch_id} does not exist", 404)


class BatchConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("BATCH_CONFLICT", message, 409)


class BatchPublicationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("PUBLICATION_NOT_ALLOWED", message, 409)


class BatchService:
    """Create batches idempotently and enforce the shared state machine."""

    def __init__(self, repository: ControlRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create_batch(
        self,
        manifest: DatasetManifest,
        *,
        source_batch_id: str,
        batch_id: BatchId | None = None,
    ) -> ImportBatchRecord:
        if not source_batch_id.strip():
            raise ValueError("source_batch_id must not be empty")
        existing = self._repository.find_batch_by_source(manifest.dataset_code, source_batch_id)
        if existing is not None:
            if _same_batch_input(existing, manifest, source_batch_id):
                return existing
            raise BatchConflictError("source batch already exists with different immutable metadata")

        now = self._clock()
        record = ImportBatchRecord(
            batch_id=batch_id or BatchId(f"batch-{uuid4().hex}"),
            dataset_code=manifest.dataset_code,
            schema_version=manifest.schema_version,
            source_batch_id=source_batch_id,
            source_uri=manifest.source_uri,
            data_date=manifest.data_date,
            row_count=manifest.row_count,
            status=BatchStatus.CREATED,
            error_summary=None,
            created_at=now,
            updated_at=now,
        )
        return self._repository.insert_batch(record)

    def transition(
        self,
        batch_id: BatchId,
        target_status: BatchStatus,
        *,
        error_summary: str | None = None,
    ) -> ImportBatchRecord:
        current = self._repository.get_batch(batch_id)
        if current is None:
            raise BatchNotFoundError(batch_id)
        batch_state_machine(current.status).transition_to(target_status)
        return self._repository.update_batch_status(
            batch_id,
            current.status,
            target_status,
            updated_at=self._clock(),
            error_summary=error_summary,
        )


class PublicationService:
    """Publish only quality-ready batches through an atomic repository port."""

    def __init__(self, repository: ControlRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def publish(
        self,
        batch_id: BatchId,
        *,
        actor: str,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> PublicationRecord:
        batch = self._repository.get_batch(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        if batch.status not in {BatchStatus.READY, BatchStatus.PUBLISHED}:
            raise BatchPublicationError("only READY batches can be published")
        if not actor.strip():
            raise ValueError("actor must not be empty")
        return self._repository.publish_batch(
            batch_id,
            publication_id=f"publication-{uuid4().hex}",
            published_at=self._clock(),
            actor=actor,
            request_id=request_id,
            reason=reason,
        )


def _same_batch_input(existing: ImportBatchRecord, manifest: DatasetManifest, source_batch_id: str) -> bool:
    return (
        existing.source_batch_id == source_batch_id
        and existing.schema_version == manifest.schema_version
        and existing.source_uri == manifest.source_uri
        and existing.data_date == manifest.data_date
        and existing.row_count == manifest.row_count
    )
