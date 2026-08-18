"""In-process "transport": runs commands on the local machine.

Used by the local backend and by tests that only need to verify script
generation without touching a real cluster.  It is intentionally trivial — no
network, no credentials.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from foundry_studio.hpc.base import Transport


class LocalTransport(Transport):
    name = "local"

    def run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        # Split cmd into list for shell=False to prevent command injection
        import shlex
        cmd_list = shlex.split(cmd) if isinstance(cmd, str) else cmd
        proc = subprocess.run(
            cmd_list,
            shell=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def copy_to(self, local: Path, remote: str) -> None:  # pragma: no cover - local is a no-op
        return None

    def copy_back(self, remote: str, local_dir: Path, patterns: list[str]) -> list[Path]:  # pragma: no cover
        return []

    def read_text(self, remote: str) -> str:  # pragma: no cover
        try:
            return Path(remote).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
