from datetime import datetime, timedelta
import sqlite3

import pytest

from ncs_backend.prediction.dataset import LoadHourlyDatasetBuilder, PredictionDatasetError
from ncs_backend.shared.db import SQLITE_DIALECT


def _database(count=4, gap=False):
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE ctl_publication (dataset_code TEXT, batch_id TEXT, status TEXT)")
    connection.execute("CREATE TABLE rpt_load_hourly (batch_id TEXT, stat_time TEXT, total_kwh REAL, order_count INTEGER, is_observed INTEGER, data_version TEXT)")
    connection.execute("INSERT INTO ctl_publication VALUES ('load_hourly', 'batch-1', 'PUBLISHED')")
    start = datetime(2015, 12, 28, 0)
    for index in range(count):
        hour = index + (1 if gap and index >= 2 else 0)
        connection.execute("INSERT INTO rpt_load_hourly VALUES (?, ?, ?, ?, ?, ?)", ("batch-1", (start + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S"), index + 1.0, index * 3, 1, "2.2.0"))
    return connection


def test_builder_creates_profile_and_five_channel_tensors():
    pytest.importorskip("numpy")
    pytest.importorskip("torch")
    dataset = LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(_database(), lookback=4, horizon=2)
    assert dataset.profile["rowCount"] == 4
    assert dataset.profile["qualityStatus"] == "PASSED"
    assert dataset.order_counts == (0, 3, 6, 9)
    assert tuple(dataset.tensor.shape) == (1, 4, 5)
    assert tuple(dataset.calendar_tensor.shape) == (1, 6, 4)


def test_builder_rejects_non_continuous_window():
    with pytest.raises(PredictionDatasetError, match="not continuous"):
        LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(_database(gap=True), lookback=4)


def test_builder_caps_implicit_cutoff_so_the_forecast_stays_on_the_business_date():
    pytest.importorskip("numpy")
    pytest.importorskip("torch")
    # _database(count=48) ends at 2015-12-29 23:00; a cutoff there would start the
    # forecast on 12-30 and the dashboard would reject the payload.
    dataset = LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(_database(count=48), lookback=24, horizon=24)

    assert dataset.cutoff_time == datetime(2015, 12, 29, 22)
    assert dataset.timestamps[-1] == datetime(2015, 12, 29, 22)
    assert len(dataset.timestamps) == 24


def test_builder_rejects_an_explicit_cutoff_that_would_start_the_forecast_next_day():
    with pytest.raises(PredictionDatasetError, match="business date"):
        LoadHourlyDatasetBuilder(dialect=SQLITE_DIALECT).build(
            _database(count=48), cutoff_time="2015-12-29 23:00", lookback=24
        )
