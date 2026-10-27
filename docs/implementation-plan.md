# Implementation Plan — Production Incident Triage and Runbook Assistant

Companion to [requirements-matrix.md](requirements-matrix.md) and [architecture.md](architecture.md).

**Rule for every phase:** a phase is complete only when its acceptance tests have been *run* and their output recorded (command + result) in `docs/progress-log.md`, and the matrix status updated with a link to that evidence. No phase starts until the previous one is verified, except where a dependency table says otherwise.

**Assessment gate (§10):** if the system does not start and serve a valid request at the demo, the project scores zero. Therefore the sequence below builds a thin but real end-to-end path in Docker Compose by **Phase 4 (target: end of week 2)** and only then deepens it. This moves Docker Compose earlier than the original "Phase 7" ordering; Phase 7 becomes hardening of service boundaries rather than first containerisation.

---

## 1. Proposed repository structure

The current directory contains only the assignment PDF, so this is a fresh layout. One Python package is shared by the API and both worker images (different entrypoints), which avoids duplicated contract code while still producing separate deployable services.

```
.
├── README.md                      # run-from-clean-clone instructions (tested)
├── .env.example                   # every setting, placeholder values only (D4)
├── .gitignore                     # .env, data/index, __pycache__, reports/tmp
├── pyproject.toml                 # deps, ruff, mypy, pytest config
├── docker-compose.yml
├── docker/
│   ├── python-base.Dockerfile     # shared base: deps + CPU torch + cached embedding model
│   ├── api.Dockerfile
│   ├── worker.Dockerfile          # used by agent-worker, verifier-worker, ingest
│   └── llm-stub.Dockerfile
├── src/triage/
│   ├── config.py                  # pydantic-settings, env only
│   ├── contracts/                 # alert.py, run.py, recommendation.py, feedback.py, evidence.py
│   ├── api/                       # main.py, routes/, ratelimit.py, deps.py, static/index.html
│   ├── validation/                # cross-field rules, quarantine.py
│   ├── persistence/               # db.py, models.py, repositories.py
│   ├── queue/                     # celery_app.py, tasks.py, watchdog.py
│   ├── agents/
│   │   ├── investigator/          # graph.py, nodes.py
│   │   ├── verifier/              # graph.py, checks.py
│   │   ├── limits.py              # step / tool-call / wall-clock budget
│   │   └── prompts.py             # versioned prompt loader
│   ├── tools/                     # search_corpus.py, get_section.py, follow_references.py, request_fields.py, get_passage.py
│   ├── retrieval/                 # embeddings.py, store.py (Chroma), hybrid.py (BM25+RRF), cache.py
│   ├── ingest/                    # fetch.py, parse_pg_html.py, parse_markdown.py, chunk.py, pipeline.py, __main__.py
│   ├── policy/                    # engine.py (severity, route, basis)
│   ├── guardrails/                # injection.py, toxicity.py, output_filter.py
│   ├── llm/                       # client.py (OpenAI-compatible), retry.py, breaker.py, fallback.py, pricing.py
│   ├── observability/             # logging.py, tracing.py, metrics.py
│   └── eval/                      # dataset.py, metrics.py, judge.py, runner.py, __main__.py
├── services/llm_stub/app.py       # OpenAI-compatible stub with delay + fail modes
├── prompts/                       # investigator/v1.yaml, v2.yaml; verifier/v1.yaml; judge/v1.yaml
├── corpus/
│   ├── manifest.yaml              # PG version, page list, sha256, fetch date
│   ├── postgresql-17/             # raw HTML (committed)
│   ├── runbooks/                  # RB-001..RB-003.md
│   └── policy/                    # severity-policy.md + severity-policy.yaml
├── eval/
│   ├── scenarios.yaml             # ≥20 scenarios
│   └── results/                   # committed reports from real runs only
├── loadtest/locustfile.py
├── observability/
│   ├── prometheus.yml
│   └── grafana/provisioning/{datasources,dashboards}/
├── ops/
│   ├── runbook.md                 # D8
│   └── incident-log.md            # D8, genuine entries only
├── docs/
│   ├── requirements-matrix.md, architecture.md, implementation-plan.md
│   ├── progress-log.md            # evidence of each phase's verification
│   ├── contracts/*.json           # exported JSON Schemas
│   └── report/report.md
└── tests/
    ├── unit/ ├── integration/ └── e2e/
```

Deliberately **not** created: a separate retrieval service, a separate frontend app/container, a microservice per tool, an OTel Collector (see architecture §4).

## 2. Phases

Legend: **[M]** mandatory · **[O]** optional polish. Effort is a rough estimate for a 2–3 person team.

### Phase 1 — Project foundations, configuration, foundational tests  *(Milestone 1, ~1–2 days)*
- **Goals [M]:** repo skeleton, `pyproject.toml` (ruff, mypy strict on `src/`, pytest), `config.py` reading only env vars, `.env.example`, `.gitignore`, structured logging bootstrap, `docs/slo.md`, `git init` + first commit containing the docs **and the SLO declaration** (D6 requires the target to pre-date measurement), `docs/progress-log.md`. No Docker, agents, retrieval or HTTP services in this phase.
- **Files:** `pyproject.toml`, `src/triage/__init__.py`, `src/triage/config.py`, `src/triage/observability/logging.py`, `src/triage/security/secret_scan.py` (CLI: `python -m triage.security.secret_scan`), `src/triage/py.typed`, `tests/unit/test_config.py`, `tests/unit/test_env_example.py`, `tests/unit/test_secret_scan.py`, `tests/unit/test_logging.py`, `.env.example`, `.gitignore`, `README.md`, `docs/slo.md`, `docs/progress-log.md`.
- **Tests / acceptance criteria:** see §4 below (precise).
- **Requirements touched:** D4, F8 (logging basis), D6 (SLO declared).
- **Depends on:** nothing.

### Phase 2 — Data contracts, validation, quarantine  *(~2 days)*
- **Goals [M]:** `AlertSubmission v1.0` (fields in architecture §15, incl. required `user_impact` and the optional metrics the policy and 4.1 variants need) and result contracts; cross-field rules; JSON Schema export; FastAPI app with `POST /v1/incidents`, `GET /v1/contracts/*`, `/health`; app-DB models (runs, quarantine) with SQLAlchemy; quarantine write path. Enqueue is an interface (`RunDispatcher`) with a recording fake for now.
- **Files:** `contracts/*`, `validation/*`, `persistence/*`, `api/main.py`, `api/routes/incidents.py`, `docs/contracts/alert-submission.v1.json`.
- **Tests:** one invalid fixture per rule class (schema, type, range, category, cross-field) → `422`, quarantine row with exact field path, fake dispatcher called **0** times, `runs` count unchanged; valid 4.1 payload → `202` + `run_id`, dispatcher called once; schema file equals generated schema; version 15 payload → accepted (escalation handled later).
- **Acceptance:** all tests pass; Demo 4 logic proven at unit/integration level (SQLite allowed only in unit tests; Postgres in integration).
- **Requirements:** F1, F2, D1. **Depends on:** Phase 1.

### Phase 3 — Corpus acquisition, ingestion and retrieval  *(~3 days)*
- **Goals [M]:** `manifest.yaml` + fetch script (one-off, polite, records SHA-256); commit raw PG 17 HTML; write RB-001..003 and the severity policy (md + yaml); HTML parser preserving anchors, `varlistentry`s and links; chunker; local embeddings; Chroma upsert by content hash; BM25 + dense hybrid via LangChain; ingestion CLI with freshness/throughput metrics; tool functions `search_corpus`, `get_section`, `follow_references`, `get_passage`.
- **Tests:** parser unit tests on saved HTML fixtures (anchors, GUC entries, links extracted); idempotency (second run: 0 embedded, identical IDs); changed-file run re-embeds only that file; `get_section("max_slot_wal_keep_size")` returns the parameter entry; retrieval smoke test listing top results for 4.1 queries; **record the real chunk IDs and text for every 4.1 passage** in architecture §8 (replacing the page-level placeholders); build the PG 17 identifier allow-list (parameters, views, columns, functions) and confirm every identifier used in RB-001..003 is in it.
- **Acceptance:** index built from a clean directory with one command; 4.1 passages confirmed present in the index with real IDs (Evaluation 1 material); metrics exposed.
- **Requirements:** L1, D2, F4 (partial), §3 corpus. **Depends on:** Phase 1 (Phase 2 can proceed in parallel by another team member).

### Phase 4 — Walking skeleton: thin end-to-end path in Docker Compose  *(target end of week 2, ~3 days)*
- **Goals [M]:** Celery app + Redis; single Investigator graph in LangGraph with the tools above and step/tool/time limits; `LLMClient` (OpenAI-compatible) with timeouts; `llm-stub` service with scripted tool-calling responses that cite real retrieved chunk IDs; deterministic citation-resolution check (precursor to verifier); minimal policy engine; `GET /v1/runs/{id}`; static web client; `docker-compose.yml` with `api`, `agent-worker`, `redis`, `app-db`, `chroma`, `llm-stub`, `ingest` and health checks.
- **Tests:** e2e (compose): submit 4.1 payload → poll → `COMPLETED` with ≥1 citation whose quote is found in the cited chunk text; malformed payload → `422` and no worker log for it; limit tests (stub that never stops → run ends `ESCALATED` at the limit); API p50 submit latency < 200 ms while run takes seconds.
- **Acceptance:** from a fresh clone in a new directory: `cp .env.example .env && docker compose up -d` → all services healthy → web client shows a cited recommendation (stub-driven). Demo 1 and 4 work in rough form.
- **Requirements:** A1 (partial), A4, D3, A8 (basic), F5 (partial). **Depends on:** Phases 2, 3.

### Phase 5 — Two agents, iterative investigation, verification  *(~4 days)*
- **Goals [M]:** split into Investigator (`agent-worker`) and Verifier (`verifier-worker`) with `EvidenceBundle` hand-off via queue `verify`; hypothesis + reflection nodes (modifier search); `REVISE` loop with a changed strategy (bounded); verifier citation + claim-support checks + counter-evidence search; stuck-run watchdog; versioned prompts with version recorded per step; switch from stub to the real free-tier provider for development runs.
- **Tests:** stub "fabricated citation" mode → verifier rejects → trace shows revision then success or escalation (Demo 6); kill verifier mid-run → `ESCALATED (verification_unavailable)`, never `COMPLETED`; property test: no `COMPLETED` run has an unresolved citation; prompt version present on every step.
- **Acceptance:** Demo 2 and Demo 6 reproducible with stub; 4.1 reaches the slot/WAL cause with the real model in at least 4 of 5 runs (measured, reported honestly).
- **Requirements:** A1, A2, A3, F3, F5, L2 (versioning). **Depends on:** Phase 4.

### Phase 6 — Severity, escalation, the §4.1 case, evaluation set v1  *(~3 days)*
- **Goals [M]:** full policy engine (rules S*, U-1, E-* in architecture §9) with `basis` and `missing_inputs`; F7 ambiguity margin and out-of-corpus detection; version-mismatch escalation; `eval/scenarios.yaml` with ≥ 20 scenarios and expected supporting chunk IDs; eval CLI computing task metrics (cause, route, escalation precision/recall, expected-passage recall).
- **Tests:** policy boundary tests for every threshold (`hours_to_full` 3.99 vs 4.0, disk 84.9 vs 85.0, lag 299 vs 300 s) and every missing-input combination → `SEV-UNDETERMINED`; policy md/yaml consistency test; eval run on real model with results committed; 4.1-A escalates with ranked hypotheses, 4.1-B answers with H1 as leading hypothesis and competing explanations addressed, 4.1-C escalates as ambiguous (architecture §8); every identifier in every answer present in the PG 17 identifier allow-list; 4.1-B severity equals the policy engine's computed value (not hand-assigned).
- **Acceptance:** Demo 5 and Demo 10 pass; first eval report committed.
- **Requirements:** F6, F7, F3, F4, L3 (dataset). **Depends on:** Phase 5.

### Phase 7 — Guardrails, reliability, service hardening  *(~3 days)*
- **Goals [M]:** injection detector on every free-text field, delimiting of untrusted text, `detoxify` on input/output, output filter; `tenacity` retries with backoff; Redis-backed circuit breaker; fallback path to retrieval-only degraded mode; stub admin endpoints (`/admin/mode` = ok | slow | fail | bad_citation); `verifier-worker` and `agent-worker` health checks, restart policies, `acks_late`.
- **Tests:** ≥ 10 injection strings flagged; benign notes not flagged (false-positive check on eval notes); output-filter unit tests; retry count and backoff timing with fake clock; breaker opens after threshold, half-opens, closes; degraded runs never `COMPLETED`.
- **Acceptance:** Demo 7 and Demo 8 performed against the compose stack and recorded.
- **Requirements:** L4, A5, A2 (failure semantics). **Depends on:** Phase 5 (can overlap Phase 6).

### Phase 8 — Observability, cost tracking, run reconstruction  *(~3 days)*
- **Goals [M]:** OTel tracing across api → agent-worker → verifier-worker (context in Celery headers) to Jaeger; Prometheus scrape of every service incl. scaled workers (DNS discovery); A6 metrics; token/cost recording per call/step/run; `GET /v1/runs/{id}/trace`; Grafana dashboards provisioned; cAdvisor **[O if it fails on Windows; then documented fallback]**.
- **Tests:** single run → one Jaeger trace with spans from 3 services; `/trace` contains every tool call, query, passage, prompt version, latency and cost; sum of step costs = run cost; every Prometheus target `UP`.
- **Acceptance:** Demo 3 performed; dashboard screenshots committed.
- **Requirements:** F8, D5, A6, L5. **Depends on:** Phase 5.

### Phase 9 — Evaluation metrics, prompt comparison, feedback
- **Goals:** **[M]** groundedness, context relevance, faithfulness, hallucination rate (definitions in architecture §10); prompt v1 vs v2 comparison; deliberate change (single-pass vs iterative retrieval) before/after; runbook-ablation run for 4.1; cost per 100 runs and largest cost driver; `POST /v1/runs/{id}/feedback` + summary. **[O]** online sampling of live runs and "quality over time" panel; TruLens adapter.
- **Tests:** metric functions unit-tested on hand-labelled toy examples; eval reports generated by the CLI and committed with the git SHA and prompt versions; feedback persisted and aggregated.
- **Acceptance:** report tables filled only from committed result files.
- **Requirements:** L2, L3, L5, L6. **Depends on:** Phases 6, 8.

### Phase 10 — Load testing, scaling, caching, rate limiting, final demo
- **Goals:** **[M]** Locust user that submits and polls to completion; step-load to find the concurrency where p95 > 60 s; run at `--scale agent-worker=1` and `=3`; bottleneck analysis from metrics; per-client rate limiting; D8 system runbook + incident log; README validated by someone who has not seen the project running; report; rehearse all ten demos. **[M-lite]** embedding/retrieval caches with measured effect on p95 and cost. **[O]** whole-run cache, `callback_url` webhooks.
- **Tests:** Locust CSV/HTML committed; rate limit test (burst + 1 → 429); clean-clone run timed by a teammate following only the README.
- **Acceptance:** all ten demo items rehearsed with evidence; matrix fully updated with honest statuses.
- **Requirements:** D6, A7, D7, D8, deliverables. **Depends on:** all.

## 3. Prioritisation (if time runs short)

1. **Never cut (P0):** F1–F7, A1–A4, D1–D4, L1, basic F8, Demo 1/2/4/5/6/10.
2. **Cut last (P1, each needed for a demo item):** A5 (Demo 8), L4 (Demo 7), D5 (Demo 3), D6 + A7 (Demo 9), L3 core metrics, L2, L5, A6, A8, D8.
3. **Cut first (P2):** whole-run cache and webhooks (D7/A4 extras), online quality sampling (L6 second half), TruLens adapter, cAdvisor (replace with documented fallback), local ML injection classifier (rules + detoxify remain).

Rationale to state in the viva: the zero-mark gate and F5/F7 ("most of the difficulty") get resources first; every P1 item is tied to a named demo item; P2 items deepen requirements that already have a working, demonstrable baseline.

## 4. Milestone 1 (Phase 1) — precise acceptance tests

Run all of these and paste the outputs into `docs/progress-log.md` before Phase 2 begins.

**Status (2026-10-27):** M1-1 … M1-9 verified on the author's machine — evidence in [progress-log.md](progress-log.md). The cross-machine exit criterion is still open.

Scanner scope (decision D-10): credential patterns are checked in every file; endpoint and model-identifier patterns only in code/config (`src/`, `services/`, `scripts/`, `docker/`, compose files). Documentation may name the technologies it describes. `.env.example` may contain the in-compose stub address as a runnable default.

| # | Test | Command | Pass condition |
|---|---|---|---|
| M1-1 | Repository and tooling exist | `git status`; `python -m pip install -e ".[dev]"` in a virtualenv | Clean install, no errors; repo initialised with docs committed. |
| M1-2 | Unit tests run | `pytest -q` | Exit code 0; ≥ 6 tests collected (not zero). |
| M1-3 | Lint, format and types | `ruff check . && ruff format --check . && mypy` | Exit code 0 (mypy strict on `src/`). |
| M1-4 | Config loads from environment only | `tests/unit/test_config.py` | With required env vars set, `Settings()` populates values; with a required var (e.g. `LLM_BASE_URL`) unset, construction raises a validation error naming the variable; numeric limits (e.g. `AGENT_MAX_TOOL_CALLS`) reject non-positive values. |
| M1-5 | `.env.example` is complete | `tests/unit/test_env_example.py` | Every `Settings` field has a matching key in `.env.example`, and every key in `.env.example` maps to a field (no stale keys). |
| M1-6 | No secrets, endpoints or model IDs committed (D4) | `tests/unit/test_secret_scan.py` + `python -m triage.security.secret_scan` | Scans tracked files (excluding `.env.example`, `corpus/`, the PDF) for API-key patterns (`sk-…`, `AIza…`, `gsk_…`, bearer tokens), hard-coded `https?://` provider endpoints in `src/`, and model-name patterns; zero matches. A planted test fixture string proves the scanner actually detects a positive. |
| M1-7 | `.env` is ignored | `git check-ignore .env` | Prints `.env`. |
| M1-8 | Structured logging | `tests/unit/test_logging.py` | A log call emits one JSON object containing `timestamp`, `level`, `event` and a bound `correlation_id`. |
| M1-9 | SLO declared before measurement | `git log --format='%H %ad' -- docs/slo.md` | `docs/slo.md` is in a commit that exists before any `loadtest/` results commit (re-checked in Phase 10). |

**Exit criterion:** M1-1 … M1-9 all pass on a second team member's machine, not only the author's.

## 5. Working agreements

- Tests and metrics are reported only from actual runs; failures are recorded, not hidden.
- Every external call (LLM, tool, HTTP) has a timeout from config.
- No code path connects to a database other than `app-db`; no tool executes SQL or shell.
- Any real failure during development is written to `ops/incident-log.md` on the day it happens.
