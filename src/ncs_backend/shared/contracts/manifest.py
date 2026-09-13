"""Manifest contract for a single immutable dataset delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping

from ncs_backend.shared.domain.identifiers import DatasetCode, SchemaVersion

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_code: DatasetCode
    schema_version: SchemaVersion
    data_date: date
    grain: tuple[str, ...]
    row_count: int
    sha256: str
    source_uri: str
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.row_count < 0:
            raise ValueError("row_count must be >= 0")
        if not self.grain:
            raise ValueError("grain must not be empty")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        if not self.source_uri:
            raise ValueError("source_uri must not be empty")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include timezone")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DatasetManifest":
        generated_at = datetime.fromisoformat(str(value["generatedAt"]).replace("Z", "+00:00"))
        return cls(
            dataset_code=DatasetCode(str(value["datasetCode"])),
            schema_version=SchemaVersion(str(value["schemaVersion"])),
            data_date=date.fromisoformat(str(value["dataDate"])),
            grain=tuple(value["grain"]),
            row_count=int(value["rowCount"]),
            sha256=str(value["sha256"]),
            source_uri=str(value["sourceUri"]),
            generated_at=generated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        generated_at = self.generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "datasetCode": str(self.dataset_code),
            "schemaVersion": str(self.schema_version),
            "dataDate": self.data_date.isoformat(),
            "grain": list(self.grain),
            "rowCount": self.row_count,
            "sha256": self.sha256,
            "sourceUri": self.source_uri,
            "generatedAt": generated_at,
        }
