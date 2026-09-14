import pytest

from ncs_backend.admin.mysql_setup import grant_reader_views, verify_mysql_accounts


class _Cursor:
    def __init__(self, grants=""):
        self.grants = grants
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        if sql == "SHOW GRANTS":
            return self
        if "rpt_dashboard_overview" in sql or "ctl_import_batch" in sql:
            error = RuntimeError(1142, "denied")
            error.args = (1142, "denied")
            raise error
        return self

    def fetchall(self):
        return [(self.grants,)]

    def close(self):
        pass


class _Connection:
    def __init__(self, grants=""):
        self.cursor_value = _Cursor(grants)
        self.committed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_grant_reader_views_uses_fixed_validated_identifiers():
    connection = _Connection()
    granted = grant_reader_views(lambda: connection, database="ncs_analytics", views=("api_v1_data_status",))

    assert granted == ("api_v1_data_status",)
    assert connection.cursor_value.executed == [
        "GRANT SELECT ON `ncs_analytics`.`api_v1_data_status` TO 'ncs_ads_reader'@'localhost'"
    ]
    assert connection.committed is True


@pytest.mark.parametrize("database,account", [("bad-name", "reader"), ("ncs", "reader'@'%")])
def test_grant_reader_views_rejects_unsafe_identifiers(database, account):
    with pytest.raises(ValueError):
        grant_reader_views(lambda: _Connection(), database=database, reader_account=account)


def test_verify_mysql_accounts_reports_least_privilege_boundary():
    migrator = lambda: _Connection("GRANT ALL PRIVILEGES ON `ncs_analytics`.* TO user")
    admin = lambda: _Connection("GRANT SELECT, INSERT, UPDATE, DELETE ON `ncs_analytics`.* TO user")
    reader = lambda: _Connection(
        "GRANT USAGE ON *.* TO user\nGRANT SELECT ON `ncs_analytics`.`api_v1_data_status` TO user"
    )

    report = verify_mysql_accounts(migrator, admin, reader)

    assert report.migrator_can_manage_schema is True
    assert report.admin_dml_only is True
    assert report.reader_physical_tables_denied is True
    assert len(report.reader_views) == 9
