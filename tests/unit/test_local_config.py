import os

import pytest

from ncs_backend.shared.config import Settings
from ncs_backend.shared.local_config import load_local_config


def test_local_config_loads_ncs_values_without_overriding_environment(tmp_path, monkeypatch):
    config = tmp_path / "ncs.env"
    config.write_text(
        "NCS_QUERY_HOST=0.0.0.0\n"
        "NCS_QUERY_PORT=5100\n"
        "NCS_CORS_ORIGINS=http://localhost:5173, http://127.0.0.1:5173\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NCS_QUERY_HOST", raising=False)
    monkeypatch.delenv("NCS_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("NCS_QUERY_PORT", "5200")

    assert load_local_config(config) == config.resolve()
    settings = Settings.from_env()

    assert settings.query_host == "0.0.0.0"
    assert settings.query_port == 5200
    assert settings.cors_origins == ("http://localhost:5173", "http://127.0.0.1:5173")


def test_local_config_rejects_non_ncs_keys(tmp_path):
    config = tmp_path / "bad.env"
    config.write_text("PATH=unsafe\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid local config key"):
        load_local_config(config)


def test_missing_local_config_is_optional(tmp_path):
    assert load_local_config(tmp_path / "missing.env") is None
