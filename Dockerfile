# Multi-stage Dockerfile for Cost Management Redux
#
# Stage 1 (builder): install Python deps into an isolated virtualenv
# Stage 2 (runtime): copy only the venv + application code; run as UID 1001

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="Cost Management Redux" \
      org.opencontainers.image.description="Red Hat Cost Management dashboard with proportional overhead distribution" \
      org.opencontainers.image.source="https://github.com/alessandrocaglio/cost-management-redux" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.vendor="Red Hat Labs"

# Non-root user with explicit UID 1001 (OpenShift-compatible)
RUN useradd --uid 1001 --create-home --shell /bin/bash appuser

WORKDIR /app

# Virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Application code
COPY backend/app /app/app

# Frontend static files (served by FastAPI StaticFiles)
COPY frontend /app/frontend

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
