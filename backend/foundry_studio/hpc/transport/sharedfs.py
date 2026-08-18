"""Shared-filesystem transport: the cluster's workdir is mounted locally.

When the HPC scratch/parallel filesystem (Lustre, GPFS, ...) is mounted on the
machine running foundry-studio, file transfer is a no-op and scheduler commands
run in that directory.  Requires ``hpc_remote_workdir`` to point at the mount;
otherwise submit fails with :class:`HPCNotConfigured`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from foundry_studio.hpc.base import HPCNotConfigured, Transport


class SharedFsTransport(Transport):
    name = "sharedfs"

    def __init__(self, *, remote_workdir: str):
        if not remote_workdir:
            raise HPCNotConfigured(
                "sharedfs transport requires FOUNDRY_STUDIO_HPC_REMOTE_WORKDIR"
            )
        self.workdir = Path(remote_workdir)

    def run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        # Split cmd into list for shell=False; use shlex for safe splitting
        import shlex
        cmd_list = shlex.split(cmd) if isinstance(cmd, str) else cmd
        workdir = str(self.workdir if cwd is None else Path(cwd))
        proc = subprocess.run(
            cmd_list,
            shell=False,
            cwd=workdir,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def copy_to(self, local: Path, remote: str) -> None:
        # Validate remote path to prevent traversal
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
        dest = self.workdir / remote
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(local).read_bytes())

    def copy_back(self, remote: str, local_dir: Path, patterns: list[str]) -> list[Path]:
        # Validate remote path to prevent traversal
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        fetched: list[Path] = []
        base = self.workdir / remote
        for pat in patterns:
            if ".." in pat or pat.startswith("/"):
                raise ValueError(f"Invalid pattern: {pat!r}")
            for p in sorted(base.glob(pat)):
                if p.is_file():
                    target = local_dir / p.name
                    target.write_bytes(p.read_bytes())
                    fetched.append(target)
        return fetched

    def read_text(self, remote: str) -> str:
        # Validate remote path to prevent traversal
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
        p = self.workdir / remote
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
