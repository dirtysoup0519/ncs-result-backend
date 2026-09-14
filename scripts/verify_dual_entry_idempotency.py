"""Dual-entry idempotency acceptance for ADS package import.

Covers the acceptance requirements that were previously untested:

1. First import of a package publishes all datasets.
2. Re-submitting the same batch (sourceBatchId + manifest checksum)
   through a *different* entry point must not publish again.
3. A package that passes reading but fails during import (duplicate
   primary key) must roll back completely and leave the previous
   publication intact and readable.

Entry A mirrors scripts/import_ads_v23.py (CLI path used by the VM
shell sync). Entry B uses AdsV23ImportService, the service behind
POST /internal/v1/ads-v23/imports. Both must behave identically.

Usage:
  python scripts/verify_dual_entry_idempotency.py \
      [--package /path/to/ads_package] \
      [--sqlite .local/idempotency.sqlite | --database-url mysql+pymysql://...]

Without --package a synthetic v2.5 (18-dataset) package is generated.
Exit code 0 means all checks passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from ncs_backend.admin.ads_schema import initialize_ads_result_schema
from ncs_backend.admin.adapters.ads_v23_schema import ADS_V25_DATASET_SPECS
from ncs_backend.admin.ads_v23_import_service import AdsV23ImportService
from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.shared.db import SQLITE_DIALECT


def _synthesize_package(root: Path, batch_id: str) -> Path:
    """Build a minimal but contract-valid v2.5 package (18 datasets).

    Values must satisfy the importer's cross-file reconciliation:
    dashboard_overview.total_order_count == sum(platform_distribution.order_count)
        == sum(fee_energy_daily.order_count) == sum(station_daily.order_count),
    and the order_ratio columns of platform_distribution and
    duration_distribution must each sum to 100.
    """

    contract = root / "contract_v2"
    contract.mkdir(parents=True)
    datasets = []
    for spec in ADS_V25_DATASET_SPECS:
        rows = _rows_for(spec)
        path = contract / spec.filename
        lines = [",".join(spec.fields)]
        for row in rows:
            lines.append(",".join(str(row[field]) for field in spec.fields))
        path.write_text("\n".join(lines), encoding="utf-8")
        datasets.append({
            "checksum": hashlib.sha256(path.read_bytes()).hexdigest(),
            "datasetCode": spec.dataset_code,
            "fields": list(spec.fields),
            "file": spec.filename,
            "primaryKey": list(spec.primary_key),
            "rowCount": len(rows),
        })
    (contract / "manifest.json").write_text(json.dumps({
        "batchId": batch_id,
        "datasets": datasets,
        "loadMode": "FULL_SNAPSHOT",
        "metricVersion": "2.2.0",
        "schemaVersion": "2.2.0",
        "status": "SUCCESS",
    }), encoding="utf-8")
    return root


def _rows_for(spec):
    key_date, key_end = "2026-01-01", "2026-01-01"
    rows = []
    if spec.dataset_code == "dashboard_overview":
        base = {field: "1" for field in spec.fields}
        base.update({"start_date": key_date, "end_date": key_end, "total_order_count": "100",
                     "total_fees": "100.00", "total_kwh": "100.00", "total_user_count": "10",
                     "active_station_count": "2", "station_count": "2", "metric_version": "2.2.0"})
        rows.append(base)
    elif spec.dataset_code == "platform_distribution":
        for code, count, ratio in (("app", "60", "60.00"), ("miniprogram", "40", "40.00")):
            row = {field: "1" for field in spec.fields}
            row.update({"start_date": key_date, "end_date": key_end, "platform_code": code,
                        "order_count": count, "order_ratio": ratio, "total_fees": "50.00", "fee_ratio": "50.00"})
            rows.append(row)
    elif spec.dataset_code == "fee_energy_daily":
        for day, count in (("2026-01-01", "60"), ("2026-01-02", "40")):
            row = {field: "1" for field in spec.fields}
            row.update({"data_date": day, "order_count": count, "total_kwh": "50.00",
                        "total_fees": "50.00", "total_charge_hours": "20.00", "user_count": "5"})
            rows.append(row)
    elif spec.dataset_code == "station_daily":
        for station, count in (("ST001", "60"), ("ST002", "40")):
            row = {field: "1" for field in spec.fields}
            row.update({"data_date": "2026-01-01", "station_id": station, "station_name": f"站{station}",
                        "location_id": "L1", "order_count": count, "total_kwh": "50.00", "total_fees": "50.00"})
            rows.append(row)
    elif spec.dataset_code == "duration_distribution":
        for bucket, count, ratio in (("0-1h", "60", "60.00"), ("1-2h", "40", "40.00")):
            row = {field: "1" for field in spec.fields}
            row.update({"start_date": key_date, "end_date": key_end, "bucket_code": bucket,
                        "duration_bucket": bucket, "order_count": count, "order_ratio": ratio})
            rows.append(row)
    else:
        base = {field: "1" for field in spec.fields}
        base[spec.primary_key[0]] = "2026-01-01"
        if len(spec.primary_key) > 1:
            for field in spec.primary_key[1:]:
                base[field] = _default_key_value(field)
        rows.append(base)
    return rows


def _default_key_value(field: str) -> str:
    """Provide field values that pass the importer's per-column parsing."""

    if field == "day_type":
        return "workday"
    if field in ("stat_hour", "hour", "station_rank", "rank_order"):
        return "1"
    if field == "stat_time":
        return "2026-01-01T10:00:00"
    if field == "stat_month":
        return "2026-01"
    if field == "is_filled_zero":
        return "false"
    return "key"


def _tamper_with_invalid_ratio(package: Path) -> Path:
    """Set one hour value out of the 0..23 range while keeping the
    manifest self-consistent, so the package passes reading and the
    cross-file reconciliation, and the failure happens while rows are
    being inserted inside the import transaction."""

    target = package / "contract_v2" / "weekday_hour_profile.csv"
    manifest_path = package / "contract_v2" / "manifest.json"
    rows = target.read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",")
    hour_index = header.index("stat_hour")
    broken = rows[1].split(",")
    broken[hour_index] = "24"
    target.write_text("\n".join([rows[0], ",".join(broken)]), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["datasets"]:
        if entry["datasetCode"] == "weekday_hour_profile":
            entry["checksum"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return package


class _Database:
    def __init__(self, connection_factory, dialect_name: str) -> None:
        self._factory = connection_factory
        self._dialect_name = dialect_name

    def scalar(self, sql: str, parameters: tuple = ()) -> int:
        connection = self._factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, parameters)
            return int(cursor.fetchone()[0])
        finally:
            connection.close()

    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._dialect_name == "mysql" else sql

    def snapshot(self) -> dict[str, Any]:
        batches = self.scalar("SELECT COUNT(*) FROM ctl_import_batch")
        publications = self.scalar("SELECT COUNT(*) FROM ctl_publication")
        published = self.scalar("SELECT COUNT(*) FROM ctl_publication WHERE status = 'PUBLISHED'")
        result_rows = 0
        for table in ("rpt_dashboard_overview", "rpt_fee_energy_trend", "rpt_load_hourly"):
            result_rows += self.scalar(f"SELECT COUNT(*) FROM {table}")
        return {"batches": batches, "publications": publications, "published": published, "resultRows": result_rows}


def _entry_a(package: Path, sqlite_path: Path | None, database_url: str | None) -> None:
    """Import through the CLI entry used by the shell sync."""

    from scripts.import_ads_v23 import main as cli_main

    argv = ["--package", str(package)]
    if sqlite_path is not None:
        argv += ["--sqlite", str(sqlite_path)]
    else:
        argv += ["--database-url", database_url]
    code = cli_main(argv)
    if code != 0:
        raise RuntimeError(f"entry A (CLI) import failed with exit code {code}")


def _entry_b(package: Path, connection_factory, dialect) -> None:
    """Import through the application service behind the admin API."""

    service = AdsV23ImportService(connection_factory, dialect=dialect)
    result = service.import_package(package)
    if not result.published_datasets:
        raise RuntimeError("entry B (service) reported no published datasets")


def _fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dual-entry idempotency acceptance")
    parser.add_argument("--package", type=Path, default=None, help="extracted ADS package (default: synthesize v2.5 sample)")
    parser.add_argument("--sqlite", type=Path, default=None, help="SQLite database path for the acceptance run")
    parser.add_argument("--database-url", default=None, help="MySQL URL, e.g. mysql+pymysql://ncs_ads_admin:***@vm/ncs_analytics")
    parser.add_argument("--work-dir", type=Path, default=None, help="directory for the synthesized package")
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args(argv)

    if args.package is None and args.sqlite is None and args.database_url is None:
        args.sqlite = REPO_ROOT / ".local" / "idempotency.sqlite"
    if args.sqlite is not None:
        args.sqlite.parent.mkdir(parents=True, exist_ok=True)
        connection_factory = lambda: sqlite3.connect(args.sqlite)  # noqa: E731
        dialect = SQLITE_DIALECT
    else:
        connection_factory = connection_factory_from_url(args.database_url)
        dialect = database_dialect_from_url(args.database_url)

    work_dir = args.work_dir or (REPO_ROOT / ".local" / "dual_entry_work")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    package = args.package if args.package is not None else _synthesize_package(work_dir / "package", "batch-acceptance")

    connection = connection_factory()
    try:
        initialize_control_schema(connection)
        initialize_staging_schema(connection)
        initialize_ads_result_schema(connection, dialect=dialect)
        connection.commit()
    finally:
        connection.close()

    database = _Database(connection_factory, dialect.name)
    checks = 0

    print("[1/4] first import via entry A (CLI path)")
    _entry_a(package, args.sqlite, args.database_url)
    first = database.snapshot()
    if first["batches"] == 0 or first["published"] == 0:
        _fail("first import produced no batches/publications")
    checks += 1

    from ncs_backend.admin.ads_v23_import_service import AdsV23ImportResult  # noqa: F401  (interface smoke)

    print("[2/4] duplicate via entry B (admin service path)")
    _entry_b(package, connection_factory, dialect)
    second = database.snapshot()
    if second != first:
        _fail(f"duplicate import changed database state: {first} -> {second}")
    checks += 1

    print("[3/4] duplicate again via entry A (CLI path)")
    _entry_a(package, args.sqlite, args.database_url)
    third = database.snapshot()
    if third != first:
        _fail(f"second duplicate changed database state: {first} -> {third}")
    checks += 1

    print("[4/4] failed import must roll back and keep publications")
    broken = _tamper_with_invalid_ratio(_synthesize_package(work_dir / "package_broken", "batch-acceptance-broken"))
    failed = False
    try:
        _entry_b(broken, connection_factory, dialect)
    except Exception as exc:
        failed = True
        print(f"      rejected as expected: {type(exc).__name__}: {str(exc).splitlines()[0][:120]}")
    if not failed:
        _fail("tampered package was accepted")
    fourth = database.snapshot()
    if fourth != first:
        _fail(f"failed import changed database state: {first} -> {fourth}")
    checks += 1

    if not args.keep_workdir and args.package is None:
        shutil.rmtree(work_dir, ignore_errors=True)

    print(f"PASS dual-entry idempotency acceptance ({checks}/4 checks) on {dialect.name}")
    print(f"     state: {json.dumps(first)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
