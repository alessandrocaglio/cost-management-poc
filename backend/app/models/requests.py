"""
Request models for API input validation.

These Pydantic models validate incoming request parameters
and provide automatic API documentation.
"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class TimeFilterParams(BaseModel):
    """
    Time filtering parameters for cost queries.

    Supports both preset time scopes (last month, last 3 days, etc.)
    and custom date ranges.
    """

    time_scope_units: Literal["month", "day"] = Field(
        default="month",
        description="Time scope unit: 'month' or 'day'"
    )

    time_scope_value: int = Field(
        default=-1,
        description="Number of periods to look back (negative). -1 = last period, -2 = 2 periods ago, etc.",
        le=0,
        ge=-12  # Max 12 periods back
    )

    start_date: Optional[str] = Field(
        default=None,
        description="Custom start date in YYYY-MM-DD format. Overrides time_scope_* if provided with end_date.",
        examples=["2026-06-01"]
    )

    end_date: Optional[str] = Field(
        default=None,
        description="Custom end date in YYYY-MM-DD format. Overrides time_scope_* if provided with start_date.",
        examples=["2026-06-30"]
    )

    resolution: Literal["daily", "monthly"] = Field(
        default="monthly",
        description="Data resolution: 'daily' for day-by-day breakdown, 'monthly' for monthly aggregation"
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format is YYYY-MM-DD."""
        if v is None:
            return v

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date must be in YYYY-MM-DD format")

        return v

    def model_post_init(self, __context) -> None:
        """Validate that custom dates are provided together."""
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Both start_date and end_date must be provided together")


class CostQueryParams(BaseModel):
    """
    Query parameters for fetching distributed costs.

    Main endpoint: GET /api/costs
    """

    tag_key: str = Field(
        ...,
        description="Tag key to group costs by (e.g., 'owner', 'team', 'env')",
        examples=["owner", "team", "environment"],
        min_length=1,
        max_length=100
    )

    time_scope_units: Literal["month", "day"] = Field(
        default="month",
        description="Time scope unit"
    )

    time_scope_value: int = Field(
        default=-1,
        description="Number of periods to look back",
        le=0,
        ge=-12
    )

    start_date: Optional[str] = Field(
        default=None,
        description="Custom start date (YYYY-MM-DD)",
        examples=["2026-06-01"]
    )

    end_date: Optional[str] = Field(
        default=None,
        description="Custom end date (YYYY-MM-DD)",
        examples=["2026-06-30"]
    )

    resolution: Literal["daily", "monthly"] = Field(
        default="monthly",
        description="Data resolution"
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format."""
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_key": "owner",
                "time_scope_units": "month",
                "time_scope_value": -1,
                "resolution": "monthly"
            }
        }
    )


class DrillDownQueryParams(BaseModel):
    """
    Query parameters for drilling down into tag value details.

    Shows project-level breakdown for a specific tag value.
    Endpoint: GET /api/costs/drilldown
    """

    tag_key: str = Field(
        ...,
        description="Tag key to filter by (e.g., 'owner', 'team')",
        examples=["owner"],
        min_length=1,
        max_length=100
    )

    tag_value: str = Field(
        ...,
        description="Tag value to filter for (e.g., 'TeamA', 'production')",
        examples=["TeamA", "production"],
        min_length=1,
        max_length=200
    )

    time_scope_units: Literal["month", "day"] = Field(
        default="month",
        description="Time scope unit"
    )

    time_scope_value: int = Field(
        default=-1,
        description="Number of periods to look back",
        le=0,
        ge=-12
    )

    start_date: Optional[str] = Field(
        default=None,
        description="Custom start date (YYYY-MM-DD)"
    )

    end_date: Optional[str] = Field(
        default=None,
        description="Custom end date (YYYY-MM-DD)"
    )

    resolution: Literal["daily", "monthly"] = Field(
        default="monthly",
        description="Data resolution"
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format."""
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_key": "owner",
                "tag_value": "TeamA",
                "time_scope_units": "month",
                "time_scope_value": -1
            }
        }
    )
