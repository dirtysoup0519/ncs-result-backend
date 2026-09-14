"""Load an optional ignored local configuration file without dependencies."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_config(path: str | Path | None = None) -> Path | None:
    """Load NCS_* values without overriding an already configured environment."""

    target = Path(path or os.getenv("NCS_LOCAL_CONFIG", ".local/ncs.env"))
    if not target.is_file():
        return None
    for line_number, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid local config line {line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key.startswith("NCS_") or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid local config key on line {line_number}")
        os.environ.setdefault(key, value)
    return target.resolve()
