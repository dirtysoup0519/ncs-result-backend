from pathlib import Path

from ncs_backend.admin.cli import main, validate_delivery

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def paths():
    return (
        EXAMPLES / "station-hourly.schema.v1.json",
        EXAMPLES / "station-hourly.manifest.v1.json",
        EXAMPLES / "station-hourly.rows.v1.json",
    )


def test_validate_delivery_accepts_contract_examples():
    result = validate_delivery(*paths())
    assert result["passed"]
    assert result["issues"] == []


def test_admin_cli_returns_success(capsys):
    schema, manifest, data = paths()
    exit_code = main(
        [
            "validate-delivery",
            "--schema",
            str(schema),
            "--manifest",
            str(manifest),
            "--data",
            str(data),
        ]
    )
    assert exit_code == 0
    assert '"passed": true' in capsys.readouterr().out
