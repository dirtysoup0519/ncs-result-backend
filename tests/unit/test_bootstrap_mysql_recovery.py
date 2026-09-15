from scripts.bootstrap_mysql_recovery import (
    _initialize_database,
    _server_state,
    connection_url,
)
import pymysql


class _Cursor:
    def __init__(self, recovery_mode="ON"):
        self.recovery_mode = recovery_mode
        self.executed = []
        self.current = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql):
        self.current = sql
        self.executed.append(sql)
        if sql == "SHOW GRANTS" and self.recovery_mode == "ON":
            raise pymysql.OperationalError(
                1290,
                "The MySQL server is running with the --skip-grant-tables option",
            )

    def fetchone(self):
        if self.current == "SELECT VERSION()":
            return ("5.7.35",)
        return ("GRANT USAGE ON *.* TO 'root'@'localhost'",)


class _Connection:
    def __init__(self, recovery_mode="ON"):
        self.cursor_value = _Cursor(recovery_mode)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_server_state_requires_recovery_mode():
    assert _server_state(_Connection("ON")) == ("5.7.35", True)
    assert _server_state(_Connection("OFF")) == ("5.7.35", False)


def test_initialize_database_only_creates_database():
    connection = _Connection()

    _initialize_database(connection, "ncs_analytics")

    assert connection.cursor_value.executed == [
        "CREATE DATABASE IF NOT EXISTS `ncs_analytics` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    ]
    assert connection.committed is True
    assert connection.rolled_back is False


def test_recovery_connection_url_has_no_password():
    assert connection_url("192.168.176.100", 3306, "ncs_analytics") == (
        "mysql+pymysql://root@192.168.176.100:3306/ncs_analytics"
    )
