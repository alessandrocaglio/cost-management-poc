"""
Red Hat SSO Authentication Service

Handles OAuth2 client credentials authentication flow with the Red Hat SSO
to obtain access tokens for the Cost Management API.
"""

import asyncio
import time
from typing import Optional

import httpx

from app.config import Settings


class AuthenticationError(Exception):
    """Raised when authentication with Red Hat SSO fails."""
    pass


class AuthService:
    """
    Service for managing Red Hat SSO authentication tokens.

    Implements OAuth2 client credentials flow with automatic token caching
    and refresh before expiry.
    """

    def __init__(self, settings: Settings):
        """
        Initialize the authentication service.

        Args:
            settings: Application settings containing credentials and SSO URL
        """
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=30.0)

        # Token cache
        self._token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

        # Lock for thread-safe token refresh
        self._lock = asyncio.Lock()

        # Safety margin before token expiry (in seconds)
        self._refresh_margin = 60

    async def get_token(self) -> str:
        """
        Get a valid access token, fetching or refreshing as needed.

        This method is thread-safe and will cache tokens to avoid
        unnecessary authentication requests.

        Returns:
            Valid access token string

        Raises:
            AuthenticationError: If authentication fails
        """
        async with self._lock:
            if self._is_token_expired():
                await self._refresh_token()

            if not self._token:
                raise AuthenticationError("Failed to obtain access token")

            return self._token

    def _is_token_expired(self) -> bool:
        """
        Check if the cached token is expired or about to expire.

        Returns:
            True if token needs refresh, False otherwise
        """
        if self._token is None or self._token_expires_at is None:
            return True

        # Refresh if within safety margin of expiry
        return time.time() >= (self._token_expires_at - self._refresh_margin)

    async def _refresh_token(self) -> None:
        """
        Fetch a new access token from Red Hat SSO.

        Uses OAuth2 client credentials flow as documented in:
        docs/curl-examples.md

        Raises:
            AuthenticationError: If the token request fails
        """
        try:
            token_data = await self._fetch_token()

            self._token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300)  # Default 5 min

            if not self._token:
                raise AuthenticationError("No access_token in response")

            # Calculate expiration timestamp
            self._token_expires_at = time.time() + expires_in

        except httpx.HTTPError as e:
            raise AuthenticationError(f"HTTP error during authentication: {e}")
        except Exception as e:
            raise AuthenticationError(f"Unexpected error during authentication: {e}")

    async def _fetch_token(self) -> dict:
        """
        Make the actual token request to Red Hat SSO.

        Reference curl command from docs/curl-examples.md:
        curl -d "client_id=$COST_CLIENT_ID" \
             -d "client_secret=$COST_CLIENT_SECRET" \
             -d "grant_type=client_credentials" \
             -d "scope=api.console" \
             "https://sso.redhat.com/.../token"

        Returns:
            Token response dictionary

        Raises:
            httpx.HTTPError: If the request fails
            AuthenticationError: If the response is invalid
        """
        form_data = {
            "client_id": self.settings.cost_client_id,
            "client_secret": self.settings.get_client_secret(),
            "grant_type": "client_credentials",
            "scope": "api.console"
        }

        response = await self.client.post(
            self.settings.sso_token_url,
            data=form_data
        )

        # Check for HTTP errors
        if response.status_code != 200:
            error_detail = response.text[:200]  # Limit error message length
            raise AuthenticationError(
                f"SSO authentication failed with status {response.status_code}: {error_detail}"
            )

        try:
            return response.json()
        except Exception as e:
            raise AuthenticationError(f"Failed to parse token response: {e}")

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
