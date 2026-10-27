# Production Incident Triage and Runbook Assistant

University mini project (UE24AM342AA5, Mini Project 08). A multi-agent service that takes a PostgreSQL alert plus an on-call note, retrieves the applicable PostgreSQL 17 documentation and runbooks, and **recommends** a cause class, first-response steps with verified citations, a severity and a route, or escalates to a human when the evidence does not support an answer. It never executes remediation and never connects to a live system.

> **Current state: Milestone 1 (foundations) only.** The repository contains configuration, structured logging, a secret scanner and their tests. There is no API, agent, retrieval or Docker stack yet. See [docs/implementation-plan.md](docs/implementation-plan.md) for the phases and [docs/requirements-matrix.md](docs/requirements-matrix.md) for verified status.

## Documentation

| Document | Content |
|---|---|
| [docs/requirements-matrix.md](docs/requirements-matrix.md) | Every requirement (F, A, L, D), demo item and deliverable, with status and evidence |
| [docs/architecture.md](docs/architecture.md) | Architecture, agent design, 4.1 investigation, severity policy, decisions and risks |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Phases, acceptance tests, repository layout |
| [docs/slo.md](docs/slo.md) | Declared p95 service-level objective (declared before any measurement) |
| [docs/progress-log.md](docs/progress-log.md) | Commands run and their actual results, per milestone |

## Development setup (Milestone 1)

Requires Python 3.11+ and Git. (Docker is required from Phase 4 onward.)

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1   |  Git Bash: source .venv/Scripts/activate
# Linux/macOS:        source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Configuration

All configuration comes from environment variables; nothing is read from a `.env` file implicitly, and no endpoint, credential or model identifier has a default in code. Every variable is documented in [.env.example](.env.example).

```bash
cp .env.example .env      # edit values; .env is git-ignored
```

From Phase 4, Docker Compose will inject `.env` into the containers. Until then, export the variables in your shell if you want to construct `Settings` manually; the tests set their own environment and need no `.env`.

## Checks

```bash
pytest -q                                  # unit tests
ruff check . && ruff format --check .      # lint + formatting
mypy                                       # strict type checking of src/
python -m triage.security.secret_scan      # D4 scan: exits 1 on any credential, endpoint or model id finding
```

The secret scan covers tracked and untracked-but-not-ignored files. Credential patterns are checked everywhere; hard-coded endpoints and model identifiers are checked in code and configuration (`src/`, `services/`, `scripts/`, `docker/`, compose files). It also fails if any `.env` file other than `.env.example` is tracked. Run it before every commit.

## Project layout (current)

```
src/triage/config.py                 environment-based settings with validation
src/triage/observability/logging.py  JSON logging, correlation IDs, redaction
src/triage/security/secret_scan.py   repository scanner for secrets/endpoints/model ids
tests/unit/                          tests for the above and for .env.example completeness
docs/                                plan, architecture, requirements matrix, SLO, progress log
```
