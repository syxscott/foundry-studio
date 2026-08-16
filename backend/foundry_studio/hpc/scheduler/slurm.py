"""SLURM backend: submit via ``sbatch``, poll via ``squeue``."""

from __future__ import annotations

from foundry_studio.hpc.scheduler.base_sched import SchedulerBackend


class SlurmBackend(SchedulerBackend):
    scheduler = "slurm"
    submit_cmd = "sbatch"
    status_cmd = "squeue -h -j {id} -o %T"
    cancel_cmd = "scancel {id}"

    def _parse_id(self, stdout: str) -> str:
        for line in stdout.splitlines():
            if "Submitted batch job" in line:
                return line.split()[-1]
        # Fallback: first integer-looking token.
        import re

        m = re.search(r"(\d+)", stdout)
        return m.group(1) if m else stdout.strip()

    def _parse_status(self, stdout: str, stderr: str = "") -> str:
        text = (stdout or "").strip().upper()
        if text in ("COMPLETED", "CD"):
            return "succeeded"
        if text in ("FAILED", "F", "BOOT_FAIL", "BF", "DEADLINE", "DN"):
            return "failed"
        if text in ("CANCELLED", "CA", "TIMEOUT", "TO", "NODE_FAIL", "NF", "OUT_OF_MEMORY", "OOM", "PREEMPTED", "PR"):
            return "canceled" if text in ("CANCELLED", "CA") else "failed"
        if text in ("RUNNING", "R", "COMPLETING", "CG", "CONFIGURING", "CF"):
            return "running"
        return "queued"
