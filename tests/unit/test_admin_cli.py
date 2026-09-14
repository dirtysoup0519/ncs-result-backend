from pathlib import Path
import sqlite3

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


def test_control_schema_initialization_is_idempotent(tmp_path, capsys):
    database = tmp_path / "control.sqlite"

    assert main(["init-control-schema", "--sqlite", str(database)]) == 0
    assert main(["init-control-schema", "--sqlite", str(database)]) == 0

    connection = sqlite3.connect(database)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert {
        "ctl_dataset",
        "ctl_schema_version",
        "ctl_import_batch",
        "ctl_quality_result",
        "ctl_publication",
        "ctl_audit_log",
    } <= tables
    assert '"initialized": true' in capsys.readouterr().out


def test_staging_schema_initialization_is_idempotent(tmp_path, capsys):
    database = tmp_path / "staging.sqlite"

    assert main(["init-staging-schema", "--sqlite", str(database)]) == 0
    assert main(["init-staging-schema", "--sqlite", str(database)]) == 0

    connection = sqlite3.connect(database)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert "stg_import_row" in tables
    assert '"initialized": true' in capsys.readouterr().out


def test_versioned_migrations_are_idempotent_and_recorded(tmp_path, capsys):
    database = tmp_path / "migrated.sqlite"

    assert main(["migrate", "--sqlite", str(database)]) == 0
    assert main(["migrate", "--sqlite", str(database)]) == 0

    connection = sqlite3.connect(database)
    migrations = connection.execute(
        "SELECT version, name FROM ctl_schema_migration ORDER BY version"
    ).fetchall()
    connection.close()
    assert migrations == [(1, "control-schema"), (2, "staging-schema")]
    assert '"appliedVersions": []' in capsys.readouterr().out
