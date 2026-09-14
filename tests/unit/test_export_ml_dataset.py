import csv
import importlib.util
import json
from pathlib import Path
import sqlite3


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_ml_dataset.py"


def _module():
    spec = importlib.util.spec_from_file_location("export_ml_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_exports_only_published_hourly_rows_with_manifest(tmp_path):
    database = tmp_path / "result.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE ctl_publication (dataset_code TEXT, batch_id TEXT, status TEXT);
        CREATE TABLE rpt_load_hourly (
          batch_id TEXT, stat_time TEXT, total_kwh NUMERIC, order_count INTEGER,
          is_observed INTEGER, fill_method TEXT, time_quality TEXT,
          allocation_method TEXT, data_version TEXT
        );
        INSERT INTO ctl_publication VALUES ('load_hourly', 'active', 'PUBLISHED');
        INSERT INTO ctl_publication VALUES ('load_hourly', 'old', 'SUPERSEDED');
        INSERT INTO rpt_load_hourly VALUES ('active','2015-01-01 00:00:00',10.5,2,1,'NONE','GOOD','DIRECT','2.0.0');
        INSERT INTO rpt_load_hourly VALUES ('old','2014-01-01 00:00:00',99,9,1,'NONE','GOOD','DIRECT','1.0.0');
        """
    )
    connection.commit()
    connection.close()

    output = tmp_path / "dataset"
    result = _module().main([
        "--database-url", f"sqlite:///{database.as_posix()}",
        "--output", str(output), "--zip",
    ])

    assert result == 0
    with (output / "load_hourly.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["stat_time"] == "2015-01-01 00:00:00"
    manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["datasets"][0]["rowCount"] == 1
    assert manifest["datasets"][0]["sha256"]
    assert output.with_suffix(".zip").is_file()
