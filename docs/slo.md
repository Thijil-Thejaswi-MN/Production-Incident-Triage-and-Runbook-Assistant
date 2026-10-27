# Service-Level Objective (requirement D6)

**Declared:** 2026-10-27, in Milestone 1, before any load-test code, load-test run or latency measurement exists in this repository. The git history of this file is the evidence of declaration order; the target must not be edited after the first Locust run except by adding a dated, separately justified revision below the original.

## Objective

> **p95 of a complete run ≤ 60 seconds**, measured from the moment the client's `POST /v1/incidents` is sent to the moment a poll of `GET /v1/runs/{run_id}` first returns a terminal state (`COMPLETED`, `ESCALATED`, `DEGRADED` or `FAILED`), **at up to 10 concurrent in-flight incidents**, with the LLM replaced by the stub service responding in **1.5 s ± 0.5 s per call**.

Supporting objectives (same conditions):
- Submission call (`POST` returning `202`) p95 ≤ 300 ms — the API must stay responsive while agents are busy.
- 0 % of runs end without a terminal state (a stuck run counts as an SLO violation, not as missing data).

## Justification against the assignment context (§1)

- The user is an on-call engineer paged at 3 a.m. who must quickly classify the problem, find the runbook, decide severity and decide whether to escalate. The first minutes after a page are spent acknowledging it and opening dashboards; a recommendation is useful only if it arrives inside that window.
- Paging acknowledgement windows are commonly a few minutes. A 60 s p95 leaves most of such a window for the human to read the evidence and act, while being realistic for a multi-agent run.
- Budget arithmetic: a run is expected to need roughly 6–10 sequential model calls (investigator hypotheses, tool-selection turns, draft; verifier judgement) plus retrieval. At 1.5 s per stubbed call that is ~9–15 s of model time, leaving headroom for queueing, retrieval, a single verification revision and contention under concurrency. A tighter target (e.g. 15 s) would leave no room for the revision loop that A3 requires; a looser one (e.g. 5 min) would not help someone under time pressure.
- Concurrency of 10 represents an alert storm (several related alerts firing at once) for one team, which is the realistic peak for this tool.
- The stub isolates our system's latency from provider rate limits (PDF D6); real-provider latency is reported separately and is not part of this SLO.

## Measurement method (to be implemented in Phase 10)

- Locust user: submit a payload sampled from the evaluation set, poll every 0.5 s until terminal, record the full duration as a custom request type `run_complete`.
- Load shape: step load 1 → 2 → 5 → 10 → 15 → 20 → 30 concurrent users, each step held long enough for ≥ 100 completed runs.
- Report RPS (completed runs/s), p50 and p95 of `run_complete` per step; state whether the target is met at 10; identify the lowest concurrency at which p95 > 60 s and the component responsible, using queue depth, per-step latency and container CPU metrics.
- Repeat at `docker compose up --scale agent-worker=1` and `=3` (A7), and with caches on/off (D7).

## Revisions

None.
