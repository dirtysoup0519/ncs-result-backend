"""Internal CLI for validating a dataset delivery before database import."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.quality import NonNullRule, QualityValidator, RowCountRule, SchemaRule, UniqueKeyRule
from ncs_backend.shared.contracts.schema import DatasetSchema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NCS data administration utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-delivery", help="validate schema, manifest and JSON rows")
    validate.add_argument("--schema", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--data", type=Path, required=True)
    return parser


def validate_delivery(schema_path: Path, manifest_path: Path, data_path: Path) -> dict[str, Any]:
    schema = DatasetSchema.from_dict(json.loads(schema_path.read_text("utf-8")))
    manifest = DatasetManifest.from_dict(json.loads(manifest_path.read_text("utf-8")))
    rows = json.loads(data_path.read_text("utf-8"))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("data must be a JSON array of objects")

    contract_issues: list[dict[str, str]] = []
    if manifest.dataset_code != schema.dataset_code:
        contract_issues.append({"code": "DATASET_CODE_MISMATCH", "message": "manifest and schema differ"})
    if manifest.schema_version != schema.version:
        contract_issues.append({"code": "SCHEMA_VERSION_MISMATCH", "message": "manifest and schema differ"})
    if manifest.grain != schema.grain:
        contract_issues.append({"code": "GRAIN_MISMATCH", "message": "manifest and schema differ"})
    if sha256(data_path.read_bytes()).hexdigest() != manifest.sha256:
        contract_issues.append({"code": "CHECKSUM_MISMATCH", "message": "data checksum does not match manifest"})

    report = QualityValidator(
        [SchemaRule(reject_unknown_fields=True), NonNullRule(), UniqueKeyRule(), RowCountRule(manifest.row_count)]
    ).validate(rows, schema)
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
    issues = contract_issues + quality_issues
    return {
        "passed": not issues,
        "datasetCode": str(schema.dataset_code),
        "schemaVersion": str(schema.version),
        "rowCount": report.row_count,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_delivery(args.schema, args.manifest, args.data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
