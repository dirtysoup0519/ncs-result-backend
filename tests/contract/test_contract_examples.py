import json
from hashlib import sha256
from pathlib import Path

from ncs_backend.shared.contracts.manifest import DatasetManifest
from ncs_backend.shared.contracts.quality import NonNullRule, QualityValidator, RowCountRule, SchemaRule, UniqueKeyRule
from ncs_backend.shared.contracts.schema import DatasetSchema

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def test_example_manifest_schema_and_rows_agree():
    rows_path = EXAMPLES / "station-hourly.rows.v1.json"
    schema = DatasetSchema.from_dict(json.loads((EXAMPLES / "station-hourly.schema.v1.json").read_text("utf-8")))
    manifest = DatasetManifest.from_dict(
        json.loads((EXAMPLES / "station-hourly.manifest.v1.json").read_text("utf-8"))
    )
    rows = json.loads(rows_path.read_text("utf-8"))
    report = QualityValidator(
        [SchemaRule(reject_unknown_fields=True), NonNullRule(), UniqueKeyRule(), RowCountRule(manifest.row_count)]
    ).validate(rows, schema)

    assert manifest.dataset_code == schema.dataset_code
    assert manifest.schema_version == schema.version
    assert manifest.grain == schema.grain
    assert sha256(rows_path.read_bytes()).hexdigest() == manifest.sha256
    assert report.passed
    assert report.row_count == manifest.row_count
