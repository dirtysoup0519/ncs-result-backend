"""Dataset schema contract independent of storage and transport formats."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from ncs_backend.shared.domain.identifiers import DatasetCode, SchemaVersion

_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class FieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    name: str
    type: FieldType
    nullable: bool = False
    description: str = ""
    unit: str | None = None

    def __post_init__(self) -> None:
        if not _FIELD_NAME.fullmatch(self.name):
            raise ValueError(f"invalid field name: {self.name}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FieldDefinition":
        return cls(
            name=str(value["name"]),
            type=FieldType(value["type"]),
            nullable=bool(value.get("nullable", False)),
            description=str(value.get("description", "")),
            unit=value.get("unit"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.type.value,
            "nullable": self.nullable,
            "description": self.description,
        }
        if self.unit:
            result["unit"] = self.unit
        return result


@dataclass(frozen=True, slots=True)
class DatasetSchema:
    dataset_code: DatasetCode
    version: SchemaVersion
    grain: tuple[str, ...]
    fields: tuple[FieldDefinition, ...]
    unique_key: tuple[str, ...]

    def __post_init__(self) -> None:
        names = [field.name for field in self.fields]
        if not self.fields:
            raise ValueError("schema must contain at least one field")
        if len(names) != len(set(names)):
            raise ValueError("schema field names must be unique")
        if not self.grain:
            raise ValueError("schema grain must not be empty")
        missing_grain = set(self.grain) - set(names)
        missing_key = set(self.unique_key) - set(names)
        if missing_grain:
            raise ValueError(f"grain fields are not defined: {sorted(missing_grain)}")
        if not self.unique_key or missing_key:
            raise ValueError("unique key must be non-empty and reference defined fields")

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(field.name for field in self.fields)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DatasetSchema":
        return cls(
            dataset_code=DatasetCode(str(value["datasetCode"])),
            version=SchemaVersion(str(value["version"])),
            grain=tuple(value["grain"]),
            fields=tuple(FieldDefinition.from_dict(item) for item in value["fields"]),
            unique_key=tuple(value["uniqueKey"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetCode": str(self.dataset_code),
            "version": str(self.version),
            "grain": list(self.grain),
            "fields": [field.to_dict() for field in self.fields],
            "uniqueKey": list(self.unique_key),
        }
