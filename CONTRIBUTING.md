# Contributing to OpenSRE AI

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone and enter the repository
git clone <repo-url>
cd opensre-ai

# Backend setup
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
make db-up

# Frontend setup
cd apps/dashboard && npm install
```

## Running Tests

```bash
make test              # unit tests
make test-integration  # integration tests
make test-security     # security tests
make lint              # ruff linting
```

## Project Structure

```
agent/           # Investigation engine, providers, prompts, policies
tools/           # Typed tool registry and implementations
integrations/    # GitHub, Prometheus, log integrations
database/        # SQLAlchemy models and Alembic migrations
simulator/       # Scenario registry with ground truth
api/             # FastAPI application
apps/dashboard/  # Next.js frontend
apps/api/        # API Dockerfile
services/demo-api/# Instrumented demo service
examples/        # Runbooks and sample workflows
scripts/         # Utility scripts
tests/           # Unit, integration, security, evaluation tests
```

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with tests
3. Ensure all tests pass: `make test && make test-integration && make test-security`
4. Ensure linting passes: `make lint`
5. Open a pull request with a clear description

## Code Style

- Python: ruff (line length 100), type hints required
- TypeScript: strict mode, no `any`
- All external text treated as untrusted data
