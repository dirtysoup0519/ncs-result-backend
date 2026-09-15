"""Execute a registered adapter and atomically publish prediction results."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

from ncs_backend.prediction.adapters import AdapterRegistry
from ncs_backend.prediction.dataset import LoadHourlyDatasetBuilder, PredictionDataset
from ncs_backend.prediction.model_registry import ModelPackage, ModelPackageError
from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT


class PredictionRunError(RuntimeError):
    pass


# The read contract encodes forecast hours as offsets from the business date's
# midnight and caps them at 47 -- one day past the latest possible cutoff
# (23 + 24). A longer horizon would publish hours the dashboard rejects, so it
# is refused at publish time rather than at read time.
MAX_READ_HORIZON = 24


class PredictionRunner:
    def __init__(
        self,
        *,
        dialect: DatabaseDialect = MYSQL_DIALECT,
        adapters: AdapterRegistry | None = None,
        dataset_builder: LoadHourlyDatasetBuilder | None = None,
        clock=None,
    ) -> None:
        self._dialect = dialect
        self._adapters = adapters or AdapterRegistry()
        self._builder = dataset_builder or LoadHourlyDatasetBuilder(dialect=dialect)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        connection: Any,
        package: ModelPackage,
        *,
        cutoff_time: datetime | str | None = None,
        horizon: int | None = None,
    ) -> str:
        adapter, loaded_model, checkpoint = self._adapters.validate_and_load(package)
        requested_horizon = int(horizon or package.manifest["output"]["horizon"])
        if requested_horizon < 1 or requested_horizon > MAX_READ_HORIZON:
            raise PredictionRunError(f"horizon must be between 1 and {MAX_READ_HORIZON}")
        dataset = self._builder.build(
            connection,
            cutoff_time=cutoff_time,
            lookback=int(package.manifest["input"]["lookback"]),
            horizon=requested_horizon,
        )
        existing = self._find_existing(connection, package, dataset, requested_horizon)
        if existing:
            return existing
        run_id = f"pred-{uuid4().hex}"
        self._ensure_model_record(connection, package, checkpoint)
        self._create_run(connection, run_id, package, dataset, requested_horizon)
        try:
            values = adapter.predict(loaded_model, dataset, requested_horizon)
            self._validate_output(values, requested_horizon)
            self._publish(connection, run_id, package, dataset, values, requested_horizon)
            return run_id
        except Exception as exc:
            self._mark_failed(connection, run_id, exc)
            if isinstance(exc, PredictionRunError):
                raise
            raise PredictionRunError(str(exc)) from exc

    def _ensure_model_record(self, connection, package, checkpoint) -> None:
        cursor = self._dialect.cursor(connection)
        try:
            cursor.execute(
                "SELECT 1 FROM ctl_model_version WHERE model_code = ? AND model_version = ?",
                (package.model_code, package.model_version),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO ctl_model_version (model_code, model_version, adapter_code, framework, weights_uri, weights_sha256, input_contract_json, output_contract_json, metrics_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED')",
                    (
                        package.model_code, package.model_version, package.adapter_code,
                        package.manifest["framework"], str(package.weights_path), package.weights_sha256,
                        json.dumps(package.manifest.get("input", {}), ensure_ascii=False),
                        json.dumps(package.manifest.get("output", {}), ensure_ascii=False),
                        json.dumps(checkpoint.get("test_metrics"), ensure_ascii=False) if checkpoint.get("test_metrics") is not None else None,
                    ),
                )
            connection.commit()
        finally:
            cursor.close()

    def _create_run(self, connection, run_id, package, dataset: PredictionDataset, horizon: int) -> None:
        now = _timestamp(self._clock())
        cursor = self._dialect.cursor(connection)
        try:
            cursor.execute(
                "INSERT INTO ctl_prediction_run (prediction_run_id, model_code, model_version, source_batch_id, cutoff_time, lookback, horizon, dataset_profile_json, status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?)",
                (run_id, package.model_code, package.model_version, dataset.source_batch_id, _timestamp(dataset.cutoff_time), len(dataset.values), horizon, json.dumps(dataset.profile, ensure_ascii=False), now),
            )
            connection.commit()
        finally:
            cursor.close()

    def _publish(self, connection, run_id, package, dataset, values, horizon) -> None:
        stamp = _timestamp(self._clock())
        forecast_start = dataset.cutoff_time + timedelta(hours=1)
        prediction_date = dataset.cutoff_time.date().isoformat()
        cursor = self._dialect.cursor(connection)
        try:
            # ``order_counts`` defaults to an empty tuple, and zipping it directly
            # would silently publish zero ACTUAL rows; fall back to nulls of the
            # right length instead.
            order_counts = dataset.order_counts or (None,) * len(dataset.values)
            actual_rows = [
                (run_id, "ACTUAL", _timestamp(timestamp), order_count, value, None, None, prediction_date, dataset.cutoff_time.hour, _timestamp(forecast_start), 0, None, package.model_version, dataset.source_batch_id, stamp, dataset.data_version, "FRESH", horizon)
                for timestamp, value, order_count in zip(dataset.timestamps, dataset.values, order_counts)
            ]
            forecast_rows = [
                (run_id, "FORECAST", _timestamp(forecast_start + timedelta(hours=index)), None, value, None, None, prediction_date, dataset.cutoff_time.hour, _timestamp(forecast_start), 0, None, package.model_version, dataset.source_batch_id, stamp, dataset.data_version, "FRESH", horizon)
                for index, value in enumerate(values)
            ]
            cursor.executemany(
                "INSERT INTO rpt_load_prediction (prediction_run_id, series_type, target_time, order_count, charging_energy, lower_bound, upper_bound, prediction_date, cutoff_hour, forecast_start_at, interval_available, confidence_level, model_version, source_batch_id, generated_at, data_version, staleness, horizon) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*actual_rows, *forecast_rows),
            )
            cursor.execute(
                "UPDATE ctl_prediction_run SET status = 'PUBLISHED', completed_at = ?, published_at = ? WHERE prediction_run_id = ?",
                (stamp, stamp, run_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def _mark_failed(self, connection, run_id: str, error: Exception) -> None:
        cursor = self._dialect.cursor(connection)
        try:
            cursor.execute(
                "UPDATE ctl_prediction_run SET status = 'FAILED', error_code = ?, error_message = ?, completed_at = ? WHERE prediction_run_id = ?",
                (type(error).__name__, str(error)[:2000], _timestamp(self._clock()), run_id),
            )
            connection.commit()
        finally:
            cursor.close()

    def _find_existing(self, connection, package, dataset, horizon):
        cursor = self._dialect.cursor(connection)
        try:
            cursor.execute(
                "SELECT prediction_run_id FROM ctl_prediction_run WHERE model_code = ? AND model_version = ? AND source_batch_id = ? AND cutoff_time = ? AND horizon = ? AND status = 'PUBLISHED' ORDER BY published_at DESC LIMIT 1",
                (package.model_code, package.model_version, dataset.source_batch_id, _timestamp(dataset.cutoff_time), horizon),
            )
            row = cursor.fetchone()
            return str(row[0]) if row else None
        finally:
            cursor.close()

    @staticmethod
    def _validate_output(values, horizon):
        if len(values) != horizon or any(value < 0 for value in values):
            raise PredictionRunError("prediction output length or range is invalid")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")
