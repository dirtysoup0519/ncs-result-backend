"""Versioned A0 result tables and published read-only views for ADS data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from typing import Any

from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT

ADS_MIGRATION_TABLE = "ctl_ads_schema_migration"
ADS_RESULT_TABLES = (
    "rpt_dashboard_overview",
    "rpt_platform_distribution",
    "rpt_fee_energy_trend",
    "rpt_station_ranking",
    "rpt_process_summary",
)
ADS_VIEW_NAMES = (
    "api_v1_data_status",
    "api_v1_dashboard_overview",
    "api_v1_platform_distribution",
    "api_v1_fee_energy_trend",
    "api_v1_station_ranking",
    "api_v1_process_summary",
)

ADS_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS rpt_dashboard_overview (
        batch_id VARCHAR(128) NOT NULL,
        metric_code VARCHAR(128) NOT NULL,
        display_name VARCHAR(255) NOT NULL,
        metric_value DECIMAL(24, 8) NOT NULL,
        unit VARCHAR(32) NOT NULL,
        precision_value INTEGER NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, metric_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_platform_distribution (
        batch_id VARCHAR(128) NOT NULL,
        platform_code VARCHAR(32) NOT NULL,
        display_name VARCHAR(255) NOT NULL,
        order_count BIGINT NOT NULL,
        total_fees DECIMAL(24, 8) NOT NULL,
        order_ratio DECIMAL(24, 8) NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, platform_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_fee_energy_trend (
        batch_id VARCHAR(128) NOT NULL,
        granularity VARCHAR(16) NOT NULL,
        period VARCHAR(32) NOT NULL,
        period_start DATE NOT NULL,
        order_count BIGINT NOT NULL,
        total_fees DECIMAL(24, 8) NOT NULL,
        total_kwh DECIMAL(24, 8) NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        station_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, granularity, period_start)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_ranking (
        batch_id VARCHAR(128) NOT NULL,
        station_id VARCHAR(64) NOT NULL,
        station_name VARCHAR(255) NOT NULL,
        order_count BIGINT NOT NULL,
        total_fees DECIMAL(24, 8) NOT NULL,
        total_kwh DECIMAL(24, 8) NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, station_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_process_summary (
        batch_id VARCHAR(128) NOT NULL,
        data_date DATE NOT NULL,
        scope_type VARCHAR(32) NOT NULL,
        station_id VARCHAR(64),
        start_date DATE,
        end_date DATE,
        record_count BIGINT NOT NULL,
        session_count BIGINT NOT NULL,
        average_soc DECIMAL(24, 8),
        average_current DECIMAL(24, 8),
        average_voltage DECIMAL(24, 8),
        average_max_temperature DECIMAL(24, 8),
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, data_date, scope_type, station_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rpt_overview_batch ON rpt_dashboard_overview (batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_platform_batch ON rpt_platform_distribution (batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_trend_batch_period ON rpt_fee_energy_trend (batch_id, period_start)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_ranking_batch_fees ON rpt_station_ranking (batch_id, total_fees)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_process_batch_date ON rpt_process_summary (batch_id, data_date)",
)

ADS_VIEW_SQL = (
    """
    CREATE VIEW IF NOT EXISTS api_v1_data_status AS
    SELECT b.dataset_code, b.data_date, b.row_count AS source_record_count,
           CAST(NULL AS INTEGER) AS station_count, b.updated_at,
           CASE WHEN EXISTS (
               SELECT 1 FROM ctl_quality_result q
               WHERE q.batch_id = b.batch_id AND q.passed = 0
                 AND q.severity IN ('BLOCKER', 'ERROR')
           ) THEN 'ERROR' ELSE 'READY' END AS quality_status,
           'UNKNOWN' AS staleness, b.schema_version AS data_version
    FROM ctl_import_batch b
    JOIN ctl_publication p ON p.dataset_code = b.dataset_code
      AND p.batch_id = b.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_dashboard_overview AS
    SELECT r.metric_code, r.display_name, r.metric_value, r.unit,
           r.precision_value AS precision, r.data_date, r.data_version,
           r.generated_at, r.staleness
    FROM rpt_dashboard_overview r
    JOIN ctl_publication p ON p.dataset_code = 'dashboard_overview'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_platform_distribution AS
    SELECT r.platform_code, r.display_name, r.order_count, r.total_fees,
           r.order_ratio, r.data_date, r.data_version, r.generated_at, r.staleness
    FROM rpt_platform_distribution r
    JOIN ctl_publication p ON p.dataset_code = 'platform_distribution'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_fee_energy_trend AS
    SELECT r.granularity, r.period, r.order_count, r.total_fees, r.total_kwh,
           r.period_start, r.data_date, r.data_version, r.generated_at,
           r.staleness, r.region_id, r.station_id
    FROM rpt_fee_energy_trend r
    JOIN ctl_publication p ON p.dataset_code = 'fee_energy_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_station_ranking AS
    SELECT r.station_id, r.station_name, r.order_count, r.total_fees,
           r.total_kwh, r.data_date, r.data_version, r.generated_at,
           r.staleness, r.region_id
    FROM rpt_station_ranking r
    JOIN ctl_publication p ON p.dataset_code = 'station_ranking_snapshot'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_process_summary AS
    SELECT r.scope_type, r.station_id, r.start_date, r.end_date,
           r.record_count, r.session_count, r.average_soc, r.average_current,
           r.average_voltage, r.average_max_temperature, r.data_date,
           r.data_version, r.generated_at, r.staleness
    FROM rpt_process_summary r
    JOIN ctl_publication p ON p.dataset_code = 'charging_process_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
)


@dataclass(frozen=True, slots=True)
class AdsSchemaResult:
    applied: bool
    tables: tuple[str, ...]
    views: tuple[str, ...]


class AdsSchemaMigrationError(RuntimeError):
    pass


def initialize_ads_result_schema(
    connection: Any,
    *,
    dialect: DatabaseDialect = SQLITE_DIALECT,
    schema_sql: Iterable[str] = (*ADS_SCHEMA_SQL, *ADS_VIEW_SQL),
) -> AdsSchemaResult:
    """Create A0 tables/views atomically and record a checksummed schema version."""

    statements = tuple(schema_sql)
    checksum = hashlib.sha256("\n".join(item.strip() for item in statements).encode("utf-8")).hexdigest()
    cursor = dialect.cursor(connection)
    try:
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {ADS_MIGRATION_TABLE} (version INTEGER PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL)"
        )
        rows = cursor.execute(f"SELECT checksum FROM {ADS_MIGRATION_TABLE} WHERE version = ?", (1,)).fetchall()
        if rows and str(rows[0][0]) != checksum:
            raise AdsSchemaMigrationError("ADS schema checksum mismatch")
        if not rows:
            for statement in statements:
                cursor.execute(statement)
            cursor.execute(
                f"INSERT INTO {ADS_MIGRATION_TABLE} (version, checksum, applied_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (1, checksum),
            )
            applied = True
        else:
            applied = False
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return AdsSchemaResult(applied, ADS_RESULT_TABLES, ADS_VIEW_NAMES)
