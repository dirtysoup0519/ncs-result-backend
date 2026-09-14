"""Schema metadata for the ADS Spark contract packages.

The v2.5 hand-off keeps the ten v2.3 datasets and adds eight datasets used by
the current dashboard.  The old constants remain exported for compatibility
with existing callers and fixtures; new code should select specs by manifest
schema version.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdsV23DatasetSpec:
    dataset_code: str
    filename: str
    fields: tuple[str, ...]
    primary_key: tuple[str, ...]


ADS_V23_DATASET_SPECS: tuple[AdsV23DatasetSpec, ...] = (
    AdsV23DatasetSpec(
        "dashboard_overview", "dashboard_overview.csv",
        ("start_date", "end_date", "total_order_count", "total_fees", "total_kwh", "total_user_count", "active_station_count", "station_count", "metric_version"),
        ("start_date", "end_date"),
    ),
    AdsV23DatasetSpec(
        "platform_distribution", "platform_distribution.csv",
        ("start_date", "end_date", "platform_code", "order_count", "order_ratio", "total_fees", "fee_ratio"),
        ("start_date", "end_date", "platform_code"),
    ),
    AdsV23DatasetSpec(
        "fee_energy_daily", "fee_energy_daily.csv",
        ("data_date", "order_count", "total_kwh", "total_fees", "total_charge_hours", "user_count"),
        ("data_date",),
    ),
    AdsV23DatasetSpec(
        "station_daily", "station_daily.csv",
        ("data_date", "station_id", "station_name", "location_id", "order_count", "total_kwh", "total_fees"),
        ("data_date", "station_id"),
    ),
    AdsV23DatasetSpec(
        "station_reference", "station_reference.csv",
        ("station_id", "location_id", "facility_type", "station_name", "address", "device_count", "open_time", "update_time"),
        ("station_id",),
    ),
    AdsV23DatasetSpec(
        "duration_distribution", "duration_distribution.csv",
        ("start_date", "end_date", "bucket_code", "duration_bucket", "order_count", "order_ratio"),
        ("start_date", "end_date", "bucket_code"),
    ),
    AdsV23DatasetSpec(
        "weekday_weekend_profile", "weekday_weekend_profile.csv",
        ("start_date", "end_date", "day_type", "order_count", "total_kwh", "total_fees", "avg_charge_hours", "user_count", "weekday_source"),
        ("start_date", "end_date", "day_type"),
    ),
    AdsV23DatasetSpec(
        "station_hour_daily", "station_hour_daily.csv",
        ("data_date", "station_id", "station_name", "stat_hour", "order_count", "total_kwh", "total_fees"),
        ("data_date", "station_id", "stat_hour"),
    ),
    AdsV23DatasetSpec(
        "process_daily", "process_daily.csv",
        ("data_date", "record_count", "session_count", "avg_soc", "max_soc", "min_soc", "avg_current", "avg_pack_voltage", "avg_max_temperature", "record_time_source"),
        ("data_date",),
    ),
    AdsV23DatasetSpec(
        "load_hourly", "load_hourly.csv",
        ("stat_time", "total_kwh", "order_count", "is_observed", "fill_method", "time_quality", "allocation_method"),
        ("stat_time",),
    ),
)

ADS_V23_SPECS_BY_CODE = {spec.dataset_code: spec for spec in ADS_V23_DATASET_SPECS}
ADS_V23_SPECS_BY_FILE = {spec.filename: spec for spec in ADS_V23_DATASET_SPECS}

# v2.5 (manifest schemaVersion 2.2.x) additions.
ADS_V25_DATASET_SPECS: tuple[AdsV23DatasetSpec, ...] = ADS_V23_DATASET_SPECS + (
    AdsV23DatasetSpec(
        "station_top10_snapshot", "station_top10_snapshot.csv",
        ("start_date", "end_date", "rank_order", "station_id", "station_name", "location_id", "order_count", "total_kwh", "total_fees", "ranking_metric"),
        ("start_date", "end_date", "rank_order"),
    ),
    AdsV23DatasetSpec(
        "station_hour_heatmap_profile", "station_hour_heatmap_profile.csv",
        ("start_date", "end_date", "station_rank", "station_id", "station_name", "stat_hour", "order_count", "total_kwh", "total_fees", "is_filled_zero"),
        ("start_date", "end_date", "station_rank", "stat_hour"),
    ),
    AdsV23DatasetSpec(
        "revenue_monthly", "revenue_monthly.csv",
        ("stat_month", "order_count", "total_kwh", "total_fees", "user_count", "active_station_count"),
        ("stat_month",),
    ),
    AdsV23DatasetSpec(
        "kpi_period_comparison", "kpi_period_comparison.csv",
        ("current_period", "previous_period", "metric_code", "metric_name", "unit", "current_value", "previous_value", "change_pct"),
        ("current_period", "metric_code"),
    ),
    AdsV23DatasetSpec(
        "weekday_hour_profile", "weekday_hour_profile.csv",
        ("start_date", "end_date", "day_type", "stat_hour", "order_count", "total_kwh", "total_fees", "avg_charge_hours"),
        ("start_date", "end_date", "day_type", "stat_hour"),
    ),
    AdsV23DatasetSpec(
        "charge_type_distribution", "charge_type_distribution.csv",
        ("start_date", "end_date", "facility_type", "charge_type", "order_count", "order_ratio", "total_kwh", "total_fees", "avg_charge_hours"),
        ("start_date", "end_date", "facility_type"),
    ),
    AdsV23DatasetSpec(
        "station_charge_type", "station_charge_type.csv",
        ("start_date", "end_date", "station_id", "station_name", "facility_type", "charge_type", "order_count", "total_kwh", "total_fees"),
        ("start_date", "end_date", "station_id", "facility_type"),
    ),
    AdsV23DatasetSpec(
        "process_overview", "process_overview.csv",
        ("start_date", "end_date", "record_count", "session_count", "avg_soc", "avg_temperature", "avg_pack_voltage", "avg_current", "record_time_source"),
        ("start_date", "end_date"),
    ),
)

ADS_V25_SPECS_BY_CODE = {spec.dataset_code: spec for spec in ADS_V25_DATASET_SPECS}
ADS_V25_SPECS_BY_FILE = {spec.filename: spec for spec in ADS_V25_DATASET_SPECS}


def specs_for_schema_version(schema_version: str) -> tuple[AdsV23DatasetSpec, ...]:
    """Return the contract selected by the manifest schema version."""
    if schema_version.startswith("2.2"):
        return ADS_V25_DATASET_SPECS
    if schema_version.startswith(("2.0", "2.1")):
        return ADS_V23_DATASET_SPECS
    raise ValueError(f"unsupported ADS schema version: {schema_version}")
