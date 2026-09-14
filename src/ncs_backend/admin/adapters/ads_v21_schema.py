"""Schema metadata for the ADS v2.1 tab-separated export package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdsV21Field:
    name: str
    type: str


@dataclass(frozen=True, slots=True)
class AdsV21FileSpec:
    filename: str
    dataset_code: str
    fields: tuple[AdsV21Field, ...]
    unique_key: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def field_count(self) -> int:
        return len(self.fields)


def _fields(*items: tuple[str, str]) -> tuple[AdsV21Field, ...]:
    return tuple(AdsV21Field(name, type_) for name, type_ in items)


ADS_V21_FILE_SPECS: tuple[AdsV21FileSpec, ...] = (
    AdsV21FileSpec(
        "kpi_total.csv",
        "dashboard_overview",
        _fields(
            ("total_order_cnt", "integer"), ("total_fees", "decimal"), ("total_kwh", "decimal"),
            ("total_user_cnt", "integer"), ("total_station_cnt", "integer"),
            ("avg_fee_per_order", "decimal"), ("avg_kwh_per_order", "decimal"),
        ),
        (),
    ),
    AdsV21FileSpec(
        "revenue_trend.csv", "fee_energy_daily",
        _fields(("stat_date", "date"), ("order_cnt", "integer"), ("total_fees", "decimal"), ("total_kwh", "decimal")),
        ("stat_date",),
    ),
    AdsV21FileSpec(
        "revenue_monthly.csv", "fee_energy_monthly",
        _fields(("stat_month", "string"), ("order_cnt", "integer"), ("total_fees", "decimal"), ("total_kwh", "decimal")),
        ("stat_month",),
    ),
    AdsV21FileSpec(
        "station_top10.csv", "station_ranking_snapshot",
        _fields(("station_id", "string"), ("station_name", "string"), ("location_id", "string"), ("order_cnt", "integer"), ("total_fees", "decimal"), ("total_kwh", "decimal")),
        ("station_id",),
    ),
    AdsV21FileSpec(
        "platform_stat.csv", "platform_distribution",
        _fields(("platform", "string"), ("order_cnt", "integer"), ("total_fees", "decimal"), ("fee_ratio", "decimal")),
        ("platform",),
    ),
    AdsV21FileSpec(
        "hourly_stat.csv", "hourly_distribution_snapshot",
        _fields(("stat_hour", "integer"), ("order_cnt", "integer"), ("total_kwh", "decimal"), ("total_fees", "decimal")),
        ("stat_hour",),
        ("MISSING_HOUR:2",),
    ),
    AdsV21FileSpec(
        "order_daily.csv", "order_daily",
        _fields(("stat_date", "date"), ("order_cnt", "integer"), ("total_kwh", "decimal"), ("total_fees", "decimal"), ("total_charge_hours", "decimal"), ("user_cnt", "integer")),
        ("stat_date",),
    ),
    AdsV21FileSpec(
        "process_daily.csv", "charging_process_daily",
        _fields(("stat_date", "date"), ("record_cnt", "integer"), ("session_cnt", "integer"), ("avg_soc", "decimal"), ("max_soc", "decimal"), ("min_soc", "decimal"), ("avg_current", "decimal"), ("avg_pack_voltage", "decimal"), ("avg_max_temp", "decimal")),
        ("stat_date",),
    ),
    AdsV21FileSpec(
        "station_hour_heatmap.csv", "station_hour_heatmap_snapshot",
        _fields(("station_id", "string"), ("station_name", "string"), ("stat_hour", "integer"), ("order_cnt", "integer"), ("total_kwh", "decimal"), ("total_fees", "decimal")),
        ("station_id", "stat_hour"),
        ("NO_DATA_DATE:ALL_HISTORY_SNAPSHOT",),
    ),
    AdsV21FileSpec(
        "duration_distribution.csv", "charging_duration_distribution",
        _fields(("bucket_order", "integer"), ("duration_bucket", "string"), ("order_cnt", "integer"), ("order_ratio", "decimal")),
        ("bucket_order",),
    ),
    AdsV21FileSpec(
        "workday_weekend.csv", "weekday_weekend_profile",
        _fields(("day_type", "string"), ("order_cnt", "integer"), ("total_kwh", "decimal"), ("total_fees", "decimal"), ("avg_charge_hours", "decimal"), ("user_cnt", "integer")),
        ("day_type",),
    ),
    AdsV21FileSpec(
        "monthly_comparison.csv", "monthly_comparison",
        _fields(("stat_month", "string"), ("order_cnt", "integer"), ("total_kwh", "decimal"), ("total_fees", "decimal"), ("user_cnt", "integer"), ("station_cnt", "integer"), ("order_mom_pct", "decimal"), ("kwh_mom_pct", "decimal"), ("fees_mom_pct", "decimal"), ("user_mom_pct", "decimal"), ("station_mom_pct", "decimal")),
        ("stat_month",),
        ("API_V1_DISABLED:COMPARISON",),
    ),
)

FILE_SPECS_BY_NAME = {spec.filename: spec for spec in ADS_V21_FILE_SPECS}
