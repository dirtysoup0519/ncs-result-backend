import sqlite3

import pytest

from ncs_backend.admin.migrations import initialize_staging_schema
from ncs_backend.admin.staging import DbApiStagingWriter, StagingConflictError
from ncs_backend.shared.domain.identifiers import BatchId


def _writer(tmp_path):
    database = tmp_path / "staging.sqlite"
    connection = sqlite3.connect(database)
    initialize_staging_schema(connection)
    connection.close()
    return DbApiStagingWriter(lambda: sqlite3.connect(database))


def test_staging_write_is_idempotent_and_rejects_changed_rows(tmp_path):
    writer = _writer(tmp_path)
    batch_id = BatchId("batch-staging-1")
    rows = ({"station_id": "S1", "value": "12.50"}, {"station_id": "S2", "value": "3.00"})

    assert writer.write(batch_id, rows) == 2
    assert writer.write(batch_id, rows) == 2
    assert writer.read(batch_id) == rows
    with pytest.raises(StagingConflictError):
        writer.write(batch_id, ({"station_id": "S1", "value": "99.00"}, {"station_id": "S2", "value": "3.00"}))


def test_staging_rejects_non_json_values(tmp_path):
    writer = _writer(tmp_path)
    with pytest.raises(ValueError):
        writer.write(BatchId("batch-staging-2"), ({"value": object()},))
