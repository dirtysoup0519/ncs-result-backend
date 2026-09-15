from pathlib import Path

import pytest

from scripts import export_dataset, import_data_package


def test_import_wrapper_uses_directory_and_skips_initialized_schema(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    called = []
    monkeypatch.setattr(import_data_package, "load_local_config", lambda path: None)
    monkeypatch.setattr(import_data_package, "import_ads_main", lambda args: called.append(args) or 0)

    assert import_data_package.main([str(package)]) == 0
    assert called == [["--package", str(package.resolve()), "--skip-initialize"]]


def test_import_wrapper_rejects_archive_path_traversal(tmp_path):
    with pytest.raises(SystemExit, match="UNSAFE_ARCHIVE_MEMBER"):
        import_data_package._safe_destination(tmp_path, "../outside.csv")


def test_export_wrapper_defaults_to_all_and_zip(tmp_path, monkeypatch):
    output = tmp_path / "export"
    called = []
    monkeypatch.setattr(export_dataset, "load_local_config", lambda path: None)
    monkeypatch.setattr(export_dataset, "export_main", lambda args: called.append(args) or 0)

    assert export_dataset.main(["--output", str(output)]) == 0
    assert called == [["--dataset", "all", "--output", str(output), "--zip"]]
