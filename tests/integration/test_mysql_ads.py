from __future__ import annotations

import importlib.util
import os

import pytest

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.query.view_contract import assert_view_contracts
from ncs_backend.admin.mysql_acceptance import run_mysql_acceptance


MYSQL_URL = os.getenv("NCS_MYSQL_TEST_URL")
ADS_PACKAGE = os.getenv("NCS_ADS_V21_PACKAGE")
MYSQL_ADMIN_URL = os.getenv("NCS_MYSQL_ADMIN_URL")
MYSQL_READER_URL = os.getenv("NCS_MYSQL_READER_URL")
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


@pytest.mark.skipif(
    not all((MYSQL_URL, MYSQL_ADMIN_URL, MYSQL_READER_URL, ADS_PACKAGE)),
    reason="set ADS package and all three MySQL account URLs to run end-to-end acceptance",
)
def test_mysql_ads_end_to_end_acceptance():
    report = run_mysql_acceptance(
        ADS_PACKAGE,
        migrator_url=MYSQL_URL,
        admin_url=MYSQL_ADMIN_URL,
        reader_url=MYSQL_READER_URL,
    )

    assert report.first_import_count == 9
    assert report.repeated_import_count == 9
    assert report.required_view_count == 9
    assert report.smoke_request_count == 12
    assert report.rollback_probe_clean is True
