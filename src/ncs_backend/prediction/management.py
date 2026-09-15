"""Model registration and activation operations for the internal runner."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from .adapters import AdapterRegistry
from .model_registry import ModelPackage
from .runner import PredictionRunner
from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT


def register_model(connection: Any, package: ModelPackage, *, dialect: DatabaseDialect = MYSQL_DIALECT) -> dict[str, Any]:
    adapter, _, checkpoint = AdapterRegistry().validate_and_load(package)
    cursor = dialect.cursor(connection)
    try:
        cursor.execute("SELECT weights_sha256, status FROM ctl_model_version WHERE model_code = ? AND model_version = ?", (package.model_code, package.model_version))
        current = cursor.fetchone()
        if current and str(current[0]) != package.weights_sha256:
            raise ValueError("model version already exists with a different weights hash")
        if not current:
            cursor.execute(
                "INSERT INTO ctl_model_version (model_code, model_version, adapter_code, framework, weights_uri, weights_sha256, input_contract_json, output_contract_json, metrics_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED')",
                (package.model_code, package.model_version, adapter.code, package.manifest["framework"], str(package.weights_path), package.weights_sha256, json.dumps(package.manifest.get("input", {}), ensure_ascii=False), json.dumps(package.manifest.get("output", {}), ensure_ascii=False), json.dumps(checkpoint.get("test_metrics"), ensure_ascii=False) if checkpoint.get("test_metrics") is not None else None),
            )
        connection.commit()
        return {"modelCode": package.model_code, "modelVersion": package.model_version, "adapterCode": adapter.code, "weightsSha256": package.weights_sha256, "status": str(current[1]) if current else "VALIDATED"}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def activate_model(connection: Any, model_code: str, model_version: str, *, dialect: DatabaseDialect = MYSQL_DIALECT) -> dict[str, Any]:
    cursor = dialect.cursor(connection)
    try:
        cursor.execute("SELECT status FROM ctl_model_version WHERE model_code = ? AND model_version = ?", (model_code, model_version))
        if cursor.fetchone() is None:
            raise ValueError("model version is not registered")
        now = _timestamp(datetime.now(timezone.utc))
        cursor.execute("UPDATE ctl_model_version SET status = 'INACTIVE', deactivated_at = ? WHERE model_code = ? AND status = 'ACTIVE'", (now, model_code))
        cursor.execute("UPDATE ctl_model_version SET status = 'ACTIVE', activated_at = ?, deactivated_at = NULL WHERE model_code = ? AND model_version = ?", (now, model_code, model_version))
        connection.commit()
        return {"modelCode": model_code, "modelVersion": model_version, "status": "ACTIVE", "activatedAt": now}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def list_models(connection: Any, *, dialect: DatabaseDialect = MYSQL_DIALECT) -> list[dict[str, Any]]:
    cursor = dialect.cursor(connection)
    try:
        cursor.execute("SELECT model_code, model_version, adapter_code, framework, weights_sha256, status, registered_at, activated_at FROM ctl_model_version ORDER BY registered_at DESC")
        return [dict(zip(("modelCode", "modelVersion", "adapterCode", "framework", "weightsSha256", "status", "registeredAt", "activatedAt"), row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class PredictionManagementService:
    """Small application-facing facade used by the internal admin API."""

    def __init__(self, connection_factory, *, dialect: DatabaseDialect = MYSQL_DIALECT) -> None:
        self._connection_factory = connection_factory
        self._dialect = dialect

    def register(self, package_path: str) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            return register_model(connection, ModelPackage.open(package_path), dialect=self._dialect)
        finally:
            connection.close()

    def activate(self, model_code: str, model_version: str) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            return activate_model(connection, model_code, model_version, dialect=self._dialect)
        finally:
            connection.close()

    def list_models(self) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            return list_models(connection, dialect=self._dialect)
        finally:
            connection.close()

    def run(self, package_path: str, *, cutoff_time=None, horizon: int = 24) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            package = ModelPackage.open(package_path)
            run_id = PredictionRunner(dialect=self._dialect).run(connection, package, cutoff_time=cutoff_time, horizon=horizon)
            return {"predictionRunId": run_id}
        finally:
            connection.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        connection = self._connection_factory()
        cursor = self._dialect.cursor(connection)
        try:
            cursor.execute("SELECT prediction_run_id, model_code, model_version, source_batch_id, cutoff_time, lookback, horizon, dataset_profile_json, status, error_code, error_message, started_at, completed_at, published_at FROM ctl_prediction_run WHERE prediction_run_id = ?", (run_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            keys = ("predictionRunId", "modelCode", "modelVersion", "sourceBatchId", "cutoffTime", "lookback", "horizon", "datasetProfile", "status", "errorCode", "errorMessage", "startedAt", "completedAt", "publishedAt")
            result = dict(zip(keys, row))
            try:
                result["datasetProfile"] = json.loads(result["datasetProfile"])
            except (TypeError, json.JSONDecodeError):
                pass
            return result
        finally:
            cursor.close()
            connection.close()
