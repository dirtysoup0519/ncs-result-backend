from scripts.bootstrap_mysql_users import _grant_tables_disabled, _initialize


class _Cursor:
    def __init__(self, skip_grant_tables="OFF"):
        self.executed = []
        self.skip_grant_tables = skip_grant_tables

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))

    def fetchone(self):
        return ("skip_grant_tables", self.skip_grant_tables)


class _Connection:
    def __init__(self, skip_grant_tables="OFF"):
        self.cursor_value = _Cursor(skip_grant_tables)
        self.committed = False
        self.rolled_back = False

    def begin(self):
        pass

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_initialize_escapes_wildcard_account_host_for_pymysql_parameters(monkeypatch):
    monkeypatch.setenv("NCS_BOOTSTRAP_MIGRATOR_PASSWORD", "migrator-password")
    monkeypatch.setenv("NCS_BOOTSTRAP_ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("NCS_BOOTSTRAP_READER_PASSWORD", "reader-password")
    connection = _Connection()

    _initialize(connection, "ncs_analytics", "%")

    parameterized = [item for item in connection.cursor_value.executed if item[1] is not None]
    assert len(parameterized) == 6
    for sql, parameters in parameterized:
        # This is the exact formatting operation PyMySQL performs internally.
        assert "'%'" in (sql % parameters)
    assert connection.committed is True
    assert connection.rolled_back is False


def test_grant_tables_disabled_detects_mysql_recovery_mode():
    assert _grant_tables_disabled(_Connection("ON")) is True
    assert _grant_tables_disabled(_Connection("OFF")) is False
