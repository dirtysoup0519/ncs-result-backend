import hashlib
import json

import pytest

from ncs_backend.prediction.model_registry import ModelPackage, ModelPackageError


def _write_package(tmp_path, manifest):
    weights = tmp_path / "model_weights.pth"
    weights.write_bytes(b"test-weights")
    manifest = dict(manifest)
    manifest["weightsFile"] = "model_weights.pth"
    manifest["weightsSha256"] = hashlib.sha256(b"test-weights").hexdigest()
    (tmp_path / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_manifest_package_is_loaded_and_hashed(tmp_path):
    package = ModelPackage.open(_write_package(tmp_path, {
        "modelCode": "global_load_forecast",
        "modelVersion": "v1",
        "adapterCode": "multiscale_conv_transformer_v1",
        "framework": "pytorch",
        "input": {"sourceDataset": "load_hourly", "lookback": 512},
        "output": {"horizon": 24},
    }))
    assert package.model_version == "v1"
    assert len(package.weights_sha256) == 64


def test_manifest_rejects_wrong_dataset(tmp_path):
    with pytest.raises(ModelPackageError, match="sourceDataset"):
        ModelPackage.open(_write_package(tmp_path, {
            "modelCode": "m", "modelVersion": "v1", "adapterCode": "x", "framework": "pytorch",
            "input": {"sourceDataset": "station_daily", "lookback": 1}, "output": {"horizon": 1},
        }))
