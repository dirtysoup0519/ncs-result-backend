"""Validate the fixed read-only result-view contract without reading data rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

ConnectionFactory = Callable[[], Any]


# These are the columns consumed by DbApiDashboardRepository.  Physical result
# tables and ADS names intentionally do not appear here.
VIEW_COLUMNS: Mapping[str, frozenset[str]] = {
    "api_v1_data_status": frozenset(
        {"dataset_code", "data_date", "source_record_count", "station_count", "updated_at", "quality_status", "staleness", "data_version"}
    ),
    "api_v1_dashboard_overview": frozenset(
        {"metric_code", "display_name", "metric_value", "unit", "precision", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_platform_distribution": frozenset(
        {"platform_code", "display_name", "order_count", "total_fees", "order_ratio", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_duration_distribution": frozenset(
        {"bucket_code", "label", "lower_minutes", "upper_minutes", "order_count", "ratio", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_weekday_weekend": frozenset(
        {"day_type", "metric_key", "label", "unit", "metric_order", "max_value", "raw_value", "normalized_value", "normalization_method", "normalization_version", "start_date", "end_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_station_hour_heatmap": frozenset(
        {"station_id", "station_name", "hour", "value", "is_observed", "metric", "metric_code", "unit", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_station_ranking": frozenset(
        {"station_id", "station_name", "order_count", "total_fees", "total_kwh", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_fee_energy_trend": frozenset(
        {"granularity", "period", "order_count", "total_fees", "total_kwh", "period_start", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_process_summary": frozenset(
        {"scope_type", "station_id", "start_date", "end_date", "record_count", "session_count", "average_soc", "average_current", "average_voltage", "average_max_temperature", "data_date", "data_version", "generated_at", "staleness"}
    ),
    "api_v1_load_prediction": frozenset(
        {"series_type", "target_time", "order_count", "charging_energy", "lower_bound", "upper_bound", "prediction_date", "cutoff_hour", "forecast_start_at", "interval_available", "confidence_level", "model_version", "prediction_run_id", "generated_at", "data_version", "staleness"}
    ),
}


@dataclass(frozen=True, slots=True)
class ViewContractResult:
    view_name: str
    exists: bool
    columns: tuple[str, ...]
    missing_columns: tuple[str, ...]
    compatible: bool
    error: str | None = None


def inspect_view_contracts(connection_factory: ConnectionFactory) -> tuple[ViewContractResult, ...]:
    """Inspect only the allowlisted API views and return a deterministic report."""

    results: list[ViewContractResult] = []
    connection = connection_factory()
    cursor = None
    try:
        cursor = connection.cursor()
        for view_name, required in VIEW_COLUMNS.items():
            try:
                cursor.execute(f"SELECT * FROM {view_name} LIMIT 0")
                columns = tuple(column[0] for column in cursor.description or ())
                missing = tuple(sorted(required - set(columns)))
                results.append(
                    ViewContractResult(
                        view_name=view_name,
                        exists=True,
                        columns=columns,
                        missing_columns=missing,
                        compatible=not missing,
                    )
                )
            except Exception as exc:
                results.append(
                    ViewContractResult(
                        view_name=view_name,
                        exists=False,
                        columns=(),
                        missing_columns=tuple(sorted(required)),
                        compatible=False,
                        error=str(exc),
                    )
                )
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()
    return tuple(results)


def assert_view_contracts(connection_factory: ConnectionFactory) -> None:
    failures = [result for result in inspect_view_contracts(connection_factory) if not result.compatible]
    if failures:
        details = "; ".join(
            f"{item.view_name}: missing={','.join(item.missing_columns)}" for item in failures
        )
        raise RuntimeError(f"read-only view contract is not satisfied: {details}")
