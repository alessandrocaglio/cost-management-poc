# Cost Management Redux

A lightweight web application that mimics the Red Hat Lightspeed Cost Management interface. Retrieves live cloud/infrastructure cost data from the Red Hat Lightspeed Cost Management API, applies custom cost aggregation and proportional distribution rules, and exposes the data via an interactive dashboard.

## Features

- **OAuth2 Authentication**: Secure integration with Red Hat SSO
- **Proportional Cost Distribution**: Distributes untagged overhead costs across tagged teams based on consumption ratios
- **Interactive Dashboard**: Vue.js frontend with Tailwind CSS
- **Flexible Filtering**: Filter by tag keys (owner, team, group), time ranges (presets + custom date picker)
- **Drill-Down Analysis**: Click on any tag to view project-level details
- **Response Caching**: 15-minute API response cache (configurable)

## Quick Start

### Prerequisites

- Python 3.9+
- Red Hat Cost Management API credentials (Client ID + Secret)
- Docker (optional, for containerized deployment)

### Local Development

1. **Clone and setup**
   ```bash
   cd costmanagement
   cp .env.example .env
   # Edit .env and add your COST_CLIENT_ID and COST_CLIENT_SECRET
   ```

2. **Run development server**
   ```bash
   make dev
   ```

3. **Access the dashboard**
   - Open http://localhost:8000 in your browser

### Available Make Commands

```bash
make dev          # Start development server with auto-reload
make test         # Run backend tests
make docker-build # Build Docker image
make push         # Push image to container registry
make clean        # Clean temporary files
```

## Project Structure

```
├── backend/              # FastAPI backend service
│   ├── app/
│   │   ├── main.py      # API routes and server
│   │   ├── config.py    # Configuration management
│   │   ├── services/    # API clients and business logic
│   │   └── models/      # Pydantic data models
│   └── tests/           # Backend tests
├── frontend/            # Vue.js frontend
│   ├── index.html       # Main dashboard
│   ├── app.js          # Vue application logic
│   └── styles.css      # Custom styles
├── charts/              # Helm chart for OpenShift deployment
├── docs/                # Reference documentation and examples
└── CLAUDE.md           # Development workflow and architecture guide
```

## Cost Distribution Algorithm

The application implements proportional overhead distribution:

1. **Aggregate**: Sum costs for each tag group
2. **Separate**: Isolate "No-group" (untagged) costs as overhead pool
3. **Calculate**: Determine each group's consumption ratio
4. **Distribute**: Apply formula:
   ```
   Final Cost = Tagged Cost + (Overhead Pool × Group Ratio)
   ```

See `docs/scripts/` for reference implementations.

## API Endpoints

- `GET /api/tags` - Available tag keys for grouping
- `GET /api/costs` - Distributed cost data (supports filtering)
- `GET /api/costs/drilldown` - Project-level details for a tag
- `GET /api/health` - Health check

Interactive API docs available at http://localhost:8000/docs

## Deployment

See `charts/cost-management-redux/` for Helm deployment to OpenShift.

## Documentation

- `docs/curl-examples.md` - API request examples
- `docs/scripts/` - Reference Python implementations
- `docs/screenshots/` - UI design reference
- `CLAUDE.md` - Complete development guide

## License

Internal Red Hat Labs Project
