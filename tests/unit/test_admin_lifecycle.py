import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema
from ncs_backend.admin.staging import DbApiStagingWriter
from ncs_backend.admin.repositories import DbApiControlRepository
from ncs_backend.admin.services import (
    BatchConflictError,
    BatchPublicationError,
    BatchService,
    DatasetRegistryConflictError,
    DatasetRegistryService,
    ImportPreparationError,
    ImportPreparationService,
    ImportLoadingService,
    PublicationService,
    QualityService,
)
from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.schema import DatasetSchema
from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def _manifest() -> DatasetManifest:
    import json

    return DatasetManifest.from_dict(json.loads((EXAMPLES / "station-hourly.manifest.v1.json").read_text("utf-8")))


def _schema() -> DatasetSchema:
    import json

    return DatasetSchema.from_dict(json.loads((EXAMPLES / "station-hourly.schema.v1.json").read_text("utf-8")))


def _services(tmp_path):
    database = tmp_path / "control.sqlite"
    connection = sqlite3.connect(database)
    initialize_control_schema(connection)
    initialize_staging_schema(connection)
    connection.close()
    repository = DbApiControlRepository(lambda: sqlite3.connect(database))
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    calls = 0

    def clock():
        nonlocal calls
        value = now + timedelta(seconds=calls)
        calls += 1
        return value

    return repository, BatchService(repository, clock), PublicationService(repository, clock)


def _ready_batch(service: BatchService):
    batch = service.create_batch(_manifest(), source_batch_id="ods-20260913", batch_id=BatchId("batch-test-1"))
    service.transition(batch.batch_id, BatchStatus.LOADING)
    service.transition(batch.batch_id, BatchStatus.VALIDATING)
    return service.transition(batch.batch_id, BatchStatus.READY)


def test_batch_creation_is_idempotent_and_conflicts_on_changed_manifest(tmp_path):
    repository, service, _ = _services(tmp_path)
    first = service.create_batch(_manifest(), source_batch_id="ods-20260913", batch_id=BatchId("batch-test-1"))
    second = service.create_batch(_manifest(), source_batch_id="ods-20260913", batch_id=BatchId("batch-other"))
    assert second.batch_id == first.batch_id
    assert second.status is BatchStatus.CREATED

    manifest = _manifest()
    changed = DatasetManifest(
        dataset_code=manifest.dataset_code,
        schema_version=manifest.schema_version,
        data_date=manifest.data_date,
        grain=manifest.grain,
        row_count=manifest.row_count + 1,
        sha256=manifest.sha256,
        source_uri=manifest.source_uri,
        generated_at=manifest.generated_at,
    )
    with pytest.raises(BatchConflictError):
        service.create_batch(changed, source_batch_id="ods-20260913")
    assert repository.get_batch(first.batch_id).status is BatchStatus.CREATED


def test_publication_switches_active_pointer_and_is_idempotent(tmp_path):
    repository, service, publication_service = _services(tmp_path)
    first = _ready_batch(service)
    publication = publication_service.publish(first.batch_id, actor="tester", request_id="req-1")
    assert publication.status == "PUBLISHED"
    assert repository.get_batch(first.batch_id).status is BatchStatus.PUBLISHED

    repeated = publication_service.publish(first.batch_id, actor="tester", request_id="req-2")
    assert repeated.publication_id == publication.publication_id

    second = service.create_batch(_manifest(), source_batch_id="ods-20260914", batch_id=BatchId("batch-test-2"))
    service.transition(second.batch_id, BatchStatus.LOADING)
    service.transition(second.batch_id, BatchStatus.VALIDATING)
    service.transition(second.batch_id, BatchStatus.READY)
    newer = publication_service.publish(second.batch_id, actor="tester")
    assert newer.supersedes_publication_id == publication.publication_id
    assert repository.get_batch(second.batch_id).status is BatchStatus.PUBLISHED

    connection = sqlite3.connect(tmp_path / "control.sqlite")
    statuses = dict(connection.execute("SELECT publication_id, status FROM ctl_publication"))
    audit_count = connection.execute("SELECT COUNT(*) FROM ctl_audit_log").fetchone()[0]
    connection.close()
    assert statuses[publication.publication_id] == "SUPERSEDED"
    assert statuses[newer.publication_id] == "PUBLISHED"
    assert audit_count == 2


def test_unready_batch_cannot_publish(tmp_path):
    _, service, publication_service = _services(tmp_path)
    batch = service.create_batch(_manifest(), source_batch_id="ods-20260913", batch_id=BatchId("batch-test-1"))
    with pytest.raises(BatchPublicationError) as error:
        publication_service.publish(batch.batch_id, actor="tester")
    assert "only READY" in str(error.value)


def test_rollback_moves_active_pointer_to_explicit_historical_batch(tmp_path):
    repository, service, publication_service = _services(tmp_path)
    first = _ready_batch(service)
    first_publication = publication_service.publish(first.batch_id, actor="tester")

    second = service.create_batch(_manifest(), source_batch_id="ods-20260914", batch_id=BatchId("batch-test-2"))
    service.transition(second.batch_id, BatchStatus.LOADING)
    service.transition(second.batch_id, BatchStatus.VALIDATING)
    service.transition(second.batch_id, BatchStatus.READY)
    second_publication = publication_service.publish(second.batch_id, actor="tester")

    restored = publication_service.rollback(
        _manifest().dataset_code,
        first.batch_id,
        actor="operator",
        reason="restore previous validated batch",
        request_id="rollback-1",
    )
    assert restored.publication_id == first_publication.publication_id
    assert restored.status == "PUBLISHED"

    connection = sqlite3.connect(tmp_path / "control.sqlite")
    statuses = dict(connection.execute("SELECT publication_id, status FROM ctl_publication"))
    audit = connection.execute(
        "SELECT action, actor, resource_id, details_json FROM ctl_audit_log ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    connection.close()
    assert statuses[first_publication.publication_id] == "PUBLISHED"
    assert statuses[second_publication.publication_id] == "ROLLED_BACK"
    assert audit[:3] == ("ROLLBACK_PUBLICATION", "operator", str(_manifest().dataset_code))
    assert json.loads(audit[3]) == {"reason": "restore previous validated batch"}

    repeated = publication_service.rollback(
        _manifest().dataset_code,
        first.batch_id,
        actor="operator",
        reason="already restored",
    )
    assert repeated.publication_id == first_publication.publication_id


def test_quality_results_control_validation_outcome(tmp_path):
    repository, service, _ = _services(tmp_path)
    quality = QualityService(repository)
    batch = service.create_batch(_manifest(), source_batch_id="ods-20260913", batch_id=BatchId("batch-quality-1"))
    service.transition(batch.batch_id, BatchStatus.LOADING)
    service.transition(batch.batch_id, BatchStatus.VALIDATING)

    result = quality.record(
        batch.batch_id,
        rule_code="schema",
        severity="BLOCKER",
        passed=False,
        checked_row_count=10,
        failure_count=1,
        details={"field": "station_id"},
    )
    assert result.failure_count == 1
    repeated = quality.record(
        batch.batch_id,
        rule_code="schema",
        severity="BLOCKER",
        passed=False,
        checked_row_count=10,
        failure_count=1,
        details={"field": "station_id"},
    )
    assert repeated.result_id == result.result_id
    rejected = quality.complete_validation(batch.batch_id)
    assert rejected.status is BatchStatus.REJECTED
    assert "blocking" in rejected.error_summary
    assert len(repository.list_quality_results(batch.batch_id)) == 1

    batch2 = service.create_batch(_manifest(), source_batch_id="ods-20260914", batch_id=BatchId("batch-quality-2"))
    service.transition(batch2.batch_id, BatchStatus.LOADING)
    service.transition(batch2.batch_id, BatchStatus.VALIDATING)
    quality.record(
        batch2.batch_id,
        rule_code="schema",
        severity="BLOCKER",
        passed=True,
        checked_row_count=10,
        failure_count=0,
    )
    ready = quality.complete_validation(batch2.batch_id)
    assert ready.status is BatchStatus.READY


def test_import_preparation_validates_delivery_before_creating_batch(tmp_path):
    repository, service, _ = _services(tmp_path)
    preparation = ImportPreparationService(service)
    batch, validation = preparation.prepare(
        EXAMPLES / "station-hourly.schema.v1.json",
        EXAMPLES / "station-hourly.manifest.v1.json",
        EXAMPLES / "station-hourly.rows.v1.json",
        source_batch_id="ods-20260913",
        batch_id=BatchId("batch-prepared-1"),
    )
    assert batch.status is BatchStatus.CREATED
    assert validation.passed is True
    assert repository.get_batch(batch.batch_id).row_count == 2

    bad_data = tmp_path / "bad.json"
    bad_data.write_text("[]", encoding="utf-8")
    with pytest.raises(ImportPreparationError) as error:
        preparation.prepare(
            EXAMPLES / "station-hourly.schema.v1.json",
            EXAMPLES / "station-hourly.manifest.v1.json",
            bad_data,
            source_batch_id="ods-bad",
        )
    assert error.value.code == "IMPORT_DELIVERY_INVALID"
    assert repository.find_batch_by_source(_manifest().dataset_code, "ods-bad") is None


def test_import_loading_writes_schema_neutral_staging_and_advances_batch(tmp_path):
    repository, service, _ = _services(tmp_path)
    preparation = ImportPreparationService(service)
    batch, validation = preparation.prepare(
        EXAMPLES / "station-hourly.schema.v1.json",
        EXAMPLES / "station-hourly.manifest.v1.json",
        EXAMPLES / "station-hourly.rows.v1.json",
        source_batch_id="ods-staging-1",
        batch_id=BatchId("batch-staging-1"),
    )
    writer = DbApiStagingWriter(lambda: sqlite3.connect(tmp_path / "control.sqlite"))
    loading = ImportLoadingService(service, writer)

    loaded = loading.load(batch.batch_id, validation)
    assert loaded.status is BatchStatus.VALIDATING
    assert writer.read(batch.batch_id) == validation.delivery.rows
    assert writer.write(batch.batch_id, validation.delivery.rows) == 2


def test_dataset_registry_keeps_schema_versions_immutable(tmp_path):
    repository, _, _ = _services(tmp_path)
    registry = DatasetRegistryService(repository)
    dataset, schema_record = registry.register_schema(
        _schema(),
        display_name="Hourly order statistics",
        owner="warehouse",
    )
    repeated_dataset, repeated_schema = registry.register_schema(
        _schema(),
        display_name="Hourly order statistics",
        owner="warehouse",
    )
    assert repeated_dataset == dataset
    assert repeated_schema == schema_record
    assert dataset.current_schema_version == _schema().version

    changed = DatasetSchema(
        dataset_code=_schema().dataset_code,
        version=_schema().version,
        grain=("data_date",),
        fields=_schema().fields,
        unique_key=_schema().unique_key,
    )
    with pytest.raises(DatasetRegistryConflictError):
        registry.register_schema(changed, display_name="Hourly order statistics", owner="warehouse")

    with pytest.raises(DatasetRegistryConflictError):
        registry.register_schema(_schema(), display_name="Other name", owner="warehouse")
