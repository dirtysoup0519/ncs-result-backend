"""Flask application factory for the read-only query service."""

from __future__ import annotations

from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from flask import Flask, g, jsonify, request

from ncs_backend.query.repository import DashboardReadRepository, EmptyDashboardRepository, QueryPayload
from ncs_backend.query.service import DashboardQueryService
from ncs_backend.shared.config import Settings
from ncs_backend.shared.errors import AppError
from ncs_backend.shared.observability import install_request_context


def create_app(
    settings: Settings | None = None,
    repository: DashboardReadRepository | None = None,
    clock: Any | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["NCS_SETTINGS"] = settings or Settings.from_env()
    install_request_context(app)
    app.config["NCS_QUERY_SERVICE"] = DashboardQueryService(repository or EmptyDashboardRepository(), clock=clock)

    def envelope(payload: QueryPayload):
        response = jsonify(
            {
                "code": "OK",
                "message": "ok",
                "data": _json_value(payload.data),
                "meta": {
                    "requestId": g.get("trace_id"),
                    "dataVersion": payload.data_version,
                    "dataDate": _json_value(payload.data_date),
                    "generatedAt": _json_value(payload.generated_at),
                    "staleness": payload.staleness,
                    "empty": payload.empty,
                    "partial": payload.partial,
                },
            }
        )
        if payload.data_version:
            etag = f'"{payload.data_version}"'
            response.headers["ETag"] = etag
            if request.headers.get("If-None-Match") == etag:
                response.status_code = 304
                response.set_data(b"")
        return response

    def resource(name: str):
        service: DashboardQueryService = app.config["NCS_QUERY_SERVICE"]
        return envelope(service.query(name, request.args))

    def static_meta(*, empty: bool) -> dict[str, Any]:
        service: DashboardQueryService = app.config["NCS_QUERY_SERVICE"]
        return {
            "requestId": g.get("trace_id"),
            "dataVersion": None,
            "dataDate": None,
            "generatedAt": _json_value(service.now()),
            "staleness": "UNKNOWN",
            "empty": empty,
            "partial": False,
        }

    @app.get("/api/v1/meta/data-status")
    def data_status():
        return resource("data_status")

    @app.get("/api/v1/dashboard/overview")
    def overview():
        return resource("overview")

    @app.get("/api/v1/audience/platform-distribution")
    def platform_distribution():
        return resource("platform")

    @app.get("/api/v1/charging/duration-distribution")
    def duration_distribution():
        return resource("duration")

    @app.get("/api/v1/charging/weekday-weekend")
    def weekday_weekend():
        return resource("weekday_weekend")

    @app.get("/api/v1/charging/station-hour-heatmap")
    def station_hour_heatmap():
        return resource("heatmap")

    @app.get("/api/v1/stations/ranking")
    def station_ranking():
        return resource("ranking")

    @app.get("/api/v1/revenue/trend")
    def fee_energy_trend():
        return resource("fee_energy_trend")

    @app.get("/api/v1/charging/process-summary")
    def process_summary():
        return resource("process_summary")

    @app.get("/api/v1/predictions/load")
    def load_prediction():
        return resource("prediction")

    @app.get("/api/v1/meta/capabilities")
    def capabilities():
        service: DashboardQueryService = app.config["NCS_QUERY_SERVICE"]
        return jsonify(
            {
                "code": "OK",
                "message": "ok",
                "data": {
                    "items": [
                        {
                            "capabilityCode": item["componentCode"],
                            "available": service.is_available(item["resource"]),
                            "registered": True,
                            "endpoint": item["endpoint"],
                            "priority": item["priority"],
                        }
                        for item in _COMPONENTS
                    ]
                },
                "meta": static_meta(empty=False),
            }
        )

    @app.get("/api/v1/meta/filter-options")
    def filter_options():
        topic = request.args.get("topic")
        if not topic:
            raise AppError("VALIDATION_INVALID_PARAMETER", "topic is required", 400, {"field": "topic"})
        if topic not in {item["componentCode"] for item in _COMPONENTS}:
            raise AppError("VALIDATION_INVALID_PARAMETER", "topic is not supported", 400, {"field": "topic"})
        service: DashboardQueryService = app.config["NCS_QUERY_SERVICE"]
        data = service.filter_options(topic)
        empty = not data.get("regions") and not data.get("stations") and data.get("dateRange") is None
        return jsonify(
            {
                "code": "OK",
                "message": "ok",
                "data": data,
                "meta": static_meta(empty=empty),
            }
        )

    @app.get("/api/v1/dashboard/manifest")
    def manifest():
        service: DashboardQueryService = app.config["NCS_QUERY_SERVICE"]
        return jsonify(
            {
                "code": "OK",
                "message": "ok",
                "data": {
                    "items": [
                        {
                            "componentCode": item["componentCode"],
                            "endpoint": item["endpoint"],
                            "priority": item["priority"],
                            "available": service.is_available(item["resource"]),
                            "registered": True,
                            "refreshIntervalSeconds": None,
                        }
                        for item in _COMPONENTS
                    ]
                },
                "meta": static_meta(empty=False),
            }
        )

    @app.get("/health/live")
    def live():
        return jsonify({"code": "OK", "message": "ok", "data": {"status": "alive"}})

    @app.get("/health/ready")
    def ready():
        current: Settings = app.config["NCS_SETTINGS"]
        if not current.database_configured:
            return jsonify({"code": "DEPENDENCY_NOT_READY", "message": "database is not configured"}), 503
        return jsonify({"code": "OK", "message": "ok", "data": {"status": "ready"}})

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_dict(g.get("trace_id"))), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        response = AppError("QUERY_ROUTE_NOT_FOUND", "route was not found", 404)
        return jsonify(response.to_dict(g.get("trace_id"))), 404

    return app


_COMPONENTS = (
    {"componentCode": "globalStatus", "resource": "data_status", "endpoint": "/api/v1/meta/data-status", "priority": "P0"},
    {"componentCode": "overview", "resource": "overview", "endpoint": "/api/v1/dashboard/overview", "priority": "P0"},
    {"componentCode": "platformDistribution", "resource": "platform", "endpoint": "/api/v1/audience/platform-distribution", "priority": "P0"},
    {"componentCode": "durationDistribution", "resource": "duration", "endpoint": "/api/v1/charging/duration-distribution", "priority": "P1"},
    {"componentCode": "weekdayWeekendProfile", "resource": "weekday_weekend", "endpoint": "/api/v1/charging/weekday-weekend", "priority": "P1"},
    {"componentCode": "loadPrediction", "resource": "prediction", "endpoint": "/api/v1/predictions/load", "priority": "P2"},
    {"componentCode": "stationHourHeatmap", "resource": "heatmap", "endpoint": "/api/v1/charging/station-hour-heatmap", "priority": "P1"},
    {"componentCode": "stationRanking", "resource": "ranking", "endpoint": "/api/v1/stations/ranking", "priority": "P0"},
    {"componentCode": "feeEnergyTrend", "resource": "fee_energy_trend", "endpoint": "/api/v1/revenue/trend", "priority": "P0"},
    {"componentCode": "processSummary", "resource": "process_summary", "endpoint": "/api/v1/charging/process-summary", "priority": "P0"},
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
