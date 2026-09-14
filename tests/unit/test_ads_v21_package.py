import hashlib
import json
from pathlib import Path

import pytest

from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageError, AdsV21PackageReader
from ncs_backend.admin.adapters.ads_v21_schema import ADS_V21_FILE_SPECS


def _write_package(root: Path) -> Path:
    root.mkdir()
    files = {}
    for spec in ADS_V21_FILE_SPECS:
        path = root / spec.filename
        path.write_text("\t".join("1" for _ in spec.fields) + "\n", encoding="utf-8")
        files[spec.filename] = {"fields": len(spec.fields), "rows": 1}
    manifest = {"files": files, "status": "SUCCESS", "total_orders": 1}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    entries = []
    for path in sorted(root.glob("*.csv")) + [root / "manifest.json"]:
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest().upper()}  {path.name}")
    (root / "文件校验_SHA256.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
    (root / "ml").mkdir()
    (root / "ml" / "ignored.csv").write_text("model", encoding="utf-8")
    return root


def test_reader_validates_package_and_describes_all_datasets(tmp_path):
    package = AdsV21PackageReader().read(_write_package(tmp_path / "package"))

    assert package.source_batch_id == "ads-sim-v2.1-20260914"
    assert package.total_orders == 1
    assert len(package.datasets) == 12
    assert package.datasets[5].dataset_code == "hourly_distribution_snapshot"
    assert "MISSING_HOUR:2" in package.datasets[5].warnings
    rows = AdsV21PackageReader().read_rows(package, "platform_distribution")
    assert rows == ({"platform": "1", "order_cnt": "1", "total_fees": "1", "fee_ratio": "1"},)


def test_reader_rejects_tampered_data(tmp_path):
    root = _write_package(tmp_path / "package")
    (root / "kpi_total.csv").write_text("2\t1\t1\t1\t1\t1\t1\n", encoding="utf-8")

    with pytest.raises(AdsV21PackageError, match="SHA-256 mismatch"):
        AdsV21PackageReader().read(root)


def test_reader_rejects_manifest_row_count_mismatch(tmp_path):
    root = _write_package(tmp_path / "package")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["files"]["kpi_total.csv"]["rows"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    entries = []
    for path in sorted(root.glob("*.csv")) + [manifest_path]:
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest().upper()}  {path.name}")
    (root / "文件校验_SHA256.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")

    with pytest.raises(AdsV21PackageError, match="row count mismatch"):
        AdsV21PackageReader().read(root)


def test_reader_rejects_wrong_field_count(tmp_path):
    root = _write_package(tmp_path / "package")
    path = root / "platform_stat.csv"
    path.write_text("1\t2\n", encoding="utf-8")

    with pytest.raises(AdsV21PackageError, match="SHA-256 mismatch"):
        AdsV21PackageReader().read(root)
