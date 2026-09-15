"""Exit-code contract tests for scripts/import_ads_v23.py.

30 = data/contract problem (no retry), 40 = MySQL unavailable (retry),
50 = other internal error (retry).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import import_ads_v23
from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageReader


def _write_package(root):
    import hashlib
    import json

    from ncs_backend.admin.adapters.ads_v23_schema import ADS_V23_DATASET_SPECS

    contract = root / "contract_v2"
    contract.mkdir(parents=True)
    datasets = []
    for spec in ADS_V23_DATASET_SPECS:
        values = {field: "1" for field in spec.fields}
        values[spec.primary_key[0]] = "2026-01-01"
        if len(spec.primary_key) > 1:
            for field in spec.primary_key[1:]:
                values[field] = "key"
        path = contract / spec.filename
        path.write_text(",".join(spec.fields) + "\n" + ",".join(values[field] for field in spec.fields) + "\n", encoding="utf-8")
        datasets.append({
            "checksum": hashlib.sha256(path.read_bytes()).hexdigest(),
            "datasetCode": spec.dataset_code,
            "fields": list(spec.fields),
            "file": spec.filename,
            "primaryKey": list(spec.primary_key),
            "rowCount": 1,
        })
    (contract / "manifest.json").write_text(json.dumps({
        "batchId": "batch-v23",
        "datasets": datasets,
        "loadMode": "FULL_SNAPSHOT",
        "metricVersion": "2.0.0",
        "schemaVersion": "2.0.0",
        "status": "SUCCESS",
    }), encoding="utf-8")
    return root


def test_missing_required_dataset_is_exit_30(tmp_path, capsys):
    package = _write_package(tmp_path / "package")
    (package / "contract_v2" / "load_hourly.csv").unlink()

    code = import_ads_v23.main([
        "--package", str(package),
        "--sqlite", str(tmp_path / "ncs.sqlite"),
    ])
    assert code == 30
    assert '"exitCode": 30' in capsys.readouterr().err


def test_mysql_unreachable_is_exit_40(tmp_path, monkeypatch, capsys):
    package = _write_package(tmp_path / "package")
    import pymysql

    def _refused(url):
        raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")

    monkeypatch.setattr(import_ads_v23, "connection_factory_from_url", _refused)

    code = import_ads_v23.main([
        "--package", str(package),
        "--database-url", "mysql+pymysql://root@127.0.0.1:1/ncs_analytics",
        "--skip-initialize",
    ])
    assert code == 40
    assert '"exitCode": 40' in capsys.readouterr().err


def test_unexpected_error_is_exit_50(tmp_path, monkeypatch, capsys):
    package = _write_package(tmp_path / "package")
    import pymysql

    def _boom(url):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(import_ads_v23, "connection_factory_from_url", _boom)

    code = import_ads_v23.main([
        "--package", str(package),
        "--database-url", "mysql+pymysql://root@127.0.0.1:1/ncs_analytics",
        "--skip-initialize",
    ])
    assert code == 50
    assert '"exitCode": 50' in capsys.readouterr().err


def test_invalid_manifest_is_exit_30(tmp_path, capsys):
    package = _write_package(tmp_path / "package")
    manifest = package / "contract_v2" / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace('"SUCCESS"', '"RUNNING"'), encoding="utf-8")

    code = import_ads_v23.main([
        "--package", str(package),
        "--sqlite", str(tmp_path / "ncs.sqlite"),
    ])
    assert code == 30
    assert '"exitCode": 30' in capsys.readouterr().err
