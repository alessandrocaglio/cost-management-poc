"""
Tests for Cost Management API Client
"""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.cost_api_client import CostAPIClient, CostAPIError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        _env_file=None,
        cost_client_id="test-id",
        cost_client_secret="test-secret",
        cost_api_base_url="https://console.redhat.com/api/cost-management/v1",
        cache_ttl_seconds=900
    )


@pytest.fixture
def mock_auth_service(mock_settings):
    """Create mock auth service."""
    auth = AuthService(mock_settings)
    auth.get_token = AsyncMock(return_value="test-token-12345")
    return auth


@pytest.fixture
def mock_tag_keys_response():
    """Mock response for tag keys endpoint."""
    return {
        "data": [
            {"key": "owner", "values": ["TeamA", "TeamB"]},
            {"key": "env", "values": ["prod", "dev"]},
            {"key": "team", "values": ["platform", "apps"]}
        ]
    }


@pytest.fixture
def mock_costs_response():
    """Mock response for costs endpoint."""
    return {
        "data": [
            {
                "date": "2026-06",
                "groups": [
                    {
                        "group": "TeamA",
                        "values": [{
                            "cost": {"total": {"value": 1500.50}},
                            "usage": {"value": 100}
                        }]
                    },
                    {
                        "group": "TeamB",
                        "values": [{
                            "cost": {"total": {"value": 2300.75}},
                            "usage": {"value": 150}
                        }]
                    }
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_get_available_tag_keys(mock_settings, mock_auth_service, mock_tag_keys_response):
    """Test fetching available tag keys."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_tag_keys_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        tag_keys = await client.get_available_tag_keys()

        # Verify request
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "/tags/openshift/" in call_args[0][0]
        assert call_args[1]["params"]["limit"] == 1000
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token-12345"

        # Verify response
        assert tag_keys == ["env", "owner", "team"]  # Sorted

    await client.close()


@pytest.mark.asyncio
async def test_get_tag_values(mock_settings, mock_auth_service):
    """Test fetching values for a specific tag."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response_data = {
        "data": [
            {"key": "owner", "values": ["TeamA", "TeamB", "TeamC"]}
        ]
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        values = await client.get_tag_values("owner")

        # Verify request
        assert "/tags/openshift/owner/" in mock_get.call_args[0][0]

        # Verify response
        assert values == ["TeamA", "TeamB", "TeamC"]

    await client.close()


@pytest.mark.asyncio
async def test_get_costs_by_tag_with_preset(mock_settings, mock_auth_service, mock_costs_response):
    """Test fetching costs grouped by tag with preset time filter."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_costs_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        data = await client.get_costs_by_tag(
            tag_key="owner",
            time_scope_units="month",
            time_scope_value=-1,
            resolution="monthly"
        )

        # Verify request params
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert params["group_by[tag:owner]"] == "*"
        assert params["filter[time_scope_units]"] == "month"
        assert params["filter[time_scope_value]"] == "-1"
        assert params["filter[resolution]"] == "monthly"

        # Verify response
        assert data == mock_costs_response

    await client.close()


@pytest.mark.asyncio
async def test_get_costs_by_tag_with_custom_dates(mock_settings, mock_auth_service, mock_costs_response):
    """Test fetching costs with custom date range."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_costs_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        data = await client.get_costs_by_tag(
            tag_key="team",
            start_date="2026-06-01",
            end_date="2026-06-30"
        )

        # Verify custom dates override preset
        params = mock_get.call_args[1]["params"]
        assert params["start_date"] == "2026-06-01"
        assert params["end_date"] == "2026-06-30"
        assert "filter[time_scope_units]" not in params  # Should not be present

    await client.close()


@pytest.mark.asyncio
async def test_get_projects_for_tag(mock_settings, mock_auth_service):
    """Test fetching project-level details for a tag value."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response_data = {
        "data": [
            {
                "date": "2026-06",
                "groups": [
                    {"group": "project-a", "values": [{"cost": {"total": {"value": 500}}}]},
                    {"group": "project-b", "values": [{"cost": {"total": {"value": 1000}}}]}
                ]
            }
        ]
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        data = await client.get_projects_for_tag(
            tag_key="owner",
            tag_value="TeamA",
            time_scope_units="month",
            time_scope_value=-1
        )

        # Verify request params for drill-down
        params = mock_get.call_args[1]["params"]
        assert params["group_by[project]"] == "*"
        assert params["filter[tag:owner]"] == "TeamA"
        assert params["filter[time_scope_units]"] == "month"

        # Verify response
        assert len(data["data"][0]["groups"]) == 2

    await client.close()


@pytest.mark.asyncio
async def test_get_resource_details(mock_settings, mock_auth_service):
    """Test fetching resource details (CPU, memory, storage)."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        # Test compute
        await client.get_resource_details("compute")
        assert "/reports/openshift/compute/" in mock_get.call_args[0][0]

        # Test memory
        await client.get_resource_details("memory")
        assert "/reports/openshift/memory/" in mock_get.call_args[0][0]

        # Test volumes
        await client.get_resource_details("volumes")
        assert "/reports/openshift/volumes/" in mock_get.call_args[0][0]

    await client.close()


@pytest.mark.asyncio
async def test_get_resource_details_invalid_type(mock_settings, mock_auth_service):
    """Test that invalid resource type raises error."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    with pytest.raises(CostAPIError) as exc_info:
        await client.get_resource_details("invalid")

    assert "Invalid resource_type" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_caching_mechanism(mock_settings, mock_auth_service, mock_costs_response):
    """Test that responses are cached and reused."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_costs_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        # First call - should hit API
        data1 = await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 1

        # Second call with same params - should use cache
        data2 = await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 1  # Still only 1 call
        assert data1 == data2

        # Different params - should hit API again
        data3 = await client.get_costs_by_tag("team")
        assert mock_get.call_count == 2

    await client.close()


@pytest.mark.asyncio
async def test_cache_expiration(mock_settings, mock_auth_service, mock_costs_response):
    """Test that cache expires after TTL."""
    mock_settings.cache_ttl_seconds = 1  # 1 second TTL
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_costs_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        # First call
        await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 1

        # Wait for cache to expire
        time.sleep(1.1)

        # Second call - cache expired, should hit API again
        await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 2

    await client.close()


@pytest.mark.asyncio
async def test_clear_cache(mock_settings, mock_auth_service, mock_costs_response):
    """Test manual cache clearing."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_costs_response

    with patch.object(client.client, 'get', return_value=mock_response) as mock_get:
        # First call
        await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 1

        # Clear cache
        await client.clear_cache()

        # Second call - cache cleared, should hit API
        await client.get_costs_by_tag("owner")
        assert mock_get.call_count == 2

    await client.close()


@pytest.mark.asyncio
async def test_api_error_handling(mock_settings, mock_auth_service):
    """Test handling of API errors."""
    client = CostAPIClient(mock_settings, mock_auth_service)

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(client.client, 'get', return_value=mock_response):
        with pytest.raises(CostAPIError) as exc_info:
            await client.get_costs_by_tag("owner")

        assert "500" in str(exc_info.value)

    await client.close()


@pytest.mark.asyncio
async def test_build_time_filters_preset():
    """Test time filter building with presets."""
    from app.services.cost_api_client import CostAPIClient

    # Use dummy client just to test the method
    filters = CostAPIClient._build_time_filters(
        None,  # self
        time_scope_units="month",
        time_scope_value=-1,
        start_date=None,
        end_date=None
    )

    assert filters["filter[time_scope_units]"] == "month"
    assert filters["filter[time_scope_value]"] == "-1"


@pytest.mark.asyncio
async def test_build_time_filters_custom_dates():
    """Test time filter building with custom dates."""
    from app.services.cost_api_client import CostAPIClient

    filters = CostAPIClient._build_time_filters(
        None,  # self
        time_scope_units="month",
        time_scope_value=-1,
        start_date="2026-06-01",
        end_date="2026-06-30"
    )

    # Custom dates should override presets
    assert filters["start_date"] == "2026-06-01"
    assert filters["end_date"] == "2026-06-30"
    assert "filter[time_scope_units]" not in filters


@pytest.mark.asyncio
async def test_context_manager(mock_settings, mock_auth_service):
    """Test CostAPIClient as async context manager."""
    async with CostAPIClient(mock_settings, mock_auth_service) as client:
        assert client.client is not None
    # Client should be closed after context exit
