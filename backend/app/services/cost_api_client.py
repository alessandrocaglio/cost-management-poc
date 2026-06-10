"""
Red Hat Cost Management API Client

Handles all interactions with the Red Hat Cost Management API to retrieve
cost data, tag information, and resource details for OpenShift clusters.
"""

import hashlib
import json
import time
from typing import Any, Optional
import asyncio

import httpx

from app.config import Settings
from app.services.auth_service import AuthService


class CostAPIError(Exception):
    """Raised when Cost Management API requests fail."""
    pass


class CostAPIClient:
    """
    Client for the Red Hat Cost Management API.

    Provides methods to retrieve cost data grouped by tags, projects,
    and other dimensions. Implements response caching to reduce API calls.
    """

    def __init__(self, settings: Settings, auth_service: AuthService):
        """
        Initialize the Cost API client.

        Args:
            settings: Application settings with API base URL and cache config
            auth_service: Authentication service for obtaining access tokens
        """
        self.settings = settings
        self.auth_service = auth_service
        self.client = httpx.AsyncClient(timeout=30.0)

        # In-memory cache: {cache_key: (data, timestamp)}
        self._cache: dict[str, tuple[Any, float]] = {}
        self._cache_lock = asyncio.Lock()

    async def get_available_tag_keys(self) -> list[str]:
        """
        Get all available tag keys from OpenShift clusters.

        Returns list of tag keys like ["owner", "team", "env", "project"].

        Reference: GET /api/cost-management/v1/tags/openshift/

        Returns:
            List of available tag key strings

        Raises:
            CostAPIError: If the API request fails
        """
        endpoint = "/tags/openshift/"
        params = {"limit": 1000}

        data = await self._request(endpoint, params)

        # Extract tag keys from response
        # Response format: {"data": [{"key": "owner", "values": [...]}, ...]}
        tag_keys = []
        for item in data.get("data", []):
            key = item.get("key")
            if key:
                tag_keys.append(key)

        return sorted(tag_keys)

    async def get_tag_values(self, tag_key: str) -> list[str]:
        """
        Get all possible values for a specific tag key.

        Reference: GET /api/cost-management/v1/tags/openshift/{tag_key}/

        Args:
            tag_key: The tag key to get values for (e.g., "owner", "team")

        Returns:
            List of tag values

        Raises:
            CostAPIError: If the API request fails
        """
        endpoint = f"/tags/openshift/{tag_key}/"
        params = {"limit": 1000}

        data = await self._request(endpoint, params)

        # Extract values from response
        # Response format: {"data": [{"key": "owner", "values": ["TeamA", "TeamB", ...]}, ...]}
        values = []
        for item in data.get("data", []):
            item_values = item.get("values", [])
            values.extend(item_values)

        return sorted(set(values))  # Remove duplicates and sort

    async def get_costs_by_tag(
        self,
        tag_key: str,
        time_scope_units: str = "month",
        time_scope_value: int = -1,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        resolution: str = "monthly"
    ) -> dict:
        """
        Get cost data grouped by a specific tag key.

        This is the main endpoint for the dashboard view showing costs
        aggregated by tag values (e.g., all costs grouped by "owner").

        Reference: GET /api/cost-management/v1/reports/openshift/costs/
                       ?group_by[tag:KEY]=*

        Args:
            tag_key: Tag key to group by (e.g., "owner", "team")
            time_scope_units: "month" or "day"
            time_scope_value: -1 for last period, -2 for 2 periods ago, etc.
            start_date: Custom start date (YYYY-MM-DD), overrides time_scope_*
            end_date: Custom end date (YYYY-MM-DD), overrides time_scope_*
            resolution: "daily" or "monthly" for data breakdown

        Returns:
            Raw API response dict with cost data

        Raises:
            CostAPIError: If the API request fails
        """
        endpoint = "/reports/openshift/costs/"

        params = {
            f"group_by[tag:{tag_key}]": "*",
            "filter[resolution]": resolution
        }

        # Add time filtering
        params.update(
            self._build_time_filters(
                time_scope_units, time_scope_value, start_date, end_date
            )
        )

        return await self._request(endpoint, params)

    async def get_projects_for_tag(
        self,
        tag_key: str,
        tag_value: str,
        time_scope_units: str = "month",
        time_scope_value: int = -1,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        resolution: str = "monthly"
    ) -> dict:
        """
        Get project-level cost breakdown for a specific tag value.

        This is the drill-down endpoint showing all projects that belong
        to a specific tag value (e.g., all projects owned by "TeamA").

        Reference: GET /api/cost-management/v1/reports/openshift/costs/
                       ?group_by[project]=*&filter[tag:KEY]=VALUE

        Args:
            tag_key: Tag key to filter by (e.g., "owner")
            tag_value: Tag value to filter for (e.g., "TeamA")
            time_scope_units: "month" or "day"
            time_scope_value: -1 for last period, -2 for 2 periods ago, etc.
            start_date: Custom start date (YYYY-MM-DD)
            end_date: Custom end date (YYYY-MM-DD)
            resolution: "daily" or "monthly" for data breakdown

        Returns:
            Raw API response dict with project-level cost data

        Raises:
            CostAPIError: If the API request fails
        """
        endpoint = "/reports/openshift/costs/"

        params = {
            "group_by[project]": "*",
            f"filter[tag:{tag_key}]": tag_value,
            "filter[resolution]": resolution
        }

        # Add time filtering
        params.update(
            self._build_time_filters(
                time_scope_units, time_scope_value, start_date, end_date
            )
        )

        return await self._request(endpoint, params)

    async def get_resource_details(
        self,
        resource_type: str,
        time_scope_units: str = "month",
        time_scope_value: int = -1,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> dict:
        """
        Get resource usage and cost details (CPU, memory, storage).

        Reference endpoints:
        - GET /api/cost-management/v1/reports/openshift/compute/
        - GET /api/cost-management/v1/reports/openshift/memory/
        - GET /api/cost-management/v1/reports/openshift/volumes/

        Args:
            resource_type: "compute", "memory", or "volumes"
            time_scope_units: "month" or "day"
            time_scope_value: -1 for last period, -2 for 2 periods ago, etc.
            start_date: Custom start date (YYYY-MM-DD)
            end_date: Custom end date (YYYY-MM-DD)

        Returns:
            Raw API response dict with resource details

        Raises:
            CostAPIError: If the API request fails or invalid resource_type
        """
        valid_types = ["compute", "memory", "volumes"]
        if resource_type not in valid_types:
            raise CostAPIError(
                f"Invalid resource_type '{resource_type}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        endpoint = f"/reports/openshift/{resource_type}/"

        params = self._build_time_filters(
            time_scope_units, time_scope_value, start_date, end_date
        )

        return await self._request(endpoint, params)

    def _build_time_filters(
        self,
        time_scope_units: str,
        time_scope_value: int,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> dict:
        """
        Build time filtering query parameters.

        Supports either preset time scopes (last month, last 3 days, etc.)
        or custom date ranges.

        Reference (from API cheatsheet page 11):
        - Presets: filter[time_scope_units]=month&filter[time_scope_value]=-1
        - Custom: start_date=2022-09-01&end_date=2022-09-10

        Args:
            time_scope_units: "month" or "day"
            time_scope_value: -1, -2, -3, etc. (negative for past periods)
            start_date: Custom start date (YYYY-MM-DD)
            end_date: Custom end date (YYYY-MM-DD)

        Returns:
            Dict of query parameters for time filtering
        """
        # Custom date range takes precedence
        if start_date and end_date:
            return {
                "start_date": start_date,
                "end_date": end_date
            }

        # Use preset time scope
        return {
            "filter[time_scope_units]": time_scope_units,
            "filter[time_scope_value]": str(time_scope_value)
        }

    async def _request(self, endpoint: str, params: dict) -> dict:
        """
        Make a GET request to the Cost Management API with caching.

        Args:
            endpoint: API endpoint path (e.g., "/reports/openshift/costs/")
            params: Query parameters dict

        Returns:
            Parsed JSON response

        Raises:
            CostAPIError: If the request fails
        """
        # Check cache first
        cache_key = self._build_cache_key(endpoint, params)

        async with self._cache_lock:
            if cache_key in self._cache:
                cached_data, cached_time = self._cache[cache_key]
                if self._is_cache_valid(cached_time):
                    return cached_data

        # Cache miss or expired - fetch from API
        url = f"{self.settings.cost_api_base_url}{endpoint}"

        try:
            # Get authentication token
            token = await self.auth_service.get_token()

            # Make request
            headers = {"Authorization": f"Bearer {token}"}
            response = await self.client.get(url, params=params, headers=headers)

            # Check for errors
            if response.status_code != 200:
                error_detail = response.text[:200]
                raise CostAPIError(
                    f"API request failed with status {response.status_code}: {error_detail}"
                )

            data = response.json()

            # Cache the response
            async with self._cache_lock:
                self._cache[cache_key] = (data, time.time())

            return data

        except httpx.HTTPError as e:
            raise CostAPIError(f"HTTP error during API request: {e}")
        except Exception as e:
            raise CostAPIError(f"Unexpected error during API request: {e}")

    def _build_cache_key(self, endpoint: str, params: dict) -> str:
        """
        Generate a unique cache key from endpoint and parameters.

        Args:
            endpoint: API endpoint path
            params: Query parameters dict

        Returns:
            Hash string to use as cache key
        """
        # Sort params for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True)
        key_string = f"{endpoint}:{sorted_params}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _is_cache_valid(self, cached_time: float) -> bool:
        """
        Check if a cached entry is still valid based on TTL.

        Args:
            cached_time: Timestamp when the entry was cached

        Returns:
            True if cache entry is still valid, False if expired
        """
        age = time.time() - cached_time
        return age < self.settings.cache_ttl_seconds

    async def clear_cache(self) -> None:
        """Clear all cached responses."""
        async with self._cache_lock:
            self._cache.clear()

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
