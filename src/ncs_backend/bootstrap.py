"""Composition root for applications backed by one configured database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Flask

from ncs_backend.admin.app import create_app as create_admin_app
from ncs_backend.admin.ads_import_service import AdsV21ImportService
from ncs_backend.admin.ads_v23_import_service import AdsV23ImportService
from ncs_backend.admin.repositories import DbApiControlRepository
from ncs_backend.admin.services import BatchService, DatasetRegistryService, PublicationService, QualityService
from ncs_backend.db_console.app import create_app as create_db_console_app
from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.query.app import create_app as create_query_app
from ncs_backend.query.db_repository import DbApiDashboardRepository
from ncs_backend.prediction.management import PredictionManagementService
from ncs_backend.shared.config import Settings
from ncs_backend.shared.db import DatabaseDialect


@dataclass(frozen=True, slots=True)
class DatabaseComponents:
    connection_factory: Callable[[], Any]
    dialect: DatabaseDialect


def configured_database(settings: Settings) -> DatabaseComponents:
    if not settings.database_url:
        raise ValueError("NCS_DATABASE_URL is required")
    return DatabaseComponents(
        connection_factory_from_url(settings.database_url),
        database_dialect_from_url(settings.database_url),
    )


def configured_admin_app(settings: Settings) -> Flask:
    database = configured_database(settings)
    repository = DbApiControlRepository(database.connection_factory, dialect=database.dialect)
    return create_admin_app(
        settings,
        registry_service=DatasetRegistryService(repository),
        batch_service=BatchService(repository),
        quality_service=QualityService(repository),
        publication_service=PublicationService(repository),
        ads_v21_import_service=AdsV21ImportService(
            database.connection_factory,
            dialect=database.dialect,
        ),
        ads_v23_import_service=AdsV23ImportService(
            database.connection_factory,
            dialect=database.dialect,
        ),
        prediction_service=PredictionManagementService(
            database.connection_factory,
            dialect=database.dialect,
        ),
    )


def configured_query_app(settings: Settings) -> Flask:
    database = configured_database(settings)
    repository = DbApiDashboardRepository(database.connection_factory, dialect=database.dialect)
    return create_query_app(settings, repository=repository)


def configured_db_console_app(settings: Settings) -> Flask:
    database = configured_database(settings)
    return create_db_console_app(settings, connection_factory=database.connection_factory)
