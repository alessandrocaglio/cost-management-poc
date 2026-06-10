# CLAUDE.md - Cost Management Redux

## Project Overview
This project is a lightweight web application designed to mimic the Red Hat Lightspeed Cost Management interface. It retrieves live cloud/infrastructure cost data from the Red Hat Lightspeed Cost Management API, applies custom cost aggregation and proportional distribution rules, and exposes this data via an interactive frontend dashboard.

### Core Objectives
1. **UI Fidelity**: Mimic the look, feel, and structural logic of the Red Hat Cost Management UI using a clean interface (ideally leveraging PatternFly or minimalist Tailwind CSS).
2. **API Integration**: Authenticate against the Red Hat Lightspeed Cost Management API using a `clientId` and `clientSecret`.
3. **Custom Cost Distribution Engine**: 
   - Aggregate costs by tags (e.g., `owner`).
   - Show the actual directly-attributed cost for each tag.
   - Calculate the total "untagged" cost pool and distribute it proportionally across the identified tags based on their consumption ratios.
4. **Interactive Exploration**: Allow users to click on specific tags to drill down into deeper granular details, such as the specific projects associated with that tag and detailed consumption data.

---

## Developer Workflow (Strict Operational Rules)
For *every single task*, feature implementation, or bug fix, you **MUST** strictly follow the workflow sequence detailed below. Do not skip steps or jump straight to implementation.

1. **Analyze**: Thoroughly inspect the task requirements, the current codebase state, and any reference materials in the `docs/` folder (such as UI screenshots, curl command syntax, or prototype Python scripts).
2. **Ask Questions**: Identify any gaps in logic, missing data contracts, or visual layout ambiguities and ask the user for clarification. **Do not make assumptions.**
3. **Plan**: Write a clean, step-by-step technical execution blueprint detailing changes to both backend and frontend.
4. **Request Approval**: Present your analysis, questions, and plan to the user. **Wait for explicit approval** before writing code.
5. **Implement**: Write minimal, readable, and highly maintainable code matching the approved plan.
6. **Test**: Write localized tests or provide concrete execution instructions/scripts to demonstrate that the feature works and doesn't break existing components.
7. **Validate**: Perform a final compliance check against the original requirements to officially close out the task.

---

## Technical Stack Guidelines
To ensure the application remains **as simple as possible**, the following stack is recommended:

- **Backend**: **Python** using **FastAPI**. FastAPI provides automatic interactive documentation (Swagger), high performance, native async support, and straightforward JSON handling matching our API processing needs.
- **Frontend**: A minimal **JavaScript Framework** setup (e.g., **Vue.js** via CDN or plain modern ES6 JS with **Tailwind CSS** or a PatternFly CSS import). Avoid complex multi-tier build configurations unless absolutely required. Keep the UI layer lightweight, reactive, and localized to a single-page style dashboard.

### Core Algorithmic Requirement: Proportional Cost Distribution
When raw data is ingested:
1. Filter out all cost entries that contain a designated tag keyset (e.g., `owner=TeamA`, `owner=TeamB`). Sum these to find **Actual Tagged Cost** and **Tag Consumption**.
2. Accumulate all records lacking these tags into a **Total Untagged Cost Pool**.
3. Compute the allocation factor for each tag group:
   $$\text{Distribution Factor}_{\text{Tag}} = \frac{\text{Consumption}_{\text{Tag}}}{\sum \text{Consumption}_{\text{All Tagged Teams}}}$$
4. Calculate the adjusted final cost for the dashboard view:
   $$\text{Distributed Final Cost}_{\text{Tag}} = \text{Actual Tagged Cost}_{\text{Tag}} + \left( \text{Total Untagged Cost Pool} \times \text{Distribution Factor}_{\text{Tag}} \right)$$


### Documentation & Reference Materials
The `docs/` folder contains critical reference materials for implementation:

#### API Reference & Authentication
- **`curl-examples.md`**: Working curl commands showing:
  - OAuth2 token acquisition from Red Hat SSO (`https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token`)
  - Cost data retrieval from `/api/cost-management/v1/reports/openshift/costs/`
  - Tag filtering examples using `group_by[tag:group]=*` and `group_by[tag:team]`
  - Time scope filtering with `filter[time_scope_units]=month` and `filter[time_scope_value]=-1`
  - Tags endpoint: `/api/cost-management/v1/tags/openshift/`
- **`lightspeed-cost-management-api-cheatsheet.pdf`**: Complete API documentation with request/response schemas

#### UI Design Reference
- **`screenshots/photo_2026-06-10_10-35-00.jpg`**: Red Hat Cost Management UI showing:
  - Project-level view with total cost (€358.28 for June 1-10)
  - Sankey-style "Cost breakdown" visualization showing cost flow (Usage cost → Project costs, Overhead cost, etc.)
  - Overhead cost distribution dropdown ("Distribute through cost models")
  - Multiple tabs: Cost overview, Historical data, Virtualization, Optimizations
  - Resource breakdown panels: Memory, Persistent Volume Claims, CPU, Storage
  - Currency selector (EUR in screenshot)
  - Navigation breadcrumbs: OpenShift → Fleet management → Cost Management → OpenShift

**Key UI Elements to Mimic:**
1. **Top Section**: Project name, total cost (large), date range, currency selector
2. **Overhead Distribution**: Dropdown to select distribution method
3. **Cost Breakdown**: Sankey diagram showing cost flow and allocation
4. **Resource Panels**: Memory, Storage, PVC, GPU, CPU usage metrics with bar charts
5. **Tabbed Navigation**: Cost overview, Historical data, etc.

#### Cost Distribution Algorithm Reference
- **`scripts/allocate_costs.py`**: Reference implementation for 10-day cost allocation
  - Aggregates costs by group across all date entries
  - Separates "No-group" (untagged) overhead pool
  - Calculates pro-rata distribution: `share_of_overhead = (base_cost / total_tracked_spend) * overhead`
  - Outputs formatted report with Base Cost, Overhead Share, True Total Cost
- **`scripts/allocate_monthly.py`**: Monthly aggregation variant with same distribution logic

**Algorithm Pattern (from reference scripts):**
```python
# Step 1: Aggregate all costs by group
aggregated_costs = {}
for day_entry in data_days:
    for group_entry in day_entry.get("groups", []):
        group_name = group_entry.get("group")
        cost_metric = inner_metrics.get("cost") or inner_metrics.get("infrastructure", {})
        total_cost = cost_metric.get("total", {}).get("value", 0.0)
        aggregated_costs[group_name] = aggregated_costs.get(group_name, 0.0) + total_cost

# Step 2: Isolate overhead
overhead = aggregated_costs.get("No-group", 0.0)
total_tracked_spend = sum(cost for group, cost in aggregated_costs.items() if group != "No-group")

# Step 3: Distribute proportionally
for group, base_cost in aggregated_costs.items():
    if group == "No-group":
        continue
    share_of_overhead = (base_cost / total_tracked_spend) * overhead
    true_total = base_cost + share_of_overhead
```

---

## Expected Project Structure
```text
├── CLAUDE.md              # This workflow, architecture, and deployment guide
├── Makefile               # Automation command suite for development & CI/CD
├── Dockerfile             # Multi-stage production container build file
├── docs/                  # Reference documents provided by the user
│   ├── screenshots/       # Cost management UI references
│   ├── curl_examples/     # Raw API request/response format templates
│   └── scripts/           # Prototype python aggregation scripts
├── charts/                # Helm Deployment Configuration
│   └── cost-management-redux/
│       ├── Chart.yaml     # Helm chart metadata
│       ├── values.yaml    # Default variables (Quay image paths, replicas, etc.)
│       └── templates/     # Deployment, Service, Route, and Secret mapping manifests
├── backend/               # Python Backend Service
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py        # API routing and server initialization
│   │   ├── config.py      # Environment setup (loads values from OpenShift Secret)
│   │   ├── services/      # Red Hat API client & Cost Distribution Engine
│   │   └── models/        # Pydantic data schemas for clean validation
│   ├── requirements.txt
│   └── tests/
└── frontend/              # Simple JS Frontend
    ├── index.html         # Main dashboard layout (PatternFly/Tailwind styling)
    ├── app.js             # API fetching, interactive drill-down state, and rendering
    └── styles.css         # Minimal custom styling / CSS compilation
