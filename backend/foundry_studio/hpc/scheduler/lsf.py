"""LSF backend: submit via ``bsub``, poll via ``bjobs``."""

from __future__ import annotations

from foundry_studio.hpc.scheduler.base_sched import SchedulerBackend


class LsfBackend(SchedulerBackend):
    scheduler = "lsf"
    submit_cmd = "bsub"
    status_cmd = "bjobs -o stat {id} 2>/dev/null | tail -1"
    cancel_cmd = "bkill {id}"

    def _parse_id(self, stdout: str) -> str:
        # bsub prints: "Job <12345> is submitted to queue <x>."
        import re

        m = re.search(r"Job\s*<\s*(\d+)\s*>", stdout)
        return m.group(1) if m else stdout.strip()

    def _parse_status(self, stdout: str, stderr: str = "") -> str:
        text = (stdout or "").strip().upper()
        if text in ("DONE", "D"):
            return "succeeded"
        if text in ("EXIT", "X"):
            return "failed"
        if text in ("PEND", "P", "WAIT", "W", "SUSP", "PSUSP", "USUSP"):
            return "queued"
        if text in ("RUN", "R", "SSUSP"):
            return "running"
        return "queued"
