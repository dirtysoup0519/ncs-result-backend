"""Application service for the frozen dashboard read contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

from ncs_backend.query.repository import DashboardReadRepository, QueryPayload
from ncs_backend.shared.errors import AppError


RESOURCE_RULES: dict[str, dict[str, Any]] = {
    "data_status": {"allowed": {"datasetCode"}},
    "overview": {"allowed": {"dataDate", "regionId"}},
    "platform": {"allowed": {"dataDate", "regionId"}},
    "duration": {"allowed": {"dataDate", "startDate", "endDate", "regionId", "stationId"}},
    "weekday_weekend": {"allowed": {"startDate", "endDate", "regionId"}},
    "heatmap": {"allowed": {"dataDate", "metric", "regionId", "stationIds", "limit"}},
    "ranking": {"allowed": {"dataDate", "startDate", "endDate", "regionId", "metric", "limit"}},
    "fee_energy_trend": {"allowed": {"startDate", "endDate", "regionId", "stationId", "granularity"}},
    "process_summary": {"allowed": {"dataDate", "startDate", "endDate", "stationId"}},
    "prediction": {"allowed": {"date", "cutoffHour", "stationId", "regionId", "horizon"}},
}


class DashboardQueryService:
    def __init__(self, repository: DashboardReadRepository, clock: Any | None = None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def query(self, resource: str, raw_params: Mapping[str, str]) -> QueryPayload:
        if resource not in RESOURCE_RULES:
            raise AppError("QUERY_RESOURCE_NOT_FOUND", "dashboard resource is not registered", 404)
        params = self._validate(resource, raw_params)
        payload = self._repository.fetch(resource, params)
        return self._with_generated_at(payload)

    def now(self) -> datetime:
        return self._clock()

    def is_available(self, resource: str) -> bool:
        checker = getattr(self._repository, "is_available", None)
        return bool(checker(resource)) if checker is not None else False

    def filter_options(self, topic: str) -> Mapping[str, Any]:
        checker = getattr(self._repository, "filter_options", None)
        if checker is None:
            return {"topic": topic, "regions": [], "stations": [], "dateRange": None}
        return checker(topic)

    def _validate(self, resource: str, raw: Mapping[str, str]) -> dict[str, Any]:
        rules = RESOURCE_RULES[resource]
        unknown = set(raw) - rules["allowed"]
        if unknown:
            raise AppError(
                "VALIDATION_UNKNOWN_PARAMETER",
                "unknown query parameter",
                400,
                {"fields": sorted(unknown)},
            )
        params = dict(raw)
        for name in ("dataDate", "startDate", "endDate", "date"):
            if name in params:
                try:
                    params[name] = date.fromisoformat(params[name])
                except ValueError as exc:
                    raise AppError("VALIDATION_INVALID_PARAMETER", f"{name} must be YYYY-MM-DD", 400, {"field": name}) from exc
        if "startDate" in params and "endDate" in params and params["startDate"] > params["endDate"]:
            raise AppError("VALIDATION_INVALID_PARAMETER", "startDate must not be after endDate", 400)
        if "dataDate" in params and ("startDate" in params or "endDate" in params):
            raise AppError("VALIDATION_INVALID_PARAMETER", "dataDate cannot be combined with a date range", 400)
        if "limit" in params:
            try:
                params["limit"] = int(params["limit"])
            except ValueError as exc:
                raise AppError("VALIDATION_INVALID_PARAMETER", "limit must be an integer", 400, {"field": "limit"}) from exc
            if params["limit"] <= 0:
                raise AppError("VALIDATION_INVALID_PARAMETER", "limit must be positive", 400, {"field": "limit"})
            maximum = 10 if resource in {"heatmap", "ranking"} else 100
            if params["limit"] > maximum:
                raise AppError("VALIDATION_INVALID_PARAMETER", f"limit must not exceed {maximum}", 400, {"field": "limit"})
        if "cutoffHour" in params:
            try:
                params["cutoffHour"] = int(params["cutoffHour"])
            except ValueError as exc:
                raise AppError("VALIDATION_INVALID_PARAMETER", "cutoffHour must be an integer", 400, {"field": "cutoffHour"}) from exc
            if not 0 <= params["cutoffHour"] <= 23:
                raise AppError("VALIDATION_INVALID_PARAMETER", "cutoffHour must be between 0 and 23", 400, {"field": "cutoffHour"})
        if resource == "heatmap" and params.get("metric", "kwh") not in {"kwh", "orders", "fees"}:
            raise AppError("VALIDATION_INVALID_PARAMETER", "metric is not supported for heatmap", 400, {"field": "metric"})
        if resource == "ranking" and params.get("metric", "fees") != "fees":
            raise AppError("VALIDATION_INVALID_PARAMETER", "V1 ranking metric must be fees", 400, {"field": "metric"})
        if resource == "fee_energy_trend" and params.get("granularity", "MONTH") not in {"HOUR", "DAY", "MONTH"}:
            raise AppError("VALIDATION_INVALID_PARAMETER", "granularity is not supported", 400, {"field": "granularity"})
        if resource == "prediction" and "horizon" in params and params["horizon"] not in {"1h", "6h", "24h"}:
            raise AppError("PREDICTION_UNSUPPORTED_HORIZON", "horizon is not supported", 400, {"field": "horizon"})
        if resource == "prediction" and "cutoffHour" not in params:
            raise AppError("VALIDATION_INVALID_PARAMETER", "cutoffHour is required", 400, {"field": "cutoffHour"})
        if resource == "process_summary" and "stationId" in params:
            raise AppError(
                "VALIDATION_UNSUPPORTED_FILTER",
                "stationId is not available for the current process summary source",
                400,
                {"field": "stationId"},
            )
        if resource == "heatmap":
            params.setdefault("metric", "kwh")
            params.setdefault("limit", 8)
        elif resource == "ranking":
            params.setdefault("metric", "fees")
            params.setdefault("limit", 10)
        elif resource == "fee_energy_trend":
            params.setdefault("granularity", "MONTH")
        return params

    def _with_generated_at(self, payload: QueryPayload) -> QueryPayload:
        if payload.generated_at is not None:
            return payload
        return QueryPayload(
            data=payload.data,
            data_date=payload.data_date,
            data_version=payload.data_version,
            generated_at=self._clock(),
            staleness=payload.staleness,
            empty=payload.empty,
            partial=payload.partial,
        )
