from fastapi.testclient import TestClient
from app.main import app


def test_client_workflow_endpoints_are_documented():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()["paths"]
    for path in ["/batches", "/batches/{batch_id}/files/{source}", "/demo/run", "/reconcile/run", "/audit/verify"]:
        assert path in schema


def test_health_check():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
