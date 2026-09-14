"""Synchronous application service for importing a verified ADS v2.1 package."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ncs_backend.admin.adapters.ads_v21_import import AdsV21A0Importer, AdsV21WaveBImporter
from ncs_backend.admin.adapters.ads_v21_package import AdsV21PackageReader
from ncs_backend.shared.db import DatabaseDialect


@dataclass(frozen=True, slots=True)
class AdsV21ImportResult:
    source_batch_id: str
    source_version: str
    waves: tuple[str, ...]
    published_datasets: tuple[str, ...]


class AdsV21ImportService:
    """Validate and import selected package waves into an initialized result DB."""

    _WAVES = ("A0", "B")

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        dialect: DatabaseDialect,
        reader: Any | None = None,
        a0_importer: type = AdsV21A0Importer,
        wave_b_importer: type = AdsV21WaveBImporter,
    ) -> None:
        self._connection_factory = connection_factory
        self._dialect = dialect
        self._reader = reader or AdsV21PackageReader()
        self._importers = {"A0": a0_importer, "B": wave_b_importer}

    def import_package(self, package_path: str | Path, waves: Iterable[str] = _WAVES) -> AdsV21ImportResult:
        path = Path(package_path).expanduser().resolve()
        selected = _normalize_waves(waves)
        package = self._reader.read(path)
        published: list[str] = []
        for wave in selected:
            importer = self._importers[wave](
                self._connection_factory,
                dialect=self._dialect,
                reader=self._reader,
                initialize_schema=False,
            )
            published.extend(importer.import_package(package))
        return AdsV21ImportResult(
            source_batch_id=package.source_batch_id,
            source_version=package.source_version,
            waves=selected,
            published_datasets=tuple(published),
        )


def _normalize_waves(waves: Iterable[str]) -> tuple[str, ...]:
    if isinstance(waves, (str, bytes)):
        raise ValueError("waves must be an array")
    requested = {str(item).strip().upper() for item in waves}
    invalid = requested - set(AdsV21ImportService._WAVES)
    if invalid:
        raise ValueError(f"unsupported ADS v2.1 wave: {sorted(invalid)}")
    if not requested:
        raise ValueError("at least one ADS v2.1 wave is required")
    return tuple(wave for wave in AdsV21ImportService._WAVES if wave in requested)
