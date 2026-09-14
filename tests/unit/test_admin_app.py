import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ncs_backend.admin.app import create_app
from ncs_backend.admin.migrations import initialize_control_schema, initialize_staging_schema
from ncs_backend.admin.repositories import DbApiControlRepository
from ncs_backend.admin.services import BatchService, DatasetRegistryService, PublicationService, QualityService
from ncs_backend.shared.config import Settings
from ncs_backend.shared.domain.enums import BatchStatus

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def _client(tmp_path):
    database = tmp_path / "admin-api.sqlite"
    connection = sqlite3.connect(database)
    initialize_control_schema(connection)
    initialize_staging_schema(connection)
    connection.close()
    repository = DbApiControlRepository(lambda: sqlite3.connect(database))
    clock = lambda: datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    app = create_app(
        Settings(database_url="sqlite:///admin-api.sqlite"),
        registry_service=DatasetRegistryService(repository, clock),
        batch_service=BatchService(repository, clock),
        quality_service=QualityService(repository, clock),
        publication_service=PublicationService(repository, clock),
    )
    return app.test_client(), repository


class _FakeAdsImportService:
    def __init__(self):
        self.calls = []

    def import_package(self, package_path, waves):
        from ncs_backend.admin.ads_import_service import AdsV21ImportResult

        self.calls.append((package_path, waves))
        return AdsV21ImportResult("ads-batch", "v2.1", tuple(waves), ("dashboard_overview",))


class _FakeAdsV23ImportService:
    def __init__(self):
        self.calls = []

    def import_package(self, package_path):
        from ncs_backend.admin.ads_v23_import_service import AdsV23ImportResult

        self.calls.append(package_path)
        return AdsV23ImportResult("ads-v23-batch", "2.0.0", "2.0.0", ("load_hourly",))


def _schema_payload():
    return json.loads((EXAMPLES / "station-hourly.schema.v1.json").read_text("utf-8"))


def _manifest_payload():
    return json.loads((EXAMPLES / "station-hourly.manifest.v1.json").read_text("utf-8"))


def test_admin_api_registers_dataset_and_creates_job(tmp_path):
    client, _ = _client(tmp_path)
    registered = client.post(
        "/internal/v1/datasets",
        json={
            "displayName": "Hourly order statistics",
            "owner": "warehouse",
            "schema": _schema_payload(),
        },
    )
    assert registered.status_code == 201
    assert registered.get_json()["data"]["dataset"]["current_schema_version"] == "v1"

    created = client.post(
        "/internal/v1/import-jobs",
        json={"manifest": _manifest_payload(), "sourceBatchId": "ods-api-1", "batchId": "batch-api-1"},
    )
    assert created.status_code == 201
    assert created.get_json()["data"]["status"] == "CREATED"
    fetched = client.get("/internal/v1/import-jobs/batch-api-1")
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["source_batch_id"] == "ods-api-1"
    datasets = client.get("/internal/v1/datasets")
    assert datasets.status_code == 200
    assert datasets.get_json()["data"]["items"][0]["dataset_code"] == "dws.order_hourly"
    schemas = client.get("/internal/v1/datasets/dws.order_hourly/schemas")
    assert schemas.status_code == 200
    assert schemas.get_json()["data"]["items"][0]["schema_version"] == "v1"


def test_admin_api_validates_publishes_and_rolls_back(tmp_path):
    client, repository = _client(tmp_path)
    created = client.post(
        "/internal/v1/import-jobs",
        json={"manifest": _manifest_payload(), "sourceBatchId": "ods-api-1", "batchId": "batch-api-1"},
    )
    assert created.status_code == 201
    from ncs_backend.shared.domain.identifiers import BatchId

    batch_service = BatchService(repository)
    batch_service.transition(BatchId("batch-api-1"), BatchStatus.LOADING)
    batch_service.transition(BatchId("batch-api-1"), BatchStatus.VALIDATING)

    validated = client.post(
        "/internal/v1/import-jobs/batch-api-1/validate",
        json={
            "results": [
                {
                    "ruleCode": "schema",
                    "severity": "BLOCKER",
                    "passed": True,
                    "checkedRowCount": 2,
                    "failureCount": 0,
                }
            ]
        },
    )
    assert validated.status_code == 200
    assert validated.get_json()["data"]["status"] == "READY"

    published = client.post("/internal/v1/import-jobs/batch-api-1/publish", json={"actor": "operator"})
    assert published.status_code == 200
    assert published.get_json()["data"]["status"] == "PUBLISHED"
    publications = client.get("/internal/v1/publications?datasetCode=dws.order_hourly")
    assert publications.status_code == 200
    assert len(publications.get_json()["data"]["items"]) == 1
    publication_id = publications.get_json()["data"]["items"][0]["publication_id"]
    publication_detail = client.get(f"/internal/v1/publications/{publication_id}")
    assert publication_detail.status_code == 200
    assert publication_detail.get_json()["data"]["publication_id"] == publication_id
    active = client.get("/internal/v1/datasets/dws.order_hourly/active-publication")
    assert active.status_code == 200
    assert active.get_json()["data"]["status"] == "PUBLISHED"

    listed_jobs = client.get("/internal/v1/import-jobs?status=PUBLISHED")
    assert listed_jobs.status_code == 200
    assert listed_jobs.get_json()["data"]["items"][0]["batch_id"] == "batch-api-1"
    quality_results = client.get("/internal/v1/quality-results?severity=blocker")
    assert quality_results.status_code == 200
    assert len(quality_results.get_json()["data"]["items"]) == 1

    missing_actor = client.post("/internal/v1/import-jobs/batch-api-1/publish", json={})
    assert missing_actor.status_code == 400
    assert missing_actor.get_json()["code"] == "AUTH_ACTOR_REQUIRED"


def test_admin_api_returns_json_for_unknown_route(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/internal/v1/not-a-route")

    assert response.status_code == 404
    assert response.get_json()["code"] == "ADMIN_ROUTE_NOT_FOUND"


def test_admin_api_imports_selected_ads_v21_waves(tmp_path):
    service = _FakeAdsImportService()
    app = create_app(
        Settings(database_url="sqlite:///admin-api.sqlite"),
        ads_v21_import_service=service,
    )

    response = app.test_client().post(
        "/internal/v1/ads-v21/imports",
        json={"packagePath": "C:/delivery/ads-v21", "waves": ["A0"], "actor": "student"},
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["import"]["source_batch_id"] == "ads-batch"
    assert response.get_json()["data"]["actor"] == "student"
    assert service.calls == [("C:/delivery/ads-v21", ["A0"])]


def test_admin_api_rejects_invalid_ads_v21_request():
    client = create_app(Settings(), ads_v21_import_service=_FakeAdsImportService()).test_client()

    missing_path = client.post("/internal/v1/ads-v21/imports", json={"actor": "student"})
    invalid_waves = client.post(
        "/internal/v1/ads-v21/imports",
        json={"packagePath": "C:/delivery", "waves": "A0", "actor": "student"},
    )

    assert missing_path.status_code == 400
    assert invalid_waves.status_code == 400


def test_admin_api_imports_ads_v23_package():
    service = _FakeAdsV23ImportService()
    app = create_app(Settings(database_url="sqlite:///admin-api.sqlite"), ads_v23_import_service=service)

    response = app.test_client().post(
        "/internal/v1/ads-v23/imports",
        json={"packagePath": "C:/delivery/ads-v23", "actor": "student"},
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["import"]["source_batch_id"] == "ads-v23-batch"
    assert response.get_json()["data"]["actor"] == "student"
    assert service.calls == ["C:/delivery/ads-v23"]


def test_admin_api_rejects_invalid_ads_v23_request():
    client = create_app(Settings(), ads_v23_import_service=_FakeAdsV23ImportService()).test_client()

    response = client.post("/internal/v1/ads-v23/imports", json={"actor": "student"})

    assert response.status_code == 400
    assert response.get_json()["code"] == "VALIDATION_INVALID_PARAMETER"
