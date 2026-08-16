"""SSH transport: reach the cluster via ``ssh``/``scp``.

Real, but requires ``hpc_remote_host`` (+ optionally user/key) to be configured;
without it ``submit`` fails loudly with :class:`HPCNotConfigured` rather than
pretending to run.  Commands and file transfers are executed through the system
``ssh``/``scp`` binaries, so no extra Python dependency is needed.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from foundry_studio.hpc.base import HPCNotConfigured, Transport


class SshTransport(Transport):
    name = "ssh"

    def __init__(
        self,
        *,
        host: str,
        user: str = "",
        key_path: str = "",
        remote_workdir: str = "",
        port: int = 22,
    ):
        if not host:
            raise HPCNotConfigured(
                "ssh transport requires FOUNDRY_STUDIO_HPC_REMOTE_HOST"
            )
        self.host = host
        self.user = user
        self.key_path = key_path
        self.remote_workdir = remote_workdir
        self.port = port

    def _target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def _ssh_base(self) -> list[str]:
        base = ["ssh", "-p", str(self.port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if self.key_path:
            base += ["-i", self.key_path]
        return base

    def _scp_base(self) -> list[str]:
        base = ["scp", "-P", str(self.port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if self.key_path:
            base += ["-i", self.key_path]
        return base

    def run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        remote_cmd = f"cd {shlex.quote(self.remote_workdir)} && {cmd}" if cwd is None and self.remote_workdir else cmd
        proc = subprocess.run(
            self._ssh_base() + [self._target(), remote_cmd],
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def copy_to(self, local: Path, remote: str) -> None:
        dest = f"{self._target()}:{remote}"
        proc = subprocess.run(
            self._scp_base() + [str(local), dest],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"scp failed: {proc.stderr}")

    def copy_back(self, remote: str, local_dir: Path, patterns: list[str]) -> list[Path]:
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        fetched: list[Path] = []
        for pat in patterns:
            proc = subprocess.run(
                self._scp_base()
                + [f"{self._target()}:{remote}/{pat}", str(local_dir) + "/"],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                for p in local_dir.rglob("*"):
                    if p.is_file():
                        fetched.append(p)
        return fetched

    def read_text(self, remote: str) -> str:
        proc = subprocess.run(
            self._ssh_base() + [self._target(), f"cat {shlex.quote(remote)}"],
            capture_output=True,
            text=True,
        )
        return proc.stdout if proc.returncode == 0 else ""
