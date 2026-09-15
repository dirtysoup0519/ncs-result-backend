"""Prediction registry, run tracking and published result schema.

This module deliberately stores model metadata and prediction lineage only.  It
does not contain training code and does not execute model-package source files.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from typing import Any

from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT

PREDICTION_MIGRATION_TABLE = "ctl_prediction_schema_migration"
PREDICTION_MIGRATION_VERSION = 3
PREDICTION_TABLES = ("ctl_model_version", "ctl_prediction_run", "rpt_load_prediction")
PREDICTION_VIEW_NAMES = ("api_v1_load_prediction",)

PREDICTION_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS ctl_model_version (
        model_code VARCHAR(128) NOT NULL,
        model_version VARCHAR(128) NOT NULL,
        adapter_code VARCHAR(128) NOT NULL,
        framework VARCHAR(64) NOT NULL,
        weights_uri TEXT NOT NULL,
        weights_sha256 VARCHAR(64) NOT NULL,
        input_contract_json TEXT NOT NULL,
        output_contract_json TEXT NOT NULL,
        metrics_json TEXT,
        status VARCHAR(32) NOT NULL,
        registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        activated_at TIMESTAMP NULL,
        deactivated_at TIMESTAMP NULL,
        PRIMARY KEY (model_code, model_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_prediction_run (
        prediction_run_id VARCHAR(128) PRIMARY KEY,
        model_code VARCHAR(128) NOT NULL,
        model_version VARCHAR(128) NOT NULL,
        source_batch_id VARCHAR(128) NOT NULL,
        cutoff_time DATETIME NOT NULL,
        lookback INTEGER NOT NULL,
        horizon INTEGER NOT NULL,
        dataset_profile_json TEXT NOT NULL,
        status VARCHAR(32) NOT NULL,
        error_code VARCHAR(128),
        error_message TEXT,
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        published_at TIMESTAMP NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rpt_load_prediction (
        prediction_run_id VARCHAR(128) NOT NULL,
        series_type VARCHAR(32) NOT NULL,
        target_time DATETIME NOT NULL,
        order_count BIGINT NULL,
        charging_energy DECIMAL(24,8) NULL,
        lower_bound DECIMAL(24,8) NULL,
        upper_bound DECIMAL(24,8) NULL,
        prediction_date DATE NOT NULL,
        cutoff_hour INTEGER NOT NULL,
        forecast_start_at DATETIME NOT NULL,
        interval_available BOOLEAN NOT NULL DEFAULT 0,
        confidence_level DECIMAL(8,5) NULL,
        model_version VARCHAR(128) NOT NULL,
        source_batch_id VARCHAR(128) NOT NULL,
        generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        data_version VARCHAR(64) NOT NULL,
        staleness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
        PRIMARY KEY (prediction_run_id, series_type, target_time)
    )
    """,
)

PREDICTION_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_prediction_run_status ON ctl_prediction_run (status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_prediction_result_date ON rpt_load_prediction (prediction_date, cutoff_hour)",
)

PREDICTION_MYSQL_INDEX_SQL = (
    "CREATE INDEX idx_prediction_run_status ON ctl_prediction_run (status, created_at)",
    "CREATE INDEX idx_prediction_result_date ON rpt_load_prediction (prediction_date, cutoff_hour)",
)

PREDICTION_VIEW_SQL = """
CREATE VIEW api_v1_load_prediction AS
SELECT r.series_type, r.target_time, r.order_count, r.charging_energy,
       r.lower_bound, r.upper_bound, r.prediction_date, r.cutoff_hour,
       r.forecast_start_at, r.interval_available, r.confidence_level,
       r.model_version, r.prediction_run_id, r.generated_at,
       r.data_version, r.staleness
FROM rpt_load_prediction r
JOIN ctl_prediction_run pr ON pr.prediction_run_id = r.prediction_run_id
WHERE pr.status = 'PUBLISHED'
"""

PREDICTION_V1_STATEMENTS = (
    *PREDICTION_SCHEMA_SQL,
    *PREDICTION_MYSQL_INDEX_SQL,
    "DROP VIEW IF EXISTS api_v1_load_prediction",
    PREDICTION_VIEW_SQL,
)
PREDICTION_V2_STATEMENTS = (
    "ALTER TABLE rpt_load_prediction ADD COLUMN horizon INTEGER NOT NULL DEFAULT 24",
    "DROP VIEW IF EXISTS api_v1_load_prediction",
    """
    CREATE VIEW api_v1_load_prediction AS
    SELECT r.series_type, r.target_time, r.order_count, r.charging_energy,
           r.lower_bound, r.upper_bound, r.prediction_date, r.cutoff_hour,
           r.forecast_start_at, r.interval_available, r.confidence_level,
           r.model_version, r.prediction_run_id, r.generated_at,
           r.data_version, r.staleness, r.horizon
    FROM rpt_load_prediction r
    JOIN ctl_prediction_run pr ON pr.prediction_run_id = r.prediction_run_id
    WHERE pr.status = 'PUBLISHED'
    """,
)

# A prediction is only as current as the hourly batch it was computed from.  The
# importer supersedes the previous publication of a dataset but leaves the runs
# that consumed it untouched, so a stale run stays PUBLISHED forever and -- since
# the read path picks the newest business date -- it can outrank a fresh run for
# an earlier date.  Tie the view to the source publication so a forecast leaves
# the read contract at the same moment its input data does.  Depends on
# ctl_publication, which the ADS result schema owns.
PREDICTION_V3_STATEMENTS = (
    "DROP VIEW IF EXISTS api_v1_load_prediction",
    """
    CREATE VIEW api_v1_load_prediction AS
    SELECT r.series_type, r.target_time, r.order_count, r.charging_energy,
           r.lower_bound, r.upper_bound, r.prediction_date, r.cutoff_hour,
           r.forecast_start_at, r.interval_available, r.confidence_level,
           r.model_version, r.prediction_run_id, r.generated_at,
           r.data_version, r.staleness, r.horizon
    FROM rpt_load_prediction r
    JOIN ctl_prediction_run pr ON pr.prediction_run_id = r.prediction_run_id
    WHERE pr.status = 'PUBLISHED'
      AND EXISTS (
          SELECT 1 FROM ctl_publication lp
          WHERE lp.dataset_code = 'load_hourly'
            AND lp.batch_id = pr.source_batch_id
            AND lp.status = 'PUBLISHED'
      )
    """,
)


@dataclass(frozen=True, slots=True)
class PredictionSchemaResult:
    applied: bool
    tables: tuple[str, ...]
    views: tuple[str, ...]


class PredictionSchemaMigrationError(RuntimeError):
    pass


def initialize_prediction_schema(
    connection: Any,
    *,
    dialect: DatabaseDialect = SQLITE_DIALECT,
    schema_sql: Iterable[str] | None = None,
) -> PredictionSchemaResult:
    """Create prediction tables and the read-only API view idempotently."""
    if schema_sql is not None:
        migrations = ((PREDICTION_MIGRATION_VERSION, tuple(schema_sql)),)
    else:
        v1 = (*PREDICTION_SCHEMA_SQL, *(PREDICTION_MYSQL_INDEX_SQL if dialect.name == "mysql" else PREDICTION_INDEX_SQL), "DROP VIEW IF EXISTS api_v1_load_prediction", PREDICTION_VIEW_SQL)
        migrations = ((1, v1), (2, PREDICTION_V2_STATEMENTS), (3, PREDICTION_V3_STATEMENTS))
    cursor = dialect.cursor(connection)
    try:
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {PREDICTION_MIGRATION_TABLE} (version INTEGER PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        applied = False
        for version, statements in migrations:
            checksum = hashlib.sha256("\n".join(item.strip() for item in statements).encode("utf-8")).hexdigest()
            rows = cursor.execute(
                f"SELECT checksum FROM {PREDICTION_MIGRATION_TABLE} WHERE version = ?",
                (version,),
            ).fetchall()
            if rows:
                if str(rows[0][0]) != checksum:
                    raise PredictionSchemaMigrationError(f"prediction schema checksum mismatch at version {version}")
                continue
            for statement in statements:
                cursor.execute(statement)
            cursor.execute(
                f"INSERT INTO {PREDICTION_MIGRATION_TABLE} (version, checksum, applied_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (version, checksum),
            )
            applied = True
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return PredictionSchemaResult(applied, PREDICTION_TABLES, PREDICTION_VIEW_NAMES)
