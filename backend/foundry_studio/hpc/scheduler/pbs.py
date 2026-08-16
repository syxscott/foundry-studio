"""PBS/Torque backend: submit via ``qsub``, poll via ``qstat``."""

from __future__ import annotations

from foundry_studio.hpc.scheduler.base_sched import SchedulerBackend


class PbsBackend(SchedulerBackend):
    scheduler = "pbs"
    submit_cmd = "qsub"
    status_cmd = "qstat -f {id} | grep job_state"
    cancel_cmd = "qdel {id}"

    def _parse_id(self, stdout: str) -> str:
        # qsub prints the numeric job id (optionally with server suffix).
        for line in stdout.splitlines():
            line = line.strip()
            if line:
                return line.split(".")[0]
        return stdout.strip()

    def _parse_status(self, stdout: str, stderr: str = "") -> str:
        text = (stdout or "").upper()
        if "JOB_STATE = C" in text or "= C" in text:
            return "succeeded"
        if "= E" in text:
            return "running"
        if "= F" in text:
            return "failed"
        if "= H" in text:
            return "canceled"
        if "= Q" in text:
            return "queued"
        if "= R" in text or "= T" in text:
            return "running"
        return "queued"
