from fastapi.testclient import TestClient

from app.main import app


def test_ping_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
