"""Repeatable end-to-end acceptance flow for a test MySQL ADS database."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer, AdsV21WaveBImporter
from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageReader
from ncs_backend.admin.mysql_setup import initialize_mysql_ads
from ncs_backend.bootstrap import configured_query_app
from ncs_backend.db_console.connections import connection_factory_from_url
from ncs_backend.query.view_contract import inspect_view_contracts
from ncs_backend.shared.config import Settings
from ncs_backend.shared.db import MYSQL_DIALECT

SMOKE_PATHS = (
    "/api/v1/meta/data-status",
    "/api/v1/meta/capabilities",
    "/api/v1/meta/filter-options?topic=stationRanking",
    "/api/v1/dashboard/manifest",
    "/api/v1/dashboard/overview",
    "/api/v1/audience/platform-distribution",
    "/api/v1/charging/duration-distribution",
    "/api/v1/charging/weekday-weekend",
    "/api/v1/charging/station-hour-heatmap",
    "/api/v1/stations/ranking",
    "/api/v1/revenue/trend",
    "/api/v1/charging/process-summary",
)


@dataclass(frozen=True, slots=True)
class MySqlAcceptanceReport:
    source_batch_id: str
    schema_applied: bool
    first_import_count: int
    repeated_import_count: int
    required_view_count: int
    smoke_request_count: int
    rollback_probe_clean: bool
    recovery_mode: bool


def run_mysql_acceptance(
    package_path: str | Path,
    *,
    database_url: str,
) -> MySqlAcceptanceReport:
    connection_factory = connection_factory_from_url(database_url)
    recovery_mode = _recovery_mode_enabled(connection_factory)
    if not recovery_mode:
        raise RuntimeError("MySQL acceptance requires skip_grant_tables=ON")
    schema_applied = initialize_mysql_ads(connection_factory)
    package_reader = AdsV21PackageReader()
    package = package_reader.read(Path(package_path).expanduser().resolve())

    first = _import_all(package, package_reader, connection_factory)
    repeated = _import_all(package, package_reader, connection_factory)
    contracts = inspect_view_contracts(connection_factory)
    required = tuple(item for item in contracts if item.required)
    incompatible = tuple(item.view_name for item in required if not item.compatible)
    if incompatible:
        raise RuntimeError(f"required view contracts failed: {incompatible}")
    smoke_count = _smoke_query_api(database_url)
    rollback_clean = _rollback_probe(package, package_reader, connection_factory)
    return MySqlAcceptanceReport(
        source_batch_id=package.source_batch_id,
        schema_applied=schema_applied,
        first_import_count=len(first),
        repeated_import_count=len(repeated),
        required_view_count=len(required),
        smoke_request_count=smoke_count,
        rollback_probe_clean=rollback_clean,
        recovery_mode=recovery_mode,
    )


def _recovery_mode_enabled(connection_factory) -> bool:
    connection = connection_factory()
    cursor = connection.cursor()
    try:
        try:
            cursor.execute("SHOW GRANTS")
            return False
        except Exception as exc:
            return bool(
                getattr(exc, "args", (None,))[0] == 1290
                and "skip-grant-tables" in str(exc).lower()
            )
    finally:
        cursor.close()
        connection.close()


def _import_all(package, reader, connection_factory) -> tuple[str, ...]:
    published: list[str] = []
    for importer_type in (AdsV21A0Importer, AdsV21WaveBImporter):
        importer = importer_type(
            connection_factory,
            dialect=MYSQL_DIALECT,
            reader=reader,
            initialize_schema=False,
        )
        published.extend(importer.import_package(package))
    return tuple(published)


def _smoke_query_api(reader_url: str) -> int:
    client = configured_query_app(Settings(database_url=reader_url)).test_client()
    failures: list[str] = []
    for path in SMOKE_PATHS:
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path}={response.status_code}")
    if failures:
        raise RuntimeError(f"query API smoke failed: {', '.join(failures)}")
    return len(SMOKE_PATHS)


def _rollback_probe(package, reader, connection_factory) -> bool:
    probe_id = f"{package.source_batch_id}-rollback-{uuid4().hex[:12]}"
    probe_package = replace(package, source_batch_id=probe_id)
    before = _scalar(connection_factory, "SELECT COUNT(*) FROM api_v1_dashboard_overview")

    class FailingImporter(AdsV21A0Importer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._write_count = 0

        def _insert_result_rows(self, *args, **kwargs):
            super()._insert_result_rows(*args, **kwargs)
            self._write_count += 1
            if self._write_count == 2:
                raise RuntimeError("intentional acceptance rollback probe")

    try:
        FailingImporter(
            connection_factory,
            dialect=MYSQL_DIALECT,
            reader=reader,
            initialize_schema=False,
        ).import_package(probe_package)
    except RuntimeError as exc:
        if str(exc) != "intentional acceptance rollback probe":
            raise
    else:
        raise RuntimeError("rollback probe did not fail as expected")

    leaked = _scalar(
        connection_factory,
        "SELECT COUNT(*) FROM ctl_import_batch WHERE source_batch_id = ?",
        (probe_id,),
    )
    after = _scalar(connection_factory, "SELECT COUNT(*) FROM api_v1_dashboard_overview")
    return leaked == 0 and before == after


def _scalar(connection_factory, sql: str, parameters=()) -> int:
    connection = connection_factory()
    cursor = MYSQL_DIALECT.cursor(connection)
    try:
        cursor.execute(sql, parameters)
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()
        connection.close()
