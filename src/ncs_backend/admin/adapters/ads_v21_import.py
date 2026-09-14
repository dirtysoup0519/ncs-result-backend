"""A0 importer for the verified ADS v2.1 package.

This adapter publishes only the five A0 datasets whose semantics are stable
enough for the current Wave A contract. It keeps package-specific transforms
here and leaves the generic batch/publication state machine independent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageDescriptor, AdsV21PackageError, AdsV21PackageReader
from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT

ConnectionFactory = Callable[[], Any]
A0_DATASETS = (
    "dashboard_overview",
    "platform_distribution",
    "fee_energy_daily",
    "fee_energy_monthly",
    "station_ranking_snapshot",
    "charging_process_daily",
)
PLATFORM_LABELS = {"android": "Android", "ios": "iOS", "web": "Web"}


class AdsV21ImportError(RuntimeError):
    """Raised when the A0 package cannot be safely published."""


class AdsV21A0Importer:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        dialect: DatabaseDialect = SQLITE_DIALECT,
        reader: AdsV21PackageReader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._dialect = dialect
        self._reader = reader or AdsV21PackageReader()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def import_package(self, package: AdsV21PackageDescriptor) -> tuple[str, ...]:
        dataset_codes = {item.dataset_code for item in package.datasets}
        if not set(A0_DATASETS).issubset(dataset_codes):
            missing = sorted(set(A0_DATASETS) - dataset_codes)
            raise AdsV21ImportError(f"A0 dataset is missing: {missing}")
        rows_by_dataset = {code: self._reader.read_rows(package, code) for code in dataset_codes}
        self._check_package_consistency(package, rows_by_dataset)
        connection = self._connection_factory()
        published: list[str] = []
        MigrationRunner(dialect=self._dialect).apply(connection)
        initialize_ads_result_schema(connection, dialect=self._dialect)
        cursor = self._dialect.cursor(connection)
        try:
            now = self._clock()
            source_date = self._source_date(rows_by_dataset["fee_energy_daily"])
            source_hash = _package_hash(package)
            for dataset_code in A0_DATASETS:
                descriptor = next(item for item in package.datasets if item.dataset_code == dataset_code)
                batch_id = _batch_id(package.source_batch_id, dataset_code)
                self._ensure_control_records(cursor, package.source_batch_id, dataset_code, descriptor, batch_id, source_date, source_hash, now)
                if self._is_published(cursor, dataset_code, batch_id):
                    published.append(dataset_code)
                    continue
                self._insert_result_rows(cursor, dataset_code, batch_id, rows_by_dataset[dataset_code], source_date, now)
                self._record_quality(cursor, batch_id, descriptor.row_count, now)
                cursor.execute(
                    "INSERT INTO ctl_publication (publication_id, dataset_code, batch_id, schema_version, status, published_at) VALUES (?, ?, ?, ?, 'PUBLISHED', ?)",
                    (f"publication-{batch_id}", dataset_code, batch_id, "v2.1", _timestamp(now)),
                )
                cursor.execute(
                    "UPDATE ctl_import_batch SET status = 'PUBLISHED', published_at = ?, updated_at = ? WHERE batch_id = ?",
                    (_timestamp(now), _timestamp(now), batch_id),
                )
                published.append(dataset_code)
            connection.commit()
            return tuple(published)
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def _check_package_consistency(self, package: AdsV21PackageDescriptor, rows_by_dataset: dict[str, tuple[dict[str, str], ...]]) -> None:
        total = _integer(rows_by_dataset["dashboard_overview"][0].get("total_order_cnt"))
        if total != package.total_orders:
            raise AdsV21ImportError(f"kpi total orders {total} does not match package total {package.total_orders}")
        monthly = sum(_integer(row["order_cnt"]) for row in rows_by_dataset["fee_energy_monthly"])
        daily = sum(_integer(row["order_cnt"]) for row in rows_by_dataset["order_daily"])
        platform = sum(_integer(row["order_cnt"]) for row in rows_by_dataset["platform_distribution"])
        if any(value != total for value in (monthly, daily, platform)):
            raise AdsV21ImportError(f"cross-file order reconciliation failed: kpi={total}, monthly={monthly}, daily={daily}, platform={platform}")
        ratio_total = sum(_decimal_value(row["fee_ratio"]) for row in rows_by_dataset["platform_distribution"])
        duration_total = sum(_decimal_value(row["order_ratio"]) for row in rows_by_dataset["charging_duration_distribution"])
        if not Decimal("99.99") <= ratio_total <= Decimal("100.01"):
            raise AdsV21ImportError(f"platform fee ratio must sum to 100, got {ratio_total}")
        if not Decimal("99.99") <= duration_total <= Decimal("100.01"):
            raise AdsV21ImportError(f"duration ratio must sum to 100, got {duration_total}")

    def _ensure_control_records(self, cursor, source_batch_id, dataset_code, descriptor, batch_id, source_date, source_hash, now) -> None:
        cursor.execute("SELECT source_sha256 FROM ctl_import_batch WHERE batch_id = ?", (batch_id,))
        existing = cursor.fetchone()
        if existing:
            if str(existing[0]) != source_hash:
                raise AdsV21ImportError(f"batch already exists with different source hash: {batch_id}")
            return
        cursor.execute(
            "SELECT dataset_code FROM ctl_dataset WHERE dataset_code = ?",
            (dataset_code,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO ctl_dataset (dataset_code, display_name, owner, current_schema_version, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)",
                (dataset_code, dataset_code, "ads-v2.1", "v2.1", _timestamp(now), _timestamp(now)),
            )
        cursor.execute(
            "INSERT INTO ctl_import_batch (batch_id, dataset_code, schema_version, source_batch_id, source_uri, source_sha256, data_date, row_count, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)",
            (batch_id, dataset_code, "v2.1", source_batch_id, f"ads-package://{source_batch_id}", source_hash, source_date, descriptor.row_count, _timestamp(now), _timestamp(now)),
        )

    def _is_published(self, cursor, dataset_code: str, batch_id: str) -> bool:
        cursor.execute("SELECT 1 FROM ctl_publication WHERE dataset_code = ? AND batch_id = ? AND status = 'PUBLISHED'", (dataset_code, batch_id))
        return cursor.fetchone() is not None

    def _record_quality(self, cursor, batch_id: str, row_count: int, now: datetime) -> None:
        cursor.execute(
            "INSERT INTO ctl_quality_result (result_id, batch_id, rule_code, severity, passed, checked_row_count, failure_count, details_json, created_at) VALUES (?, ?, ?, 'INFO', 1, ?, 0, ?, ?)",
            (f"quality-{batch_id}-package", batch_id, "ADS_PACKAGE_RECONCILIATION", row_count, json.dumps({"status": "passed"}), _timestamp(now)),
        )

    def _insert_result_rows(self, cursor, dataset_code: str, batch_id: str, rows: tuple[dict[str, str], ...], source_date: date, now: datetime) -> None:
        version = "v2.1"
        timestamp = _timestamp(now)
        if dataset_code == "dashboard_overview":
            source = rows[0]
            metrics = (
                ("total_order_count", "总订单数", source["total_order_cnt"], "count", 0),
                ("total_fees", "总费用", source["total_fees"], "CNY", 2),
                ("total_kwh", "总充电量", source["total_kwh"], "kWh", 2),
                ("total_user_count", "总用户数", source["total_user_cnt"], "count", 0),
                ("total_station_count", "总站点数", source["total_station_cnt"], "count", 0),
                ("average_fee_per_order", "订单平均费用", source["avg_fee_per_order"], "CNY", 2),
                ("average_kwh_per_order", "订单平均电量", source["avg_kwh_per_order"], "kWh", 2),
            )
            cursor.executemany(
                "INSERT INTO rpt_dashboard_overview (batch_id, metric_code, display_name, metric_value, unit, precision_value, data_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(batch_id, code, label, _decimal(value), unit, precision, source_date.isoformat(), version, timestamp, timestamp) for code, label, value, unit, precision in metrics],
            )
        elif dataset_code == "platform_distribution":
            total = sum(_integer(row["order_cnt"]) for row in rows)
            cursor.executemany(
                "INSERT INTO rpt_platform_distribution (batch_id, platform_code, display_name, order_count, total_fees, order_ratio, data_date, data_version, generated_at, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(batch_id, row["platform"].upper(), PLATFORM_LABELS.get(row["platform"].lower(), "Unknown"), _integer(row["order_cnt"]), _decimal(row["total_fees"]), format(_decimal_value(row["order_cnt"]) / Decimal(total), "f"), source_date.isoformat(), version, timestamp, timestamp) for row in rows],
            )
        elif dataset_code == "fee_energy_daily":
            cursor.executemany(
                "INSERT INTO rpt_fee_energy_trend (batch_id, granularity, period, period_start, order_count, total_fees, total_kwh, data_date, data_version, generated_at, region_id, station_id, loaded_at) VALUES (?, 'DAY', ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
                [(batch_id, row["stat_date"], row["stat_date"], _integer(row["order_cnt"]), _decimal(row["total_fees"]), _decimal(row["total_kwh"]), row["stat_date"], version, timestamp, timestamp) for row in rows],
            )
        elif dataset_code == "fee_energy_monthly":
            cursor.executemany(
                "INSERT INTO rpt_fee_energy_trend (batch_id, granularity, period, period_start, order_count, total_fees, total_kwh, data_date, data_version, generated_at, region_id, station_id, loaded_at) VALUES (?, 'MONTH', ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
                [(batch_id, row["stat_month"], f"{row['stat_month']}-01", _integer(row["order_cnt"]), _decimal(row["total_fees"]), _decimal(row["total_kwh"]), source_date.isoformat(), version, timestamp, timestamp) for row in rows],
            )
        elif dataset_code == "station_ranking_snapshot":
            cursor.executemany(
                "INSERT INTO rpt_station_ranking (batch_id, station_id, station_name, order_count, total_fees, total_kwh, data_date, data_version, generated_at, staleness, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', ?)",
                [(batch_id, row["station_id"], row["station_name"], _integer(row["order_cnt"]), _decimal(row["total_fees"]), _decimal(row["total_kwh"]), source_date.isoformat(), version, timestamp, timestamp) for row in rows],
            )
        elif dataset_code == "charging_process_daily":
            cursor.executemany(
                "INSERT INTO rpt_process_summary (batch_id, data_date, scope_type, station_id, start_date, end_date, record_count, session_count, average_soc, average_current, average_voltage, average_max_temperature, data_version, generated_at, loaded_at) VALUES (?, ?, 'ALL_STATIONS', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(batch_id, row["stat_date"], row["stat_date"], row["stat_date"], _integer(row["record_cnt"]), _integer(row["session_cnt"]), _decimal(row["avg_soc"]), _decimal(row["avg_current"]), _decimal(row["avg_pack_voltage"]), _decimal(row["avg_max_temp"]), version, timestamp, timestamp) for row in rows],
            )
        else:
            raise AdsV21ImportError(f"unsupported A0 dataset: {dataset_code}")

    @staticmethod
    def _source_date(rows: tuple[dict[str, str], ...]) -> date:
        try:
            return max(date.fromisoformat(row["stat_date"]) for row in rows)
        except (KeyError, ValueError) as exc:
            raise AdsV21ImportError("fee_energy_daily contains invalid stat_date") from exc


def _batch_id(source_batch_id: str, dataset_code: str) -> str:
    return f"{source_batch_id}-{dataset_code.replace('_', '-') }"


def _package_hash(package: AdsV21PackageDescriptor) -> str:
    value = "".join(sorted(item.sha256 for item in package.datasets)).encode("ascii")
    return hashlib.sha256(value).hexdigest()


def _integer(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AdsV21ImportError(f"invalid integer value: {value}") from exc


def _decimal(value: str) -> str:
    return format(_decimal_value(value), "f")


def _decimal_value(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AdsV21ImportError(f"invalid decimal value: {value}") from exc


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
