from pathlib import Path
import zipfile

import pytest

from scripts.package_frontend_handoff import _verify_archive


def test_handoff_archive_accepts_tracked_source_files(tmp_path):
    archive = tmp_path / "handoff.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("README.md", "safe")
        output.writestr("config/handoff.example", "placeholders only")

    _verify_archive(archive)

    assert archive.exists()


@pytest.mark.parametrize("name", [".env", ".local/ncs.env", "data/local.sqlite", "secret.pem"])
def test_handoff_archive_rejects_local_secret_or_database_files(tmp_path, name):
    archive = tmp_path / "handoff.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, "unsafe")

    with pytest.raises(RuntimeError, match="forbidden files"):
        _verify_archive(archive)

    assert not archive.exists()


def test_handoff_archive_rejects_embedded_database_password(tmp_path):
    archive = tmp_path / "handoff.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("settings.txt", "mysql+pymysql://reader:real-password@localhost/ncs")

    with pytest.raises(RuntimeError, match="forbidden files"):
        _verify_archive(archive)
