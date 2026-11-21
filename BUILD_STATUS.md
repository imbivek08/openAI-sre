# OpenSRE AI — Build Status

Last updated: 2026-10-10

## Phase 1 — Repository and foundation ✅
- Repository structure created (monorepo: apps/, services/, agent/, tools/, integrations/, database/, simulator/)
- Python 3.12+ backend with FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic
- PostgreSQL-backed job queue (no Redis)
- docker-compose.yml (postgres, api, demo-api, dashboard, prometheus; optional grafana/ollama profiles)
- .env.example, Makefile, .gitignore, LICENSE (MIT)
- Alembic initial migration generated

## Phase 2 — Runtime simulator ✅
- Instrumented demo-api (FastAPI + PostgreSQL + prometheus-client)
- Structured JSON logging (stdout + shared file)
- Real Prometheus metrics: request count/duration, 5xx, DB op duration, pool checked-out (real), dependency health
- 3 fault-injection scenarios (pool exhaustion, elevated latency, config failure) — disabled by default, secret-protected
- Reset endpoint

## Phase 3 — Runtime evidence tools ✅
- query_prometheus (predefined query allowlist, bounded range/step)
- search_application_logs (JSONL store with filters)
- get_service_health, get_recent_deployments, search_runbook
- All tools typed (Pydantic inputs), with timeouts and output limits

## Phase 4 — Investigation engine ✅
- Model-provider abstraction (base, ollama, hosted, scripted-for-tests)
- Bounded loop: max iterations, tool calls, wall time, context size, output size
- Deterministic parsing + Pydantic validation of model outputs
- Evidence-reference validation (strips invalid refs)
- Per-source tool allowlists enforced independently by the engine
- SqlAlchemy store, events, findings, audit trail

## Phase 5 — GitHub integration ✅
- HMAC-SHA256 webhook verification (constant-time)
- Delivery deduplication, repository allowlist, event filtering
- GitHub REST client (read-only) with pagination, rate limits, redaction
- 5 GitHub tools (run, jobs, logs, commit, changed files)
- Background job queue + worker

## Phase 6 — Dashboard 🚧
- Next.js + TypeScript + Tailwind
- Overview, Incident details, Demo lab, Settings pages

## Phase 7 — Evaluation and security ✅
- Evaluation harness with deterministic scoring (root-cause, evidence relevance, refs validity, tool validity)
- 6 ground-truth scenarios
- Security tests: webhook auth, dedup, allowlist, redaction, admin auth
- 47 tests passing (unit + security + evaluation + integration)

## Phase 8 — Final integration 🚧
- Full stack startup verification
- Documentation

## Commands
```bash
make install          # Python venv + deps
make test             # unit tests
make test-integration # integration tests
make test-security    # security tests + bandit
make lint             # ruff
make eval             # evaluation harness
make compose-up       # full stack
```

## Known issues
- None currently.
