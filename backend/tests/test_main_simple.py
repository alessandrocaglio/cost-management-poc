"""
Simple smoke tests for FastAPI application.

These tests verify the app structure and endpoint existence.
Full integration tests with real credentials are in test_integration.py
"""

import pytest
from fastapi.testclient import TestClient

# Create a test-safe version of the app
from app.config import Settings
from app.main import app, get_settings


@pytest.fixture
def mock_settings():
    """Provide test settings."""
    return Settings(
        _env_file=None,
        cost_client_id="test-id",
        cost_client_secret="test-secret"
    )


@pytest.fixture
def client(mock_settings):
    """Create test client with mocked settings."""
    app.dependency_overrides[get_settings] = lambda: mock_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_app_exists():
    """Test that the FastAPI app is created."""
    assert app is not None
    assert app.title == "Cost Management Redux API"


def test_app_version():
    """Test that version is set."""
    assert app.version == "0.1.0"


def test_openapi_schema_generated(client):
    """Test that OpenAPI schema is available."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema


def test_docs_endpoint_exists(client):
    """Test that Swagger UI is available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_endpoint_exists(client):
    """Test that ReDoc is available."""
    response = client.get("/redoc")
    assert response.status_code == 200


def test_api_endpoints_in_schema(client):
    """Test that all expected endpoints are in the OpenAPI schema."""
    response = client.get("/openapi.json")
    schema = response.json()
    paths = schema["paths"]

    # Check all expected endpoints exist
    assert "/api/tags" in paths
    assert "/api/costs" in paths
    assert "/api/costs/drilldown" in paths
    assert "/api/health" in paths


def test_health_endpoint_structure(client):
    """Test health endpoint returns correct structure (without auth)."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert "status" in data
    assert "version" in data
    assert "cache_enabled" in data
    assert "cache_ttl_seconds" in data


def test_costs_endpoint_requires_tag_key(client):
    """Test that tag_key parameter is required."""
    response = client.get("/api/costs")
    # Should return 422 validation error
    assert response.status_code == 422


def test_drill_down_requires_parameters(client):
    """Test that drill-down requires tag_key and tag_value."""
    response = client.get("/api/costs/drilldown")
    assert response.status_code == 422  # Missing required params
