# Production Deployment Guide

This guide covers deploying **foundry-studio** for real protein-design workloads on
two target platforms:

| Platform | Compute | Scheduler | How it works |
|---|---|---|---|
| Standalone GPU | Local workstation / server | None (local subprocess) | `LocalBackend` runs inference directly |
| HPC cluster | Slurm / PBS / LSF farm | Scheduler (Slurm, PBS, LSF) | `SchedulerBackend` ships jobs to cluster via SSH |

Run `foundry-studio doctor` after every major step to verify the environment is ready.

---

## Step 0 — Verify the installation

```bash
foundry-studio doctor
```

Expected on a bare machine:

```
[FAIL] GPU / CUDA        — PyTorch not installed (or no GPU)
[FAIL] Foundry packages   — rc-foundry not installed
[FAIL] Checkpoints        — Essential checkpoints missing
[PASS] Simulation engine  — Always available (UI testing)
[WARN] Container runtime  — Singularity/Apptainer not found
[PASS] Data dir           — writable
[WARN] Config             — No .env file
[FAIL] Network            — Checkpoint hosts unreachable
[PASS] HPC SSH            — local backend; SSH check skipped
```

Each FAIL item in this document corresponds to a `foundry-studio doctor` check.
When all critical checks pass, the summary line reads:

```
Summary: N passed, N warning(s), 0 failure(s)   ✓ All critical checks pass!
```

---

## Option A — Standalone GPU (Recommended for Teams / Small Labs)

### A1. Install Python 3.12+

```bash
# https://www.python.org/downloads/
python --version   # must be >= 3.12
```

### A2. Install PyTorch with CUDA

```bash
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124
```

Verify:

```bash
python -c "import torch; print(torch.cuda.is_available())"   # True
```

### A3. Install rc-foundry

```bash
pip install "rc-foundry[all]>=0.1"
```

This pulls in `rfd3`, `rf3`, `proteinmpnn`, and `rfd3na` inference packages.
Verify with:

```bash
python -c "import rfd3, rf3, proteinmpnn; print('All packages OK')"
```

> **Note:** `rc-foundry[all]` is a meta-package. Individual sub-packages can be
> installed separately to reduce dependencies:
> `pip install rfd3 rf3 proteinmpnn`

### A4. Download model checkpoints

Check which are missing:

```bash
foundry-studio doctor --json | Select-String "Checkpoint"
```

Download the ones you need:

```bash
foundry-studio install-checkpoints rfd3 rf3 proteinmpnn
# Each checkpoint is 0.5–3 GB; downloads may take 10–30 min per file
```

Checkpoints are stored in `~/.foundry/checkpoints/` by default.
Override with:

```bash
# In .env
FOUNDRY_STUDIO_CHECKPOINT_DIRS=/data/checkpoints:/scratch/foundry/checkpoints
```

### A5. Configure .env

```bash
cp .env.example .env
# Edit .env with your settings
```

Key variables for standalone GPU:

```env
# .env — standalone GPU deployment
FOUNDRY_STUDIO_DATA_DIR=/data/foundry-studio
FOUNDRY_STUDIO_HOST=0.0.0.0          # allow LAN access (use reverse proxy + TLS)
FOUNDRY_STUDIO_PORT=8765
FOUNDRY_STUDIO_ENGINE_MODE=auto       # use real engine when available, simulate otherwise
FOUNDRY_STUDIO_ALLOW_SIMULATION_FALLBACK=true
FOUNDRY_STUDIO_HPC_BACKEND=local      # no cluster; run locally
# CORS — set to your frontend origin in production
FOUNDRY_STUDIO_CORS_ALLOWED_ORIGINS=["https://studio.example.com"]
```

### A6. Verify the full stack

```bash
foundry-studio doctor
```

Expected:

```
[PASS] Python
[PASS] foundry-studio
[PASS] GPU / CUDA
[PASS] Foundry packages
[PASS] Checkpoints
[PASS] Simulation engine
[WARN] Container runtime    # not needed for local backend
[PASS] Data dir
[PASS] Config
[PASS] Network
[PASS] HPC SSH              # local backend; SSH check skipped
```

### A7. Start the server

```bash
foundry-studio serve
# Server starts at http://0.0.0.0:8765
```

For production, run behind a reverse proxy (nginx, Caddy) with TLS and, optionally,
HTTP Basic Auth or SSO.

---

## Option B — HPC Cluster (Slurm / PBS / LSF)

### B1. Prepare your workstation

Follow **A1–A3** (Python + PyTorch + rc-foundry) on your local machine.
You only need `foundry-studio` installed locally; the actual inference runs on
the cluster.

### B2. Build a Singularity / Apptainer container

The cluster GPU nodes need the full inference stack. Build a container image:

```bash
# On a machine with Singularity/Apptainer installed (often the HPC login node)
singularity pull docker://rosettacommons/foundry:latest   # or your custom image
```

Alternatively, use a module or conda environment on the cluster (see B4).

Store the `.sif` file in a shared filesystem path accessible from all compute nodes,
e.g. `/share/foundry/foundry.sif`.

### B3. Configure SSH passwordless access

```bash
# On your workstation
ssh-keygen -t ed25519 -f ~/.ssh/foundry_hpc -N ""
ssh-copy-id -i ~/.ssh/foundry_hpc.pub user@hpc-cluster.example.edu
# Verify
ssh -i ~/.ssh/foundry_hpc -o BatchMode=yes user@hpc-cluster.example.edu 'echo OK'
```

Verify with `foundry-studio doctor`:

```bash
# In .env, set HPC_REMOTE_HOST before running
FOUNDRY_STUDIO_HPC_REMOTE_HOST=hpc-cluster.example.edu
FOUNDRY_STUDIO_HPC_REMOTE_USER=your_username
FOUNDRY_STUDIO_HPC_REMOTE_KEY=~/.ssh/foundry_hpc
FOUNDRY_STUDIO_HPC_BACKEND=slurm
foundry-studio doctor
```

Expected output when SSH is configured:

```
[PASS] HPC SSH   SSH to hpc-cluster.example.edu OK (passwordless auth working)
```

### B4. Configure .env for HPC

```env
# .env — HPC Slurm cluster deployment
FOUNDRY_STUDIO_DATA_DIR=/data/foundry-studio
FOUNDRY_STUDIO_HOST=0.0.0.0
FOUNDRY_STUDIO_PORT=8765
FOUNDRY_STUDIO_ENGINE_MODE=auto
FOUNDRY_STUDIO_ALLOW_SIMULATION_FALLBACK=false   # force real engine; fail if missing

# HPC backend
FOUNDRY_STUDIO_HPC_BACKEND=slrum      # slurm | pbs | lsf
FOUNDRY_STUDIO_HPC_INVOCATION_KIND=container
FOUNDRY_STUDIO_HPC_CONTAINER_IMAGE=/share/foundry/foundry.sif

# Scheduler resource defaults (overridable per job in the UI)
FOUNDRY_STUDIO_HPC_PARTITION=gpu         # your partition name
FOUNDRY_STUDIO_HPC_ACCOUNT=my_project     # Slurm account
FOUNDRY_STUDIO_HPC_TIME=24:00:00
FOUNDRY_STUDIO_HPC_GRES=gpu:1
FOUNDRY_STUDIO_HPC_CPUS=8
FOUNDRY_STUDIO_HPC_MEM=32G

# Transport
FOUNDRY_STUDIO_HPC_TRANSPORT=ssh
FOUNDRY_STUDIO_HPC_REMOTE_HOST=hpc-cluster.example.edu
FOUNDRY_STUDIO_HPC_REMOTE_USER=your_username
FOUNDRY_STUDIO_HPC_REMOTE_KEY=~/.ssh/foundry_hpc
FOUNDRY_STUDIO_HPC_REMOTE_WORKDIR=/scratch/your_username/foundry
```

Alternative invocation modes (instead of container):

```env
# Module-based (if your HPC has a foundry module)
FOUNDRY_STUDIO_HPC_INVOCATION_KIND=module
FOUNDRY_STUDIO_HPC_MODULE_LOAD=foundry

# Conda environment
FOUNDRY_STUDIO_HPC_INVOCATION_KIND=conda
FOUNDRY_STUDIO_HPC_CONDA_ENV=foundry
```

### B5. Verify HPC connectivity

```bash
foundry-studio doctor
```

Expected on a working HPC setup:

```
[PASS] Python
[PASS] foundry-studio
[PASS] GPU / CUDA          # check cluster GPUs via SSH in production
[PASS] Foundry packages
[PASS] Checkpoints
[PASS] Simulation engine
[PASS] Container runtime   # Singularity/Apptainer found
[PASS] Data dir
[PASS] Config
[PASS] Network
[PASS] HPC SSH             SSH to hpc-cluster.example.edu OK (passwordless auth working)
```

### B6. Start the server

```bash
foundry-studio serve
```

Jobs are submitted to the cluster; the UI polls status and fetches outputs back
to the local `data_dir`.

---

## Simulation Engine — What It Does and Doesn't Do

The **Simulation Engine** (`engine_mode=simulation`) is always available — no GPU
or model weights needed. It produces:

- **Valid CIF files** with backbone atoms (N, CA, C, O) and side-chain Cβ
- **Realistic secondary structure**: alpha-helical regions (phi=−57°, psi=−47°,
  3.6 residues/turn), beta-strand regions, and random-coil loops
- **Deterministic output**: same job parameters always produce the same
  placeholder structure (seeded by job ID)

It does **NOT** produce real protein predictions. Every output is labelled
`"simulated": true` in the metadata and the UI shows a persistent warning
banner.

**When to use it:**

- UI / workflow testing without a GPU
- Training team members on the interface
- CI/CD testing

**When NOT to use it:**

- Actual protein design research — install rc-foundry + checkpoints + GPU

---

## Troubleshooting

### `foundry-studio doctor` exits with code 1

At least one check failed. Run with `--json` for machine-readable output:

```bash
foundry-studio doctor --json | python -m json.tool
```

### GPU OOM (Out of Memory) during inference

Reduce batch size in job parameters, or use a GPU with more VRAM.
The doctor warns for GPUs < 6 GB.

### HPC job hangs in "running" forever

Check:
1. SSH passwordless auth: `ssh user@host 'echo OK'` should succeed without a password
2. Container image path is accessible from compute nodes (shared filesystem, not local)
3. Checkpoint paths are identical on the cluster or bundled in the container

```bash
# Verify HPC SSH
foundry-studio doctor --json | Select-String "HPC SSH"
```

### rc-foundry import fails

```bash
# Verify the package is installed
pip show rc-foundry
# Reinstall if needed
pip install --force-reinstall "rc-foundry[all]>=0.1"
```

### Simulation engine output looks wrong

The simulation engine generates a deterministic helix-fold structure. If the
output looks scrambled, check the `.json` metadata for `"simulated": true`
— that confirms it is a placeholder, not a real prediction.

---

## Security Notes

- **CORS**: `FOUNDRY_STUDIO_CORS_ALLOWED_ORIGINS` defaults to loopback only.
  Set it explicitly before exposing the server on a LAN or public network.
- **API key**: `FOUNDRY_STUDIO_AGENT_LLM_API_KEY_ENV` stores only the env-var
  name, never the key itself. Set `OPENAI_API_KEY` (or your chosen env var)
  before starting the server.
- **Remote access**: `FOUNDRY_STUDIO_ALLOW_REMOTE_ACCESS=false` (default) binds
  to `127.0.0.1`. Set to `true` only behind a TLS-terminating reverse proxy.
- **HPC SSH key**: store the key outside the repo; reference it by path in
  `FOUNDRY_STUDIO_HPC_REMOTE_KEY`.
