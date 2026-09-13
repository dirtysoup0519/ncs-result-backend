"""Idempotent control-plane schema for the data administration service."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CONTROL_TABLES = (
    "ctl_dataset",
    "ctl_schema_version",
    "ctl_import_batch",
    "ctl_quality_result",
    "ctl_publication",
    "ctl_audit_log",
    "ml_model_version",
    "ml_prediction_run",
)

STAGING_TABLES = ("stg_import_row",)

CONTROL_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS ctl_dataset (
        dataset_code VARCHAR(128) PRIMARY KEY,
        display_name VARCHAR(255) NOT NULL,
        owner VARCHAR(128) NOT NULL,
        current_schema_version VARCHAR(32),
        status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_schema_version (
        dataset_code VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        schema_json TEXT NOT NULL,
        schema_checksum VARCHAR(64) NOT NULL,
        compatibility VARCHAR(32) NOT NULL DEFAULT 'BACKWARD',
        created_at TIMESTAMP NOT NULL,
        PRIMARY KEY (dataset_code, schema_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_import_batch (
        batch_id VARCHAR(128) PRIMARY KEY,
        dataset_code VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        source_batch_id VARCHAR(128) NOT NULL,
        source_uri TEXT NOT NULL,
        source_sha256 VARCHAR(64) NOT NULL,
        data_date DATE NOT NULL,
        row_count BIGINT NOT NULL DEFAULT 0,
        status VARCHAR(32) NOT NULL,
        error_summary TEXT,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        published_at TIMESTAMP,
        UNIQUE (dataset_code, source_batch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_quality_result (
        result_id VARCHAR(128) PRIMARY KEY,
        batch_id VARCHAR(128) NOT NULL,
        rule_code VARCHAR(128) NOT NULL,
        severity VARCHAR(32) NOT NULL,
        passed BOOLEAN NOT NULL,
        checked_row_count BIGINT NOT NULL DEFAULT 0,
        failure_count BIGINT NOT NULL DEFAULT 0,
        details_json TEXT,
        created_at TIMESTAMP NOT NULL,
        UNIQUE (batch_id, rule_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_publication (
        publication_id VARCHAR(128) PRIMARY KEY,
        dataset_code VARCHAR(128) NOT NULL,
        batch_id VARCHAR(128) NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL,
        supersedes_publication_id VARCHAR(128),
        published_at TIMESTAMP NOT NULL,
        retracted_at TIMESTAMP,
        UNIQUE (dataset_code, batch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ctl_audit_log (
        audit_id VARCHAR(128) PRIMARY KEY,
        action VARCHAR(128) NOT NULL,
        actor VARCHAR(255) NOT NULL,
        resource_type VARCHAR(128) NOT NULL,
        resource_id VARCHAR(128),
        request_id VARCHAR(128),
        details_json TEXT,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_model_version (
        model_version VARCHAR(128) PRIMARY KEY,
        model_code VARCHAR(128) NOT NULL,
        feature_version VARCHAR(128) NOT NULL,
        status VARCHAR(32) NOT NULL,
        metrics_json TEXT NOT NULL,
        artifact_uri TEXT NOT NULL,
        artifact_sha256 VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL,
        activated_at TIMESTAMP,
        retired_at TIMESTAMP,
        UNIQUE (model_code, model_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_prediction_run (
        prediction_run_id VARCHAR(128) PRIMARY KEY,
        model_code VARCHAR(128) NOT NULL,
        model_version VARCHAR(128) NOT NULL,
        dataset_code VARCHAR(128) NOT NULL,
        source_batch_id VARCHAR(128) NOT NULL,
        prediction_date DATE NOT NULL,
        horizon VARCHAR(16) NOT NULL,
        status VARCHAR(32) NOT NULL,
        output_uri TEXT,
        generated_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL,
        UNIQUE (model_version, prediction_date, horizon)
    )
    """,
)

STAGING_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS stg_import_row (
        batch_id VARCHAR(128) NOT NULL,
        row_number BIGINT NOT NULL,
        payload_json TEXT NOT NULL,
        row_sha256 VARCHAR(64) NOT NULL,
        loaded_at TIMESTAMP NOT NULL,
        PRIMARY KEY (batch_id, row_number)
    )
    """,
)


def initialize_control_schema(connection: Any, statements: Iterable[str] = CONTROL_SCHEMA_SQL) -> tuple[str, ...]:
    """Create control tables atomically and return their logical names."""

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return CONTROL_TABLES


def initialize_staging_schema(connection: Any, statements: Iterable[str] = STAGING_SCHEMA_SQL) -> tuple[str, ...]:
    """Create local staging tables atomically and return their logical names."""

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return STAGING_TABLES
