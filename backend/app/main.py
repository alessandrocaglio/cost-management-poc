"""
FastAPI backend for Cost Management Redux.

Provides REST API endpoints for retrieving and distributing cost data
from Red Hat Cost Management API.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.services.auth_service import AuthService, AuthenticationError
from app.services.cost_api_client import CostAPIClient, CostAPIError
from app.services.cost_distribution_engine import DistributionEngine
from app.models import (
    CostQueryParams,
    DrillDownQueryParams,
    DistributedCostsResponse,
    GroupCostResponse,
    MetaInfo,
    TagKeysResponse,
    ProjectDetailResponse,
    ProjectCost,
    HealthResponse,
    ErrorResponse,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Application version
__version__ = "0.1.0"


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    logger.info(f"Starting Cost Management Redux v{__version__}")

    # Startup
    settings = load_settings()
    logger.info(f"Configuration loaded - Cache TTL: {settings.cache_ttl_seconds}s")

    yield

    # Shutdown
    logger.info("Shutting down Cost Management Redux")


# Create FastAPI application
app = FastAPI(
    title="Cost Management Redux API",
    description="REST API for Red Hat Cost Management with proportional overhead distribution",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware — configured at app creation using env/defaults; always allows * in dev
try:
    _cors_origins = load_settings().cors_origins
except Exception:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Dependency Injection for Services
async def get_settings() -> Settings:
    """Get application settings."""
    return load_settings()


async def get_auth_service(
    settings: Annotated[Settings, Depends(get_settings)]
) -> AuthService:
    """Get authenticated auth service instance."""
    auth_service = AuthService(settings)
    try:
        yield auth_service
    finally:
        await auth_service.close()


async def get_api_client(
    settings: Annotated[Settings, Depends(get_settings)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)]
) -> CostAPIClient:
    """Get API client instance with authentication."""
    api_client = CostAPIClient(settings, auth_service)
    try:
        yield api_client
    finally:
        await api_client.close()


# Error Handlers
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request, exc: AuthenticationError):
    """Handle authentication errors."""
    logger.error(f"Authentication error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=ErrorResponse(
            error="AuthenticationError",
            message=str(exc),
            details=None
        ).model_dump()
    )


@app.exception_handler(CostAPIError)
async def cost_api_error_handler(request, exc: CostAPIError):
    """Handle Cost Management API errors."""
    logger.error(f"Cost API error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error="CostAPIError",
            message=str(exc),
            details=None
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Handle unexpected errors."""
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="InternalServerError",
            message="An unexpected error occurred",
            details={"error_type": type(exc).__name__}
        ).model_dump()
    )


# Helper Functions
def build_time_period_description(
    time_scope_units: str,
    time_scope_value: int,
    start_date: str = None,
    end_date: str = None
) -> str:
    """
    Generate human-readable time period description.

    Args:
        time_scope_units: "month" or "day"
        time_scope_value: Negative integer (-1, -2, etc.)
        start_date: Custom start date
        end_date: Custom end date

    Returns:
        Human-readable string like "Last month" or "2026-06-01 to 2026-06-30"
    """
    if start_date and end_date:
        return f"{start_date} to {end_date}"

    periods = abs(time_scope_value)
    unit = time_scope_units.rstrip('s')  # Remove trailing 's' if present

    if periods == 1:
        return f"Last {unit}"
    else:
        return f"Last {periods} {unit}s"


# API Endpoints

@app.get(
    "/api/tags",
    response_model=TagKeysResponse,
    summary="Get available tag keys",
    description="Returns all available tag keys that can be used for cost grouping",
    tags=["Tags"]
)
async def get_available_tags(
    api_client: Annotated[CostAPIClient, Depends(get_api_client)]
) -> TagKeysResponse:
    """
    Get all available tag keys from OpenShift clusters.

    Returns a list of tag keys like ["owner", "team", "env", "project"].
    """
    logger.info("Fetching available tag keys")

    tags = await api_client.get_available_tag_keys()

    logger.info(f"Retrieved {len(tags)} tag keys")

    return TagKeysResponse(
        tags=tags,
        count=len(tags)
    )


@app.get(
    "/api/costs",
    response_model=DistributedCostsResponse,
    summary="Get distributed costs by tag",
    description="Returns cost data grouped by tag with proportional overhead distribution",
    tags=["Costs"]
)
async def get_distributed_costs(
    tag_key: Annotated[str, Query(description="Tag key to group by", min_length=1, max_length=100)],
    time_scope_units: Annotated[str, Query(description="Time scope unit")] = "month",
    time_scope_value: Annotated[int, Query(description="Periods to look back", le=0, ge=-12)] = -1,
    start_date: Annotated[str | None, Query(description="Custom start date (YYYY-MM-DD)")] = None,
    end_date: Annotated[str | None, Query(description="Custom end date (YYYY-MM-DD)")] = None,
    resolution: Annotated[str, Query(description="Data resolution")] = "monthly",
    api_client: Annotated[CostAPIClient, Depends(get_api_client)] = None
) -> DistributedCostsResponse:
    """
    Get cost data grouped by a specific tag with overhead distribution.

    This endpoint:
    1. Fetches raw cost data from Red Hat Cost Management API
    2. Separates tagged costs from untagged overhead
    3. Distributes overhead proportionally based on consumption ratios
    4. Returns structured cost breakdown per group
    """
    logger.info(f"Fetching distributed costs for tag_key='{tag_key}'")

    # Fetch raw cost data from API
    raw_data = await api_client.get_costs_by_tag(
        tag_key=tag_key,
        time_scope_units=time_scope_units,
        time_scope_value=time_scope_value,
        start_date=start_date,
        end_date=end_date,
        resolution=resolution
    )

    # Calculate cost distribution
    distribution = DistributionEngine.distribute_costs(raw_data, tag_key)

    # Convert to response model
    groups = [
        GroupCostResponse(
            group_name=g.group_name,
            base_cost=g.base_cost,
            overhead_share=g.overhead_share,
            total_cost=g.total_cost,
            consumption_ratio=g.consumption_ratio
        )
        for g in distribution.groups
    ]

    # Build metadata
    time_period = build_time_period_description(
        time_scope_units, time_scope_value, start_date, end_date
    )

    meta = MetaInfo(
        tag_key=tag_key,
        untagged_group_name=distribution.untagged_group_name,
        resolution=resolution,
        time_period=time_period
    )

    logger.info(
        f"Distributed costs calculated: {len(groups)} groups, "
        f"total overhead: ${distribution.total_overhead:.2f}"
    )

    return DistributedCostsResponse(
        groups=groups,
        total_overhead=distribution.total_overhead,
        total_tracked_cost=distribution.total_tracked_cost,
        total_distributed_cost=distribution.total_distributed_cost,
        meta=meta
    )


@app.get(
    "/api/costs/drilldown",
    response_model=ProjectDetailResponse,
    summary="Get project-level cost details",
    description="Returns project-level breakdown for a specific tag value (drill-down)",
    tags=["Costs"]
)
async def get_project_drilldown(
    tag_key: Annotated[str, Query(description="Tag key to filter by", min_length=1, max_length=100)],
    tag_value: Annotated[str, Query(description="Tag value to filter for", min_length=1, max_length=200)],
    time_scope_units: Annotated[str, Query(description="Time scope unit")] = "month",
    time_scope_value: Annotated[int, Query(description="Periods to look back", le=0, ge=-12)] = -1,
    start_date: Annotated[str | None, Query(description="Custom start date (YYYY-MM-DD)")] = None,
    end_date: Annotated[str | None, Query(description="Custom end date (YYYY-MM-DD)")] = None,
    resolution: Annotated[str, Query(description="Data resolution")] = "monthly",
    api_client: Annotated[CostAPIClient, Depends(get_api_client)] = None
) -> ProjectDetailResponse:
    """
    Get project-level cost breakdown for a specific tag value.

    Shows all projects that belong to the specified tag value
    (e.g., all projects owned by "TeamA").
    """
    logger.info(f"Fetching drill-down for {tag_key}={tag_value}")

    # Fetch project-level data
    raw_data = await api_client.get_projects_for_tag(
        tag_key=tag_key,
        tag_value=tag_value,
        time_scope_units=time_scope_units,
        time_scope_value=time_scope_value,
        start_date=start_date,
        end_date=end_date,
        resolution=resolution
    )

    # Extract project costs from response.
    # group_by[project]=* → response key is "projects", name field is "project"
    projects = []
    total_cost = 0.0

    for entry in raw_data.get("data", []):
        # Use "projects" key; fall back to scanning any non-date list
        group_list = entry.get("projects") or next(
            (v for k, v in entry.items() if k != "date" and isinstance(v, list)), []
        )
        for group in group_list:
            project_name = group.get("project") or group.get("group")

            if not project_name:
                continue

            # Extract cost value
            values = group.get("values", [])
            if values:
                cost_metric = values[0].get("cost") or values[0].get("infrastructure", {})
                cost_value = cost_metric.get("total", {}).get("value", 0.0)

                # Extract usage if available
                usage_value = values[0].get("usage", {}).get("value")

                projects.append(
                    ProjectCost(
                        project_name=project_name,
                        cost=cost_value,
                        usage=usage_value
                    )
                )

                total_cost += cost_value

    logger.info(
        f"Drill-down complete: {len(projects)} projects, "
        f"total cost: ${total_cost:.2f}"
    )

    return ProjectDetailResponse(
        projects=projects,
        tag_key=tag_key,
        tag_value=tag_value,
        total_cost=total_cost,
        project_count=len(projects)
    )


@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service health status and configuration",
    tags=["System"]
)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)]
) -> HealthResponse:
    """
    Health check endpoint.

    Returns service status, version, and configuration information.
    Can optionally check if the Red Hat Cost Management API is accessible.
    """
    logger.debug("Health check requested")

    # Basic health response
    response = HealthResponse(
        status="ok",
        version=__version__,
        cache_enabled=True,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        api_accessible=None  # Could test with a lightweight API call
    )

    return response


@app.get(
    "/api/probe/costs",
    summary="Probe raw costs (no tag grouping)",
    description="Returns raw OpenShift costs grouped by cluster — useful to verify API connectivity and data existence",
    tags=["Diagnostics"]
)
async def probe_costs(
    api_client: Annotated[CostAPIClient, Depends(get_api_client)]
) -> dict:
    """Probe endpoint: GET /reports/openshift/costs/?group_by[cluster]=*"""
    return await api_client._request(
        "/reports/openshift/costs/",
        {
            "group_by[cluster]": "*",
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": "monthly",
        }
    )


@app.get(
    "/api/probe/costs/tag",
    summary="Probe raw costs grouped by a specific tag key",
    description="Returns the raw API response for group_by[tag:KEY]=* so you can inspect the actual response shape",
    tags=["Diagnostics"]
)
async def probe_costs_by_tag(
    tag_key: Annotated[str, Query(description="Tag key to group by")],
    api_client: Annotated[CostAPIClient, Depends(get_api_client)]
) -> dict:
    """Probe endpoint: GET /reports/openshift/costs/?group_by[tag:KEY]=*"""
    return await api_client._request(
        "/reports/openshift/costs/",
        {
            f"group_by[tag:{tag_key}]": "*",
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": "monthly",
        }
    )


@app.get(
    "/api/probe/tags",
    summary="Probe raw tag discovery",
    description="Calls both tag discovery endpoints and returns raw responses for inspection",
    tags=["Diagnostics"]
)
async def probe_tags(
    api_client: Annotated[CostAPIClient, Depends(get_api_client)]
) -> dict:
    """
    Probe endpoint that tries both tag sources and returns raw responses.
    """
    result: dict = {}

    try:
        settings_tags = await api_client._request(
            "/settings/tags/",
            {"filter[enabled]": "true", "filter[source_type]": "OCP", "limit": 1000}
        )
        result["settings_tags"] = settings_tags
    except Exception as e:
        result["settings_tags_error"] = str(e)

    try:
        openshift_tags = await api_client._request(
            "/tags/openshift/",
            {"limit": 100}
        )
        result["openshift_tags"] = openshift_tags
    except Exception as e:
        result["openshift_tags_error"] = str(e)

    return result


# Mount static files for frontend (must be last)
# Check if frontend directory exists
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"Serving frontend from {frontend_path}")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
