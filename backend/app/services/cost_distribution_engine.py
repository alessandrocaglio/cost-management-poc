"""
Cost Distribution Calculation Engine

Implements proportional overhead distribution algorithm for untagged resources.
Distributes costs from untagged resources ("No-{tag_key}") proportionally across
tagged groups based on their consumption ratios.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GroupCostBreakdown:
    """
    Cost breakdown for a single group/tag value.

    Attributes:
        group_name: The tag value (e.g., "TeamA", "production")
        base_cost: Direct cost attributed to this group
        overhead_share: Proportional share of untagged overhead
        total_cost: base_cost + overhead_share
        consumption_ratio: Percentage of total tracked consumption (0.0-1.0)
    """
    group_name: str
    base_cost: float
    overhead_share: float
    total_cost: float
    consumption_ratio: float


@dataclass
class DistributionResult:
    """
    Result of cost distribution calculation.

    Attributes:
        groups: List of cost breakdowns per group
        total_overhead: Total untagged overhead pool
        total_tracked_cost: Sum of all tracked (tagged) costs
        total_distributed_cost: Sum of all final distributed costs
        tag_key: The tag key used for grouping
        untagged_group_name: Name of the untagged group (e.g., "No-owner")
    """
    groups: list[GroupCostBreakdown]
    total_overhead: float
    total_tracked_cost: float
    total_distributed_cost: float
    tag_key: str
    untagged_group_name: str


class DistributionEngine:
    """
    Engine for calculating proportional cost distribution.

    Follows the algorithm from docs/scripts/allocate_costs.py and allocate_monthly.py
    """

    @staticmethod
    def distribute_costs(api_response: dict, tag_key: str) -> DistributionResult:
        """
        Calculate proportional cost distribution from API response.

        Algorithm:
        1. Aggregate costs by group across all date entries
        2. Separate "No-{tag_key}" overhead from tracked costs
        3. Calculate each group's proportional share
        4. Distribute overhead based on consumption ratios

        Args:
            api_response: Raw API response from get_costs_by_tag()
            tag_key: The tag key used for grouping (e.g., "owner", "team")

        Returns:
            DistributionResult with cost breakdowns per group

        Raises:
            ValueError: If response format is invalid
        """
        # Step 1: Aggregate costs by group
        aggregated_costs = DistributionEngine._aggregate_by_group(api_response, tag_key)

        if not aggregated_costs:
            # No cost data
            return DistributionResult(
                groups=[],
                total_overhead=0.0,
                total_tracked_cost=0.0,
                total_distributed_cost=0.0,
                tag_key=tag_key,
                untagged_group_name=f"No-{tag_key}"
            )

        # Step 2: Separate overhead (untagged) from tracked costs
        untagged_group_name = f"No-{tag_key}"
        overhead = aggregated_costs.get(untagged_group_name, 0.0)

        # Calculate total tracked (tagged) spend
        total_tracked_spend = sum(
            cost for group, cost in aggregated_costs.items()
            if group != untagged_group_name
        )

        # Step 3: Calculate distribution for each group
        group_breakdowns = []

        if total_tracked_spend == 0:
            # Edge case: All costs are untagged, no distribution possible
            # Return overhead as a single entry
            if overhead > 0:
                group_breakdowns.append(
                    GroupCostBreakdown(
                        group_name=untagged_group_name,
                        base_cost=overhead,
                        overhead_share=0.0,
                        total_cost=overhead,
                        consumption_ratio=0.0
                    )
                )
        else:
            # Normal case: Distribute overhead proportionally
            for group_name, base_cost in sorted(aggregated_costs.items()):
                if group_name == untagged_group_name:
                    # Skip the overhead group itself
                    continue

                # Calculate this group's share of overhead
                consumption_ratio = base_cost / total_tracked_spend
                share_of_overhead = consumption_ratio * overhead
                true_total = base_cost + share_of_overhead

                group_breakdowns.append(
                    GroupCostBreakdown(
                        group_name=group_name,
                        base_cost=base_cost,
                        overhead_share=share_of_overhead,
                        total_cost=true_total,
                        consumption_ratio=consumption_ratio
                    )
                )

        # Calculate total distributed cost
        total_distributed = sum(g.total_cost for g in group_breakdowns)

        return DistributionResult(
            groups=group_breakdowns,
            total_overhead=overhead,
            total_tracked_cost=total_tracked_spend,
            total_distributed_cost=total_distributed,
            tag_key=tag_key,
            untagged_group_name=untagged_group_name
        )

    @staticmethod
    def _aggregate_by_group(api_response: dict, tag_key: str) -> dict[str, float]:
        """
        Aggregate costs by group across all date entries.

        The API uses a dynamic key naming convention: for group_by[tag:KEY]=*
        the response uses KEY+"s" as the array key and KEY as the item field.
        Examples:
          group_by[tag:team]=*   → data[].teams[].team
          group_by[tag:owner]=*  → data[].owners[].owner
          group_by[tag:cost_center]=* → data[].cost_centers[].cost_center

        Args:
            api_response: Raw API response dict
            tag_key: Tag key used for grouping (e.g. "team", "owner")

        Returns:
            Dict mapping group names to aggregated costs
        """
        aggregated_costs: dict[str, float] = {}

        # Derive the response keys from tag_key: "team" → "teams", "cost_center" → "cost_centers"
        group_list_key = f"{tag_key}s"
        group_name_field = tag_key

        data_entries = api_response.get("data", [])

        for entry in data_entries:
            # Try derived key first, then scan for any non-date list key as fallback
            groups = entry.get(group_list_key)
            if groups is None:
                groups = next(
                    (v for k, v in entry.items() if k != "date" and isinstance(v, list)),
                    []
                )
                if groups:
                    # Detect the name field from the first item (any non-"values" str field)
                    first = groups[0] if groups else {}
                    group_name_field = next(
                        (k for k, v in first.items() if k != "values" and isinstance(v, str)),
                        tag_key
                    )

            for group_entry in groups:
                group_name = group_entry.get(group_name_field)

                if not group_name:
                    continue

                cost_value = DistributionEngine._extract_cost_value(group_entry)
                aggregated_costs[group_name] = aggregated_costs.get(group_name, 0.0) + cost_value

        return aggregated_costs

    @staticmethod
    def _extract_cost_value(group_entry: dict) -> float:
        """
        Extract cost value from nested group structure.

        Follows pattern from docs/scripts/allocate_costs.py:
        - Try: values[0].cost.total.value
        - Fallback: values[0].infrastructure.total.value

        Args:
            group_entry: Single group entry from API response

        Returns:
            Cost value as float, or 0.0 if not found
        """
        values = group_entry.get("values", [])

        if not values:
            return 0.0

        inner_metrics = values[0]

        # Try "cost" first (primary path)
        cost_metric = inner_metrics.get("cost")
        if cost_metric:
            total = cost_metric.get("total", {})
            value = total.get("value")
            if value is not None:
                return float(value)

        # Fallback to "infrastructure" (alternative path)
        infra_metric = inner_metrics.get("infrastructure")
        if infra_metric:
            total = infra_metric.get("total", {})
            value = total.get("value")
            if value is not None:
                return float(value)

        return 0.0
