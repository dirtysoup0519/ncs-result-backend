"""MySQL ADS schema initialization for the single-connection lab mode."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.admin.prediction_schema import initialize_prediction_schema
from ncs_backend.shared.db import MYSQL_DIALECT

ConnectionFactory = Callable[[], Any]


def initialize_mysql_ads(connection_factory: ConnectionFactory) -> bool:
    connection = connection_factory()
    try:
        MigrationRunner(dialect=MYSQL_DIALECT).apply(connection)
        result = initialize_ads_result_schema(connection, dialect=MYSQL_DIALECT)
        initialize_prediction_schema(connection, dialect=MYSQL_DIALECT)
        return result.applied
    finally:
        connection.close()
