"""Controlled local delivery readers and contract validation.

This module stops at an immutable in-memory delivery package.  It does not
write result tables or accept arbitrary SQL; staging writers can consume the
package after the upstream delivery format and database are confirmed.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Protocol

from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.quality import NonNullRule, QualityValidator, RowCountRule, SchemaRule, UniqueKeyRule
from ncs_backend.shared.contracts.schema import DatasetSchema
from ncs_backend.shared.errors import AppError

Row = dict[str, Any]


class DeliveryImportError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("IMPORT_DELIVERY_INVALID", message, 422)


@dataclass(frozen=True, slots=True)
class DeliveryPackage:
    source_path: Path
    rows: tuple[Row, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class DeliveryValidation:
    passed: bool
    dataset_code: str
    schema_version: str
    row_count: int
    issues: tuple[dict[str, Any], ...]
    delivery: DeliveryPackage


class DeliveryImporter(Protocol):
    def read(self, source_path: Path) -> DeliveryPackage: ...


class FileDeliveryImporter:
    """Read UTF-8 JSON, CSV or TSV files from a local controlled workspace."""

    _DELIMITERS = {".csv": ",", ".tsv": "\t"}

    def read(self, source_path: Path) -> DeliveryPackage:
        path = Path(source_path)
        if not path.is_file():
            raise DeliveryImportError(f"delivery file does not exist: {path}")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeliveryImportError("delivery file must be UTF-8") from exc

        suffix = path.suffix.lower()
        if suffix == ".json":
            rows = self._read_json(text)
        elif suffix in self._DELIMITERS:
            rows = self._read_delimited(text, self._DELIMITERS[suffix])
        else:
            raise DeliveryImportError("only .json, .csv and .tsv deliveries are supported")
        return DeliveryPackage(path, tuple(rows), sha256(raw).hexdigest())

    def _read_json(self, text: str) -> list[Row]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeliveryImportError(f"invalid JSON delivery: {exc.msg}") from exc
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise DeliveryImportError("JSON delivery must be an array of objects")
        return [dict(row) for row in value]

    def _read_delimited(self, text: str, delimiter: str) -> list[Row]:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if reader.fieldnames is None or not reader.fieldnames:
            raise DeliveryImportError("delimited delivery must contain a header row")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise DeliveryImportError("delimited delivery contains duplicate column names")
        rows: list[Row] = []
        for index, row in enumerate(reader, start=2):
            if None in row:
                raise DeliveryImportError(f"delimited row {index} has more values than the header")
            if any(value is None for value in row.values()):
                raise DeliveryImportError(f"delimited row {index} has fewer values than the header")
            rows.append(dict(row))
        return rows


class DeliveryValidator:
    """Validate a delivery package against its schema and manifest."""

    def __init__(self, importer: DeliveryImporter | None = None) -> None:
        self._importer = importer or FileDeliveryImporter()

    def validate(self, schema: DatasetSchema, manifest: DatasetManifest, delivery: DeliveryPackage) -> DeliveryValidation:
        contract_issues: list[dict[str, Any]] = []
        if manifest.dataset_code != schema.dataset_code:
            contract_issues.append({"code": "DATASET_CODE_MISMATCH", "message": "manifest and schema differ"})
        if manifest.schema_version != schema.version:
            contract_issues.append({"code": "SCHEMA_VERSION_MISMATCH", "message": "manifest and schema differ"})
        if manifest.grain != schema.grain:
            contract_issues.append({"code": "GRAIN_MISMATCH", "message": "manifest and schema differ"})
        if delivery.sha256 != manifest.sha256:
            contract_issues.append({"code": "CHECKSUM_MISMATCH", "message": "data checksum does not match manifest"})

        report = QualityValidator(
            [SchemaRule(reject_unknown_fields=True), NonNullRule(), UniqueKeyRule(), RowCountRule(manifest.row_count)]
        ).validate(delivery.rows, schema)
        quality_issues = [
            {
                "code": issue.rule_code,
                "message": issue.message,
                "rowIndex": issue.row_index,
                "field": issue.field,
                "severity": issue.severity.value,
            }
            for issue in report.issues
        ]
        issues = tuple(contract_issues + quality_issues)
        return DeliveryValidation(
            passed=not issues,
            dataset_code=str(schema.dataset_code),
            schema_version=str(schema.version),
            row_count=report.row_count,
            issues=issues,
            delivery=delivery,
        )

    def validate_files(self, schema_path: Path, manifest_path: Path, data_path: Path) -> DeliveryValidation:
        try:
            schema = DatasetSchema.from_dict(json.loads(Path(schema_path).read_text("utf-8")))
            manifest = DatasetManifest.from_dict(json.loads(Path(manifest_path).read_text("utf-8")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise DeliveryImportError(f"invalid schema or manifest: {exc}") from exc
        return self.validate(schema, manifest, self._importer.read(Path(data_path)))
