from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer, AdsV21ImportError, AdsV21WaveBImporter
from ncs_backend.admin.adapters.ads_v21_package import AdsV21DatasetDescriptor, AdsV21PackageDescriptor
from ncs_backend.admin.adapters.ads_v21_schema import ADS_V21_FILE_SPECS
from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.local_database import initialize_local_database
from ncs_backend.bootstrap import configured_query_app
from ncs_backend.shared.config import Settings


class _FakeReader:
    def __init__(self, rows_by_code: dict[str, tuple[dict[str, str], ...]]) -> None:
        self.rows_by_code = rows_by_code

    def read_rows(self, package: AdsV21PackageDescriptor, dataset_code: str) -> tuple[dict[str, str], ...]:
        return self.rows_by_code[dataset_code]


def _fixture_package() -> tuple[AdsV21PackageDescriptor, _FakeReader]:
    overrides = {
        "dashboard_overview": ({
            "total_order_cnt": "1", "total_fees": "2", "total_kwh": "3",
            "total_user_cnt": "1", "total_station_cnt": "1",
            "avg_fee_per_order": "2", "avg_kwh_per_order": "3",
        },),
        "fee_energy_daily": (("stat_date", "2015-12-28"), ("order_cnt", "1"), ("total_fees", "2"), ("total_kwh", "3")),
        "fee_energy_monthly": (("stat_month", "2015-12"), ("order_cnt", "1"), ("total_fees", "2"), ("total_kwh", "3")),
        "platform_distribution": (("platform", "android"), ("order_cnt", "1"), ("total_fees", "2"), ("fee_ratio", "100")),
        "order_daily": (("stat_date", "2015-12-28"), ("order_cnt", "1"), ("total_kwh", "3"), ("total_fees", "2"), ("total_charge_hours", "1"), ("user_cnt", "1")),
        "charging_duration_distribution": (("bucket_order", "1"), ("duration_bucket", "0-1h"), ("order_cnt", "1"), ("order_ratio", "100")),
        "weekday_weekend_profile": (("day_type", "workday"), ("order_cnt", "1"), ("total_kwh", "3"), ("total_fees", "2"), ("avg_charge_hours", "1"), ("user_cnt", "1")),
        "station_hour_heatmap_snapshot": (("station_id", "S1"), ("station_name", "站点1"), ("stat_hour", "0"), ("order_cnt", "1"), ("total_kwh", "3"), ("total_fees", "2")),
        "station_ranking_snapshot": (("station_id", "S1"), ("station_name", "站点1"), ("location_id", "L1"), ("order_cnt", "1"), ("total_fees", "2"), ("total_kwh", "3")),
        "charging_process_daily": (("stat_date", "2015-12-28"), ("record_cnt", "1"), ("session_cnt", "1"), ("avg_soc", "50"), ("max_soc", "80"), ("min_soc", "20"), ("avg_current", "10"), ("avg_pack_voltage", "400"), ("avg_max_temp", "30")),
    }
    rows_by_code: dict[str, tuple[dict[str, str], ...]] = {}
    descriptors: list[AdsV21DatasetDescriptor] = []
    for spec in ADS_V21_FILE_SPECS:
        if spec.dataset_code == "dashboard_overview":
            rows = overrides[spec.dataset_code]
        elif spec.dataset_code in overrides:
            rows = (dict(overrides[spec.dataset_code]),)
        else:
            rows = (dict(zip((field.name for field in spec.fields), ("1" for _ in spec.fields))),)
        rows_by_code[spec.dataset_code] = rows
        descriptors.append(AdsV21DatasetDescriptor(
            dataset_code=spec.dataset_code,
            source_file=spec.filename,
            schema_version="v2.1",
            row_count=len(rows),
            field_count=spec.field_count,
            sha256="a" * 64,
            unique_key=spec.unique_key,
            warnings=spec.warnings,
        ))
    return AdsV21PackageDescriptor(
        root=Path("."),
        source_batch_id="ads-sim-v2.1-20260914",
        source_version="v2.1",
        status="SUCCESS",
        total_orders=1,
        datasets=tuple(descriptors),
        ignored_files=("ml/",),
    ), _FakeReader(rows_by_code)


def test_importer_publishes_a0_views_and_is_idempotent(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    package, reader = _fixture_package()
    importer = AdsV21A0Importer(
        lambda: sqlite3.connect(database),
        reader=reader,
        clock=lambda: datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc),
    )

    assert importer.import_package(package) == (
        "dashboard_overview", "platform_distribution", "fee_energy_daily", "fee_energy_monthly",
        "station_ranking_snapshot", "charging_process_daily",
    )
    assert importer.import_package(package) == (
        "dashboard_overview", "platform_distribution", "fee_energy_daily", "fee_energy_monthly",
        "station_ranking_snapshot", "charging_process_daily",
    )

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM api_v1_dashboard_overview").fetchone()[0] == 7
        assert connection.execute("SELECT order_ratio FROM api_v1_platform_distribution").fetchone()[0] == 1
        assert connection.execute("SELECT data_date FROM api_v1_station_ranking").fetchone()[0] == "2015-12-28"
        assert connection.execute("SELECT COUNT(*) FROM api_v1_fee_energy_trend").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM api_v1_fee_energy_trend WHERE granularity = 'MONTH'").fetchone()[0] == 1
        assert connection.execute("SELECT station_id FROM api_v1_process_summary").fetchone()[0] is None
        assert connection.execute("SELECT COUNT(*) FROM ctl_publication WHERE status = 'PUBLISHED'").fetchone()[0] == 6
        assert connection.execute("SELECT COUNT(*) FROM ctl_quality_result WHERE passed = 1").fetchone()[0] == 6
    finally:
        connection.close()


def test_importer_can_use_an_already_initialized_schema(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    with sqlite3.connect(database) as connection:
        initialize_ads_result_schema(connection)
    package, reader = _fixture_package()

    result = AdsV21A0Importer(
        lambda: sqlite3.connect(database),
        reader=reader,
        initialize_schema=False,
    ).import_package(package)

    assert "dashboard_overview" in result
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM api_v1_dashboard_overview").fetchone()[0] == 7


def test_importer_rejects_cross_file_order_mismatch(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    package, reader = _fixture_package()
    reader.rows_by_code["fee_energy_monthly"] = ({
        "stat_month": "2015-12", "order_cnt": "2", "total_fees": "2", "total_kwh": "3",
    },)

    with pytest.raises(AdsV21ImportError, match="cross-file order reconciliation"):
        AdsV21A0Importer(lambda: sqlite3.connect(database), reader=reader).import_package(package)


def test_configured_query_app_reads_published_ads_views(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    package, reader = _fixture_package()
    AdsV21A0Importer(lambda: sqlite3.connect(database), reader=reader).import_package(package)
    client = configured_query_app(Settings(database_url=f"sqlite:///{database.as_posix()}"),).test_client()

    overview = client.get("/api/v1/dashboard/overview")
    trend = client.get("/api/v1/revenue/trend")
    status = client.get("/api/v1/meta/data-status")
    capabilities = client.get("/api/v1/meta/capabilities")
    filters = client.get("/api/v1/meta/filter-options?topic=stationRanking")

    assert overview.status_code == 200
    assert len(overview.json["data"]["items"]) == 7
    assert trend.json["data"]["granularity"] == "MONTH"
    assert len(trend.json["data"]["points"]) == 1
    assert status.json["data"]["qualityStatus"] == "PASSED"
    assert status.json["data"]["stationCount"] == 1
    available = {item["capabilityCode"]: item["available"] for item in capabilities.json["data"]["items"]}
    assert available["overview"] is True
    assert available["stationRanking"] is True
    assert available["durationDistribution"] is False
    assert filters.json["data"]["stations"][0]["stationId"] == "S1"
    assert filters.json["data"]["dateRange"] == {"minDate": "2015-12-28", "maxDate": "2015-12-28"}
    assert filters.json["meta"]["empty"] is False


def test_wave_b_importer_expands_snapshot_datasets(tmp_path):
    database = tmp_path / "ncs.sqlite"
    initialize_local_database(database)
    package, reader = _fixture_package()
    importer = AdsV21WaveBImporter(lambda: sqlite3.connect(database), reader=reader)

    assert importer.import_package(package) == (
        "charging_duration_distribution",
        "weekday_weekend_profile",
        "station_hour_heatmap_snapshot",
    )
    client = configured_query_app(Settings(database_url=f"sqlite:///{database.as_posix()}"),).test_client()

    duration = client.get("/api/v1/charging/duration-distribution")
    profile = client.get("/api/v1/charging/weekday-weekend")
    heatmap = client.get("/api/v1/charging/station-hour-heatmap")
    dated_heatmap = client.get("/api/v1/charging/station-hour-heatmap?dataDate=2015-12-28")

    assert [item["bucketCode"] for item in duration.json["data"]["items"]] == [
        "PT0H_PT1H", "PT1H_PT2H", "PT2H_PT3H", "PT3H_PLUS",
    ]
    assert duration.json["data"]["items"][0]["ratio"] == "1"
    assert profile.json["data"]["series"][0]["dayType"] == "WEEKDAY"
    assert profile.json["data"]["series"][0]["rawValues"][0] == 1
    assert heatmap.json["data"]["availability"] == "AVAILABLE"
    assert len(heatmap.json["data"]["points"]) == 24
    assert heatmap.json["data"]["points"][0]["isObserved"] is True
    assert dated_heatmap.status_code == 400
    assert dated_heatmap.json["code"] == "VALIDATION_UNSUPPORTED_FILTER"
