"""Reader and integrity validator for the ADS v2.1 export package.

The adapter intentionally stops at immutable in-memory metadata and rows. It
does not execute the supplied SQL, connect to MySQL, or import model files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ncs_backend.admin.adapters.ads_v21_schema import ADS_V21_FILE_SPECS, AdsV21FileSpec, FILE_SPECS_BY_NAME

_HASH_LINE = re.compile(r"^([0-9A-Fa-f]{64})\s+(.+?)\s*$")
SOURCE_BATCH_ID = "ads-sim-v2.1-20260914"


class AdsV21PackageError(ValueError):
    """Raised when a v2.1 package fails structural or integrity validation."""


@dataclass(frozen=True, slots=True)
class AdsV21DatasetDescriptor:
    dataset_code: str
    source_file: str
    schema_version: str
    row_count: int
    field_count: int
    sha256: str
    unique_key: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetCode": self.dataset_code,
            "sourceFile": self.source_file,
            "schemaVersion": self.schema_version,
            "rowCount": self.row_count,
            "fieldCount": self.field_count,
            "sha256": self.sha256,
            "uniqueKey": list(self.unique_key),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AdsV21PackageDescriptor:
    root: Path
    source_batch_id: str
    source_version: str
    status: str
    total_orders: int
    datasets: tuple[AdsV21DatasetDescriptor, ...]
    ignored_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceBatchId": self.source_batch_id,
            "sourceVersion": self.source_version,
            "status": self.status,
            "totalOrders": self.total_orders,
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "ignoredFiles": list(self.ignored_files),
        }


class AdsV21PackageReader:
    """Validate and describe one extracted v2.1 package directory."""

    def read(self, root: Path) -> AdsV21PackageDescriptor:
        package_root = Path(root)
        if not package_root.is_dir():
            raise AdsV21PackageError(f"package directory does not exist: {package_root}")
        manifest = self._read_json(package_root / "manifest.json")
        if manifest.get("status") != "SUCCESS":
            raise AdsV21PackageError("package manifest status must be SUCCESS")
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise AdsV21PackageError("package manifest files must be an object")
        expected_names = {spec.filename for spec in ADS_V21_FILE_SPECS}
        if set(files) != expected_names:
            missing = sorted(expected_names - set(files))
            extra = sorted(set(files) - expected_names)
            raise AdsV21PackageError(f"package manifest file set mismatch; missing={missing}, extra={extra}")
        self._verify_hashes(package_root)

        descriptors: list[AdsV21DatasetDescriptor] = []
        for spec in ADS_V21_FILE_SPECS:
            metadata = files[spec.filename]
            if not isinstance(metadata, dict):
                raise AdsV21PackageError(f"manifest entry must be an object: {spec.filename}")
            rows = self._read_rows(package_root / spec.filename, spec)
            expected_rows = self._positive_int(metadata.get("rows"), f"{spec.filename}.rows")
            expected_fields = self._positive_int(metadata.get("fields"), f"{spec.filename}.fields")
            if len(rows) != expected_rows:
                raise AdsV21PackageError(f"row count mismatch for {spec.filename}: expected {expected_rows}, got {len(rows)}")
            if expected_fields != spec.field_count:
                raise AdsV21PackageError(f"field count mismatch for {spec.filename}: manifest={expected_fields}, schema={spec.field_count}")
            descriptors.append(
                AdsV21DatasetDescriptor(
                    dataset_code=spec.dataset_code,
                    source_file=spec.filename,
                    schema_version="v2.1",
                    row_count=len(rows),
                    field_count=spec.field_count,
                    sha256=_sha256(package_root / spec.filename),
                    unique_key=spec.unique_key,
                    warnings=spec.warnings,
                )
            )

        return AdsV21PackageDescriptor(
            root=package_root.resolve(),
            source_batch_id=SOURCE_BATCH_ID,
            source_version="v2.1",
            status="SUCCESS",
            total_orders=self._positive_int(manifest.get("total_orders"), "total_orders"),
            datasets=tuple(descriptors),
            ignored_files=("ml/",),
        )

    def read_rows(self, package: AdsV21PackageDescriptor, dataset_code: str) -> tuple[dict[str, str], ...]:
        descriptor = next((item for item in package.datasets if item.dataset_code == dataset_code), None)
        if descriptor is None:
            raise AdsV21PackageError(f"dataset is not present in package: {dataset_code}")
        spec = FILE_SPECS_BY_NAME[descriptor.source_file]
        return tuple(self._read_rows(package.root / spec.filename, spec))

    def _read_rows(self, path: Path, spec: AdsV21FileSpec) -> list[dict[str, str]]:
        if not path.is_file():
            raise AdsV21PackageError(f"dataset file does not exist: {spec.filename}")
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdsV21PackageError(f"dataset file must be UTF-8: {spec.filename}") from exc
        reader = csv.reader(io.StringIO(text), delimiter="\t", strict=True)
        field_names = [field.name for field in spec.fields]
        rows: list[dict[str, str]] = []
        try:
            for row_number, values in enumerate(reader, start=1):
                if not values or all(value == "" for value in values):
                    raise AdsV21PackageError(f"blank row in {spec.filename}: {row_number}")
                if len(values) != spec.field_count:
                    raise AdsV21PackageError(
                        f"field count mismatch in {spec.filename} row {row_number}: expected {spec.field_count}, got {len(values)}"
                    )
                rows.append(dict(zip(field_names, values)))
        except csv.Error as exc:
            raise AdsV21PackageError(f"invalid TSV in {spec.filename}: {exc}") from exc
        return rows

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdsV21PackageError(f"invalid package manifest: {path}") from exc
        if not isinstance(value, dict):
            raise AdsV21PackageError("package manifest must be an object")
        return value

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AdsV21PackageError(f"{field} must be a non-negative integer")
        return value

    @staticmethod
    def _hash_entries(path: Path) -> dict[str, str]:
        try:
            lines = path.read_text("utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise AdsV21PackageError("SHA-256 file cannot be read") from exc
        entries: dict[str, str] = {}
        for line in lines:
            match = _HASH_LINE.fullmatch(line)
            if not match:
                raise AdsV21PackageError(f"invalid SHA-256 entry: {line}")
            name = match.group(2).replace("\\", "/")
            if name in entries:
                raise AdsV21PackageError(f"duplicate SHA-256 entry: {name}")
            entries[name] = match.group(1).lower()
        return entries

    def _verify_hashes(self, root: Path) -> None:
        entries = self._hash_entries(root / "文件校验_SHA256.txt")
        for relative_name, expected in entries.items():
            path = root / Path(relative_name)
            if not path.is_file():
                raise AdsV21PackageError(f"SHA-256 entry points to missing file: {relative_name}")
            actual = _sha256(path)
            if actual != expected:
                raise AdsV21PackageError(f"SHA-256 mismatch: {relative_name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
