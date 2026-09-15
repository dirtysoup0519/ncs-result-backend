"""Whitelisted inference adapters for trained model packages."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Protocol

from .model_registry import ModelPackage, ModelPackageError


class PredictionAdapter(Protocol):
    code: str

    def validate(self, package: ModelPackage, checkpoint: dict[str, Any]) -> None: ...
    def load(self, package: ModelPackage, checkpoint: dict[str, Any]) -> Any: ...
    def predict(self, model: Any, dataset: Any, horizon: int) -> list[float]: ...


class AdapterRegistry:
    def __init__(self, adapters: tuple[PredictionAdapter, ...] | None = None) -> None:
        self._adapters = {adapter.code: adapter for adapter in (adapters or (MultiScaleConvTransformerV1(),))}

    def get(self, code: str) -> PredictionAdapter:
        try:
            return self._adapters[code]
        except KeyError as exc:
            raise ModelPackageError(f"unsupported model adapter: {code}") from exc

    def validate_and_load(self, package: ModelPackage) -> tuple[PredictionAdapter, Any, dict[str, Any]]:
        checkpoint = package.load_checkpoint()
        adapter = self.get(package.adapter_code)
        adapter.validate(package, checkpoint)
        return adapter, adapter.load(package, checkpoint), checkpoint


class MultiScaleConvTransformerV1:
    code = "multiscale_conv_transformer_v1"

    def validate(self, package: ModelPackage, checkpoint: dict[str, Any]) -> None:
        data_cfg = checkpoint.get("data_cfg", {})
        features = package.manifest.get("input", {}).get("features", [])
        if features != ["kwh", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]:
            raise ModelPackageError("v1 requires the standard five input features")
        if data_cfg.get("use_state_feats") or data_cfg.get("diff_target") or data_cfg.get("log1p_target"):
            raise ModelPackageError("v1 does not support state, diff, or log targets")
        if int(data_cfg.get("lookback", 0)) != int(package.manifest["input"]["lookback"]):
            raise ModelPackageError("checkpoint lookback does not match manifest")
        if int(data_cfg.get("horizon", 0)) != int(package.manifest["output"]["horizon"]):
            raise ModelPackageError("checkpoint horizon does not match manifest")
        if not isinstance(checkpoint.get("norm"), dict):
            raise ModelPackageError("checkpoint norm statistics are required")

    def load(self, package: ModelPackage, checkpoint: dict[str, Any]) -> Any:
        try:
            import torch
        except ImportError as exc:  # pragma: no cover
            raise ModelPackageError("PyTorch is required for inference") from exc
        data_cfg, model_cfg = checkpoint["data_cfg"], checkpoint["model_cfg"]
        pos_shape = tuple(checkpoint.get("model_state", {}).get("pos.pe", ()).shape)
        max_len = pos_shape[0] if len(pos_shape) == 2 else int(data_cfg["lookback"]) + int(data_cfg["horizon"])
        model = _build_model(5, int(data_cfg["horizon"]), data_cfg["periods"], model_cfg, max_len=max_len)
        try:
            model.load_state_dict(checkpoint["model_state"], strict=True)
        except Exception as exc:
            raise ModelPackageError("checkpoint parameters do not match v1 adapter") from exc
        model.eval()
        return _LoadedV1(model, checkpoint["norm"])

    def predict(self, model: Any, dataset: Any, horizon: int) -> list[float]:
        try:
            import torch
        except ImportError as exc:  # pragma: no cover
            raise ModelPackageError("PyTorch is required for inference") from exc
        tensor = dataset.tensor.clone()
        mean = float(model.norm["mean"][0])
        std = float(model.norm["std"][0])
        tensor[:, :, 0] = (tensor[:, :, 0] - mean) / std
        with torch.no_grad():
            output = model.model(tensor, dataset.calendar_tensor)
        values = output[0].detach().cpu().tolist()[:horizon]
        if len(values) != horizon or any(not math.isfinite(float(value)) for value in values):
            raise ModelPackageError("model returned invalid prediction values")
        return [max(0.0, float(value) * std + mean) for value in values]


@dataclass(frozen=True, slots=True)
class _LoadedV1:
    model: Any
    norm: dict[str, Any]


def _build_model(c_in: int, horizon: int, periods: list[int], config: dict[str, Any], *, max_len: int) -> Any:
    import torch
    import torch.nn as nn

    class CausalConv1d(nn.Module):
        def __init__(self, c_in, c_out, kernel, dilation):
            super().__init__(); self.pad = (kernel - 1) * dilation; self.conv = nn.Conv1d(c_in, c_out, kernel, dilation=dilation)
        def forward(self, x): return self.conv(nn.functional.pad(x, (self.pad, 0)))

    class SEGate(nn.Module):
        def __init__(self, ch, red=4):
            super().__init__(); self.net = nn.Sequential(nn.Linear(ch, max(ch // red, 4)), nn.GELU(), nn.Linear(max(ch // red, 4), ch))
        def forward(self, x): return x * torch.sigmoid(self.net(x.mean(-1))).unsqueeze(-1)

    class MultiScaleConv(nn.Module):
        def __init__(self, c_in, periods, kernel, channels, gate):
            super().__init__(); self.branches = nn.ModuleList([nn.Sequential(CausalConv1d(c_in, channels, kernel, d), nn.GELU(), SEGate(channels) if gate else nn.Identity(), nn.Conv1d(channels, channels, 1)) for d in periods]); self.fuse = nn.Conv1d(c_in + channels * len(periods), c_in, 1); self.norm = nn.LayerNorm(c_in)
        def forward(self, x):
            h = x.transpose(1, 2); out = self.fuse(torch.cat([h] + [branch(h) for branch in self.branches], dim=1)).transpose(1, 2); return self.norm(x + out)

    class PosEncode(nn.Module):
        def __init__(self, d_model, max_len):
            super().__init__(); self.pe = nn.Parameter(torch.zeros(max_len, d_model)); nn.init.trunc_normal_(self.pe, std=0.02)
        def forward(self, x): return x + self.pe[:x.size(1)].unsqueeze(0)

    class Model(nn.Module):
        def __init__(self):
            super().__init__(); blocks = config.get("conv_blocks", 1); gate = config.get("use_scale_gate", False); channels = config["conv_channels"]; d_model = config["d_model"]
            self.horizon = horizon; self.msconv = nn.Sequential(*[MultiScaleConv(c_in, periods, config["conv_kernel"], channels, gate) for _ in range(max(1, blocks))]); self.proj = nn.Linear(c_in, d_model); self.pos = PosEncode(d_model, max_len); enc = nn.TransformerEncoderLayer(d_model, config["nhead"], config["dim_ff"], config["dropout"], batch_first=True, norm_first=True); self.encoder = nn.TransformerEncoder(enc, config["num_encoder_layers"]); dec = nn.TransformerDecoderLayer(d_model, config["nhead"], config["dim_ff"], config["dropout"], batch_first=True, norm_first=True); self.decoder = nn.TransformerDecoder(dec, config["num_decoder_layers"]); self.q_embed = nn.Embedding(horizon, d_model); self.q_cal = nn.Linear(4, d_model); self.head = nn.Linear(d_model, 1)
        def forward(self, x, cal=None):
            h = self.pos(self.proj(self.msconv(x))); memory = self.encoder(h); idx = x.size(1) - 1; q = self.q_embed.weight.unsqueeze(0).expand(x.size(0), -1, -1)
            if cal is not None and cal.size(1) >= idx + 1 + self.horizon: q = q + self.q_cal(cal[:, idx + 1:idx + 1 + self.horizon, :])
            return self.head(self.decoder(q, memory)).squeeze(-1)
    return Model()
