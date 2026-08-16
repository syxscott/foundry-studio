<div align="center">

# 🧬 foundry-studio

**Web UI for the RosettaCommons Foundry protein design toolkit**

RFD3 · RFD3NA · RF3 · ProteinMPNN — async job management, 3D structure viewer,
multilingual UI (中文 / English / 日本語 / Русский)

</div>

---

## What it is

foundry-studio is an independent, self-contained **web interface** for
[RosettaCommons Foundry](https://github.com/RosettaCommons/foundry) — the
all-in-one toolkit for protein design. It wraps the four released models with
a clean REST API, a persistent worker queue, and a modern single-page UI:

| Model | Purpose |
|-------|---------|
| **RFD3** | All-atom de novo protein design (diffusion) |
| **RFD3NA** | Protein / nucleic-acid co-design |
| **RF3** | Structure prediction (open AF-3 alternative) |
| **ProteinMPNN / LigandMPNN** | Inverse folding: sequence design for a backbone |

It is designed to be used on a local machine first: no external services are
required (SQLite instead of Redis, subprocess workers instead of Celery).

---

## Screenshots / features

- **Async job queue** — submit and return immediately; a persistent worker per
  model loads weights once and executes jobs in the background.
- **3D structure viewer** — built-in [NGL](https://nglviewer.org) viewer with
  cartoon / ball-and-stick / surface / spacefill / ribbon and coloring modes.
- **Multilingual UI** — 中文 / English / 日本語 / Русский (switchable, persisted).
- **Checkpoint management** — install / list / clean model weights from the UI.
- **Engine modes** — `auto` (real engine when available, else clearly-labelled
  *simulation* for UI/flow validation), `real` (force), `simulation` (force).
- **Advanced JSON mode** — every model form also accepts raw engine parameters.

---

## Quick start (local)

### 0. Requirements

- Python ≥ 3.12 (for the real Foundry engines: a CUDA GPU and
  `rc-foundry[all]` — see the [Foundry README](https://github.com/RosettaCommons/foundry))
- Node.js ≥ 20 (only to build the frontend)
- No Redis / database server needed.

### 1. Install & start the backend

```bash
git clone https://github.com/syxscott/foundry-studio.git
cd foundry-studio
python -m venv .venv
.venv/bin/pip install -e .            # Windows: .venv\Scripts\pip install -e .
.venv/bin/foundry-studio serve        # Windows: .venv\Scripts\foundry-studio serve
```

The API starts at <http://127.0.0.1:8765> (Swagger at `/docs`).

### 2. Install model weights (optional but needed for real runs)

```bash
.venv/bin/foundry-studio install-checkpoints rfd3 rf3 proteinmpnn
# or use the Environment page in the UI
```

### 3. Build & serve the frontend

```bash
cd frontend
npm install
npm run build
cd ..
# restart the server so it picks up frontend/dist, then open http://127.0.0.1:8765
```

During development, run `npm run dev` and open <http://localhost:5173> — Vite
proxies `/api` to the backend automatically.

> **Without Foundry installed, the UI still works** in *simulation mode*: jobs
> run through a clearly-labelled simulation engine that produces valid CIF /
> FASTA outputs so you can validate the whole flow (upload → queue → worker →
> results → 3D viewer). A persistent amber banner indicates simulation mode.

---

## Real engines (when Foundry is installed)

foundry-studio calls the upstream Foundry Python APIs directly (no CLI
wrapping, no output parsing):

- `rfd3.engine.RFD3InferenceEngine(...).run(inputs=..., n_batches=..., out_dir=...)`
- `rfd3na.engine.RFD3NAInferenceEngine(...)` — same conventions
- `rf3.inference_engines.rf3.RF3InferenceEngine(...).run(inputs=..., out_dir=...)`
- `mpnn.inference_engines.mpnn.MPNNInferenceEngine(...).run(input_dicts=..., atom_arrays=None)`

Worker processes exploit the upstream `initialize()/run()` separation: the
model is loaded once per worker and reused across jobs.

### Input conventions per model

| Model | Form fields | Files (uploaded) |
|-------|-------------|------------------|
| RFD3 | contigs, n_batches, hotspots, symmetry, diffusion_steps, sampler, seed | scaffold / motif CIF, or a design-spec JSON/YAML |
| RFD3NA | contigs, n_batches, diffusion_steps, sampler, seed | scaffold / motif CIF |
| RF3 | n_recycles, num_steps, dump_trajectories, seed | FASTA / CIF / PDB |
| MPNN | model_type, number_of_batches, temperature, batch_size, seed | backbone CIF / PDB |

Advanced mode accepts raw engine parameter names (matching the upstream
`DesignInputSpecification` / per-input defaults) for full control.

---

## Project layout

```
foundry-studio/
├── backend/foundry_studio/      # FastAPI app, engines, workers
│   ├── api/                     # REST routes + error handling
│   ├── engines/                 # model registry, real + simulation engines
│   ├── workers/                 # worker process + supervisor
│   ├── app.py / main.py / cli.py
│   └── i18n.py                  # backend message catalog (4 languages)
├── frontend/src/                # React SPA
│   ├── i18n/                    # zh / en / ja / ru translations
│   ├── pages/                   # Home, Jobs, JobDetail, Environment
│   ├── components/              # NGL viewer, status badges, banner
│   └── api/client.ts            # typed API client
├── tests/                       # backend pytest suite
├── Dockerfile / docker-compose.yml
└── pyproject.toml
```

---

## Docker (GPU)

```bash
docker compose up --build
# open http://localhost:8765
```

The image installs `rc-foundry[all]` and shares the host checkpoint directory
(`~/.foundry/checkpoints`) so weights can be reused with the host CLI.

---

## Configuration

All settings can be set via `FOUNDRY_STUDIO_*` environment variables or a
`.env` file (see `.env.example`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `FOUNDRY_STUDIO_HOST` | `127.0.0.1` | bind host |
| `FOUNDRY_STUDIO_PORT` | `8765` | bind port |
| `FOUNDRY_STUDIO_DATA_DIR` | `~/.foundry-studio` | jobs / logs / outputs |
| `FOUNDRY_STUDIO_ENGINE_MODE` | `auto` | `auto` / `real` / `simulation` |
| `FOUNDRY_STUDIO_ALLOW_SIMULATION_FALLBACK` | `true` | allow labelled simulation fallback |
| `FOUNDRY_STUDIO_WORKER_AUTOSTART` | `true` | spawn workers with the server |
| `FOUNDRY_STUDIO_FRONTEND_DIST` | unset | built frontend dir (for `serve`) |

---

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest backend/tests -q
```

The suite covers the job state machine, the API (create → upload → submit →
run → download), localized errors, the simulation engine, and the checkpoint
registry — all offline.

---

## License

MIT for foundry-studio itself. It wraps
[RosettaCommons Foundry](https://github.com/RosettaCommons/foundry)
(BSD-3-Clause); model checkpoints belong to their respective authors
(Institute for Protein Design, University of Washington, and others).
