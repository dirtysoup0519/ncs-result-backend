import hashlib
import json

import pytest

from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageError, AdsV23PackageReader
from ncs_backend.admin.adapters.ads_v23_schema import ADS_V23_DATASET_SPECS


def _write_package(root):
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


def test_reader_validates_v23_manifest_and_csv_contract(tmp_path):
    package = AdsV23PackageReader().read(_write_package(tmp_path / "package"))

    assert package.source_batch_id == "batch-v23"
    assert package.schema_version == "2.0.0"
    assert len(package.datasets) == 10
    rows = AdsV23PackageReader().read_rows(package, "platform_distribution")
    assert rows[0]["platform_code"] == "key"


def test_reader_rejects_tampered_csv(tmp_path):
    root = _write_package(tmp_path / "package")
    (root / "contract_v2" / "load_hourly.csv").write_text(
        (root / "contract_v2" / "load_hourly.csv").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(AdsV23PackageError, match="SHA-256 mismatch"):
        AdsV23PackageReader().read(root)


def test_reader_rejects_duplicate_primary_key(tmp_path):
    root = _write_package(tmp_path / "package")
    path = root / "contract_v2" / "fee_energy_daily.csv"
    content = path.read_text(encoding="utf-8")
    path.write_text(content + content.split("\n", 1)[1], encoding="utf-8")
    manifest = json.loads((root / "contract_v2" / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["datasets"]:
        if entry["datasetCode"] == "fee_energy_daily":
            entry["rowCount"] = 2
            entry["checksum"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "contract_v2" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AdsV23PackageError, match="duplicate primary key"):
        AdsV23PackageReader().read(root)
