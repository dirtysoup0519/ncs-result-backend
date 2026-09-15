from scripts import ensure_dashboard_data


def test_existing_publication_skips_import(monkeypatch):
    monkeypatch.setattr(ensure_dashboard_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_dashboard_data, "_dashboard_ready", lambda url: True)
    monkeypatch.setattr(
        ensure_dashboard_data,
        "import_package_main",
        lambda args: (_ for _ in ()).throw(AssertionError("must not import")),
    )

    assert ensure_dashboard_data.main() == 0


def test_empty_database_imports_latest_package(monkeypatch):
    states = iter((False, True))
    called = []
    monkeypatch.setattr(ensure_dashboard_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_dashboard_data, "_dashboard_ready", lambda url: next(states))
    monkeypatch.setattr(ensure_dashboard_data, "import_package_main", lambda args: called.append(args) or 0)

    assert ensure_dashboard_data.main() == 0
    assert called == [[]]


def test_empty_database_without_package_returns_distinct_exit(monkeypatch):
    monkeypatch.setattr(ensure_dashboard_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_dashboard_data, "_dashboard_ready", lambda url: False)
    monkeypatch.setattr(
        ensure_dashboard_data,
        "import_package_main",
        lambda args: (_ for _ in ()).throw(SystemExit("NO_PACKAGE: add one")),
    )

    assert ensure_dashboard_data.main() == ensure_dashboard_data.NO_PACKAGE_EXIT
