"""Versioned A0 result tables and published read-only views for ADS data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from typing import Any

from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT

ADS_MIGRATION_TABLE = "ctl_ads_schema_migration"
ADS_MIGRATION_VERSION = 13
ADS_RESULT_TABLES = (
    "rpt_dashboard_overview",
    "rpt_platform_distribution",
    "rpt_fee_energy_trend",
    "rpt_station_ranking",
    "rpt_process_summary",
    "rpt_duration_distribution",
    "rpt_weekday_weekend",
    "rpt_station_hour_heatmap",
    "rpt_station_daily",
    "rpt_station_reference",
    "rpt_station_hour_daily",
    "rpt_load_hourly",
    "rpt_station_top10_snapshot",
    "rpt_station_hour_heatmap_profile",
    "rpt_revenue_monthly",
    "rpt_kpi_period_comparison",
    "rpt_weekday_hour_profile",
    "rpt_charge_type_distribution",
    "rpt_station_charge_type",
    "rpt_process_overview",
)
ADS_VIEW_NAMES = (
    "api_v1_data_status",
    "api_v1_dashboard_overview",
    "api_v1_platform_distribution",
    "api_v1_fee_energy_trend",
    "api_v1_station_ranking",
    "api_v1_process_summary",
    "api_v1_duration_distribution",
    "api_v1_weekday_weekend",
    "api_v1_station_hour_heatmap",
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
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        station_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, station_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_process_summary (
        batch_id VARCHAR(128) NOT NULL,
        data_date DATE NOT NULL,
        scope_type VARCHAR(32) NOT NULL,
        station_id VARCHAR(64) NOT NULL DEFAULT '',
        start_date DATE,
        end_date DATE,
        record_count BIGINT NOT NULL,
        session_count BIGINT NOT NULL,
        average_soc DECIMAL(24, 8),
        average_current DECIMAL(24, 8),
        average_voltage DECIMAL(24, 8),
        average_max_temperature DECIMAL(24, 8),
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, data_date, scope_type, station_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_duration_distribution (
        batch_id VARCHAR(128) NOT NULL,
        bucket_code VARCHAR(64) NOT NULL,
        label VARCHAR(255) NOT NULL,
        lower_minutes INTEGER NOT NULL,
        upper_minutes INTEGER,
        order_count BIGINT NOT NULL,
        ratio DECIMAL(24, 8) NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        station_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, bucket_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_weekday_weekend (
        batch_id VARCHAR(128) NOT NULL,
        day_type VARCHAR(32) NOT NULL,
        metric_key VARCHAR(64) NOT NULL,
        label VARCHAR(255) NOT NULL,
        unit VARCHAR(32) NOT NULL,
        metric_order INTEGER NOT NULL,
        max_value DECIMAL(24, 8),
        raw_value DECIMAL(24, 8),
        normalized_value DECIMAL(24, 8),
        normalization_method VARCHAR(64),
        normalization_version VARCHAR(64),
        start_date DATE,
        end_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, day_type, metric_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_hour_heatmap (
        batch_id VARCHAR(128) NOT NULL,
        station_id VARCHAR(64) NOT NULL,
        station_name VARCHAR(255) NOT NULL,
        hour INTEGER NOT NULL,
        metric VARCHAR(32) NOT NULL,
        value DECIMAL(24, 8) NOT NULL,
        is_observed BOOLEAN NOT NULL,
        data_date DATE,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        region_id VARCHAR(64),
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, station_id, hour, metric)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_daily (
        batch_id VARCHAR(128) NOT NULL,
        data_date DATE NOT NULL,
        station_id VARCHAR(64) NOT NULL,
        station_name VARCHAR(255) NOT NULL,
        location_id VARCHAR(64),
        order_count BIGINT NOT NULL,
        total_kwh DECIMAL(24, 8) NOT NULL,
        total_fees DECIMAL(24, 8) NOT NULL,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, data_date, station_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_reference (
        batch_id VARCHAR(128) NOT NULL,
        station_id VARCHAR(64) NOT NULL,
        location_id VARCHAR(64),
        facility_type VARCHAR(64),
        station_name VARCHAR(255) NOT NULL,
        address VARCHAR(512),
        device_count BIGINT,
        open_time VARCHAR(64),
        update_time VARCHAR(64),
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, station_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_hour_daily (
        batch_id VARCHAR(128) NOT NULL,
        data_date DATE NOT NULL,
        station_id VARCHAR(64) NOT NULL,
        station_name VARCHAR(255) NOT NULL,
        stat_hour INTEGER NOT NULL,
        order_count BIGINT NOT NULL,
        total_kwh DECIMAL(24, 8) NOT NULL,
        total_fees DECIMAL(24, 8) NOT NULL,
        is_observed BOOLEAN NOT NULL DEFAULT 1,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, data_date, station_id, stat_hour)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_load_hourly (
        batch_id VARCHAR(128) NOT NULL,
        stat_time DATETIME NOT NULL,
        total_kwh DECIMAL(24, 8) NOT NULL,
        order_count BIGINT NOT NULL,
        is_observed BOOLEAN NOT NULL,
        fill_method VARCHAR(64) NOT NULL,
        time_quality VARCHAR(64) NOT NULL,
        allocation_method VARCHAR(64) NOT NULL,
        data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, stat_time)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_top10_snapshot (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL,
        rank_order INTEGER NOT NULL, station_id VARCHAR(64) NOT NULL, station_name VARCHAR(255) NOT NULL,
        location_id VARCHAR(64), order_count BIGINT NOT NULL, total_kwh DECIMAL(24,8) NOT NULL,
        total_fees DECIMAL(24,8) NOT NULL, ranking_metric VARCHAR(64) NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, start_date, end_date, rank_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_hour_heatmap_profile (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL,
        station_rank INTEGER NOT NULL, station_id VARCHAR(64) NOT NULL, station_name VARCHAR(255) NOT NULL,
        stat_hour INTEGER NOT NULL, order_count BIGINT NOT NULL, total_kwh DECIMAL(24,8) NOT NULL,
        total_fees DECIMAL(24,8) NOT NULL, is_filled_zero BOOLEAN NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, start_date, end_date, station_rank, stat_hour)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_revenue_monthly (
        batch_id VARCHAR(128) NOT NULL, stat_month VARCHAR(16) NOT NULL, order_count BIGINT NOT NULL,
        total_kwh DECIMAL(24,8) NOT NULL, total_fees DECIMAL(24,8) NOT NULL, user_count BIGINT NOT NULL,
        active_station_count BIGINT NOT NULL, data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (batch_id, stat_month)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_kpi_period_comparison (
        batch_id VARCHAR(128) NOT NULL, current_period VARCHAR(32) NOT NULL, previous_period VARCHAR(32) NOT NULL,
        metric_code VARCHAR(64) NOT NULL, metric_name VARCHAR(255) NOT NULL, unit VARCHAR(32) NOT NULL,
        current_value DECIMAL(24,8) NOT NULL, previous_value DECIMAL(24,8) NOT NULL, change_pct DECIMAL(24,8) NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, current_period, metric_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_weekday_hour_profile (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, day_type VARCHAR(32) NOT NULL,
        stat_hour INTEGER NOT NULL, order_count BIGINT NOT NULL, total_kwh DECIMAL(24,8) NOT NULL,
        total_fees DECIMAL(24,8) NOT NULL, avg_charge_hours DECIMAL(24,8) NOT NULL, data_version VARCHAR(64) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (batch_id, start_date, end_date, day_type, stat_hour)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_charge_type_distribution (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, facility_type VARCHAR(64) NOT NULL,
        charge_type VARCHAR(64) NOT NULL, order_count BIGINT NOT NULL, order_ratio DECIMAL(24,8) NOT NULL,
        total_kwh DECIMAL(24,8) NOT NULL, total_fees DECIMAL(24,8) NOT NULL, avg_charge_hours DECIMAL(24,8) NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, start_date, end_date, facility_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_station_charge_type (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, station_id VARCHAR(64) NOT NULL,
        station_name VARCHAR(255) NOT NULL, facility_type VARCHAR(64) NOT NULL, charge_type VARCHAR(64) NOT NULL,
        order_count BIGINT NOT NULL, total_kwh DECIMAL(24,8) NOT NULL, total_fees DECIMAL(24,8) NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, start_date, end_date, station_id, facility_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_process_overview (
        batch_id VARCHAR(128) NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, record_count BIGINT NOT NULL,
        session_count BIGINT NOT NULL, avg_soc DECIMAL(24,8), avg_temperature DECIMAL(24,8),
        avg_pack_voltage DECIMAL(24,8), avg_current DECIMAL(24,8), record_time_source VARCHAR(64) NOT NULL,
        data_version VARCHAR(64) NOT NULL, generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN', loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (batch_id, start_date, end_date)
    )
    """,
)

ADS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_rpt_overview_batch ON rpt_dashboard_overview (batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_platform_batch ON rpt_platform_distribution (batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_trend_batch_period ON rpt_fee_energy_trend (batch_id, period_start)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_ranking_batch_fees ON rpt_station_ranking (batch_id, total_fees)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_process_batch_date ON rpt_process_summary (batch_id, data_date)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_duration_batch ON rpt_duration_distribution (batch_id, lower_minutes)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_profile_batch ON rpt_weekday_weekend (batch_id, day_type, metric_order)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_heatmap_batch ON rpt_station_hour_heatmap (batch_id, station_id, hour, metric)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_station_daily_batch_date ON rpt_station_daily (batch_id, data_date, total_fees)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_station_reference_batch ON rpt_station_reference (batch_id, station_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_station_hour_daily_batch_date ON rpt_station_hour_daily (batch_id, data_date, station_id, stat_hour)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_load_hourly_batch_time ON rpt_load_hourly (batch_id, stat_time)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_station_top10_batch ON rpt_station_top10_snapshot (batch_id, rank_order)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_heatmap_profile_batch ON rpt_station_hour_heatmap_profile (batch_id, station_rank, stat_hour)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_revenue_monthly_batch ON rpt_revenue_monthly (batch_id, stat_month)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_kpi_comparison_batch ON rpt_kpi_period_comparison (batch_id, current_period)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_weekday_hour_batch ON rpt_weekday_hour_profile (batch_id, day_type, stat_hour)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_charge_type_batch ON rpt_charge_type_distribution (batch_id, facility_type)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_station_charge_type_batch ON rpt_station_charge_type (batch_id, station_id)",
    "CREATE INDEX IF NOT EXISTS idx_rpt_process_overview_batch ON rpt_process_overview (batch_id, end_date)",
)

ADS_MYSQL_INDEX_SQL = (
    "CREATE INDEX idx_rpt_overview_batch ON rpt_dashboard_overview (batch_id)",
    "CREATE INDEX idx_rpt_platform_batch ON rpt_platform_distribution (batch_id)",
    "CREATE INDEX idx_rpt_trend_batch_period ON rpt_fee_energy_trend (batch_id, period_start)",
    "CREATE INDEX idx_rpt_ranking_batch_fees ON rpt_station_ranking (batch_id, total_fees)",
    "CREATE INDEX idx_rpt_process_batch_date ON rpt_process_summary (batch_id, data_date)",
    "CREATE INDEX idx_rpt_duration_batch ON rpt_duration_distribution (batch_id, lower_minutes)",
    "CREATE INDEX idx_rpt_profile_batch ON rpt_weekday_weekend (batch_id, day_type, metric_order)",
    "CREATE INDEX idx_rpt_heatmap_batch ON rpt_station_hour_heatmap (batch_id, station_id, hour, metric)",
    "CREATE INDEX idx_rpt_station_daily_batch_date ON rpt_station_daily (batch_id, data_date, total_fees)",
    "CREATE INDEX idx_rpt_station_reference_batch ON rpt_station_reference (batch_id, station_id)",
    "CREATE INDEX idx_rpt_station_hour_daily_batch_date ON rpt_station_hour_daily (batch_id, data_date, station_id, stat_hour)",
    "CREATE INDEX idx_rpt_load_hourly_batch_time ON rpt_load_hourly (batch_id, stat_time)",
    "CREATE INDEX idx_rpt_station_top10_batch ON rpt_station_top10_snapshot (batch_id, rank_order)",
    "CREATE INDEX idx_rpt_heatmap_profile_batch ON rpt_station_hour_heatmap_profile (batch_id, station_rank, stat_hour)",
    "CREATE INDEX idx_rpt_revenue_monthly_batch ON rpt_revenue_monthly (batch_id, stat_month)",
    "CREATE INDEX idx_rpt_kpi_comparison_batch ON rpt_kpi_period_comparison (batch_id, current_period)",
    "CREATE INDEX idx_rpt_weekday_hour_batch ON rpt_weekday_hour_profile (batch_id, day_type, stat_hour)",
    "CREATE INDEX idx_rpt_charge_type_batch ON rpt_charge_type_distribution (batch_id, facility_type)",
    "CREATE INDEX idx_rpt_station_charge_type_batch ON rpt_station_charge_type (batch_id, station_id)",
    "CREATE INDEX idx_rpt_process_overview_batch ON rpt_process_overview (batch_id, end_date)",
)

ADS_VIEW_SQL = (
    """
    CREATE VIEW IF NOT EXISTS api_v1_data_status AS
    SELECT b.dataset_code, b.data_date,
           CASE WHEN b.dataset_code = 'dashboard_overview' THEN CAST((
               SELECT r.metric_value
               FROM rpt_dashboard_overview r
               JOIN ctl_publication op ON op.dataset_code = 'dashboard_overview'
                 AND op.batch_id = r.batch_id AND op.status = 'PUBLISHED'
               WHERE r.metric_code = 'total_order_count'
               ORDER BY r.data_date DESC LIMIT 1
           ) AS INTEGER) ELSE b.row_count END AS source_record_count,
           CAST((SELECT r.metric_value
                 FROM rpt_dashboard_overview r
                 JOIN ctl_publication op ON op.dataset_code = 'dashboard_overview'
                   AND op.batch_id = r.batch_id AND op.status = 'PUBLISHED'
                 WHERE r.metric_code = 'total_station_count'
                 ORDER BY r.data_date DESC LIMIT 1) AS INTEGER) AS station_count,
           b.updated_at,
           CASE WHEN EXISTS (
               SELECT 1 FROM ctl_quality_result q
               WHERE q.batch_id = b.batch_id AND q.passed = 0
                 AND q.severity IN ('BLOCKER', 'ERROR')
           ) THEN 'FAILED' ELSE 'PASSED' END AS quality_status,
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
    JOIN ctl_publication p ON p.dataset_code IN ('fee_energy_daily', 'fee_energy_monthly')
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
    UNION ALL
    SELECT r.station_id, r.station_name, SUM(r.order_count) AS order_count,
           SUM(r.total_fees) AS total_fees, SUM(r.total_kwh) AS total_kwh,
           (SELECT MAX(r2.data_date) FROM rpt_station_daily r2 WHERE r2.batch_id = r.batch_id) AS data_date,
           r.data_version, MAX(r.generated_at) AS generated_at,
           r.staleness, r.location_id AS region_id
    FROM rpt_station_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    GROUP BY r.batch_id, r.station_id, r.station_name, r.data_version, r.staleness, r.location_id
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_process_summary AS
    SELECT r.scope_type, NULLIF(r.station_id, '') AS station_id, r.start_date, r.end_date,
           r.record_count, r.session_count, r.average_soc, r.average_current,
           r.average_voltage, r.average_max_temperature, r.data_date,
           r.data_version, r.generated_at, r.staleness
    FROM rpt_process_summary r
    JOIN ctl_publication p ON p.dataset_code = 'charging_process_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    UNION ALL
    SELECT r.scope_type, NULLIF(r.station_id, '') AS station_id,
           MIN(r.start_date) AS start_date, MAX(r.end_date) AS end_date,
           SUM(r.record_count) AS record_count, SUM(r.session_count) AS session_count,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_soc * r.record_count) / SUM(r.record_count) END AS average_soc,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_current * r.record_count) / SUM(r.record_count) END AS average_current,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_voltage * r.record_count) / SUM(r.record_count) END AS average_voltage,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_max_temperature * r.record_count) / SUM(r.record_count) END AS average_max_temperature,
           MAX(r.data_date) AS data_date, r.data_version, MAX(r.generated_at) AS generated_at, r.staleness
    FROM rpt_process_summary r
    JOIN ctl_publication p ON p.dataset_code = 'process_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    GROUP BY r.batch_id, r.scope_type, r.station_id, r.data_version, r.staleness
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_duration_distribution AS
    SELECT r.bucket_code, r.label, r.lower_minutes, r.upper_minutes,
           r.order_count, r.ratio, r.data_date, r.data_version,
           r.generated_at, r.staleness, r.region_id, r.station_id
    FROM rpt_duration_distribution r
    JOIN ctl_publication p ON p.dataset_code IN ('charging_duration_distribution', 'duration_distribution')
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_weekday_weekend AS
    SELECT r.day_type, r.metric_key, r.label, r.unit, r.metric_order,
           r.max_value, r.raw_value, r.normalized_value,
           r.normalization_method, r.normalization_version,
           r.start_date, r.end_date, r.data_version, r.generated_at,
           r.staleness, r.region_id
    FROM rpt_weekday_weekend r
    JOIN ctl_publication p ON p.dataset_code = 'weekday_weekend_profile'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW IF NOT EXISTS api_v1_station_hour_heatmap AS
    SELECT r.station_id, r.station_name, r.hour, r.value, r.is_observed,
           r.metric, CASE r.metric
               WHEN 'kwh' THEN 'charging_energy'
               WHEN 'orders' THEN 'order_count'
               WHEN 'fees' THEN 'total_fees'
               ELSE r.metric END AS metric_code,
           CASE r.metric
               WHEN 'kwh' THEN 'kWh'
               WHEN 'orders' THEN 'count'
               WHEN 'fees' THEN 'CNY'
               ELSE 'UNKNOWN' END AS unit,
           r.data_date, r.data_version, r.generated_at, r.staleness,
           r.region_id
    FROM rpt_station_hour_heatmap r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_heatmap_snapshot'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.total_kwh) AS value,
           MAX(r.is_observed), 'kwh' AS metric, 'charging_energy' AS metric_code, 'kWh' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.order_count) AS value,
           MAX(r.is_observed), 'orders' AS metric, 'order_count' AS metric_code, 'count' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.total_fees) AS value,
           MAX(r.is_observed), 'fees' AS metric, 'total_fees' AS metric_code, 'CNY' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    """,
)

ADS_MYSQL_VIEW_SQL = (
    """
    CREATE VIEW api_v1_data_status AS
    SELECT b.dataset_code, b.data_date,
           CASE WHEN b.dataset_code = 'dashboard_overview' THEN CAST((
               SELECT r.metric_value
               FROM rpt_dashboard_overview r
               JOIN ctl_publication op ON op.dataset_code = 'dashboard_overview'
                 AND op.batch_id = r.batch_id AND op.status = 'PUBLISHED'
               WHERE r.metric_code = 'total_order_count'
               ORDER BY r.data_date DESC LIMIT 1
           ) AS SIGNED) ELSE b.row_count END AS source_record_count,
           CAST((SELECT r.metric_value
                 FROM rpt_dashboard_overview r
                 JOIN ctl_publication op ON op.dataset_code = 'dashboard_overview'
                   AND op.batch_id = r.batch_id AND op.status = 'PUBLISHED'
                 WHERE r.metric_code = 'total_station_count'
                 ORDER BY r.data_date DESC LIMIT 1) AS SIGNED) AS station_count,
           b.updated_at,
           CASE WHEN EXISTS (
               SELECT 1 FROM ctl_quality_result q
               WHERE q.batch_id = b.batch_id AND q.passed = 0
                 AND q.severity IN ('BLOCKER', 'ERROR')
           ) THEN 'FAILED' ELSE 'PASSED' END AS quality_status,
           'UNKNOWN' AS staleness, b.schema_version AS data_version
    FROM ctl_import_batch b
    JOIN ctl_publication p ON p.dataset_code = b.dataset_code
      AND p.batch_id = b.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_dashboard_overview AS
    SELECT r.metric_code, r.display_name, r.metric_value, r.unit,
           r.precision_value AS `precision`, r.data_date, r.data_version,
           r.generated_at, r.staleness
    FROM rpt_dashboard_overview r
    JOIN ctl_publication p ON p.dataset_code = 'dashboard_overview'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_platform_distribution AS
    SELECT r.platform_code, r.display_name, r.order_count, r.total_fees,
           r.order_ratio, r.data_date, r.data_version, r.generated_at, r.staleness
    FROM rpt_platform_distribution r
    JOIN ctl_publication p ON p.dataset_code = 'platform_distribution'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_fee_energy_trend AS
    SELECT r.granularity, r.period, r.order_count, r.total_fees, r.total_kwh,
           r.period_start, r.data_date, r.data_version, r.generated_at,
           r.staleness, r.region_id, r.station_id
    FROM rpt_fee_energy_trend r
    JOIN ctl_publication p ON p.dataset_code IN ('fee_energy_daily', 'fee_energy_monthly')
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_station_ranking AS
    SELECT r.station_id, r.station_name, r.order_count, r.total_fees,
           r.total_kwh, r.data_date, r.data_version, r.generated_at,
           r.staleness, r.region_id
    FROM rpt_station_ranking r
    JOIN ctl_publication p ON p.dataset_code = 'station_ranking_snapshot'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    UNION ALL
    SELECT r.station_id, r.station_name, SUM(r.order_count) AS order_count,
           SUM(r.total_fees) AS total_fees, SUM(r.total_kwh) AS total_kwh,
           (SELECT MAX(r2.data_date) FROM rpt_station_daily r2 WHERE r2.batch_id = r.batch_id) AS data_date,
           r.data_version, MAX(r.generated_at) AS generated_at,
           r.staleness, r.location_id AS region_id
    FROM rpt_station_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    GROUP BY r.batch_id, r.station_id, r.station_name, r.data_version, r.staleness, r.location_id
    """,
    """
    CREATE VIEW api_v1_process_summary AS
    SELECT r.scope_type, NULLIF(r.station_id, '') AS station_id, r.start_date, r.end_date,
           r.record_count, r.session_count, r.average_soc, r.average_current,
           r.average_voltage, r.average_max_temperature, r.data_date,
           r.data_version, r.generated_at, r.staleness
    FROM rpt_process_summary r
    JOIN ctl_publication p ON p.dataset_code = 'charging_process_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    UNION ALL
    SELECT r.scope_type, NULLIF(r.station_id, '') AS station_id,
           MIN(r.start_date) AS start_date, MAX(r.end_date) AS end_date,
           SUM(r.record_count) AS record_count, SUM(r.session_count) AS session_count,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_soc * r.record_count) / SUM(r.record_count) END AS average_soc,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_current * r.record_count) / SUM(r.record_count) END AS average_current,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_voltage * r.record_count) / SUM(r.record_count) END AS average_voltage,
           CASE WHEN SUM(r.record_count) = 0 THEN NULL ELSE SUM(r.average_max_temperature * r.record_count) / SUM(r.record_count) END AS average_max_temperature,
           MAX(r.data_date) AS data_date, r.data_version, MAX(r.generated_at) AS generated_at, r.staleness
    FROM rpt_process_summary r
    JOIN ctl_publication p ON p.dataset_code = 'process_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    GROUP BY r.batch_id, r.scope_type, r.station_id, r.data_version, r.staleness
    """,
    """
    CREATE VIEW api_v1_duration_distribution AS
    SELECT r.bucket_code, r.label, r.lower_minutes, r.upper_minutes,
           r.order_count, r.ratio, r.data_date, r.data_version,
           r.generated_at, r.staleness, r.region_id, r.station_id
    FROM rpt_duration_distribution r
    JOIN ctl_publication p ON p.dataset_code IN ('charging_duration_distribution', 'duration_distribution')
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_weekday_weekend AS
    SELECT r.day_type, r.metric_key, r.label, r.unit, r.metric_order,
           r.max_value, r.raw_value, r.normalized_value,
           r.normalization_method, r.normalization_version,
           r.start_date, r.end_date, r.data_version, r.generated_at,
           r.staleness, r.region_id
    FROM rpt_weekday_weekend r
    JOIN ctl_publication p ON p.dataset_code = 'weekday_weekend_profile'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    """,
    """
    CREATE VIEW api_v1_station_hour_heatmap AS
    SELECT r.station_id, r.station_name, r.hour, r.value, r.is_observed,
           r.metric, CASE r.metric
               WHEN 'kwh' THEN 'charging_energy'
               WHEN 'orders' THEN 'order_count'
               WHEN 'fees' THEN 'total_fees'
               ELSE r.metric END AS metric_code,
           CASE r.metric
               WHEN 'kwh' THEN 'kWh'
               WHEN 'orders' THEN 'count'
               WHEN 'fees' THEN 'CNY'
               ELSE 'UNKNOWN' END AS unit,
           r.data_date, r.data_version, r.generated_at, r.staleness,
           r.region_id
    FROM rpt_station_hour_heatmap r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_heatmap_snapshot'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.total_kwh) AS value,
           MAX(r.is_observed), 'kwh' AS metric, 'charging_energy' AS metric_code, 'kWh' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.order_count) AS value,
           MAX(r.is_observed), 'orders' AS metric, 'order_count' AS metric_code, 'count' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    UNION ALL
    SELECT r.station_id, r.station_name, r.stat_hour AS hour, SUM(r.total_fees) AS value,
           MAX(r.is_observed), 'fees' AS metric, 'total_fees' AS metric_code, 'CNY' AS unit,
           latest.data_date,
           r.data_version, MAX(r.generated_at), r.staleness, NULL AS region_id
    FROM rpt_station_hour_daily r
    JOIN ctl_publication p ON p.dataset_code = 'station_hour_daily'
      AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'
    JOIN (SELECT batch_id, MAX(data_date) AS data_date FROM rpt_station_hour_daily GROUP BY batch_id) latest
      ON latest.batch_id = r.batch_id
    GROUP BY r.batch_id, r.station_id, r.station_name, r.stat_hour, latest.data_date, r.data_version, r.staleness
    """,
)

ADS_SCHEMA_STATEMENTS = (
    *ADS_SCHEMA_SQL,
    *ADS_INDEX_SQL,
    *(f"DROP VIEW IF EXISTS {view_name}" for view_name in ADS_VIEW_NAMES),
    *ADS_VIEW_SQL,
)

ADS_MYSQL_SCHEMA_STATEMENTS = (
    *ADS_SCHEMA_SQL,
    *ADS_MYSQL_INDEX_SQL,
    *(f"DROP VIEW IF EXISTS {view_name}" for view_name in ADS_VIEW_NAMES),
    *ADS_MYSQL_VIEW_SQL,
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
    schema_sql: Iterable[str] | None = None,
) -> AdsSchemaResult:
    """Create A0 tables/views atomically and record a checksummed schema version."""

    statements = tuple(schema_sql) if schema_sql is not None else (
        ADS_MYSQL_SCHEMA_STATEMENTS if dialect.name == "mysql" else ADS_SCHEMA_STATEMENTS
    )
    checksum = hashlib.sha256("\n".join(item.strip() for item in statements).encode("utf-8")).hexdigest()
    cursor = dialect.cursor(connection)
    try:
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {ADS_MIGRATION_TABLE} (version INTEGER PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        rows = cursor.execute(
            f"SELECT checksum FROM {ADS_MIGRATION_TABLE} WHERE version = ?",
            (ADS_MIGRATION_VERSION,),
        ).fetchall()
        if rows and str(rows[0][0]) != checksum:
            raise AdsSchemaMigrationError("ADS schema checksum mismatch")
        if not rows:
            for statement in statements:
                try:
                    cursor.execute(statement)
                except Exception as exc:
                    if not _is_mysql_duplicate_index(exc, statement, dialect):
                        raise
            cursor.execute(
                f"INSERT INTO {ADS_MIGRATION_TABLE} (version, checksum, applied_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (ADS_MIGRATION_VERSION, checksum),
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


def _is_mysql_duplicate_index(error: Exception, statement: str, dialect: DatabaseDialect) -> bool:
    """Allow a retry after MySQL committed an index before a later DDL error."""

    if dialect.name != "mysql" or not statement.lstrip().upper().startswith("CREATE INDEX"):
        return False
    args = getattr(error, "args", ())
    return bool(args) and args[0] == 1061
