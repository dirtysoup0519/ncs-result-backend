from ncs_backend.admin.app import create_app as create_admin_app
from ncs_backend.query.app import create_app as create_query_app
from ncs_backend.shared.config import Settings


def test_query_live_and_ready_are_distinct():
    client = create_query_app(Settings()).test_client()
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert live.json["data"]["status"] == "alive"
    assert ready.status_code == 503
    assert ready.json["code"] == "DEPENDENCY_NOT_READY"


def test_admin_preserves_trace_id():
    client = create_admin_app(Settings(database_url="mysql://test" )).test_client()
    response = client.get("/health/live", headers={"X-Trace-Id": "test-trace"})
    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == "test-trace"
