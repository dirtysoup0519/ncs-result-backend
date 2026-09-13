"""Validated identifiers shared across data, API and ML contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def _validate(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _CODE.fullmatch(value):
        raise ValueError(f"{field_name} must match {_CODE.pattern}")
    return value


@dataclass(frozen=True, slots=True)
class DatasetCode:
    value: str

    def __post_init__(self) -> None:
        _validate(self.value, "dataset code")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SchemaVersion:
    value: str

    def __post_init__(self) -> None:
        _validate(self.value, "schema version")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class BatchId:
    value: str

    def __post_init__(self) -> None:
        _validate(self.value, "batch id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ModelVersion:
    value: str

    def __post_init__(self) -> None:
        _validate(self.value, "model version")

    def __str__(self) -> str:
        return self.value
