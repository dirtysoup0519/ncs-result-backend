import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ncs_backend.admin.migrations import initialize_control_schema
from ncs_backend.admin.repositories import DbApiControlRepository
from ncs_backend.admin.services import BatchConflictError, BatchPublicationError, BatchService, PublicationService
from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def _manifest() -> DatasetManifest:
    import json

    return DatasetManifest.from_dict(json.loads((EXAMPLES / "station-hourly.manifest.v1.json").read_text("utf-8")))


def _services(tmp_path):
    database = tmp_path / "control.sqlite"
    connection = sqlite3.connect(database)
    initialize_control_schema(connection)
    connection.close()
    repository = DbApiControlRepository(lambda: sqlite3.connect(database))
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    clock = lambda: now
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
