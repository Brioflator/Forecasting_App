# Forecast Platform — local developer entry points (doc 1 §4).
COMPOSE = docker compose -f docker/docker-compose.yml
TEST_DB ?= postgresql+psycopg://forecast:forecast@localhost:5432/forecast_test

.PHONY: up down logs seed seed-live migrate test lint regen-golden

up:            ## build + start the whole stack (pg, redis, api, worker, ml, frontend)
	$(COMPOSE) up --build -d

down:          ## stop the stack (keep data)
	$(COMPOSE) down

logs:          ## follow all service logs
	$(COMPOSE) logs -f

seed:          ## load connector catalog + demo connector/metric + 48-point backfill
	$(COMPOSE) exec api uv run --no-sync python -m api.seed

seed-live:     ## add real free-API connectors (CoinGecko, Open-Meteo, Frankfurter) + real history
	$(COMPOSE) exec api uv run --no-sync python -m api.seed_live

migrate:       ## run alembic upgrade head (api container)
	$(COMPOSE) exec api uv run --no-sync alembic upgrade head

test:          ## ruff + mypy + full pytest suite (DB tests hit the compose postgres)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	TEST_DATABASE_URL=$(TEST_DB) uv run pytest -q

lint:          ## ruff + mypy only
	uv run ruff check .
	uv run mypy

regen-golden:  ## deliberately regenerate ml golden fixtures (review the diff!)
	uv run python services/ml/tests/regen_golden.py
