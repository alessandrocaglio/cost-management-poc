"""
Tests for Cost Distribution Calculation Engine
"""

import pytest

from app.services.cost_distribution_engine import (
    DistributionEngine,
    DistributionResult,
    GroupCostBreakdown
)


@pytest.fixture
def sample_api_response_owner():
    """
    Sample API response for costs grouped by 'owner' tag.
    Includes "No-owner" overhead group.
    """
    return {
        "data": [
            {
                "date": "2026-06",
                "groups": [
                    {
                        "group": "TeamA",
                        "values": [{
                            "cost": {"total": {"value": 1000.0}},
                            "usage": {"value": 100}
                        }]
                    },
                    {
                        "group": "TeamB",
                        "values": [{
                            "cost": {"total": {"value": 1500.0}},
                            "usage": {"value": 150}
                        }]
                    },
                    {
                        "group": "No-owner",  # Untagged overhead
                        "values": [{
                            "cost": {"total": {"value": 500.0}},
                            "usage": {"value": 50}
                        }]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_api_response_team():
    """
    Sample API response for costs grouped by 'team' tag.
    Includes "No-team" overhead group.
    """
    return {
        "data": [
            {
                "date": "2026-06",
                "groups": [
                    {
                        "group": "platform",
                        "values": [{
                            "cost": {"total": {"value": 2000.0}}
                        }]
                    },
                    {
                        "group": "No-team",  # Untagged overhead
                        "values": [{
                            "cost": {"total": {"value": 1000.0}}
                        }]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def multi_day_response():
    """API response with costs spread across multiple days."""
    return {
        "data": [
            {
                "date": "2026-06-01",
                "groups": [
                    {
                        "group": "TeamA",
                        "values": [{"cost": {"total": {"value": 100.0}}}]
                    },
                    {
                        "group": "No-owner",
                        "values": [{"cost": {"total": {"value": 50.0}}}]
                    }
                ]
            },
            {
                "date": "2026-06-02",
                "groups": [
                    {
                        "group": "TeamA",
                        "values": [{"cost": {"total": {"value": 200.0}}}]
                    },
                    {
                        "group": "No-owner",
                        "values": [{"cost": {"total": {"value": 100.0}}}]
                    }
                ]
            }
        ]
    }


def test_distribute_costs_basic(sample_api_response_owner):
    """Test basic cost distribution calculation."""
    result = DistributionEngine.distribute_costs(sample_api_response_owner, "owner")

    # Verify result structure
    assert isinstance(result, DistributionResult)
    assert result.tag_key == "owner"
    assert result.untagged_group_name == "No-owner"

    # Verify overhead separation
    assert result.total_overhead == 500.0
    assert result.total_tracked_cost == 2500.0  # TeamA (1000) + TeamB (1500)

    # Verify group count (excludes "No-owner")
    assert len(result.groups) == 2

    # Find TeamA breakdown
    team_a = next(g for g in result.groups if g.group_name == "TeamA")
    assert team_a.base_cost == 1000.0
    assert team_a.consumption_ratio == pytest.approx(0.4)  # 1000 / 2500
    assert team_a.overhead_share == pytest.approx(200.0)  # 0.4 * 500
    assert team_a.total_cost == pytest.approx(1200.0)  # 1000 + 200

    # Find TeamB breakdown
    team_b = next(g for g in result.groups if g.group_name == "TeamB")
    assert team_b.base_cost == 1500.0
    assert team_b.consumption_ratio == pytest.approx(0.6)  # 1500 / 2500
    assert team_b.overhead_share == pytest.approx(300.0)  # 0.6 * 500
    assert team_b.total_cost == pytest.approx(1800.0)  # 1500 + 300

    # Verify total distributed cost
    assert result.total_distributed_cost == pytest.approx(3000.0)  # 1200 + 1800


def test_distribute_costs_different_tag(sample_api_response_team):
    """Test distribution with different tag key (team vs owner)."""
    result = DistributionEngine.distribute_costs(sample_api_response_team, "team")

    assert result.tag_key == "team"
    assert result.untagged_group_name == "No-team"
    assert result.total_overhead == 1000.0
    assert result.total_tracked_cost == 2000.0

    # Single group gets all overhead
    assert len(result.groups) == 1
    platform = result.groups[0]
    assert platform.group_name == "platform"
    assert platform.consumption_ratio == pytest.approx(1.0)
    assert platform.overhead_share == pytest.approx(1000.0)
    assert platform.total_cost == pytest.approx(3000.0)


def test_aggregate_multi_day_costs(multi_day_response):
    """Test cost aggregation across multiple date entries."""
    result = DistributionEngine.distribute_costs(multi_day_response, "owner")

    # TeamA costs: Day 1 (100) + Day 2 (200) = 300
    # No-owner costs: Day 1 (50) + Day 2 (100) = 150

    assert result.total_tracked_cost == 300.0
    assert result.total_overhead == 150.0

    team_a = result.groups[0]
    assert team_a.base_cost == 300.0
    assert team_a.overhead_share == pytest.approx(150.0)  # All overhead goes to only group
    assert team_a.total_cost == pytest.approx(450.0)


def test_no_overhead():
    """Test distribution when there's no overhead (all costs tagged)."""
    response = {
        "data": [{
            "groups": [
                {"group": "TeamA", "values": [{"cost": {"total": {"value": 1000.0}}}]},
                {"group": "TeamB", "values": [{"cost": {"total": {"value": 500.0}}}]}
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "owner")

    assert result.total_overhead == 0.0
    assert result.total_tracked_cost == 1500.0

    # No overhead to distribute
    for group in result.groups:
        assert group.overhead_share == 0.0
        assert group.total_cost == group.base_cost


def test_only_overhead_no_tracked():
    """Test when all costs are untagged (only overhead, no tracked costs)."""
    response = {
        "data": [{
            "groups": [
                {"group": "No-env", "values": [{"cost": {"total": {"value": 1000.0}}}]}
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "env")

    assert result.total_overhead == 1000.0
    assert result.total_tracked_cost == 0.0

    # Should return overhead as single group
    assert len(result.groups) == 1
    assert result.groups[0].group_name == "No-env"
    assert result.groups[0].base_cost == 1000.0
    assert result.groups[0].overhead_share == 0.0
    assert result.groups[0].total_cost == 1000.0


def test_empty_response():
    """Test with empty API response."""
    response = {"data": []}

    result = DistributionEngine.distribute_costs(response, "owner")

    assert len(result.groups) == 0
    assert result.total_overhead == 0.0
    assert result.total_tracked_cost == 0.0
    assert result.total_distributed_cost == 0.0


def test_cost_extraction_infrastructure_fallback():
    """Test cost extraction falls back to infrastructure.total.value."""
    response = {
        "data": [{
            "groups": [
                {
                    "group": "TeamA",
                    "values": [{
                        "infrastructure": {"total": {"value": 750.0}},  # No "cost" field
                        "usage": {"value": 100}
                    }]
                },
                {
                    "group": "No-owner",
                    "values": [{
                        "infrastructure": {"total": {"value": 250.0}}
                    }]
                }
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "owner")

    # Should extract from infrastructure path
    assert result.total_tracked_cost == 750.0
    assert result.total_overhead == 250.0


def test_missing_cost_values():
    """Test handling of groups with missing cost values."""
    response = {
        "data": [{
            "groups": [
                {"group": "TeamA", "values": [{"cost": {"total": {"value": 1000.0}}}]},
                {"group": "TeamB", "values": []},  # No values
                {"group": "TeamC", "values": [{}]},  # Empty value
                {"group": "No-owner", "values": [{"cost": {"total": {"value": 100.0}}}]}
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "owner")

    # TeamB and TeamC should be treated as 0 cost
    assert result.total_tracked_cost == 1000.0  # Only TeamA
    assert result.total_overhead == 100.0


def test_single_group_gets_all_overhead():
    """Test that single tagged group receives all overhead."""
    response = {
        "data": [{
            "groups": [
                {"group": "OnlyTeam", "values": [{"cost": {"total": {"value": 500.0}}}]},
                {"group": "No-team", "values": [{"cost": {"total": {"value": 200.0}}}]}
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "team")

    assert len(result.groups) == 1
    only_team = result.groups[0]
    assert only_team.consumption_ratio == pytest.approx(1.0)
    assert only_team.overhead_share == pytest.approx(200.0)  # All overhead
    assert only_team.total_cost == pytest.approx(700.0)


def test_proportional_distribution_matches_reference():
    """
    Test that distribution matches reference script calculation.

    Based on docs/scripts/allocate_costs.py example output.
    """
    # Simulated data similar to reference script
    response = {
        "data": [{
            "groups": [
                {"group": "group1", "values": [{"cost": {"total": {"value": 1000.0}}}]},
                {"group": "group2", "values": [{"cost": {"total": {"value": 2000.0}}}]},
                {"group": "group3", "values": [{"cost": {"total": {"value": 1500.0}}}]},
                {"group": "No-group", "values": [{"cost": {"total": {"value": 900.0}}}]}
            ]
        }]
    }

    result = DistributionEngine.distribute_costs(response, "group")

    total_tracked = 4500.0  # 1000 + 2000 + 1500
    overhead = 900.0

    assert result.total_tracked_cost == total_tracked
    assert result.total_overhead == overhead

    # Verify proportional distribution
    # group1: 1000 / 4500 = 0.222... of overhead = 200
    # group2: 2000 / 4500 = 0.444... of overhead = 400
    # group3: 1500 / 4500 = 0.333... of overhead = 300

    group1 = next(g for g in result.groups if g.group_name == "group1")
    assert group1.overhead_share == pytest.approx(200.0, rel=1e-2)
    assert group1.total_cost == pytest.approx(1200.0, rel=1e-2)

    group2 = next(g for g in result.groups if g.group_name == "group2")
    assert group2.overhead_share == pytest.approx(400.0, rel=1e-2)
    assert group2.total_cost == pytest.approx(2400.0, rel=1e-2)

    group3 = next(g for g in result.groups if g.group_name == "group3")
    assert group3.overhead_share == pytest.approx(300.0, rel=1e-2)
    assert group3.total_cost == pytest.approx(1800.0, rel=1e-2)

    # Total distributed should equal tracked + overhead
    assert result.total_distributed_cost == pytest.approx(5400.0)
