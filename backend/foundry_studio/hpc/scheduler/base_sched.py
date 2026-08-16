"""Shared logic for the SLURM/PBS/LSF scheduler backends.

Every scheduler backend does the same four things with the same transport:
build a submission script from the JobSpec, ship the script + inputs, submit,
and later poll/cancel/fetch.  Only the *directive syntax* and the
submit/query/cancel command lines differ per scheduler, so those are the only
methods subclasses override.  The launch command reuses the cluster-side
:mod:`foundry_studio.hpc.remote_invoke` entrypoint, so the exact same engine
code path runs on the supercomputer as on a laptop.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from foundry_studio.hpc.base import Backend, HPCNotConfigured, RemoteHandle, STATUS_CANCELED, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED
from foundry_studio.hpc.job_spec import JobSpec


class SchedulerBackend(Backend):
    """Base class for SLURM/PBS/LSF backends."""

    scheduler: str = "abstract"
    # Overridden by subclasses.
    submit_cmd: str = ""
    status_cmd: str = ""  # receives {id}
    cancel_cmd: str = ""  # receives {id}

    def __init__(self, *, settings: Any, db: Any, transport: Any):
        self.settings = settings
        self.db = db
        self.transport = transport
        if not settings.hpc_remote_workdir:
            raise HPCNotConfigured(
                f"{self.scheduler} backend requires FOUNDRY_STUDIO_HPC_REMOTE_WORKDIR"
            )

    # ------------------------------------------------------------------ #
    # Script generation
    # ------------------------------------------------------------------ #
    def _directives(self, spec: JobSpec) -> list[str]:
        r = spec.resources
        if self.scheduler == "slurm":
            out = [
                f"#SBATCH --job-name={self._safe(spec.name or spec.model)}",
                f"#SBATCH --output={self._safe(spec.job_id)}.out",
                f"#SBATCH --error={self._safe(spec.job_id)}.err",
            ]
            if r.get("time"):
                out.append(f"#SBATCH --time={self._safe(r['time'])}")
            if r.get("partition"):
                out.append(f"#SBATCH --partition={self._safe(r['partition'])}")
            if r.get("account"):
                out.append(f"#SBATCH --account={self._safe(r['account'])}")
            if r.get("gres"):
                out.append(f"#SBATCH --gres={self._safe(r['gres'])}")
            if r.get("cpus"):
                out.append(f"#SBATCH --cpus-per-task={int(r['cpus'])}")
            if r.get("mem"):
                out.append(f"#SBATCH --mem={self._safe(r['mem'])}")
            if r.get("tasks"):
                out.append(f"#SBATCH --ntasks={int(r['tasks'])}")
            return out
        if self.scheduler == "pbs":
            out = [
                f"#PBS -N {self._safe(spec.name or spec.model)}",
                f"#PBS -o {self._safe(spec.job_id)}.out",
                f"#PBS -e {self._safe(spec.job_id)}.err",
            ]
            if r.get("time"):
                out.append(f"#PBS -l walltime={self._safe(r['time'])}")
            if r.get("partition"):
                out.append(f"#PBS -q {self._safe(r['partition'])}")
            if r.get("account"):
                out.append(f"#PBS -A {self._safe(r['account'])}")
            sel = []
            if r.get("cpus"):
                sel.append(f"ncpus={int(r['cpus'])}")
            if r.get("mem"):
                sel.append(f"mem={self._safe(r['mem'])}")
            if r.get("gres"):
                sel.append(f"gres={self._safe(r['gres'])}")
            if sel:
                out.append("#PBS -l " + ",".join(sel))
            return out
        if self.scheduler == "lsf":
            out = [
                f"#BSUB -J {self._safe(spec.name or spec.model)}",
                f"#BSUB -o {self._safe(spec.job_id)}.out",
                f"#BSUB -e {self._safe(spec.job_id)}.err",
            ]
            if r.get("time"):
                out.append(f"#BSUB -W {self._hhmm(r['time'])}")
            if r.get("partition"):
                out.append(f"#BSUB -q {self._safe(r['partition'])}")
            if r.get("account"):
                out.append(f"#BSUB -P {self._safe(r['account'])}")
            if r.get("cpus"):
                out.append(f"#BSUB -n {int(r['cpus'])}")
            if r.get("mem"):
                out.append(f"#BSUB -M {self._safe(r['mem'])}")
            if r.get("gres"):
                out.append(f"#BSUB -gpu '{self._safe(r['gres'])}'")
            return out
        return []

    def _launch(self, spec: JobSpec) -> list[str]:
        inv = spec.invocation
        mode = inv.get("engine_mode") or "auto"
        base = (
            f"python -m foundry_studio.hpc.remote_invoke "
            f"--model {self._safe(spec.model)} "
            f"--params params.json --inputs . --out . "
            f"--engine-mode {self._safe(mode)}"
        )
        lines: list[str] = []
        kind = inv.get("kind", "container")
        if kind == "container":
            image = inv.get("image") or self.settings.hpc_container_image or "foundry.sif"
            lines.append(f"singularity exec --nv {self._safe(image)} {base}")
        elif kind == "module":
            mod = inv.get("module") or self.settings.hpc_module_load or "foundry"
            lines.append(f"module load {self._safe(mod)}")
            lines.append(base)
        elif kind == "conda":
            env = inv.get("conda_env") or self.settings.hpc_conda_env or "foundry"
            lines.append(f"source \"$(conda info --base)/etc/profile.d/conda.sh\"")
            lines.append(f"conda activate {self._safe(env)}")
            lines.append(base)
        else:
            # script: user supplies a full command template.
            lines.append(inv.get("command", base))
        return lines

    def _build_script(self, spec: JobSpec, remote_wd: str) -> str:
        shebang = "#!/bin/bash" if self.scheduler != "lsf" else "#!/bin/bash"
        header = [
            shebang,
            f"# Generated by foundry-studio for model {spec.model} (job {spec.job_id})",
            f"cd {self._safe(remote_wd)}",
            "set -euo pipefail",
        ]
        body = self._directives(spec) + [""] + self._launch(spec)
        return "\n".join(header + body) + "\n"

    # ------------------------------------------------------------------ #
    # Backend interface
    # ------------------------------------------------------------------ #
    def submit(self, spec: JobSpec, local_job_dir: Path) -> RemoteHandle:
        local_job_dir = Path(local_job_dir)
        local_job_dir.mkdir(parents=True, exist_ok=True)
        remote_wd = f"{self.settings.hpc_remote_workdir.rstrip('/')}/{spec.job_id}"
        script = self._build_script(spec, remote_wd)
        script_path = local_job_dir / "run.sh"
        script_path.write_text(script, encoding="utf-8")
        # Persist spec + params next to the script (also shipped to the cluster).
        (local_job_dir / "params.json").write_text(
            __import__("json").dumps(spec.params, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (local_job_dir / "job_spec.json").write_text(
            __import__("json").dumps(spec.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self.transport.copy_to(script_path, f"{remote_wd}/run.sh")
        self.transport.copy_to(local_job_dir / "params.json", f"{remote_wd}/params.json")
        for f in spec.input_files:
            local_file = local_job_dir / f.get("filename", "")
            if local_file.is_file():
                self.transport.copy_to(local_file, f"{remote_wd}/{f.get('filename')}")

        rc, out, err = self.transport.run(f"{self.submit_cmd} {remote_wd}/run.sh")
        if rc != 0:
            raise RuntimeError(f"{self.scheduler} submit failed: {err or out}")
        remote_id = self._parse_id(out)
        return RemoteHandle(
            backend=self.scheduler,
            remote_id=remote_id,
            meta={"remote_wd": remote_wd, "spec": spec},
        )

    def status(self, handle: RemoteHandle) -> tuple[str, int | None]:
        rc, out, err = self.transport.run(self.status_cmd.format(id=handle.remote_id))
        return self._parse_status(out, err), None

    def cancel(self, handle: RemoteHandle) -> None:
        self.transport.run(self.cancel_cmd.format(id=handle.remote_id))

    def fetch_outputs(self, handle: RemoteHandle, dest_dir: Path) -> list[Path]:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        spec = handle.meta.get("spec")
        patterns = spec.output_patterns if spec else ["*"]
        return self.transport.copy_back(handle.meta.get("remote_wd", ""), dest_dir, patterns)

    def logs(self, handle: RemoteHandle) -> str:
        return self.transport.read_text(f"{handle.meta.get('remote_wd', '')}/{handle.remote_id}.out")

    # ------------------------------------------------------------------ #
    # Helpers (overridden where the scheduler differs)
    # ------------------------------------------------------------------ #
    def _parse_id(self, stdout: str) -> str:
        m = re.search(r"(\d+)", stdout)
        return m.group(1) if m else stdout.strip()

    def _parse_status(self, stdout: str, stderr: str = "") -> str:
        text = (stdout or stderr or "").upper()
        if "COMPLETED" in text or "C " in text or "DONE" in text:
            return STATUS_SUCCEEDED
        if "FAILED" in text or "EXIT" in text or "E " in text or "F " in text:
            return STATUS_FAILED
        if "CANCEL" in text or "CANCELLED" in text:
            return STATUS_CANCELED
        if "RUNNING" in text or "R " in text or "RUN" in text:
            return STATUS_RUNNING
        if "PEND" in text or "PD" in text or "QUEUED" in text or "Q " in text or "P " in text:
            return STATUS_PENDING
        return STATUS_PENDING

    @staticmethod
    def _safe(value: Any) -> str:
        return re.sub(r"[^A-Za-z0-9._:/@-]", "_", str(value))

    @staticmethod
    def _hhmm(time_str: str) -> str:
        # Accept HH:MM:SS or MM:SS or plain minutes; LSF -W wants [HH:]MM.
        parts = str(time_str).split(":")
        if len(parts) == 3:
            return f"{parts[0]}:{parts[1]}"
        if len(parts) == 2:
            return f"00:{parts[0]}"
        return "00:30"
