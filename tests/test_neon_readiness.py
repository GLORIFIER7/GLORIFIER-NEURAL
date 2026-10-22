from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_readiness_marks_invalid_opt_in_neon_configuration_degraded(monkeypatch):
    monkeypatch.setenv("GLORIFIER_NEON_CONNECTIVITY_ENABLED", "true")
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "DEGRADED"
    assert "URL is missing" not in response.text
