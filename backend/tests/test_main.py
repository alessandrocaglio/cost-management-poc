"""
Tests for FastAPI endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.main import app, get_settings, get_api_client
from app.config import Settings
from app.services.cost_api_client import CostAPIClient


@pytest.fixture
def mock_settings():
    """Mock settings."""
    return Settings(
        cost_client_id="test-id",
        cost_client_secret="test-secret",
        cache_ttl_seconds=900,
        cors_origins="*"
    )


@pytest.fixture
def mock_tag_keys():
    """Mock tag keys response."""
    return ["owner", "team", "env"]


@pytest.fixture
def mock_api_response():
    """Mock API response for costs."""
    return {
        "data": [{
            "groups": [
                {
                    "group": "TeamA",
                    "values": [{"cost": {"total": {"value": 1000.0}}}]
                },
                {
                    "group": "No-owner",
                    "values": [{"cost": {"total": {"value": 500.0}}}]
                }
            ]
        }]
    }


@pytest.fixture
def mock_project_response():
    """Mock API response for project drill-down."""
    return {
        "data": [{
            "groups": [
                {
                    "group": "project-a",
                    "values": [{
                        "cost": {"total": {"value": 300.0}},
                        "usage": {"value": 50.0}
                    }]
                },
                {
                    "group": "project-b",
                    "values": [{
                        "cost": {"total": {"value": 700.0}},
                        "usage": {"value": 150.0}
                    }]
                }
            ]
        }]
    }


@pytest.fixture
def client(mock_settings):
    """Create test client with mocked settings."""
    app.dependency_overrides[get_settings] = lambda: mock_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_api_client_override(mock_api_client):
    """Helper to create a DI override that yields a mock API client."""
    async def override():
        yield mock_api_client
    return override


class TestTagsEndpoint:
    """Tests for /api/tags endpoint."""

    def test_get_tags_success(self, client, mock_settings, mock_tag_keys):
        """Test successful tag keys retrieval."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_available_tag_keys.return_value = mock_tag_keys

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get("/api/tags")

            assert response.status_code == 200
            data = response.json()
            assert data["tags"] == mock_tag_keys
            assert data["count"] == 3
        finally:
            app.dependency_overrides.pop(get_api_client, None)

    def test_get_tags_empty(self, client, mock_settings):
        """Test tags endpoint with no tags."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_available_tag_keys.return_value = []

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get("/api/tags")

            assert response.status_code == 200
            data = response.json()
            assert data["tags"] == []
            assert data["count"] == 0
        finally:
            app.dependency_overrides.pop(get_api_client, None)


class TestCostsEndpoint:
    """Tests for /api/costs endpoint."""

    def test_get_costs_success(self, client, mock_settings, mock_api_response):
        """Test successful distributed costs retrieval."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_costs_by_tag.return_value = mock_api_response

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get("/api/costs?tag_key=owner")

            assert response.status_code == 200
            data = response.json()

            assert "groups" in data
            assert "total_overhead" in data
            assert "total_tracked_cost" in data
            assert "meta" in data

            assert data["meta"]["tag_key"] == "owner"
            assert data["meta"]["untagged_group_name"] == "No-owner"
            assert data["total_overhead"] == 500.0
            assert data["total_tracked_cost"] == 1000.0
        finally:
            app.dependency_overrides.pop(get_api_client, None)

    def test_get_costs_with_custom_dates(self, client, mock_settings, mock_api_response):
        """Test costs endpoint with custom date range."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_costs_by_tag.return_value = mock_api_response

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get(
                "/api/costs?tag_key=owner&start_date=2026-06-01&end_date=2026-06-30"
            )

            assert response.status_code == 200
            data = response.json()
            assert "2026-06-01 to 2026-06-30" in data["meta"]["time_period"]
        finally:
            app.dependency_overrides.pop(get_api_client, None)

    def test_get_costs_missing_tag_key(self, client):
        """Test that tag_key is required."""
        response = client.get("/api/costs")
        assert response.status_code == 422

    def test_get_costs_invalid_time_scope_value(self, client):
        """Test invalid time_scope_value range."""
        response = client.get("/api/costs?tag_key=owner&time_scope_value=1")
        assert response.status_code == 422

    def test_get_costs_with_presets(self, client, mock_settings, mock_api_response):
        """Test costs with different time presets."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_costs_by_tag.return_value = mock_api_response

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get(
                "/api/costs?tag_key=owner&time_scope_units=month&time_scope_value=-1"
            )
            assert response.status_code == 200
            assert "Last month" in response.json()["meta"]["time_period"]

            response = client.get(
                "/api/costs?tag_key=owner&time_scope_units=day&time_scope_value=-3"
            )
            assert response.status_code == 200
            assert "Last 3 days" in response.json()["meta"]["time_period"]
        finally:
            app.dependency_overrides.pop(get_api_client, None)


class TestDrilldownEndpoint:
    """Tests for /api/costs/drilldown endpoint."""

    def test_drilldown_success(self, client, mock_settings, mock_project_response):
        """Test successful project drill-down."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_projects_for_tag.return_value = mock_project_response

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get(
                "/api/costs/drilldown?tag_key=owner&tag_value=TeamA"
            )

            assert response.status_code == 200
            data = response.json()

            assert "projects" in data
            assert "tag_key" in data
            assert "tag_value" in data
            assert "total_cost" in data
            assert "project_count" in data

            assert data["tag_key"] == "owner"
            assert data["tag_value"] == "TeamA"
            assert len(data["projects"]) == 2
            assert data["project_count"] == 2
            assert data["total_cost"] == 1000.0  # 300 + 700

            project_a = next(p for p in data["projects"] if p["project_name"] == "project-a")
            assert project_a["cost"] == 300.0
            assert project_a["usage"] == 50.0
        finally:
            app.dependency_overrides.pop(get_api_client, None)

    def test_drilldown_missing_tag_value(self, client):
        """Test that tag_value is required."""
        response = client.get("/api/costs/drilldown?tag_key=owner")
        assert response.status_code == 422

    def test_drilldown_empty_response(self, client, mock_settings):
        """Test drill-down with no projects."""
        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_projects_for_tag.return_value = {"data": []}

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get(
                "/api/costs/drilldown?tag_key=owner&tag_value=EmptyTeam"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["projects"] == []
            assert data["project_count"] == 0
            assert data["total_cost"] == 0.0
        finally:
            app.dependency_overrides.pop(get_api_client, None)


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "version" in data
        assert data["cache_enabled"] is True
        assert data["cache_ttl_seconds"] == 900


class TestErrorHandling:
    """Tests for error handling."""

    def test_authentication_error(self, client, mock_settings):
        """Test authentication error handling."""
        from app.services.auth_service import AuthenticationError

        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_available_tag_keys.side_effect = AuthenticationError("Auth failed")

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get("/api/tags")

            assert response.status_code == 401
            data = response.json()
            assert data["error"] == "AuthenticationError"
            assert "Auth failed" in data["message"]
        finally:
            app.dependency_overrides.pop(get_api_client, None)

    def test_cost_api_error(self, client, mock_settings):
        """Test Cost API error handling."""
        from app.services.cost_api_client import CostAPIError

        mock_api_client = AsyncMock(spec=CostAPIClient)
        mock_api_client.get_costs_by_tag.side_effect = CostAPIError("API error")

        app.dependency_overrides[get_api_client] = make_api_client_override(mock_api_client)
        app.dependency_overrides[get_settings] = lambda: mock_settings

        try:
            response = client.get("/api/costs?tag_key=owner")

            assert response.status_code == 502
            data = response.json()
            assert data["error"] == "CostAPIError"
            assert "API error" in data["message"]
        finally:
            app.dependency_overrides.pop(get_api_client, None)


class TestCORSConfiguration:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are included in OPTIONS response."""
        response = client.options(
            "/api/health",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
        )
        assert "access-control-allow-origin" in response.headers


class TestTimePeriodDescription:
    """Tests for time period description helper."""

    def test_custom_date_range(self):
        """Test custom date range description."""
        from app.main import build_time_period_description

        result = build_time_period_description(
            "month", -1, "2026-06-01", "2026-06-30"
        )
        assert result == "2026-06-01 to 2026-06-30"

    def test_last_month(self):
        """Test 'last month' description."""
        from app.main import build_time_period_description

        result = build_time_period_description("month", -1)
        assert result == "Last month"

    def test_last_3_days(self):
        """Test 'last 3 days' description."""
        from app.main import build_time_period_description

        result = build_time_period_description("day", -3)
        assert result == "Last 3 days"

    def test_last_2_months(self):
        """Test 'last 2 months' description."""
        from app.main import build_time_period_description

        result = build_time_period_description("month", -2)
        assert result == "Last 2 months"
