"""Backend and Transport abstractions for remote job execution.

A ``Backend`` turns a :class:`JobSpec` into a remote task, reports its status,
and fetches outputs back.  A ``Transport`` is the lower-level pipe used by
real HPC backends (SSH/scp, a shared parallel filesystem, or a REST gateway).

The local backend ships fully working so the whole stack runs on a laptop with
no cluster.  The SLURM/PBS/LSF backends generate *correct* submission scripts
and issue *real* scheduler/transport commands; they simply require cluster
connection settings before ``submit`` will succeed.  That boundary is explicit
and is never faked.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# User-facing status vocabulary (a subset of the DB statuses).
STATUS_PENDING = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"


@dataclass
class RemoteHandle:
    """Backend-specific handle for a submitted job.

    For the local backend this holds the subprocess + pid.  For SLURM it holds
    the scheduler job id + remote workdir.  It is opaque to the orchestrator.
    """

    backend: str
    remote_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class HPCNotConfigured(Exception):
    """Raised when a real backend/transport lacks the connection settings."""


class Backend(ABC):
    """Executes JobSpecs on some compute target."""

    name: str = "abstract"

    @abstractmethod
    def submit(self, spec: Any, local_job_dir: Path) -> RemoteHandle:
        """Submit ``spec``; return a handle for later status/cancel/fetch."""

    @abstractmethod
    def status(self, handle: RemoteHandle) -> tuple[str, int | None]:
        """Return (status, progress_0_100).  progress may be None."""

    @abstractmethod
    def cancel(self, handle: RemoteHandle) -> None:
        """Request cancellation of the remote task."""

    @abstractmethod
    def fetch_outputs(self, handle: RemoteHandle, dest_dir: Path) -> list[Path]:
        """Copy outputs back into ``dest_dir``; return the produced paths."""

    @abstractmethod
    def logs(self, handle: RemoteHandle) -> str:
        """Return the remote task's stdout/stderr tail (best effort)."""


class Transport(ABC):
    """Low-level connection to a remote cluster (SSH / shared FS / REST)."""

    name: str = "abstract"

    @abstractmethod
    def run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        """Run a remote command; return (returncode, stdout, stderr)."""

    @abstractmethod
    def copy_to(self, local: Path, remote: str) -> None:
        """Copy a local file to ``remote`` (absolute or relative to workdir)."""

    @abstractmethod
    def copy_back(self, remote: str, local_dir: Path, patterns: list[str]) -> list[Path]:
        """Copy files matching ``patterns`` from remote workdir into ``local_dir``."""

    @abstractmethod
    def read_text(self, remote: str) -> str:
        """Read a remote file's text content (best effort)."""


def sanitize_cmd(text: str) -> str:
    """Strip obviously dangerous shell metacharacters from user-influenced
    script fragments.  Kept conservative: we only block command separators and
    redirections that could escape the generated script's intent."""
    banned = [";", "&", "|", "$", "`", ">", "<", "\n", "\r"]
    out = []
    for ch in text:
        if ch in banned:
            out.append("_")
        else:
            out.append(ch)
    return "".join(out)
