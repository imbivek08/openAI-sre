SHELL := /bin/bash
COMPOSE := docker compose
PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn

.PHONY: install install-api install-frontend dev-api dev-demo dev-dashboard \
        db-up db-revision test test-unit test-integration test-security lint format \
        eval eval-all compose-up compose-down logs build clean

# --- Setup ------------------------------------------------------------------
install: install-api

install-api:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

install-frontend:
	cd apps/dashboard && npm install

dev-api:
	$(UVICORN) api.main:app --reload --host 0.0.0.0 --port 8000

dev-demo:
	cd services/demo-api && ../../.venv/bin/uvicorn demo_api.main:app --reload --port 8001

dev-dashboard:
	cd apps/dashboard && npm run dev

# --- Database ---------------------------------------------------------------
db-up:
	$(PY) -m alembic -c database/alembic.ini upgrade head

db-revision:
	$(PY) -m alembic -c database/alembic.ini revision --autogenerate -m "$(name)"

# --- Tests ------------------------------------------------------------------
test: test-unit

test-unit:
	$(PY) -m pytest tests/unit -q

test-integration:
	$(PY) -m pytest tests/integration -q

test-security:
	$(PY) -m pytest tests/security -q
	.venv/bin/bandit -r agent tools integrations api database simulator -q

test-eval:
	$(PY) -m pytest tests/evaluation -q

lint:
	.venv/bin/ruff check agent tools integrations api database simulator tests
	.venv/bin/ruff format --check agent tools integrations api database simulator tests

format:
	.venv/bin/ruff check --fix agent tools integrations api database simulator tests
	.venv/bin/ruff format agent tools integrations api database simulator tests

typecheck:
	$(PY) -m compileall -q agent tools integrations api database simulator api

eval:
	$(PY) -m agent.evaluator run

eval-all:
	$(PY) -m agent.evaluator run-all

# --- Compose ----------------------------------------------------------------
compose-up:
	$(COMPOSE) up -d --build

compose-down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api demo-api

# --- Demo helpers -----------------------------------------------------------
demo-traffic:
	$(PY) scripts/generate_traffic.py --seconds 60 --rps 5

demo-reset:
	$(PY) scripts/reset_demo.py

build:
	$(COMPOSE) build

clean:
	rm -rf .pytest_cache .ruff_cache var/log apps/dashboard/.next apps/dashboard/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
