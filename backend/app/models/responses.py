"""
Response models for API output.

These Pydantic models define the structure of API responses
and provide automatic OpenAPI documentation.
"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class GroupCostResponse(BaseModel):
    """
    Cost breakdown for a single group/tag value.

    Includes base cost, proportional overhead share, and total distributed cost.
    """

    group_name: str = Field(
        ...,
        description="Tag value / group name (e.g., 'TeamA', 'production')",
        examples=["TeamA", "production"]
    )

    base_cost: float = Field(
        ...,
        description="Direct cost attributed to this group (before overhead distribution)",
        examples=[1500.50],
        ge=0
    )

    overhead_share: float = Field(
        ...,
        description="Proportional share of untagged overhead allocated to this group",
        examples=[200.25],
        ge=0
    )

    total_cost: float = Field(
        ...,
        description="Total distributed cost (base_cost + overhead_share)",
        examples=[1700.75],
        ge=0
    )

    consumption_ratio: float = Field(
        ...,
        description="Group's share of total tracked consumption (0.0-1.0)",
        examples=[0.35],
        ge=0,
        le=1
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "group_name": "TeamA",
                "base_cost": 1500.50,
                "overhead_share": 200.25,
                "total_cost": 1700.75,
                "consumption_ratio": 0.35
            }
        }
    )


class MetaInfo(BaseModel):
    """Metadata about the request/response."""

    tag_key: str = Field(..., description="Tag key used for grouping")
    untagged_group_name: str = Field(..., description="Name of untagged group (e.g., 'No-owner')")
    resolution: str = Field(..., description="Data resolution used")
    time_period: str = Field(..., description="Human-readable time period description")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_key": "owner",
                "untagged_group_name": "No-owner",
                "resolution": "monthly",
                "time_period": "Last month"
            }
        }
    )


class DistributedCostsResponse(BaseModel):
    """
    Main response for distributed cost data.

    Contains cost breakdowns for all groups with proportional overhead distribution.
    """

    groups: list[GroupCostResponse] = Field(
        ...,
        description="List of cost breakdowns per group"
    )

    total_overhead: float = Field(
        ...,
        description="Total untagged overhead pool",
        examples=[500.00],
        ge=0
    )

    total_tracked_cost: float = Field(
        ...,
        description="Sum of all tracked (tagged) costs before distribution",
        examples=[4500.00],
        ge=0
    )

    total_distributed_cost: float = Field(
        ...,
        description="Sum of all final distributed costs (tracked + overhead)",
        examples=[5000.00],
        ge=0
    )

    meta: MetaInfo = Field(
        ...,
        description="Request metadata"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "groups": [
                    {
                        "group_name": "TeamA",
                        "base_cost": 1500.00,
                        "overhead_share": 200.00,
                        "total_cost": 1700.00,
                        "consumption_ratio": 0.4
                    },
                    {
                        "group_name": "TeamB",
                        "base_cost": 2250.00,
                        "overhead_share": 300.00,
                        "total_cost": 2550.00,
                        "consumption_ratio": 0.6
                    }
                ],
                "total_overhead": 500.00,
                "total_tracked_cost": 3750.00,
                "total_distributed_cost": 4250.00,
                "meta": {
                    "tag_key": "owner",
                    "untagged_group_name": "No-owner",
                    "resolution": "monthly",
                    "time_period": "Last month"
                }
            }
        }
    )


class TagKeysResponse(BaseModel):
    """
    Response containing available tag keys.

    Lists all tag keys that can be used for cost grouping.
    """

    tags: list[str] = Field(
        ...,
        description="List of available tag keys",
        examples=[["owner", "team", "env", "project"]]
    )

    count: int = Field(
        ...,
        description="Number of available tags",
        examples=[4],
        ge=0
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tags": ["owner", "team", "env", "project"],
                "count": 4
            }
        }
    )


class ProjectCost(BaseModel):
    """Cost information for a single project."""

    project_name: str = Field(
        ...,
        description="OpenShift project/namespace name",
        examples=["cost-management-prod"]
    )

    cost: float = Field(
        ...,
        description="Total cost for this project",
        examples=[350.75],
        ge=0
    )

    usage: Optional[float] = Field(
        None,
        description="Resource usage metric (if available)",
        ge=0
    )

    cluster: Optional[str] = Field(
        None,
        description="Cluster name(s) where this project runs (comma-separated if multiple)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_name": "cost-management-prod",
                "cost": 350.75,
                "usage": 125.5,
                "cluster": "my-cluster"
            }
        }
    )


class ProjectDetailResponse(BaseModel):
    """
    Drill-down response showing project-level details.

    Shows all projects under a specific tag value.
    """

    projects: list[ProjectCost] = Field(
        ...,
        description="List of projects and their costs"
    )

    tag_key: str = Field(
        ...,
        description="Tag key used for filtering",
        examples=["owner"]
    )

    tag_value: str = Field(
        ...,
        description="Tag value filtered for",
        examples=["TeamA"]
    )

    total_cost: float = Field(
        ...,
        description="Total cost across all projects",
        examples=[1500.00],
        ge=0
    )

    project_count: int = Field(
        ...,
        description="Number of projects",
        examples=[5],
        ge=0
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "projects": [
                    {"project_name": "app-frontend", "cost": 500.00, "usage": 100.0},
                    {"project_name": "app-backend", "cost": 750.00, "usage": 150.0},
                    {"project_name": "app-database", "cost": 250.00, "usage": 50.0}
                ],
                "tag_key": "owner",
                "tag_value": "TeamA",
                "total_cost": 1500.00,
                "project_count": 3
            }
        }
    )


class ResourceMetric(BaseModel):
    """
    Aggregated usage/request/limit metrics for a single resource type.

    Sourced from meta.total of the compute, memory, or volumes endpoint.
    Limit is absent for storage (volumes API does not return it).
    """

    usage: Optional[float] = Field(None, description="Total resource usage for the period", ge=0)
    units: Optional[str] = Field(None, description="Units for all metrics (e.g. Core-Hours, GiB-Hours, GiB-Mo)")
    request: Optional[float] = Field(None, description="Total resource requested", ge=0)
    limit: Optional[float] = Field(None, description="Total resource limit (absent for storage)", ge=0)
    capacity: Optional[float] = Field(None, description="Total cluster capacity for this resource", ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "usage": 30.79,
                "units": "Core-Hours",
                "request": 12527.67,
                "limit": 14703.53,
                "capacity": 2350400.33
            }
        }
    )


class ProjectResourcesResponse(BaseModel):
    """
    CPU, memory, and storage resource metrics for a single project.

    All three resource types are fetched concurrently from the respective
    OpenShift resource endpoints and aggregated via meta.total.
    """

    project_name: str = Field(..., description="OpenShift project/namespace name")
    cpu: ResourceMetric = Field(..., description="CPU (compute) metrics in Core-Hours")
    memory: ResourceMetric = Field(..., description="Memory metrics in GiB-Hours")
    storage: ResourceMetric = Field(..., description="Persistent volume metrics in GiB-Mo")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_name": "caching",
                "cpu": {"usage": 30.79, "units": "Core-Hours", "request": 12527.67, "limit": 14703.53, "capacity": 2350400.33},
                "memory": {"usage": 9266.67, "units": "GiB-Hours", "request": 12957.70, "limit": 24994.25, "capacity": 9343394.70},
                "storage": {"usage": 70.24, "units": "GiB-Mo", "request": 6805.19, "limit": None, "capacity": 6841.85}
            }
        }
    )


class HealthResponse(BaseModel):
    """
    Health check response.

    Indicates service status and configuration.
    """

    status: Literal["ok", "degraded", "error"] = Field(
        ...,
        description="Service health status"
    )

    version: str = Field(
        ...,
        description="Application version",
        examples=["0.1.0"]
    )

    cache_enabled: bool = Field(
        ...,
        description="Whether API response caching is enabled"
    )

    cache_ttl_seconds: int = Field(
        ...,
        description="Cache TTL in seconds",
        examples=[900],
        ge=0
    )

    api_accessible: Optional[bool] = Field(
        None,
        description="Whether the Red Hat Cost Management API is accessible"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "0.1.0",
                "cache_enabled": True,
                "cache_ttl_seconds": 900,
                "api_accessible": True
            }
        }
    )


class ErrorResponse(BaseModel):
    """
    Error response for failed requests.

    Provides detailed error information for troubleshooting.
    """

    error: str = Field(
        ...,
        description="Error type/category",
        examples=["ValidationError", "AuthenticationError", "APIError"]
    )

    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Invalid tag_key: must be between 1 and 100 characters"]
    )

    details: Optional[dict] = Field(
        None,
        description="Additional error details (validation errors, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "ValidationError",
                "message": "Invalid request parameters",
                "details": {
                    "tag_key": ["Field required"]
                }
            }
        }
    )
