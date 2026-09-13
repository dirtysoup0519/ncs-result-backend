"""Flask application factory for the internal administration service."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from flask import Flask, g, jsonify, request

from ncs_backend.admin.services import (
    BatchService,
    DatasetRegistryService,
    PublicationService,
    QualityService,
)
from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.schema import DatasetSchema
from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.identifiers import BatchId, DatasetCode, SchemaVersion
from ncs_backend.shared.config import Settings
from ncs_backend.shared.errors import AppError
from ncs_backend.shared.observability import install_request_context


def create_app(
    settings: Settings | None = None,
    *,
    registry_service: DatasetRegistryService | None = None,
    batch_service: BatchService | None = None,
    quality_service: QualityService | None = None,
    publication_service: PublicationService | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["NCS_SETTINGS"] = settings or Settings.from_env()
    app.config["NCS_ADMIN_SERVICES"] = {
        "registry": registry_service,
        "batch": batch_service,
        "quality": quality_service,
        "publication": publication_service,
    }
    install_request_context(app)

    def services() -> dict[str, Any]:
        return app.config["NCS_ADMIN_SERVICES"]

    def require(name: str) -> Any:
        service = services().get(name)
        if service is None:
            raise AppError("DEPENDENCY_NOT_READY", f"admin service dependency is not configured: {name}", 503)
        return service

    def body() -> dict[str, Any]:
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise AppError("VALIDATION_INVALID_REQUEST", "request body must be a JSON object", 400)
        return value

    def actor(payload: Mapping[str, Any]) -> str:
        value = payload.get("actor") or request.headers.get("X-Actor")
        if not isinstance(value, str) or not value.strip():
            raise AppError("AUTH_ACTOR_REQUIRED", "actor is required for management actions", 400)
        return value.strip()

    def success(data: Any, status: int = 200):
        return jsonify({"code": "OK", "message": "ok", "data": _json_value(data), "meta": {"requestId": g.get("trace_id")}}), status

    @app.get("/health/live")
    def live():
        return jsonify({"code": "OK", "message": "ok", "data": {"status": "alive"}})

    @app.get("/health/ready")
    def ready():
        current: Settings = app.config["NCS_SETTINGS"]
        if not current.database_configured:
            return jsonify({"code": "DEPENDENCY_NOT_READY", "message": "database is not configured"}), 503
        if any(value is None for value in services().values()):
            return jsonify({"code": "DEPENDENCY_NOT_READY", "message": "admin service dependencies are not configured"}), 503
        return jsonify({"code": "OK", "message": "ok", "data": {"status": "ready"}})

    @app.post("/internal/v1/datasets")
    def register_dataset():
        payload = body()
        schema_payload = payload.get("schema")
        if not isinstance(schema_payload, dict):
            raise AppError("VALIDATION_INVALID_PARAMETER", "schema is required", 400, {"field": "schema"})
        try:
            schema = DatasetSchema.from_dict(schema_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400, {"field": "schema"}) from exc
        display_name = payload.get("displayName")
        owner = payload.get("owner")
        if not isinstance(display_name, str) or not isinstance(owner, str):
            raise AppError("VALIDATION_INVALID_PARAMETER", "displayName and owner are required", 400)
        dataset, schema_record = require("registry").register_schema(
            schema,
            display_name=display_name,
            owner=owner,
            compatibility=str(payload.get("compatibility", "BACKWARD")),
        )
        return success({"dataset": dataset, "schema": schema_record}, 201)

    @app.get("/internal/v1/datasets")
    def list_datasets():
        return success({"items": require("registry").list()})

    @app.get("/internal/v1/datasets/<dataset_code>")
    def get_dataset(dataset_code: str):
        return success(require("registry").get(_dataset_code(dataset_code)))

    @app.get("/internal/v1/datasets/<dataset_code>/schemas")
    def list_schemas(dataset_code: str):
        code = _dataset_code(dataset_code)
        require("registry").get(code)
        return success({"datasetCode": code, "items": require("registry").list_schemas(code)})

    @app.post("/internal/v1/import-jobs")
    def create_import_job():
        payload = body()
        manifest_payload = payload.get("manifest", payload)
        if not isinstance(manifest_payload, dict):
            raise AppError("VALIDATION_INVALID_PARAMETER", "manifest is required", 400, {"field": "manifest"})
        source_batch_id = payload.get("sourceBatchId") or manifest_payload.get("sourceBatchId")
        if not isinstance(source_batch_id, str) or not source_batch_id.strip():
            raise AppError("VALIDATION_INVALID_PARAMETER", "sourceBatchId is required", 400, {"field": "sourceBatchId"})
        try:
            manifest = DatasetManifest.from_dict(manifest_payload)
            supplied_batch_id = payload.get("batchId")
            batch_id = _batch_id(supplied_batch_id) if supplied_batch_id else None
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400) from exc
        batch = require("batch").create_batch(manifest, source_batch_id=source_batch_id, batch_id=batch_id)
        return success(batch, 201)

    @app.get("/internal/v1/import-jobs/<batch_id>")
    def get_import_job(batch_id: str):
        return success(require("batch").get(_batch_id(batch_id)))

    @app.get("/internal/v1/import-jobs")
    def list_import_jobs():
        dataset_code = request.args.get("datasetCode")
        status_value = request.args.get("status")
        try:
            code = _dataset_code(dataset_code) if dataset_code else None
            status = BatchStatus(status_value) if status_value else None
        except ValueError as exc:
            raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400) from exc
        return success({"items": require("batch").list(code, status)})

    @app.post("/internal/v1/import-jobs/<batch_id>/validate")
    def validate_import_job(batch_id: str):
        payload = body()
        quality = require("quality")
        batch = require("batch").get(_batch_id(batch_id))
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise AppError("VALIDATION_INVALID_PARAMETER", "results must be an array", 400, {"field": "results"})
        for item in results:
            if not isinstance(item, dict):
                raise AppError("VALIDATION_INVALID_PARAMETER", "each quality result must be an object", 400)
            try:
                quality.record(
                    batch.batch_id,
                    rule_code=_required_text(item, "ruleCode"),
                    severity=_required_text(item, "severity"),
                    passed=_required_bool(item, "passed"),
                    checked_row_count=_required_int(item, "checkedRowCount"),
                    failure_count=_required_int(item, "failureCount"),
                    details=item.get("details") if isinstance(item.get("details"), dict) else None,
                )
            except ValueError as exc:
                raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400) from exc
        completed = quality.complete_validation(batch.batch_id)
        return success(completed)

    @app.get("/internal/v1/import-jobs/<batch_id>/quality-results")
    def quality_results(batch_id: str):
        batch = require("batch").get(_batch_id(batch_id))
        return success({"batchId": batch.batch_id, "items": require("quality").list_results(batch.batch_id)})

    @app.get("/internal/v1/quality-results")
    def list_quality_results():
        batch_value = request.args.get("batchId")
        batch_id = _batch_id(batch_value) if batch_value else None
        severity = request.args.get("severity")
        if severity:
            severity = severity.upper()
        return success(
            {
                "items": require("quality").list_results(
                    batch_id,
                    rule_code=request.args.get("ruleCode"),
                    severity=severity,
                )
            }
        )

    @app.post("/internal/v1/import-jobs/<batch_id>/publish")
    def publish_import_job(batch_id: str):
        payload = body()
        publication = require("publication").publish(
            _batch_id(batch_id),
            actor=actor(payload),
            request_id=payload.get("requestId") or request.headers.get("X-Request-ID"),
            reason=payload.get("reason"),
        )
        return success(publication)

    @app.post("/internal/v1/datasets/<dataset_code>/rollback")
    def rollback_dataset(dataset_code: str):
        payload = body()
        target_batch_id = payload.get("targetBatchId")
        reason = payload.get("reason")
        if not isinstance(target_batch_id, str) or not isinstance(reason, str):
            raise AppError("VALIDATION_INVALID_PARAMETER", "targetBatchId and reason are required", 400)
        publication = require("publication").rollback(
            _dataset_code(dataset_code),
            _batch_id(target_batch_id),
            actor=actor(payload),
            reason=reason,
            request_id=payload.get("requestId") or request.headers.get("X-Request-ID"),
        )
        return success(publication)

    @app.get("/internal/v1/publications")
    def list_publications():
        dataset_code = request.args.get("datasetCode")
        code = _dataset_code(dataset_code) if dataset_code else None
        return success({"items": require("publication").list(code)})

    @app.get("/internal/v1/publications/<publication_id>")
    def get_publication(publication_id: str):
        if not publication_id.strip():
            raise AppError("VALIDATION_INVALID_PARAMETER", "publicationId is invalid", 400)
        return success(require("publication").get(publication_id))

    @app.get("/internal/v1/datasets/<dataset_code>/active-publication")
    def active_publication(dataset_code: str):
        return success(require("publication").active(_dataset_code(dataset_code)))

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_dict(g.get("trace_id"))), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        response = AppError("ADMIN_ROUTE_NOT_FOUND", "route was not found", 404)
        return jsonify(response.to_dict(g.get("trace_id"))), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        response = AppError("INTERNAL_ERROR", "unexpected internal error", 500)
        return jsonify(response.to_dict(g.get("trace_id"))), 500

    return app


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (BatchId, DatasetCode, SchemaVersion)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    return value


def _batch_id(value: Any) -> BatchId:
    if not isinstance(value, str):
        raise AppError("VALIDATION_INVALID_PARAMETER", "batchId is invalid", 400, {"field": "batchId"})
    try:
        return BatchId(value)
    except ValueError as exc:
        raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400, {"field": "batchId"}) from exc


def _dataset_code(value: Any) -> DatasetCode:
    if not isinstance(value, str):
        raise AppError("VALIDATION_INVALID_PARAMETER", "datasetCode is invalid", 400, {"field": "datasetCode"})
    try:
        return DatasetCode(value)
    except ValueError as exc:
        raise AppError("VALIDATION_INVALID_PARAMETER", str(exc), 400, {"field": "datasetCode"}) from exc


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_bool(payload: Mapping[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _required_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value
