"""CORS is what lets the Next.js frontend (a different origin in dev:
localhost:3000 vs the API's localhost:8000) call this API from a browser
at all, so it gets a test rather than being config nobody notices is
broken until the browser console says so.
"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_configured_frontend_origin_is_allowed():
    response = client.get("/health", headers={"Origin": settings.frontend_origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin


def test_preflight_permits_the_post_that_starts_a_research_run():
    # Starting a run is a POST with a JSON-capable content type, so the
    # browser sends a preflight OPTIONS first — if this isn't allowed, the
    # frontend's primary action silently fails.
    response = client.options(
        "/companies/AAPL/research",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin
    assert "POST" in response.headers["access-control-allow-methods"]


def test_unknown_origin_is_not_granted_access():
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert "access-control-allow-origin" not in response.headers
