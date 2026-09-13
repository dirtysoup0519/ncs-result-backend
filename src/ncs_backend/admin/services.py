"""Application services for import-batch lifecycle and publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ncs_backend.admin.importers import DeliveryValidation, DeliveryValidator
from ncs_backend.admin.repositories import (
    ControlRepository,
    ControlRepositoryError,
    DatasetRecord,
    ImportBatchRecord,
    PublicationRecord,
    QualityResultRecord,
    SchemaVersionRecord,
)
from ncs_backend.admin.staging import StagingWriter
from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.schema import DatasetSchema
from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId, DatasetCode
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


class QualityValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("QUALITY_VALIDATION_FAILED", message, 409)


class ImportPreparationError(AppError):
    def __init__(self, validation: DeliveryValidation) -> None:
        super().__init__(
            "IMPORT_DELIVERY_INVALID",
            "delivery did not pass manifest or schema validation",
            422,
            details={"issues": list(validation.issues)},
        )


class ImportLoadingError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("IMPORT_LOAD_FAILED", message, 422)


class DatasetRegistryConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("DATASET_REGISTRY_CONFLICT", message, 409)


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
        normalized_source_batch_id = source_batch_id.strip()
        if not normalized_source_batch_id:
            raise ValueError("source_batch_id must not be empty")
        existing = self._repository.find_batch_by_source(manifest.dataset_code, normalized_source_batch_id)
        if existing is not None:
            if _same_batch_input(existing, manifest, normalized_source_batch_id):
                return existing
            raise BatchConflictError("source batch already exists with different immutable metadata")

        now = self._clock()
        record = ImportBatchRecord(
            batch_id=batch_id or BatchId(f"batch-{uuid4().hex}"),
            dataset_code=manifest.dataset_code,
            schema_version=manifest.schema_version,
            source_batch_id=normalized_source_batch_id,
            source_uri=manifest.source_uri,
            source_sha256=manifest.sha256,
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

    def get(self, batch_id: BatchId) -> ImportBatchRecord:
        batch = self._repository.get_batch(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        return batch


class DatasetRegistryService:
    """Register stable dataset metadata and immutable schema versions."""

    _COMPATIBILITIES = frozenset({"BACKWARD", "FORWARD", "FULL", "NONE"})

    def __init__(self, repository: ControlRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def get(self, dataset_code: DatasetCode) -> DatasetRecord:
        dataset = self._repository.get_dataset(dataset_code)
        if dataset is None:
            raise AppError("DATASET_NOT_FOUND", f"dataset {dataset_code} does not exist", 404)
        return dataset

    def register_schema(
        self,
        schema: DatasetSchema,
        *,
        display_name: str,
        owner: str,
        compatibility: str = "BACKWARD",
    ) -> tuple[DatasetRecord, SchemaVersionRecord]:
        if not display_name.strip() or not owner.strip():
            raise ValueError("display_name and owner must not be empty")
        normalized_compatibility = compatibility.upper()
        if normalized_compatibility not in self._COMPATIBILITIES:
            raise ValueError(f"unsupported schema compatibility: {compatibility}")

        schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        schema_checksum = sha256(schema_json.encode("utf-8")).hexdigest()
        existing_schema = self._repository.get_schema_version(schema.dataset_code, schema.version)
        if existing_schema is not None:
            if existing_schema.schema_checksum != schema_checksum:
                raise DatasetRegistryConflictError("schema version already exists with different content")
            if existing_schema.compatibility != normalized_compatibility:
                raise DatasetRegistryConflictError("schema version already exists with different compatibility")
            schema_record = existing_schema
        else:
            schema_record = self._repository.insert_schema_version(
                SchemaVersionRecord(
                    dataset_code=schema.dataset_code,
                    schema_version=schema.version,
                    schema_json=schema_json,
                    schema_checksum=schema_checksum,
                    compatibility=normalized_compatibility,
                    created_at=self._clock(),
                )
            )

        dataset = self._repository.get_dataset(schema.dataset_code)
        if dataset is None:
            now = self._clock()
            dataset = self._repository.insert_dataset(
                DatasetRecord(
                    dataset_code=schema.dataset_code,
                    display_name=display_name.strip(),
                    owner=owner.strip(),
                    current_schema_version=schema.version,
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            if dataset.display_name != display_name.strip() or dataset.owner != owner.strip():
                raise DatasetRegistryConflictError("dataset metadata differs from the registered owner or name")
            if dataset.current_schema_version != schema.version:
                dataset = self._repository.update_dataset_schema(
                    schema.dataset_code,
                    schema.version,
                    updated_at=self._clock(),
                )
        return dataset, schema_record


class ImportPreparationService:
    """Validate a file delivery before creating its import batch."""

    def __init__(self, batch_service: BatchService, validator: DeliveryValidator | None = None) -> None:
        self._batch_service = batch_service
        self._validator = validator or DeliveryValidator()

    def prepare(
        self,
        schema_path: Path,
        manifest_path: Path,
        data_path: Path,
        *,
        source_batch_id: str,
        batch_id: BatchId | None = None,
    ) -> tuple[ImportBatchRecord, DeliveryValidation]:
        validation = self._validator.validate_files(schema_path, manifest_path, data_path)
        if not validation.passed:
            raise ImportPreparationError(validation)
        manifest = _manifest_from_path(manifest_path)
        batch = self._batch_service.create_batch(
            manifest,
            source_batch_id=source_batch_id,
            batch_id=batch_id,
        )
        return batch, validation


class ImportLoadingService:
    """Write a validated delivery to staging and advance its batch state."""

    def __init__(self, batch_service: BatchService, staging_writer: StagingWriter) -> None:
        self._batch_service = batch_service
        self._staging_writer = staging_writer

    def load(self, batch_id: BatchId, validation: DeliveryValidation) -> ImportBatchRecord:
        if not validation.passed:
            raise ImportLoadingError("only a delivery that passed validation can be loaded")
        batch = self._batch_service.get(batch_id)
        if batch.status is not BatchStatus.CREATED:
            raise ImportLoadingError("only CREATED batches can be loaded")
        try:
            self._batch_service.transition(batch_id, BatchStatus.LOADING)
            loaded_count = self._staging_writer.write(batch_id, validation.delivery.rows)
            if loaded_count != validation.row_count:
                raise ImportLoadingError("staging row count differs from validated delivery")
            return self._batch_service.transition(batch_id, BatchStatus.VALIDATING)
        except ImportLoadingError:
            self._mark_failed(batch_id, "staging row count differs from validated delivery")
            raise
        except Exception as exc:
            self._mark_failed(batch_id, str(exc))
            raise ImportLoadingError("could not load delivery into staging") from exc

    def _mark_failed(self, batch_id: BatchId, message: str) -> None:
        current = self._batch_service.get(batch_id)
        if current.status is BatchStatus.LOADING:
            self._batch_service.transition(batch_id, BatchStatus.FAILED, error_summary=message)


class QualityService:
    """Persist rule outcomes and close a batch validation transaction."""

    _SEVERITIES = frozenset({"BLOCKER", "ERROR", "WARN", "INFO"})

    def __init__(self, repository: ControlRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def list_results(self, batch_id: BatchId) -> tuple[QualityResultRecord, ...]:
        return self._repository.list_quality_results(batch_id)

    def record(
        self,
        batch_id: BatchId,
        *,
        rule_code: str,
        severity: str,
        passed: bool,
        checked_row_count: int,
        failure_count: int,
        details: Mapping[str, object] | None = None,
    ) -> QualityResultRecord:
        batch = self._repository.get_batch(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        if batch.status is not BatchStatus.VALIDATING:
            raise QualityValidationError("quality results can only be recorded while batch is VALIDATING")
        normalized_severity = str(severity).upper()
        if normalized_severity == "WARNING":
            normalized_severity = "WARN"
        if normalized_severity not in self._SEVERITIES:
            raise ValueError(f"unsupported quality severity: {severity}")
        if not rule_code.strip():
            raise ValueError("rule_code must not be empty")
        if checked_row_count < 0 or failure_count < 0 or failure_count > checked_row_count:
            raise ValueError("quality row counts are invalid")
        if passed and failure_count:
            raise ValueError("a passed quality result cannot contain failures")
        result = QualityResultRecord(
            result_id=f"quality-{uuid4().hex}",
            batch_id=batch_id,
            rule_code=rule_code.strip(),
            severity=normalized_severity,
            passed=passed,
            checked_row_count=checked_row_count,
            failure_count=failure_count,
            details_json=json.dumps(details, ensure_ascii=False, sort_keys=True) if details is not None else None,
            created_at=self._clock(),
        )
        try:
            return self._repository.insert_quality_result(result)
        except ControlRepositoryError as exc:
            raise QualityValidationError(str(exc)) from exc

    def complete_validation(self, batch_id: BatchId) -> ImportBatchRecord:
        batch = self._repository.get_batch(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        if batch.status is not BatchStatus.VALIDATING:
            raise QualityValidationError("validation can only be completed while batch is VALIDATING")
        results = self._repository.list_quality_results(batch_id)
        if not results:
            return BatchService(self._repository, self._clock).transition(
                batch_id,
                BatchStatus.REJECTED,
                error_summary="no quality result was recorded",
            )
        target = BatchStatus.REJECTED if self._repository.has_blocking_quality_failure(batch_id) else BatchStatus.READY
        summary = "blocking quality check failed" if target is BatchStatus.REJECTED else None
        return BatchService(self._repository, self._clock).transition(batch_id, target, error_summary=summary)


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

    def rollback(
        self,
        dataset_code: DatasetCode,
        target_batch_id: BatchId,
        *,
        actor: str,
        reason: str,
        request_id: str | None = None,
    ) -> PublicationRecord:
        if not actor.strip():
            raise ValueError("actor must not be empty")
        if not reason.strip():
            raise ValueError("reason must not be empty")
        target = self._repository.get_batch(target_batch_id)
        if target is None or target.dataset_code != dataset_code:
            raise BatchNotFoundError(target_batch_id)
        try:
            return self._repository.rollback_to(
                dataset_code,
                target_batch_id,
                rolled_back_at=self._clock(),
                actor=actor,
                request_id=request_id,
                reason=reason,
            )
        except ControlRepositoryError as exc:
            raise BatchPublicationError(str(exc)) from exc


def _same_batch_input(existing: ImportBatchRecord, manifest: DatasetManifest, source_batch_id: str) -> bool:
    return (
        existing.source_batch_id == source_batch_id
        and existing.schema_version == manifest.schema_version
        and existing.source_uri == manifest.source_uri
        and existing.source_sha256 == manifest.sha256
        and existing.data_date == manifest.data_date
        and existing.row_count == manifest.row_count
    )


def _manifest_from_path(path: Path) -> DatasetManifest:
    return DatasetManifest.from_dict(json.loads(Path(path).read_text("utf-8")))
