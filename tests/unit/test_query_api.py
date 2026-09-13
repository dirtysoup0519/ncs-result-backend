from datetime import date, datetime, timezone

from ncs_backend.query.app import create_app
from ncs_backend.query.repository import EmptyDashboardRepository, QueryPayload
from ncs_backend.shared.config import Settings


def _app(repository=None):
    return create_app(
        Settings(),
        repository=repository or EmptyDashboardRepository(),
        clock=lambda: datetime(2026, 9, 13, 6, 0, tzinfo=timezone.utc),
    )


def test_overview_uses_frozen_envelope_without_demo_numbers():
    response = _app().test_client().get("/api/v1/dashboard/overview", headers={"X-Trace-Id": "trace-1"})

    assert response.status_code == 200
    assert response.json["code"] == "OK"
    assert response.json["data"] == {"items": []}
    assert response.json["meta"]["requestId"] == "trace-1"
    assert response.json["meta"]["generatedAt"] == "2026-09-13T06:00:00+00:00"
    assert response.json["meta"]["empty"] is True


def test_duration_keeps_the_four_frozen_buckets():
    response = _app().test_client().get("/api/v1/charging/duration-distribution")

    items = response.json["data"]["items"]
    assert [item["bucketCode"] for item in items] == [
        "PT0H_PT1H",
        "PT1H_PT2H",
        "PT2H_PT3H",
        "PT3H_PLUS",
    ]
    assert items[0]["lowerMinutes"] == 0
    assert items[-1]["upperMinutes"] is None


def test_invalid_query_returns_contract_error_shape():
    response = _app().test_client().get("/api/v1/stations/ranking?metric=kwh")

    assert response.status_code == 400
    assert response.json["code"] == "VALIDATION_INVALID_PARAMETER"
    assert response.json["data"] is None
    assert response.json["meta"]["requestId"]
    assert response.json["errors"][0]["field"] == "metric"


def test_prediction_requires_a_cutoff_hour():
    response = _app().test_client().get("/api/v1/predictions/load?date=2019-09-13")

    assert response.status_code == 400
    assert response.json["code"] == "VALIDATION_INVALID_PARAMETER"


def test_metadata_routes_use_the_same_response_meta_contract():
    client = _app().test_client()

    response = client.get("/api/v1/meta/capabilities")
    assert response.status_code == 200
    assert response.json["meta"]["requestId"]
    assert response.json["meta"]["generatedAt"] == "2026-09-13T06:00:00+00:00"
    assert response.json["meta"]["dataVersion"] is None
    overview = next(item for item in response.json["data"]["items"] if item["capabilityCode"] == "overview")
    assert overview["available"] is False
    assert overview["registered"] is True
    assert overview["endpoint"] == "/api/v1/dashboard/overview"
    assert overview["priority"] == "P0"

    manifest = client.get("/api/v1/dashboard/manifest")
    overview = next(item for item in manifest.json["data"]["items"] if item["componentCode"] == "overview")
    assert overview["available"] is False
    assert overview["registered"] is True
    assert overview["endpoint"] == "/api/v1/dashboard/overview"
    assert overview["priority"] == "P0"

    response = client.get("/api/v1/not-a-route")
    assert response.status_code == 404
    assert response.json["code"] == "QUERY_ROUTE_NOT_FOUND"


def test_repository_payload_is_serialized_and_preserves_version():
    repository = EmptyDashboardRepository(
        _resources={
            "overview": QueryPayload(
                data={"items": [{"metricCode": "total_order_count", "value": "12"}]},
                data_date=date(2019, 9, 13),
                data_version="overview:batch-1",
                staleness="FRESH",
                empty=False,
            )
        }
    )
    response = _app(repository).test_client().get("/api/v1/dashboard/overview")

    assert response.status_code == 200
    assert response.json["data"]["items"][0]["value"] == "12"
    assert response.json["meta"]["dataDate"] == "2019-09-13"
    assert response.json["meta"]["dataVersion"] == "overview:batch-1"
    assert response.json["meta"]["staleness"] == "FRESH"

    cached = _app(repository).test_client().get(
        "/api/v1/dashboard/overview",
        headers={"If-None-Match": '"overview:batch-1"'},
    )
    assert cached.status_code == 304
    assert cached.data == b""
    assert cached.headers["ETag"] == '"overview:batch-1"'
