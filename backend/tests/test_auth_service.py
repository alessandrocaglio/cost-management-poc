"""
Tests for Red Hat SSO Authentication Service
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.config import Settings
from app.services.auth_service import AuthService, AuthenticationError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        _env_file=None,
        cost_client_id="test-client-id",
        cost_client_secret="test-client-secret",
        sso_token_url="https://sso.example.com/token"
    )


@pytest.fixture
def mock_token_response():
    """Create a mock successful token response."""
    return {
        "access_token": "test-token-12345",
        "expires_in": 300,
        "token_type": "Bearer",
        "scope": "api.console"
    }


@pytest.mark.asyncio
async def test_fetch_token_success(mock_settings, mock_token_response):
    """Test successful token fetch."""
    auth_service = AuthService(mock_settings)

    # Mock the HTTP response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_token_response

    with patch.object(auth_service.client, 'post', return_value=mock_response) as mock_post:
        token_data = await auth_service._fetch_token()

        # Verify the request was made correctly
        mock_post.assert_called_once_with(
            "https://sso.example.com/token",
            data={
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "grant_type": "client_credentials",
                "scope": "api.console"
            }
        )

        # Verify response
        assert token_data["access_token"] == "test-token-12345"
        assert token_data["expires_in"] == 300

    await auth_service.close()


@pytest.mark.asyncio
async def test_fetch_token_http_error(mock_settings):
    """Test token fetch with HTTP error."""
    auth_service = AuthService(mock_settings)

    # Mock a 401 error response
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials"

    with patch.object(auth_service.client, 'post', return_value=mock_response):
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service._fetch_token()

        assert "401" in str(exc_info.value)
        assert "Invalid credentials" in str(exc_info.value)

    await auth_service.close()


@pytest.mark.asyncio
async def test_get_token_caching(mock_settings, mock_token_response):
    """Test that tokens are cached and reused."""
    auth_service = AuthService(mock_settings)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_token_response

    with patch.object(auth_service.client, 'post', return_value=mock_response) as mock_post:
        # First call - should fetch token
        token1 = await auth_service.get_token()
        assert token1 == "test-token-12345"
        assert mock_post.call_count == 1

        # Second call - should use cached token
        token2 = await auth_service.get_token()
        assert token2 == "test-token-12345"
        assert mock_post.call_count == 1  # Still only 1 call

    await auth_service.close()


@pytest.mark.asyncio
async def test_token_refresh_on_expiry(mock_settings, mock_token_response):
    """Test that expired tokens are automatically refreshed."""
    auth_service = AuthService(mock_settings)
    auth_service._refresh_margin = 5  # Short margin for testing

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_token_response

    with patch.object(auth_service.client, 'post', return_value=mock_response) as mock_post:
        # First call - fetch token
        token1 = await auth_service.get_token()
        assert mock_post.call_count == 1

        # Simulate token expiry by setting expiration in the past
        auth_service._token_expires_at = time.time() - 10

        # Second call - should refresh
        token2 = await auth_service.get_token()
        assert mock_post.call_count == 2  # Token was refreshed

    await auth_service.close()


@pytest.mark.asyncio
async def test_is_token_expired_no_token(mock_settings):
    """Test that _is_token_expired returns True when no token exists."""
    auth_service = AuthService(mock_settings)
    assert auth_service._is_token_expired() is True
    await auth_service.close()


@pytest.mark.asyncio
async def test_is_token_expired_within_margin(mock_settings):
    """Test that tokens expiring soon are marked as expired."""
    auth_service = AuthService(mock_settings)
    auth_service._token = "test-token"
    auth_service._refresh_margin = 60

    # Set expiry to 30 seconds from now (within 60s margin)
    auth_service._token_expires_at = time.time() + 30
    assert auth_service._is_token_expired() is True

    # Set expiry to 120 seconds from now (outside 60s margin)
    auth_service._token_expires_at = time.time() + 120
    assert auth_service._is_token_expired() is False

    await auth_service.close()


@pytest.mark.asyncio
async def test_concurrent_token_requests(mock_settings, mock_token_response):
    """Test that concurrent token requests don't cause multiple fetches."""
    auth_service = AuthService(mock_settings)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_token_response

    with patch.object(auth_service.client, 'post', return_value=mock_response) as mock_post:
        # Make 5 concurrent requests
        results = await asyncio.gather(*[
            auth_service.get_token() for _ in range(5)
        ])

        # All should return the same token
        assert all(token == "test-token-12345" for token in results)

        # Should only make 1 HTTP request (due to locking)
        assert mock_post.call_count == 1

    await auth_service.close()


@pytest.mark.asyncio
async def test_context_manager(mock_settings):
    """Test AuthService as async context manager."""
    async with AuthService(mock_settings) as auth_service:
        assert auth_service.client is not None

    # Client should be closed after context exit
    # (we can't easily verify this without internal inspection)


@pytest.mark.asyncio
async def test_malformed_json_response(mock_settings):
    """Test handling of malformed JSON response."""
    auth_service = AuthService(mock_settings)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch.object(auth_service.client, 'post', return_value=mock_response):
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service._fetch_token()

        assert "Failed to parse token response" in str(exc_info.value)

    await auth_service.close()


@pytest.mark.asyncio
async def test_missing_access_token_in_response(mock_settings):
    """Test handling of response missing access_token."""
    auth_service = AuthService(mock_settings)

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"expires_in": 300}  # Missing access_token

    with patch.object(auth_service.client, 'post', return_value=mock_response):
        with pytest.raises(AuthenticationError) as exc_info:
            await auth_service._refresh_token()

        assert "No access_token in response" in str(exc_info.value)

    await auth_service.close()
