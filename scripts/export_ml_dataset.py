"""Export published result data as a machine-learning dataset package."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url


DATASETS = {
    "load_hourly": {
        "table": "rpt_load_hourly",
        "date_column": "stat_time",
        "columns": (
            "stat_time", "total_kwh", "order_count", "is_observed",
            "fill_method", "time_quality", "allocation_method", "data_version",
        ),
        "order_by": "stat_time",
        "purpose": "连续小时负荷预测主数据集；total_kwh 或 order_count 可作为预测目标",
    },
    "station_hour_daily": {
        "table": "rpt_station_hour_daily",
        "date_column": "data_date",
        "columns": (
            "data_date", "station_id", "station_name", "stat_hour",
            "order_count", "total_kwh", "total_fees", "data_version",
        ),
        "order_by": "data_date, station_id, stat_hour",
        "purpose": "站点、日期、小时粒度特征数据集",
    },
    "fee_energy_daily": {
        "table": "rpt_fee_energy_trend",
        "date_column": "period_start",
        "columns": (
            "period_start", "order_count", "total_kwh", "total_fees", "data_version",
        ),
        "order_by": "period_start",
        "purpose": "日粒度订单、电量、费用趋势特征数据集",
    },
    "process_daily": {
        "table": "rpt_process_summary",
        "date_column": "data_date",
        "columns": (
            "data_date", "record_count", "session_count", "average_soc",
            "average_current", "average_voltage", "average_max_temperature", "data_version",
        ),
        "order_by": "data_date",
        "purpose": "日粒度充电过程统计特征数据集",
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export published MySQL result data for ML training")
    parser.add_argument("--database-url", default=os.getenv("NCS_DATABASE_URL"))
    parser.add_argument("--dataset", choices=(*DATASETS, "all"), default="load_hourly")
    parser.add_argument("--output", type=Path, default=Path("exports/ml_dataset"))
    parser.add_argument("--start-date", help="inclusive ISO date/time lower bound")
    parser.add_argument("--end-date", help="inclusive ISO date/time upper bound")
    parser.add_argument("--station-id", help="only valid for station_hour_daily")
    parser.add_argument("--zip", action="store_true", dest="make_zip", help="also create a zip handoff package")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or NCS_DATABASE_URL is required")
    if args.station_id and args.dataset not in {"station_hour_daily", "all"}:
        parser.error("--station-id is only valid with station_hour_daily or all")

    selected = tuple(DATASETS) if args.dataset == "all" else (args.dataset,)
    args.output.mkdir(parents=True, exist_ok=True)
    connection = connection_factory_from_url(args.database_url)()
    dialect = database_dialect_from_url(args.database_url)
    exported = []
    try:
        for code in selected:
            entry = _export_one(connection, dialect, code, args.output, args.start_date, args.end_date, args.station_id)
            exported.append(entry)
    finally:
        connection.close()

    manifest = {
        "formatVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "ncs_analytics published result database",
        "filters": {"startDate": args.start_date, "endDate": args.end_date, "stationId": args.station_id},
        "datasets": exported,
        "notes": [
            "只包含当前 PUBLISHED 批次，不包含控制表和未发布数据。",
            "load_hourly 为连续小时序列；is_observed=0 表示该小时为补齐值。",
            "时间戳沿用上游脱敏后的业务时间，不应解释为真实运营日期。",
        ],
    }
    manifest_path = args.output / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = _make_zip(args.output) if args.make_zip else None
    print(json.dumps({"output": str(args.output.resolve()), "archive": str(archive.resolve()) if archive else None, "datasets": exported}, ensure_ascii=False, indent=2))
    return 0


def _export_one(connection, dialect, code: str, output: Path, start_date: str | None, end_date: str | None, station_id: str | None) -> dict:
    spec = DATASETS[code]
    columns = spec["columns"]
    where = ["p.dataset_code = ?", "p.status = 'PUBLISHED'", "p.batch_id = r.batch_id"]
    parameters: list[object] = [code]
    if start_date:
        where.append(f"r.{spec['date_column']} >= ?")
        parameters.append(start_date)
    if end_date:
        where.append(f"r.{spec['date_column']} <= ?")
        parameters.append(end_date)
    if station_id and code == "station_hour_daily":
        where.append("r.station_id = ?")
        parameters.append(station_id)
    sql = (
        f"SELECT {', '.join('r.' + column for column in columns)} "
        f"FROM {spec['table']} r JOIN ctl_publication p ON " + " AND ".join(where) +
        f" ORDER BY r.{spec['order_by'].replace(', ', ', r.')}"
    )
    cursor = connection.cursor()
    try:
        cursor.execute(dialect.prepare(sql), tuple(parameters))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    path = output / f"{code}.csv"
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "datasetCode": code,
        "file": path.name,
        "rowCount": len(rows),
        "columns": list(columns),
        "sha256": digest.hexdigest(),
        "purpose": spec["purpose"],
    }


def _make_zip(directory: Path) -> Path:
    archive = directory.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(directory.iterdir()):
            if path.is_file():
                bundle.write(path, arcname=path.name)
    return archive


if __name__ == "__main__":
    raise SystemExit(main())
