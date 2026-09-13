import sqlite3

import pytest

from ncs_backend.query.view_contract import assert_view_contracts, inspect_view_contracts


def test_view_contract_reports_missing_views_without_using_physical_tables(tmp_path):
    database = tmp_path / "views.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE api_v1_dashboard_overview ("
        "metric_code TEXT, display_name TEXT, metric_value TEXT, unit TEXT, precision INTEGER, "
        "data_date TEXT, data_version TEXT, generated_at TEXT, staleness TEXT)"
    )
    connection.commit()
    connection.close()

    results = inspect_view_contracts(lambda: sqlite3.connect(database))
    overview = next(item for item in results if item.view_name == "api_v1_dashboard_overview")
    ranking = next(item for item in results if item.view_name == "api_v1_station_ranking")
    assert overview.compatible is True
    assert ranking.exists is False
    assert ranking.compatible is False
    assert overview.to_dict()["viewName"] == "api_v1_dashboard_overview"
    assert ranking.to_dict()["missingColumns"]

    with pytest.raises(RuntimeError, match="read-only view contract"):
        assert_view_contracts(lambda: sqlite3.connect(database))
