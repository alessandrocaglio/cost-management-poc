.PHONY: help install dev dev-token test lint format build push clean

# ── Configuration ────────────────────────────────────────────────────────────
IMAGE_NAME    ?= cost-management-redux
IMAGE_TAG     ?= latest
REGISTRY      ?= quay.io/acaglio
FULL_IMAGE    := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

BACKEND_DIR   := backend
PYTHON        := python3

# ── Help ─────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nCost Management Redux\n\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	      /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── Development ───────────────────────────────────────────────────────────────
install: ## Install Python dependencies
	pip install -r $(BACKEND_DIR)/requirements.txt

dev: ## Start dev server using .env credentials (requires .env file)
	@test -f .env || { echo "ERROR: .env not found — copy .env.example to .env and fill in credentials"; exit 1; }
	$(PYTHON) run_server.py --reload

dev-token: ## Start dev server with a bearer token: make dev-token TOKEN=eyJ...
	@test -n "$(TOKEN)" || { echo "ERROR: TOKEN is required — run: make dev-token TOKEN=<your-token>"; exit 1; }
	$(PYTHON) run_server.py --token "$(TOKEN)" --reload

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run tests with coverage report
	cd $(BACKEND_DIR) && pytest -v --cov=app --cov-report=term --cov-report=html

test-fast: ## Run tests without coverage (faster)
	cd $(BACKEND_DIR) && pytest -q

# ── Code Quality ──────────────────────────────────────────────────────────────
lint: ## Lint backend code with ruff (install: pip install ruff)
	@command -v ruff >/dev/null 2>&1 || { echo "ruff not found — run: pip install ruff"; exit 1; }
	ruff check $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

format: ## Auto-format backend code with black (install: pip install black)
	@command -v black >/dev/null 2>&1 || { echo "black not found — run: pip install black"; exit 1; }
	black $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

# ── Container ─────────────────────────────────────────────────────────────────
build: ## Build container image with podman
	podman build -t $(FULL_IMAGE) .
	@echo "Built: $(FULL_IMAGE)"

push: build ## Build and push image to registry
	podman push $(FULL_IMAGE)
	@echo "Pushed: $(FULL_IMAGE)"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean: ## Remove caches, build artifacts, and coverage reports
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov"       -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"         -delete 2>/dev/null || true
	find . -type f -name ".coverage"     -delete 2>/dev/null || true
	@echo "Clean complete."
