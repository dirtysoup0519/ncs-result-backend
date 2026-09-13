from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.quality import NonNullRule, QualityValidator, RangeRule, SchemaRule, UniqueKeyRule
from ncs_backend.shared.contracts.schema import DatasetSchema, FieldDefinition, FieldType
from ncs_backend.shared.domain.identifiers import DatasetCode, SchemaVersion


def schema() -> DatasetSchema:
    return DatasetSchema(
        dataset_code=DatasetCode("dws.order_hourly"),
        version=SchemaVersion("v1"),
        grain=("data_date", "stat_hour"),
        unique_key=("data_date", "stat_hour"),
        fields=(
            FieldDefinition("data_date", FieldType.DATE),
            FieldDefinition("stat_hour", FieldType.INTEGER),
            FieldDefinition("ratio", FieldType.DECIMAL, unit="ratio"),
        ),
    )


def test_manifest_requires_timezone_and_checksum():
    manifest = DatasetManifest(
        dataset_code=DatasetCode("dws.order_hourly"),
        schema_version=SchemaVersion("v1"),
        data_date=date(2019, 1, 1),
        grain=("data_date", "stat_hour"),
        row_count=1,
        sha256="0" * 64,
        source_uri="example://rows.csv",
        generated_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
    )
    assert manifest.to_dict()["generatedAt"].endswith("Z")
    with pytest.raises(ValueError):
        DatasetManifest(
            manifest.dataset_code,
            manifest.schema_version,
            manifest.data_date,
            manifest.grain,
            manifest.row_count,
            "bad",
            manifest.source_uri,
            manifest.generated_at,
        )


def test_quality_validator_reports_duplicate_null_and_range():
    rows = [
        {"data_date": "2019-01-01", "stat_hour": 0, "ratio": "0.5"},
        {"data_date": "2019-01-01", "stat_hour": 0, "ratio": "1.2"},
        {"data_date": "2019-01-01", "stat_hour": "not-an-hour", "ratio": "0.2"},
        {"data_date": "2019-01-01", "stat_hour": "", "ratio": "0.2"},
    ]
    report = QualityValidator(
        [SchemaRule(), NonNullRule(), UniqueKeyRule(), RangeRule("ratio", Decimal("0"), Decimal("1"))]
    ).validate(rows, schema())
    codes = {issue.rule_code for issue in report.issues}
    assert not report.passed
    assert codes == {"SCHEMA_MISMATCH", "NULL_NOT_ALLOWED", "DUPLICATE_UNIQUE_KEY", "VALUE_OUT_OF_RANGE"}
