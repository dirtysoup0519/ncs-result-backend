"""Safe, manifest-first model package loading."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


class ModelPackageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelPackage:
    root: Path
    manifest: dict[str, Any]
    weights_path: Path
    weights_sha256: str

    @property
    def model_code(self) -> str:
        return str(self.manifest["modelCode"])

    @property
    def model_version(self) -> str:
        return str(self.manifest["modelVersion"])

    @property
    def adapter_code(self) -> str:
        return str(self.manifest["adapterCode"])

    @classmethod
    def open(cls, path: str | Path) -> "ModelPackage":
        root = Path(path).expanduser().resolve()
        if root.is_file():
            weights_path = root
            root = root.parent
        else:
            weights_path = root / "model_weights.pth"
            if not weights_path.is_file():
                legacy = root / "model_all.pth"
                if legacy.is_file():
                    weights_path = legacy
        if not root.is_dir() or not weights_path.is_file():
            raise ModelPackageError("model package must contain a weights file")
        manifest_path = root / "model_manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ModelPackageError("invalid model_manifest.json") from exc
        else:
            manifest = _legacy_manifest(weights_path)
        _validate_manifest(manifest, weights_path)
        digest = _sha256(weights_path)
        expected = str(manifest.get("weightsSha256", "")).lower()
        if expected and expected != digest:
            raise ModelPackageError("model weights SHA-256 mismatch")
        return cls(root, manifest, weights_path, digest)

    def load_checkpoint(self) -> dict[str, Any]:
        try:
            import torch
        except ImportError as exc:  # pragma: no cover
            raise ModelPackageError("PyTorch is required to load model weights") from exc
        try:
            checkpoint = torch.load(self.weights_path, map_location="cpu", weights_only=True)
        except Exception as exc:
            raise ModelPackageError("weights must be loadable with safe weights_only mode") from exc
        if not isinstance(checkpoint, dict) or "model_state" not in checkpoint:
            raise ModelPackageError("checkpoint must contain model_state")
        return checkpoint


def _legacy_manifest(weights_path: Path) -> dict[str, Any]:
    """Build a temporary manifest for the supplied hand-off checkpoint."""
    try:
        import torch
        checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ModelPackageError("legacy checkpoint cannot be inspected safely") from exc
    data_cfg = checkpoint.get("data_cfg", {})
    model_cfg = checkpoint.get("model_cfg", {})
    return {
        "modelCode": "global_load_forecast",
        "modelVersion": f"legacy-{_sha256(weights_path)[:12]}",
        "adapterCode": "multiscale_conv_transformer_v1",
        "framework": "pytorch",
        "weightsFile": weights_path.name,
        "input": {
            "sourceDataset": "load_hourly",
            "lookback": data_cfg.get("lookback", 512),
            "frequency": "1h",
            "features": ["kwh", "hour_sin", "hour_cos", "dow_sin", "dow_cos"],
        },
        "output": {"target": "total_kwh", "unit": "kWh", "horizon": data_cfg.get("horizon", 24)},
        "checkpointModelConfig": model_cfg,
    }


def _validate_manifest(manifest: Any, weights_path: Path) -> None:
    if not isinstance(manifest, dict):
        raise ModelPackageError("model manifest must be an object")
    required = ("modelCode", "modelVersion", "adapterCode", "framework")
    if any(not isinstance(manifest.get(key), str) or not manifest[key].strip() for key in required):
        raise ModelPackageError("model manifest is missing required identity fields")
    if manifest["framework"].lower() != "pytorch":
        raise ModelPackageError("only pytorch model packages are supported")
    if manifest.get("weightsFile") and Path(str(manifest["weightsFile"])).name != weights_path.name:
        raise ModelPackageError("manifest weightsFile does not match package")
    input_contract = manifest.get("input", {})
    output_contract = manifest.get("output", {})
    if input_contract.get("sourceDataset") != "load_hourly":
        raise ModelPackageError("model input sourceDataset must be load_hourly")
    if int(input_contract.get("lookback", 0)) < 1 or int(output_contract.get("horizon", 0)) < 1:
        raise ModelPackageError("model input lookback and output horizon must be positive")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
