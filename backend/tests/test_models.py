"""
Tests for Pydantic request/response models
"""

import pytest
from pydantic import ValidationError

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


class TestCostQueryParams:
    """Tests for CostQueryParams validation."""

    def test_valid_preset_params(self):
        """Test valid preset time scope parameters."""
        params = CostQueryParams(
            tag_key="owner",
            time_scope_units="month",
            time_scope_value=-1
        )

        assert params.tag_key == "owner"
        assert params.time_scope_units == "month"
        assert params.time_scope_value == -1
        assert params.resolution == "monthly"  # Default

    def test_valid_custom_date_params(self):
        """Test valid custom date range parameters."""
        params = CostQueryParams(
            tag_key="team",
            start_date="2026-06-01",
            end_date="2026-06-30"
        )

        assert params.start_date == "2026-06-01"
        assert params.end_date == "2026-06-30"

    def test_invalid_date_format(self):
        """Test that invalid date format raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CostQueryParams(
                tag_key="owner",
                start_date="06/01/2026",  # Wrong format
                end_date="2026-06-30"
            )

        errors = exc_info.value.errors()
        assert any("YYYY-MM-DD" in str(e) for e in errors)

    def test_empty_tag_key(self):
        """Test that empty tag_key raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CostQueryParams(tag_key="")

        errors = exc_info.value.errors()
        assert any("min_length" in str(e) for e in errors)

    def test_time_scope_value_range(self):
        """Test time_scope_value validation."""
        # Valid
        params = CostQueryParams(tag_key="owner", time_scope_value=-1)
        assert params.time_scope_value == -1

        # Invalid: positive value
        with pytest.raises(ValidationError):
            CostQueryParams(tag_key="owner", time_scope_value=1)

        # Invalid: too far back
        with pytest.raises(ValidationError):
            CostQueryParams(tag_key="owner", time_scope_value=-13)

    def test_resolution_enum(self):
        """Test resolution enum validation."""
        # Valid
        params = CostQueryParams(tag_key="owner", resolution="daily")
        assert params.resolution == "daily"

        # Invalid
        with pytest.raises(ValidationError):
            CostQueryParams(tag_key="owner", resolution="hourly")


class TestDrillDownQueryParams:
    """Tests for DrillDownQueryParams validation."""

    def test_valid_params(self):
        """Test valid drill-down parameters."""
        params = DrillDownQueryParams(
            tag_key="owner",
            tag_value="TeamA"
        )

        assert params.tag_key == "owner"
        assert params.tag_value == "TeamA"

    def test_requires_tag_value(self):
        """Test that tag_value is required."""
        with pytest.raises(ValidationError) as exc_info:
            DrillDownQueryParams(tag_key="owner")

        errors = exc_info.value.errors()
        assert any("tag_value" in str(e) for e in errors)


class TestGroupCostResponse:
    """Tests for GroupCostResponse model."""

    def test_valid_response(self):
        """Test valid group cost response."""
        response = GroupCostResponse(
            group_name="TeamA",
            base_cost=1500.50,
            overhead_share=200.25,
            total_cost=1700.75,
            consumption_ratio=0.35
        )

        assert response.group_name == "TeamA"
        assert response.base_cost == 1500.50
        assert response.total_cost == 1700.75

    def test_negative_cost_rejected(self):
        """Test that negative costs are rejected."""
        with pytest.raises(ValidationError):
            GroupCostResponse(
                group_name="TeamA",
                base_cost=-100.0,  # Invalid
                overhead_share=50.0,
                total_cost=0.0,
                consumption_ratio=0.5
            )

    def test_ratio_range(self):
        """Test consumption_ratio range validation."""
        # Valid: 0.0
        response = GroupCostResponse(
            group_name="TeamA",
            base_cost=100.0,
            overhead_share=0.0,
            total_cost=100.0,
            consumption_ratio=0.0
        )
        assert response.consumption_ratio == 0.0

        # Valid: 1.0
        response = GroupCostResponse(
            group_name="TeamA",
            base_cost=100.0,
            overhead_share=0.0,
            total_cost=100.0,
            consumption_ratio=1.0
        )
        assert response.consumption_ratio == 1.0

        # Invalid: > 1.0
        with pytest.raises(ValidationError):
            GroupCostResponse(
                group_name="TeamA",
                base_cost=100.0,
                overhead_share=0.0,
                total_cost=100.0,
                consumption_ratio=1.5
            )


class TestDistributedCostsResponse:
    """Tests for DistributedCostsResponse model."""

    def test_valid_response(self):
        """Test valid distributed costs response."""
        response = DistributedCostsResponse(
            groups=[
                GroupCostResponse(
                    group_name="TeamA",
                    base_cost=1000.0,
                    overhead_share=200.0,
                    total_cost=1200.0,
                    consumption_ratio=0.4
                )
            ],
            total_overhead=500.0,
            total_tracked_cost=2500.0,
            total_distributed_cost=3000.0,
            meta=MetaInfo(
                tag_key="owner",
                untagged_group_name="No-owner",
                resolution="monthly",
                time_period="Last month"
            )
        )

        assert len(response.groups) == 1
        assert response.total_overhead == 500.0
        assert response.meta.tag_key == "owner"

    def test_serialization(self):
        """Test that response can be serialized to JSON."""
        response = DistributedCostsResponse(
            groups=[],
            total_overhead=0.0,
            total_tracked_cost=0.0,
            total_distributed_cost=0.0,
            meta=MetaInfo(
                tag_key="owner",
                untagged_group_name="No-owner",
                resolution="monthly",
                time_period="Last month"
            )
        )

        json_data = response.model_dump()
        assert isinstance(json_data, dict)
        assert "groups" in json_data
        assert "meta" in json_data


class TestTagKeysResponse:
    """Tests for TagKeysResponse model."""

    def test_valid_response(self):
        """Test valid tag keys response."""
        response = TagKeysResponse(
            tags=["owner", "team", "env"],
            count=3
        )

        assert response.tags == ["owner", "team", "env"]
        assert response.count == 3

    def test_empty_tags(self):
        """Test response with no tags."""
        response = TagKeysResponse(tags=[], count=0)
        assert response.tags == []
        assert response.count == 0


class TestProjectDetailResponse:
    """Tests for ProjectDetailResponse model."""

    def test_valid_response(self):
        """Test valid project detail response."""
        response = ProjectDetailResponse(
            projects=[
                ProjectCost(project_name="app-frontend", cost=500.0, usage=100.0),
                ProjectCost(project_name="app-backend", cost=750.0)
            ],
            tag_key="owner",
            tag_value="TeamA",
            total_cost=1250.0,
            project_count=2
        )

        assert len(response.projects) == 2
        assert response.total_cost == 1250.0
        assert response.project_count == 2

    def test_project_cost_optional_usage(self):
        """Test that usage field is optional."""
        project = ProjectCost(project_name="test-project", cost=100.0)
        assert project.usage is None

        project_with_usage = ProjectCost(project_name="test-project", cost=100.0, usage=50.0)
        assert project_with_usage.usage == 50.0


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_valid_response(self):
        """Test valid health response."""
        response = HealthResponse(
            status="ok",
            version="0.1.0",
            cache_enabled=True,
            cache_ttl_seconds=900
        )

        assert response.status == "ok"
        assert response.version == "0.1.0"
        assert response.cache_enabled is True

    def test_status_enum(self):
        """Test status enum validation."""
        # Valid statuses
        for status in ["ok", "degraded", "error"]:
            response = HealthResponse(
                status=status,
                version="0.1.0",
                cache_enabled=True,
                cache_ttl_seconds=900
            )
            assert response.status == status

        # Invalid status
        with pytest.raises(ValidationError):
            HealthResponse(
                status="unknown",
                version="0.1.0",
                cache_enabled=True,
                cache_ttl_seconds=900
            )


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_valid_response(self):
        """Test valid error response."""
        response = ErrorResponse(
            error="ValidationError",
            message="Invalid request parameters",
            details={"tag_key": ["Field required"]}
        )

        assert response.error == "ValidationError"
        assert response.message == "Invalid request parameters"
        assert response.details is not None

    def test_optional_details(self):
        """Test that details field is optional."""
        response = ErrorResponse(
            error="APIError",
            message="External API unavailable"
        )

        assert response.details is None
