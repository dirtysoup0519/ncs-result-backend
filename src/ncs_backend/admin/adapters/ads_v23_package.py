"""Reader and integrity validator for the versioned ADS contract package."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ncs_backend.admin.adapters.ads_v23_schema import (
    AdsV23DatasetSpec,
    specs_for_schema_version,
)


class AdsV23PackageError(ValueError):
    """Raised when an ADS package violates its manifest or CSV contract."""


@dataclass(frozen=True, slots=True)
class AdsV23DatasetDescriptor:
    dataset_code: str
    source_file: str
    row_count: int
    fields: tuple[str, ...]
    primary_key: tuple[str, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class AdsV23PackageDescriptor:
    root: Path
    source_batch_id: str
    schema_version: str
    metric_version: str
    status: str
    load_mode: str
    datasets: tuple[AdsV23DatasetDescriptor, ...]


class AdsV23PackageReader:
    """Validate one extracted package without executing its SQL or ML files."""

    def read(self, root: str | Path) -> AdsV23PackageDescriptor:
        package_root = Path(root).expanduser()
        contract_root = self._locate_contract_root(package_root)
        if not contract_root.is_dir():
            raise AdsV23PackageError(f"package directory does not exist: {package_root}")
        manifest = self._read_json(contract_root / "manifest.json")
        if manifest.get("status") != "SUCCESS":
            raise AdsV23PackageError("package manifest status must be SUCCESS")
        entries = manifest.get("datasets")
        if not isinstance(entries, list):
            raise AdsV23PackageError("package manifest datasets must be an array")
        schema_version = self._required_string(manifest, "schemaVersion")
        try:
            specs = specs_for_schema_version(schema_version)
        except ValueError as exc:
            raise AdsV23PackageError(str(exc)) from exc
        by_code = {entry.get("datasetCode"): entry for entry in entries if isinstance(entry, dict)}
        expected_codes = {spec.dataset_code for spec in specs}
        if set(by_code) != expected_codes:
            raise AdsV23PackageError(
                f"package dataset set mismatch; missing={sorted(expected_codes - set(by_code))}, "
                f"extra={sorted(set(by_code) - expected_codes)}"
            )

        descriptors: list[AdsV23DatasetDescriptor] = []
        for spec in specs:
            entry = by_code[spec.dataset_code]
            if entry.get("file") != spec.filename:
                raise AdsV23PackageError(f"unexpected file for {spec.dataset_code}: {entry.get('file')}")
            path = self._safe_path(contract_root, spec.filename)
            if not path.is_file():
                raise AdsV23PackageError(f"required dataset file is missing: {spec.filename}")
            actual_hash = _sha256(path)
            if str(entry.get("checksum", "")).lower() != actual_hash:
                raise AdsV23PackageError(f"SHA-256 mismatch: {spec.filename}")
            fields = entry.get("fields")
            if fields != list(spec.fields):
                raise AdsV23PackageError(f"field contract mismatch: {spec.dataset_code}")
            if entry.get("primaryKey") != list(spec.primary_key):
                raise AdsV23PackageError(f"primary key contract mismatch: {spec.dataset_code}")
            rows = self._read_rows(path, spec)
            expected_rows = self._non_negative_int(entry.get("rowCount"), f"{spec.dataset_code}.rowCount")
            if len(rows) != expected_rows:
                raise AdsV23PackageError(
                    f"row count mismatch for {spec.dataset_code}: expected {expected_rows}, got {len(rows)}"
                )
            descriptors.append(AdsV23DatasetDescriptor(
                dataset_code=spec.dataset_code,
                source_file=spec.filename,
                row_count=len(rows),
                fields=spec.fields,
                primary_key=spec.primary_key,
                sha256=actual_hash,
            ))
        return AdsV23PackageDescriptor(
            root=contract_root.resolve(),
            source_batch_id=self._required_string(manifest, "batchId"),
            schema_version=schema_version,
            metric_version=self._required_string(manifest, "metricVersion"),
            status="SUCCESS",
            load_mode=self._required_string(manifest, "loadMode"),
            datasets=tuple(descriptors),
        )

    @staticmethod
    def _locate_contract_root(package_root: Path) -> Path:
        if not package_root.is_dir():
            return package_root
        direct = package_root / "contract_v2"
        if direct.is_dir():
            return direct
        candidates = [path for path in package_root.glob("**/contract_v2") if path.is_dir()]
        if len(candidates) == 1:
            return candidates[0]
        return package_root

    def read_rows(self, package: AdsV23PackageDescriptor, dataset_code: str) -> tuple[dict[str, str], ...]:
        try:
            specs = specs_for_schema_version(package.schema_version)
        except ValueError as exc:
            raise AdsV23PackageError(str(exc)) from exc
        spec = next((item for item in specs if item.dataset_code == dataset_code), None)
        if spec is None:
            raise AdsV23PackageError(f"dataset is not present in package: {dataset_code}")
        return tuple(self._read_rows(package.root / spec.filename, spec))

    def _read_rows(self, path: Path, spec: AdsV23DatasetSpec) -> list[dict[str, str]]:
        if not path.is_file():
            raise AdsV23PackageError(f"dataset file does not exist: {spec.filename}")
        try:
            # Spark's CSV writer may emit a UTF-8 BOM; accept it only at the
            # beginning of the header while still rejecting other encodings.
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != list(spec.fields):
                    raise AdsV23PackageError(f"CSV header mismatch: {spec.filename}")
                rows: list[dict[str, str]] = []
                seen: set[tuple[str, ...]] = set()
                for row_number, row in enumerate(reader, start=2):
                    if None in row or any(value is None for value in row.values()):
                        raise AdsV23PackageError(f"invalid CSV row in {spec.filename}: {row_number}")
                    values = tuple(row[field] for field in spec.primary_key)
                    if any(value == "" for value in values):
                        raise AdsV23PackageError(f"blank primary key in {spec.filename}: {row_number}")
                    if values in seen:
                        raise AdsV23PackageError(f"duplicate primary key in {spec.filename}: {row_number}")
                    seen.add(values)
                    rows.append({field: row[field] for field in spec.fields})
                return rows
        except UnicodeDecodeError as exc:
            raise AdsV23PackageError(f"dataset file must be UTF-8: {spec.filename}") from exc
        except csv.Error as exc:
            raise AdsV23PackageError(f"invalid CSV in {spec.filename}: {exc}") from exc

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdsV23PackageError(f"invalid package manifest: {path}") from exc
        if not isinstance(value, dict):
            raise AdsV23PackageError("package manifest must be an object")
        return value

    @staticmethod
    def _safe_path(root: Path, filename: str) -> Path:
        path = (root / filename).resolve()
        if root.resolve() not in path.parents:
            raise AdsV23PackageError(f"manifest file escapes contract root: {filename}")
        return path

    @staticmethod
    def _required_string(value: dict[str, Any], field: str) -> str:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise AdsV23PackageError(f"manifest field {field} must be a non-empty string")
        return item

    @staticmethod
    def _non_negative_int(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AdsV23PackageError(f"{field} must be a non-negative integer")
        return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
