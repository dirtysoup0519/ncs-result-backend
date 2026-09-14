"""Application service for importing a verified ADS Spark v2.3 package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ncs_backend.admin.adapters.ads_v23_import import AdsV23Importer
from ncs_backend.admin.adapters.ads_v23_package import AdsV23PackageReader
from ncs_backend.shared.db import DatabaseDialect


@dataclass(frozen=True, slots=True)
class AdsV23ImportResult:
    source_batch_id: str
    schema_version: str
    metric_version: str
    published_datasets: tuple[str, ...]


class AdsV23ImportService:
    """Validate and import one v2.3 package using the configured database."""

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        dialect: DatabaseDialect,
        reader: AdsV23PackageReader | None = None,
        importer: type[AdsV23Importer] = AdsV23Importer,
    ) -> None:
        self._connection_factory = connection_factory
        self._dialect = dialect
        self._reader = reader or AdsV23PackageReader()
        self._importer = importer

    def import_package(self, package_path: str | Path) -> AdsV23ImportResult:
        package = self._reader.read(Path(package_path).expanduser().resolve())
        published = self._importer(
            self._connection_factory,
            dialect=self._dialect,
            reader=self._reader,
            initialize_schema=False,
        ).import_package(package)
        return AdsV23ImportResult(
            source_batch_id=package.source_batch_id,
            schema_version=package.schema_version,
            metric_version=package.metric_version,
            published_datasets=published,
        )
