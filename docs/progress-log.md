# Progress Log

Evidence of what was actually run. Each entry: date, environment, command, real outcome. Failures are recorded, not removed.

## Milestone 1 — Foundations (2026-10-27)

**Environment:** Windows 11, Git Bash, Python 3.12.10 (`.venv`), Git 2.45.1. Tool versions installed by `pip install -e ".[dev]"`: pydantic 2.14.1, pydantic-settings 2.16.1, structlog 26.1.0, pytest 9.1.1, ruff 0.17.3, mypy 2.4.0. Docker 29.9.2 is present but not used in this milestone.

### Design corrections applied before implementation
- PostgreSQL 17 fixed as the only documentation version (decision D-1); removed all mention of version-18-only settings; added a PG 17 identifier allow-list check (architecture §7, §11).
- Severity policy rewritten with explicit thresholds, required inputs, and an undetermined path `SEV-UNDETERMINED` (rule U-1) instead of hand-assigned severities (architecture §9).
- §4.1 case rewritten around competing hypotheses H1–H6 and three test payloads (4.1-A/B/C); the cause is a verified leading hypothesis, never inferred from the symptom alone (architecture §8).
- Decision log with unresolved decisions D-1…D-9 (architecture §17).

### Commands and results

| # | Command | Result |
|---|---|---|
| 1 | `git status` (before any change) | `fatal: not a git repository` — no existing repo; directory contained only the PDF and `docs/` |
| 2 | `python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"` | Succeeded |
| 3 | `git init` | Initialised (default branch `master`) |
| 4 | `pytest -q` (first run) | **2 failed, 60 passed.** (a) `test_example_values_produce_valid_settings`: `PG_DOCS_MAJOR_VERSION=17` from the environment is the string `"17"`, which `Literal[17]` rejected — a real config bug; fixed by using `int` constrained to 17. (b) `test_repository_is_clean`: the scanner flagged a literal fake secret in `tests/unit/test_logging.py:75`; fixed by building the fake value at runtime. |
| 5 | `ruff check .` (first run) | 3 errors: 2 unused `noqa` (RUF100), 1 line too long (E501). Fixed in code, no new suppressions. |
| 6 | `ruff format --check .` (first run) | 1 file would be reformatted → `ruff format .` |
| 7 | `mypy` (first run, src only) | 1 error: unused `type: ignore` in `config.py`. Removed. |
| 8 | `pytest -q` | **62 passed** |
| 9 | `ruff check .` | `All checks passed!` |
| 10 | `ruff format --check .` | `18 files already formatted` |
| 11 | `mypy` (strict, `src` + `tests`, after adding `py.typed`) | `Success: no issues found in 13 source files` |
| 12 | `python -m triage.security.secret_scan` | `secret scan: 0 finding(s)`, exit 0 |
| 13 | `cp .env.example .env && git check-ignore -v .env` | `.gitignore:2:.env  .env` (ignored); `.env` then deleted |
| 14 | `Settings()` with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` unset | `ValidationError: 3 validation errors` naming `llm_base_url`, `llm_api_key`, `llm_model` |
| 15 | Log one event in a correlation scope | `{"llm_api_key": "[REDACTED]", "prompt_tokens": 42, "event": "run_submitted", "correlation_id": "demo-run-0001", "level": "info", "timestamp": "2026-10-27T15:49:50.292281Z"}` |

### Acceptance criteria (implementation-plan §4)

| # | Status |
|---|---|
| M1-1 install + repo with docs committed | Install verified (row 2). Commit: see git history (first commit of the repository). |
| M1-2 pytest ≥ 6 tests, exit 0 | **Verified** — 62 passed (row 8) |
| M1-3 ruff + format + mypy | **Verified** (rows 9–11) |
| M1-4 config from env, missing var named, non-positive limits rejected | **Verified** — `tests/unit/test_config.py` (row 8) and manual check (row 14) |
| M1-5 `.env.example` ↔ Settings both directions | **Verified** — `tests/unit/test_env_example.py` |
| M1-6 no secrets/endpoints/model ids; scanner proven on planted positives | **Verified** — `tests/unit/test_secret_scan.py` + row 12 |
| M1-7 `.env` ignored | **Verified** (row 13) |
| M1-8 JSON log with timestamp, level, event, correlation ID | **Verified** — `tests/unit/test_logging.py` + row 15 |
| M1-9 SLO committed before any load-test result | `docs/slo.md` in the first commit; no `loadtest/` exists. Re-check in Phase 10. |
| Exit: all pass on a second team member's machine | **Not yet done** — only run on the author's machine |
