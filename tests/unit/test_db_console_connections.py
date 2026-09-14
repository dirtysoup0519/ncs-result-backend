import sqlite3

import pytest

from ncs_backend.db_console.connections import connection_factory_from_url


def test_sqlite_connection_factory_supports_memory_database():
    factory = connection_factory_from_url("sqlite:///:memory:")
    connection = factory()
    try:
        assert isinstance(connection, sqlite3.Connection)
        assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        connection.close()


def test_connection_factory_rejects_unsupported_url():
    with pytest.raises(ValueError, match="supported database URLs"):
        connection_factory_from_url("postgresql://localhost/demo")
