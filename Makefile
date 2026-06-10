.PHONY: dev test docker-build push clean help

# Configuration
IMAGE_NAME ?= cost-management-redux
IMAGE_TAG ?= latest
REGISTRY ?= quay.io/your-org

help:
	@echo "Cost Management Redux - Available Commands"
	@echo "==========================================="
	@echo "make dev          - Start development server (backend + frontend)"
	@echo "make test         - Run backend tests with coverage"
	@echo "make docker-build - Build Docker image"
	@echo "make push         - Push Docker image to registry"
	@echo "make clean        - Clean temporary files and caches"
	@echo ""

dev:
	@echo "Starting development server..."
	@echo "Frontend: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"
	@if [ ! -f .env ]; then echo "ERROR: .env file not found. Copy .env.example to .env and configure credentials."; exit 1; fi
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "Running backend tests..."
	cd backend && pytest -v --cov=app --cov-report=html --cov-report=term

docker-build:
	@echo "Building Docker image: $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)"
	docker build -t $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG) .

push: docker-build
	@echo "Pushing image to registry..."
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "Clean complete."
