# Architecture

This document describes the internal architecture of foundry-studio at a
level useful for contributors.

## Overview

```
┌───────────────────────────── Browser ─────────────────────────────┐
│  React SPA (Vite + TS + Tailwind + i18next + NGL)                  │
│  Home · Jobs · JobDetail · Environment                             │
└───────────────────────────────┬────────────────────────────────────┘
                                │ HTTP/JSON + SSE (logs)
┌───────────────────────────────▼────────────────────────────────────┐
│  FastAPI (backend/foundry_studio)                                  │
│  api/        REST routes (jobs, models, checkpoints, files, i18n)  │
│  db.py       SQLite (WAL) — jobs + worker heartbeats               │
│  engines/    model registry + real/simulation engines              │
│  workers/    WorkerManager (spawn/monitor)                         │
└───────────────┬────────────────────────────────┬───────────────────┘
                │ subprocess                     │ heartbeats / status
┌───────────────▼────────────────┐   ┌───────────▼───────────────────┐
│  worker processes              │   │ data dir                      │
│  python -m foundry_studio.     │   │ jobs/<id>/  inputs+outputs     │
│     workers.worker --model X   │   │ logs/<id>.log                 │
│  (one per model, model loaded  │   │ studio.db                    │
│   once, reuse via initialize/  │   └───────────────────────────────┘
│   run separation)              │
└────────────────────────────────┘
```

## Data model

**jobs** (SQLite table): the single source of truth for the queue.

| Field | Type | Meaning |
|-------|------|---------|
| id | str | uuid hex |
| model | str | rfd3 / rfd3na / rf3 / mpnn |
| status | str | draft → queued → running → succeeded / failed / canceled |
| params_json | str | engine parameters (validated by frontend schema) |
| input_files_json | str | uploaded file descriptors [{role, filename, name}] |
| engine_mode | str | auto / real / simulation |
| progress | int? | 0–100 |
| error_code / error_detail | str? | stable message key + detail |
| cancel_requested | int | cooperative cancellation flag |
| log_path / outputs_dir | str? | file locations |

**workers** (SQLite table): heartbeat + pid per model so the manager can
detect dead workers and the health endpoint can report them.

## Engine resolution (engines/registry.py)

`resolve_engine(model, engine_mode, allow_simulation, ...)`:

- `simulation`  → labelled `SimulationEngine`
- `real`        → real engine or raise (job fails)
- `auto`        → real engine if `is_available()` else SimulationEngine
                  (only when `allow_simulation_fallback`)

`is_available()` per real engine checks (a) the model package is importable
(`rfd3`, `rf3`, `mpnn`, `rfd3na`) and (b) the checkpoint exists in the
search path.  The heavy imports are deferred into `_initialize()`, so the API
server and simulation mode never pay the torch/atomworks import cost.

The simulation engine is **never** presented as a real prediction: jobs it
runs are tagged `engine_mode="simulation"` and the UI shows a persistent
amber banner.

## Worker lifecycle

1. `WorkerManager.start()` (API startup): requeue stale `running` jobs, then
   spawn one worker per model when `worker_autostart=true`.
2. Each worker process (`workers/worker.py`) resolves its engine once,
   calls `initialize()`, then loops: `claim_next_job(model)` → `run()` →
   update DB to terminal state → heartbeat every poll interval.
3. `_monitor_loop` (15 s tick) respawns dead workers only when queued jobs
   remain; `workers` table reflects liveness for the UI.

Cooperative cancellation: `POST /api/jobs/{id}/cancel` sets
`cancel_requested`; queued jobs are canceled immediately, running jobs are
aborted by the engine between work units (worker checks the flag).

## API surface (prefix /api)

| Route | Purpose |
|-------|---------|
| GET /health | version, engine mode, GPU/Foundry availability, workers |
| GET /models | catalog incl. param schemas + checkpoint state |
| GET /checkpoints · POST /checkpoints/install · POST /checkpoints/clean | weight management |
| GET /i18n | backend message catalog for all 4 locales |
| POST /jobs | create draft job |
| GET /jobs | list (optional status filter) |
| GET /jobs/{id} | job detail incl. output file listing |
| POST /jobs/{id}/submit | draft → queued |
| POST /jobs/{id}/cancel | cooperative cancel |
| DELETE /jobs/{id} | remove job + artifacts (terminal states only) |
| POST /jobs/{id}/files | multipart upload |
| GET /jobs/{id}/files/{name} | download an output/input file |
| GET /jobs/{id}/logs · /logs/stream | poll / SSE log tail |

Errors: every error carries `message_key` + `params` + a localized `message`
(zh/en/ja/ru); the frontend renders from its own catalog and falls back to
the backend `message`.

## Localization

- Frontend: `frontend/src/i18n/{zh,en,ja,ru}.ts` — full UI copy, keyed off
  the `zh` catalog type (`TranslationKey`). Language persisted in
  `localStorage`, detected from `navigator.language` otherwise.
- Backend: `backend/foundry_studio/i18n.py` — server-side message catalog
  used for error payloads and log lines (same 4 locales).

Adding a language: add a `frontend/src/i18n/<code>.ts` typed as
`TranslationKey`, register it in `i18n/index.ts`, and add the matching
backend catalog entries in `i18n.py`.
