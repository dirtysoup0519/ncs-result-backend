"""Transactional importer for the ADS Spark v2.3 contract package."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageDescriptor, AdsV23PackageReader
from ncs_backend.admin.adapters.ads_v23_schema import specs_for_schema_version
from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT

ConnectionFactory = Callable[[], Any]
V23_DATASETS = (
    "dashboard_overview", "platform_distribution", "fee_energy_daily", "station_daily",
    "station_reference", "duration_distribution", "weekday_weekend_profile",
    "station_hour_daily", "process_daily", "load_hourly",
)
V25_DATASETS = tuple(spec.dataset_code for spec in specs_for_schema_version("2.2.0"))
PLATFORM_LABELS = {"android": "Android", "ios": "iOS", "web": "Web"}


class AdsV23ImportError(RuntimeError):
    """Raised when a v2.3 package cannot be safely published."""


class AdsV23Importer:
    DATASETS = V23_DATASETS

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        dialect: DatabaseDialect = SQLITE_DIALECT,
        reader: AdsV23PackageReader | None = None,
        clock: Callable[[], datetime] | None = None,
        initialize_schema: bool = True,
    ) -> None:
        self._connection_factory = connection_factory
        self._dialect = dialect
        self._reader = reader or AdsV23PackageReader()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize_schema = initialize_schema

    def import_package(self, package: AdsV23PackageDescriptor) -> tuple[str, ...]:
        datasets = V25_DATASETS if package.schema_version.startswith("2.2") else V23_DATASETS
        codes = {item.dataset_code for item in package.datasets}
        missing = sorted(set(datasets) - codes)
        if missing:
            raise AdsV23ImportError(f"required dataset is missing: {missing}")
        rows = {code: self._reader.read_rows(package, code) for code in datasets}
        self._check_consistency(rows)
        connection = self._connection_factory()
        if self._initialize_schema:
            MigrationRunner(dialect=self._dialect).apply(connection)
            initialize_ads_result_schema(connection, dialect=self._dialect)
        cursor = self._dialect.cursor(connection)
        now = self._clock()
        package_hash = _package_hash(package)
        published: list[str] = []
        try:
            self._assert_v23_schema(cursor, datasets)
            for code in datasets:
                descriptor = next(item for item in package.datasets if item.dataset_code == code)
                batch_id = _batch_id(package.source_batch_id, code)
                self._ensure_control(cursor, package, descriptor, batch_id, package_hash, now)
                self._supersede_other_publications(cursor, code, batch_id, now)
                if self._is_published(cursor, code, batch_id):
                    published.append(code)
                    continue
                self._insert_rows(cursor, code, batch_id, rows[code], package, now)
                cursor.execute(
                    "INSERT INTO ctl_quality_result (result_id, batch_id, rule_code, severity, passed, checked_row_count, failure_count, details_json, created_at) VALUES (?, ?, ?, 'INFO', 1, ?, 0, ?, ?)",
                    (f"quality-{batch_id}-contract", batch_id, "ADS_V23_CONTRACT", descriptor.row_count, json.dumps({"status": "passed"}), _timestamp(now)),
                )
                cursor.execute(
                    "INSERT INTO ctl_publication (publication_id, dataset_code, batch_id, schema_version, status, published_at) VALUES (?, ?, ?, ?, 'PUBLISHED', ?)",
                    (f"publication-{batch_id}", code, batch_id, package.schema_version, _timestamp(now)),
                )
                cursor.execute(
                    "UPDATE ctl_import_batch SET status = 'PUBLISHED', published_at = ?, updated_at = ? WHERE batch_id = ?",
                    (_timestamp(now), _timestamp(now), batch_id),
                )
                published.append(code)
            connection.commit()
            return tuple(published)
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def _assert_v23_schema(cursor, datasets=V23_DATASETS) -> None:
        required = ["rpt_station_daily", "rpt_station_reference", "rpt_station_hour_daily", "rpt_load_hourly"]
        if "station_top10_snapshot" in datasets:
            required.extend(("rpt_station_top10_snapshot", "rpt_station_hour_heatmap_profile", "rpt_revenue_monthly", "rpt_kpi_period_comparison", "rpt_weekday_hour_profile", "rpt_charge_type_distribution", "rpt_station_charge_type", "rpt_process_overview"))
        try:
            for table in required:
                cursor.execute(f"SELECT 1 FROM {table} LIMIT 0")
        except Exception as exc:
            raise AdsV23ImportError(
                "ADS v2.3 result schema is not initialized; run scripts/setup_mysql_ads.py --initialize with the migrator account"
            ) from exc

    @staticmethod
    def _check_consistency(rows: dict[str, tuple[dict[str, str], ...]]) -> None:
        total = _integer(rows["dashboard_overview"][0]["total_order_count"])
        platform = sum(_integer(row["order_count"]) for row in rows["platform_distribution"])
        daily = sum(_integer(row["order_count"]) for row in rows["fee_energy_daily"])
        station = sum(_integer(row["order_count"]) for row in rows["station_daily"])
        if any(value != total for value in (platform, daily, station)):
            raise AdsV23ImportError(f"cross-file order reconciliation failed: overview={total}, platform={platform}, daily={daily}, station={station}")
        for dataset, field in (("platform_distribution", "order_ratio"), ("duration_distribution", "order_ratio")):
            ratio = sum((Decimal(_decimal(row[field])) for row in rows[dataset]), Decimal("0"))
            if not Decimal("99.99") <= ratio <= Decimal("100.01"):
                raise AdsV23ImportError(f"{dataset}.{field} must sum to 100, got {ratio}")

    def _ensure_control(self, cursor, package, descriptor, batch_id, source_hash, now) -> None:
        cursor.execute("SELECT source_sha256 FROM ctl_import_batch WHERE batch_id = ?", (batch_id,))
        existing = cursor.fetchone()
        if existing:
            if str(existing[0]) != source_hash:
                raise AdsV23ImportError(f"batch already exists with different source hash: {batch_id}")
            return
        cursor.execute("SELECT dataset_code FROM ctl_dataset WHERE dataset_code = ?", (descriptor.dataset_code,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO ctl_dataset (dataset_code, display_name, owner, current_schema_version, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)",
                (descriptor.dataset_code, descriptor.dataset_code, "ads-v2.5" if package.schema_version.startswith("2.2") else "ads-v2.3", package.schema_version, _timestamp(now), _timestamp(now)),
            )
        cursor.execute(
            "INSERT INTO ctl_import_batch (batch_id, dataset_code, schema_version, source_batch_id, source_uri, source_sha256, data_date, row_count, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)",
            (batch_id, descriptor.dataset_code, package.schema_version, package.source_batch_id, f"ads-package://{package.source_batch_id}", source_hash, _source_date(descriptor.dataset_code, package, self._reader), descriptor.row_count, _timestamp(now), _timestamp(now)),
        )

    @staticmethod
    def _is_published(cursor, dataset_code: str, batch_id: str) -> bool:
        cursor.execute("SELECT 1 FROM ctl_publication WHERE dataset_code = ? AND batch_id = ? AND status = 'PUBLISHED'", (dataset_code, batch_id))
        return cursor.fetchone() is not None

    @staticmethod
    def _supersede_other_publications(cursor, dataset_code: str, batch_id: str, now: datetime) -> None:
        """Keep one visible publication per dataset during an atomic package switch."""
        cursor.execute(
            "UPDATE ctl_publication SET status = 'SUPERSEDED', retracted_at = ? "
            "WHERE dataset_code = ? AND status = 'PUBLISHED' AND batch_id <> ?",
            (_timestamp(now), dataset_code, batch_id),
        )

    def _insert_rows(self, cursor, code, batch_id, rows, package, now) -> None:
        version = package.metric_version
        stamp = _timestamp(now)
        if code == "dashboard_overview":
            row = rows[0]
            values = (
                ("total_order_count", "总订单数", row["total_order_count"], "count", 0),
                ("total_fees", "总费用", row["total_fees"], "CNY", 2),
                ("total_kwh", "总充电量", row["total_kwh"], "kWh", 2),
                ("total_user_count", "总用户数", row["total_user_count"], "count", 0),
                ("active_station_count", "活跃站点数", row["active_station_count"], "count", 0),
                ("total_station_count", "总站点数", row["station_count"], "count", 0),
            )
            cursor.executemany("INSERT INTO rpt_dashboard_overview (batch_id, metric_code, display_name, metric_value, unit, precision_value, data_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, key, label, _decimal(value), unit, precision, row["end_date"], version, stamp, stamp) for key, label, value, unit, precision in values])
        elif code == "platform_distribution":
            cursor.executemany("INSERT INTO rpt_platform_distribution (batch_id, platform_code, display_name, order_count, total_fees, order_ratio, data_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["platform_code"].upper(), PLATFORM_LABELS.get(row["platform_code"].lower(), row["platform_code"]), _integer(row["order_count"]), _decimal(row["total_fees"]), _ratio(row["order_ratio"]), row["end_date"], version, stamp, stamp) for row in rows])
        elif code == "fee_energy_daily":
            cursor.executemany("INSERT INTO rpt_fee_energy_trend (batch_id, granularity, period, period_start, order_count, total_fees, total_kwh, data_date, data_version, generated_at, loaded_at) VALUES (?, 'DAY', ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["data_date"], row["data_date"], _integer(row["order_count"]), _decimal(row["total_fees"]), _decimal(row["total_kwh"]), row["data_date"], version, stamp, stamp) for row in rows])
        elif code == "station_daily":
            cursor.executemany("INSERT INTO rpt_station_daily (batch_id, data_date, station_id, station_name, location_id, order_count, total_kwh, total_fees, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["data_date"], row["station_id"], row["station_name"], row["location_id"], _integer(row["order_count"]), _decimal(row["total_kwh"]), _decimal(row["total_fees"]), version, stamp, stamp) for row in rows])
        elif code == "station_reference":
            cursor.executemany("INSERT INTO rpt_station_reference (batch_id, station_id, location_id, facility_type, station_name, address, device_count, open_time, update_time, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["station_id"], row["location_id"], row["facility_type"], row["station_name"], row["address"], _integer(row["device_count"]), row["open_time"], row["update_time"], version, stamp, stamp) for row in rows])
        elif code == "duration_distribution":
            cursor.executemany("INSERT INTO rpt_duration_distribution (batch_id, bucket_code, label, lower_minutes, upper_minutes, order_count, ratio, data_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["bucket_code"], row["duration_bucket"], _lower_minutes(row["duration_bucket"]), _upper_minutes(row["duration_bucket"]), _integer(row["order_count"]), _ratio(row["order_ratio"]), row["end_date"], version, stamp, stamp) for row in rows])
        elif code == "weekday_weekend_profile":
            metrics = (("order_count", "订单量", "count", "order_count"), ("charging_energy", "充电量", "kWh", "total_kwh"), ("total_fees", "费用", "CNY", "total_fees"), ("user_count", "用户数", "count", "user_count"), ("average_charge_hours", "平均时长", "hour", "avg_charge_hours"))
            values = []
            for row in rows:
                day_type = {"workday": "WEEKDAY", "weekday": "WEEKDAY", "weekend": "WEEKEND"}.get(row["day_type"].lower())
                if day_type is None:
                    raise AdsV23ImportError(f"unsupported day type: {row['day_type']}")
                for order, (key, label, unit, field) in enumerate(metrics, 1):
                    values.append((batch_id, day_type, key, label, unit, order, _decimal(row[field]), row["start_date"], row["end_date"], version, stamp, stamp))
            cursor.executemany("INSERT INTO rpt_weekday_weekend (batch_id, day_type, metric_key, label, unit, metric_order, raw_value, start_date, end_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        elif code == "station_hour_daily":
            cursor.executemany("INSERT INTO rpt_station_hour_daily (batch_id, data_date, station_id, station_name, stat_hour, order_count, total_kwh, total_fees, is_observed, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)", [(batch_id, row["data_date"], row["station_id"], row["station_name"], _hour(row["stat_hour"]), _integer(row["order_count"]), _decimal(row["total_kwh"]), _decimal(row["total_fees"]), version, stamp, stamp) for row in rows])
        elif code == "process_daily":
            cursor.executemany("INSERT INTO rpt_process_summary (batch_id, data_date, scope_type, station_id, start_date, end_date, record_count, session_count, average_soc, average_current, average_voltage, average_max_temperature, data_version, generated_at, loaded_at) VALUES (?, ?, 'ALL_STATIONS', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["data_date"], row["data_date"], row["data_date"], _integer(row["record_count"]), _integer(row["session_count"]), _decimal(row["avg_soc"]), _decimal(row["avg_current"]), _decimal(row["avg_pack_voltage"]), _decimal(row["avg_max_temperature"]), version, stamp, stamp) for row in rows])
        elif code == "load_hourly":
            cursor.executemany("INSERT INTO rpt_load_hourly (batch_id, stat_time, total_kwh, order_count, is_observed, fill_method, time_quality, allocation_method, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(batch_id, row["stat_time"], _decimal(row["total_kwh"]), _integer(row["order_count"]), _boolean(row["is_observed"]), row["fill_method"], row["time_quality"], row["allocation_method"], version, stamp, stamp) for row in rows])
        elif code == "station_top10_snapshot":
            cursor.executemany("INSERT INTO rpt_station_top10_snapshot (batch_id,start_date,end_date,rank_order,station_id,station_name,location_id,order_count,total_kwh,total_fees,ranking_metric,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], _integer(r["rank_order"]), r["station_id"], r["station_name"], r["location_id"], _integer(r["order_count"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), r["ranking_metric"], version, stamp, stamp) for r in rows])
        elif code == "station_hour_heatmap_profile":
            cursor.executemany("INSERT INTO rpt_station_hour_heatmap_profile (batch_id,start_date,end_date,station_rank,station_id,station_name,stat_hour,order_count,total_kwh,total_fees,is_filled_zero,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], _integer(r["station_rank"]), r["station_id"], r["station_name"], _hour(r["stat_hour"]), _integer(r["order_count"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), _boolean(r["is_filled_zero"]), version, stamp, stamp) for r in rows])
        elif code == "revenue_monthly":
            cursor.executemany("INSERT INTO rpt_revenue_monthly (batch_id,stat_month,order_count,total_kwh,total_fees,user_count,active_station_count,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["stat_month"], _integer(r["order_count"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), _integer(r["user_count"]), _integer(r["active_station_count"]), version, stamp, stamp) for r in rows])
        elif code == "kpi_period_comparison":
            cursor.executemany("INSERT INTO rpt_kpi_period_comparison (batch_id,current_period,previous_period,metric_code,metric_name,unit,current_value,previous_value,change_pct,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["current_period"], r["previous_period"], r["metric_code"], r["metric_name"], r["unit"], _decimal(r["current_value"]), _decimal(r["previous_value"]), _decimal(r["change_pct"]), version, stamp, stamp) for r in rows])
        elif code == "weekday_hour_profile":
            cursor.executemany("INSERT INTO rpt_weekday_hour_profile (batch_id,start_date,end_date,day_type,stat_hour,order_count,total_kwh,total_fees,avg_charge_hours,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], r["day_type"], _hour(r["stat_hour"]), _integer(r["order_count"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), _decimal(r["avg_charge_hours"]), version, stamp, stamp) for r in rows])
        elif code == "charge_type_distribution":
            cursor.executemany("INSERT INTO rpt_charge_type_distribution (batch_id,start_date,end_date,facility_type,charge_type,order_count,order_ratio,total_kwh,total_fees,avg_charge_hours,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], r["facility_type"], r["charge_type"], _integer(r["order_count"]), _ratio(r["order_ratio"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), _decimal(r["avg_charge_hours"]), version, stamp, stamp) for r in rows])
        elif code == "station_charge_type":
            cursor.executemany("INSERT INTO rpt_station_charge_type (batch_id,start_date,end_date,station_id,station_name,facility_type,charge_type,order_count,total_kwh,total_fees,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], r["station_id"], r["station_name"], r["facility_type"], r["charge_type"], _integer(r["order_count"]), _decimal(r["total_kwh"]), _decimal(r["total_fees"]), version, stamp, stamp) for r in rows])
        elif code == "process_overview":
            cursor.executemany("INSERT INTO rpt_process_overview (batch_id,start_date,end_date,record_count,session_count,avg_soc,avg_temperature,avg_pack_voltage,avg_current,record_time_source,data_version,generated_at,loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [(batch_id, r["start_date"], r["end_date"], _integer(r["record_count"]), _integer(r["session_count"]), _decimal(r["avg_soc"]), _decimal(r["avg_temperature"]), _decimal(r["avg_pack_voltage"]), _decimal(r["avg_current"]), r["record_time_source"], version, stamp, stamp) for r in rows])


def _batch_id(source: str, code: str) -> str:
    return f"{source}-{code.replace('_', '-')}"


def _package_hash(package: AdsV23PackageDescriptor) -> str:
    return hashlib.sha256("".join(sorted(item.sha256 for item in package.datasets)).encode("ascii")).hexdigest()


def _source_date(code: str, package: AdsV23PackageDescriptor, reader: AdsV23PackageReader) -> str:
    rows = reader.read_rows(package, code)
    if code in {"dashboard_overview", "platform_distribution", "duration_distribution", "weekday_weekend_profile", "station_top10_snapshot", "station_hour_heatmap_profile", "weekday_hour_profile", "charge_type_distribution", "station_charge_type", "process_overview"}:
        return rows[0]["end_date"]
    if code == "revenue_monthly":
        month = max(row["stat_month"] for row in rows)
        return f"{month}-01" if len(month) == 7 else month
    if code == "kpi_period_comparison":
        period = max(row["current_period"] for row in rows)
        return f"{period}-01" if len(period) == 7 else period
    if code == "station_reference":
        return reader.read_rows(package, "dashboard_overview")[0]["end_date"]
    if code == "load_hourly":
        return rows[-1]["stat_time"][:10]
    return max(row.get("data_date", "") for row in rows)


def _integer(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AdsV23ImportError(f"invalid integer value: {value}") from exc


def _decimal(value: str) -> str:
    try:
        return format(Decimal(value), "f")
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AdsV23ImportError(f"invalid decimal value: {value}") from exc


def _ratio(value: str) -> str:
    decimal = Decimal(_decimal(value))
    if not Decimal("0") <= decimal <= Decimal("100"):
        raise AdsV23ImportError(f"ratio must be between 0 and 100: {value}")
    return format(decimal / Decimal("100"), "f")


def _hour(value: str) -> int:
    hour = _integer(value)
    if not 0 <= hour <= 23:
        raise AdsV23ImportError(f"hour must be between 0 and 23: {value}")
    return hour


def _boolean(value: str) -> int:
    if str(value).strip().lower() in {"1", "true", "yes"}:
        return 1
    if str(value).strip().lower() in {"0", "false", "no"}:
        return 0
    raise AdsV23ImportError(f"invalid boolean value: {value}")


def _lower_minutes(value: str) -> int:
    return {"0-1h": 0, "1-2h": 60, "2-3h": 120, "3h+": 180}.get(value, 0)


def _upper_minutes(value: str) -> int | None:
    return {"0-1h": 60, "1-2h": 120, "2-3h": 180}.get(value)


def _timestamp(value: datetime) -> str:
    # MySQL 5.7 DATETIME does not accept an ISO-8601 timezone suffix.
    # Persist UTC wall-clock time in the same format accepted by SQLite.
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
