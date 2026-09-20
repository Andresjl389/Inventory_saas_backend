.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install dependencies
	uv sync --extra dev

up: ## Start postgres + redis
	docker compose up -d postgres redis

down: ## Stop everything
	docker compose down

stack: ## Start the whole stack (api + worker included)
	docker compose up --build

migrate: ## Apply all migrations
	uv run alembic upgrade head

downgrade: ## Roll back one migration
	uv run alembic downgrade -1

revision: ## Autogenerate a migration: make revision m="add sales"
	uv run alembic revision --autogenerate -m "$(m)"

superuser: ## Create the first platform administrator (prompts for a password)
	uv run python -m app.cli create-superuser --email $(email)

sweep-files: ## Delete stored blobs no database row points at
	uv run python -m app.cli sweep-files --dry-run

low-stock: ## Run the low-stock sweep once, now
	uv run python -c "import asyncio; from app.infrastructure.jobs.low_stock import sweep_low_stock; print(asyncio.run(sweep_low_stock()))"

worker: ## Run the Arq worker
	uv run arq app.infrastructure.jobs.worker.WorkerSettings

run: ## Run the API with reload
	uv run uvicorn app.main:app --reload --port 8000

test: ## Run the test suite
	uv run pytest -q

test-db: ## Create the test database and run every test against it
	docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS inventory_test" || true
	docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE inventory_test OWNER inventory"
	TEST_DATABASE_URL=postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_test uv run pytest -q

lint: ## Lint and format check
	uv run ruff check app tests alembic
	uv run ruff format --check app tests alembic

format: ## Auto-format
	uv run ruff format app tests alembic
	uv run ruff check --fix app tests alembic

.PHONY: help install up down stack migrate downgrade revision superuser sweep-files low-stock worker run test test-db lint format
