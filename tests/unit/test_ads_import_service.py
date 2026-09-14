from pathlib import Path
from types import SimpleNamespace

import pytest

from ncs_backend.admin.ads_import_service import AdsV21ImportService
from ncs_backend.shared.db import SQLITE_DIALECT


class _Reader:
    def read(self, path):
        return SimpleNamespace(source_batch_id="ads-1", source_version="v2.1", root=path)


class _Importer:
    calls = []

    def __init__(self, factory, **kwargs):
        self.__class__.calls.append(kwargs)

    def import_package(self, package):
        return ("dataset",)


def test_service_imports_waves_in_stable_order(tmp_path):
    _Importer.calls = []
    service = AdsV21ImportService(
        lambda: None,
        dialect=SQLITE_DIALECT,
        reader=_Reader(),
        a0_importer=_Importer,
        wave_b_importer=_Importer,
    )

    result = service.import_package(tmp_path, ["b", "a0"])

    assert result.waves == ("A0", "B")
    assert result.published_datasets == ("dataset", "dataset")
    assert all(call["initialize_schema"] is False for call in _Importer.calls)


@pytest.mark.parametrize("waves", [[], ["C"], "A0"])
def test_service_rejects_invalid_waves(tmp_path, waves):
    service = AdsV21ImportService(lambda: None, dialect=SQLITE_DIALECT, reader=_Reader())

    with pytest.raises(ValueError):
        service.import_package(Path(tmp_path), waves)
