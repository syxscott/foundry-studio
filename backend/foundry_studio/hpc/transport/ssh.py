"""SSH transport: reach the cluster via ``ssh``/``scp``.

Real, but requires ``hpc_remote_host`` (+ optionally user/key) to be configured;
without it ``submit`` fails loudly with :class:`HPCNotConfigured` rather than
pretending to run.  Commands and file transfers are executed through the system
``ssh``/``scp`` binaries, so no extra Python dependency is needed.
"""

from __future__ import annotations

import re
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
        # SECURITY: use StrictHostKeyChecking=yes to prevent MITM attacks
        base = ["ssh", "-p", str(self.port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
        if self.key_path:
            base += ["-i", self.key_path]
        return base

    def _scp_base(self) -> list[str]:
        # SECURITY: use StrictHostKeyChecking=yes to prevent MITM attacks
        base = ["scp", "-P", str(self.port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
        if self.key_path:
            base += ["-i", self.key_path]
        return base

    def run(self, cmd: str, cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
        if cwd is not None:
            # Always shell-quote when cwd is provided to prevent injection
            remote_cmd = f"cd {shlex.quote(cwd)} && {shlex.quote(cmd)}"
        elif self.remote_workdir:
            remote_cmd = f"cd {shlex.quote(self.remote_workdir)} && {shlex.quote(cmd)}"
        else:
            remote_cmd = shlex.quote(cmd)
        proc = subprocess.run(
            self._ssh_base() + [self._target(), remote_cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def copy_to(self, local: Path, remote: str) -> None:
        # Validate remote path to prevent traversal
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
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
        # Validate remote path
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
        for pat in patterns:
            # Prevent path traversal via pattern
            if ".." in pat or pat.startswith("/"):
                raise ValueError(f"Invalid pattern: {pat!r}")
            # Restrict to safe filename characters
            safe_pat = re.sub(r"[^a-zA-Z0-9.*_\-]", "_", pat)
            # Quote the remote path properly using shlex.quote
            quoted_remote = shlex.quote(f"{remote}/{safe_pat}")
            proc = subprocess.run(
                self._scp_base()
                + [f"{self._target()}:{quoted_remote}", str(local_dir) + "/"],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                for p in local_dir.rglob("*"):
                    if p.is_file():
                        fetched.append(p)
            else:
                # Propagate SCP errors instead of silently ignoring
                raise RuntimeError(f"SCP copy_back failed: {proc.stderr}")
        return fetched

    def read_text(self, remote: str) -> str:
        proc = subprocess.run(
            self._ssh_base() + [self._target(), f"cat {shlex.quote(remote)}"],
            capture_output=True,
            text=True,
        )
        return proc.stdout if proc.returncode == 0 else ""
