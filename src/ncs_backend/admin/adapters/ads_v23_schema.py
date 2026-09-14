"""Schema metadata for the ADS Spark v2.3 contract package."""

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
