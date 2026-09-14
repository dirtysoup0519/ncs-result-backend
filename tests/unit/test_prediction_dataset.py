from datetime import datetime, timedelta
import sqlite3

import pytest

from ncs_backend.prediction.dataset import LoadHourlyDatasetBuilder, PredictionDatasetError
from ncs_backend.shared.db import SQLITE_DIALECT


def _database(count=4, gap=False):
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE ctl_publication (dataset_code TEXT, batch_id TEXT, status TEXT)")
    connection.execute("CREATE TABLE rpt_load_hourly (batch_id TEXT, stat_time TEXT, total_kwh REAL, is_observed INTEGER, data_version TEXT)")
    connection.execute("INSERT INTO ctl_publication VALUES ('load_hourly', 'batch-1', 'PUBLISHED')")
    start = datetime(2015, 12, 28, 0)
    for index in range(count):
        hour = index + (1 if gap and index >= 2 else 0)
        connection.execute("INSERT INTO rpt_load_hourly VALUES (?, ?, ?, ?, ?)", ("batch-1", (start + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S"), index + 1.0, 1, "2.2.0"))
    return connection


def test_builder_creates_profile_and_five_channel_tensors():
    dataset = LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(_database(), lookback=4, horizon=2)
    assert dataset.profile["rowCount"] == 4
    assert dataset.profile["qualityStatus"] == "PASSED"
    assert tuple(dataset.tensor.shape) == (1, 4, 5)
    assert tuple(dataset.calendar_tensor.shape) == (1, 6, 4)


def test_builder_rejects_non_continuous_window():
    with pytest.raises(PredictionDatasetError, match="not continuous"):
        LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(_database(gap=True), lookback=4)
