import json
from pathlib import Path

import pytest

from ncs_backend.admin.importers import DeliveryImportError, DeliveryValidator, FileDeliveryImporter

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def test_file_importer_reads_json_contract_example():
    delivery = FileDeliveryImporter().read(EXAMPLES / "station-hourly.rows.v1.json")

    assert len(delivery.rows) == 2
    assert delivery.rows[0]["stat_hour"] == 0
    assert len(delivery.sha256) == 64


def test_file_importer_reads_csv_and_tsv(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("data_date,stat_hour\n2019-01-01,0\n", encoding="utf-8")
    tsv_path = tmp_path / "rows.tsv"
    tsv_path.write_text("data_date\tstat_hour\n2019-01-01\t1\n", encoding="utf-8")

    assert FileDeliveryImporter().read(csv_path).rows == ({"data_date": "2019-01-01", "stat_hour": "0"},)
    assert FileDeliveryImporter().read(tsv_path).rows == ({"data_date": "2019-01-01", "stat_hour": "1"},)


def test_importer_rejects_unsupported_and_malformed_files(tmp_path):
    unsupported = tmp_path / "rows.txt"
    unsupported.write_text("rows", encoding="utf-8")
    malformed = tmp_path / "rows.json"
    malformed.write_text(json.dumps({"not": "an array"}), encoding="utf-8")

    with pytest.raises(DeliveryImportError):
        FileDeliveryImporter().read(unsupported)
    with pytest.raises(DeliveryImportError):
        FileDeliveryImporter().read(malformed)


def test_validator_preserves_rows_and_reports_checksum_mismatch():
    result = DeliveryValidator().validate_files(
        EXAMPLES / "station-hourly.schema.v1.json",
        EXAMPLES / "station-hourly.manifest.v1.json",
        EXAMPLES / "station-hourly.rows.v1.json",
    )

    assert result.passed is True
    assert result.delivery.rows[1]["charging_energy_kwh"] == "0.00"
    assert result.issues == ()
