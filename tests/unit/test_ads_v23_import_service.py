from pathlib import Path

from ncs_backend.admin.ads_v23_import_service import AdsV23ImportResult, AdsV23ImportService
from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageDescriptor
from ncs_backend.shared.db import SQLITE_DIALECT


class _Reader:
    def read(self, path: Path):
        return AdsV23PackageDescriptor(path, "batch", "2.0.0", "2.0.0", "SUCCESS", "FULL_SNAPSHOT", ())


class _Importer:
    def __init__(self, connection_factory, *, dialect, reader, initialize_schema):
        assert initialize_schema is False

    def import_package(self, package):
        assert package.source_batch_id == "batch"
        return ("load_hourly",)


def test_v23_service_reads_package_and_delegates(tmp_path):
    service = AdsV23ImportService(
        lambda: None,
        dialect=SQLITE_DIALECT,
        reader=_Reader(),
        importer=_Importer,
    )

    result = service.import_package(tmp_path)

    assert result == AdsV23ImportResult("batch", "2.0.0", "2.0.0", ("load_hourly",))
