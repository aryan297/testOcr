from fastapi.testclient import TestClient
from app import app


def test_health():
    """Test health endpoint."""
    c = TestClient(app)
    r = c.get("/ocr/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] == "ok"
    assert "modelsLoaded" in data
    assert "uptimeSec" in data

