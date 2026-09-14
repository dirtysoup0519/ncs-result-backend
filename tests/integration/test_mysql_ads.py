from __future__ import annotations

import importlib.util
import os

import pytest

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.query.view_contract import assert_view_contracts


MYSQL_URL = os.getenv("NCS_MYSQL_TEST_URL")
pytestmark = pytest.mark.skipif(
    not MYSQL_URL or importlib.util.find_spec("pymysql") is None,
    reason="set NCS_MYSQL_TEST_URL and install PyMySQL to run ADS-5 integration tests",
)


def test_mysql_ads_schema_and_view_contracts():
    dialect = database_dialect_from_url(MYSQL_URL)
    assert dialect.name == "mysql"
    factory = connection_factory_from_url(MYSQL_URL)
    connection = factory()
    try:
        MigrationRunner(dialect=dialect).apply(connection)
        initialize_ads_result_schema(connection, dialect=dialect)
    finally:
        connection.close()

    assert_view_contracts(factory)
