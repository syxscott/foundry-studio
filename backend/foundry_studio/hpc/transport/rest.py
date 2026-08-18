"""REST gateway transport: submit/query via a cluster web API.

Some supercomputers expose a REST gateway (e.g. an in-house job-submission
service).  This transport POSTs commands and file blobs to ``hpc_gateway_url``.
It is real code, but requires the gateway URL + an auth token; without them
``submit`` raises :class:`HPCNotConfigured`.  Uses only the standard library.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from foundry_studio.hpc.base import HPCNotConfigured, Transport


class RestTransport(Transport):
    name = "rest"

    def __init__(self, *, gateway_url: str, token: str = ""):
        if not gateway_url:
            raise HPCNotConfigured(
                "rest transport requires FOUNDRY_STUDIO_HPC_GATEWAY_URL"
            )
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token

    def _post(self, path: str, payload: dict) -> tuple[int, str, str]:
        url = f"{self.gateway_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, ""
        except urllib.error.HTTPError as exc:  # noqa: BLE001
            return exc.code, "", exc.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return -1, "", str(exc)

    def run(self, cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        code, out, err = self._post("/exec", {"cmd": cmd, "cwd": cwd})
        return code, out, err

    def copy_to(self, local: Path, remote: str) -> None:
        # Validate remote path to prevent path traversal
        if ".." in remote or remote.startswith("/"):
            raise ValueError(f"Invalid remote path: {remote!r}")
        with open(local, "rb") as fh:
            body = fh.read()
        req = urllib.request.Request(
            f"{self.gateway_url}/upload?path={urllib.parse.quote(remote, safe='/')}",
            data=body,
            headers={
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=60)  # noqa: S310

    def copy_back(self, remote: str, local_dir: Path, patterns: list[str]) -> list[Path]:
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        fetched: list[Path] = []
        for pat in patterns:
            # Validate pattern to prevent path traversal
            if ".." in pat or pat.startswith("/"):
                raise ValueError(f"Invalid pattern: {pat!r}")
            code, out, _ = self._post("/download", {"path": remote, "pattern": pat})
            if code == 200 and out:
                target = local_dir / Path(pat).name
                target.write_bytes(out.encode("utf-8", "replace") if isinstance(out, str) else out)
                fetched.append(target)
        return fetched

    def read_text(self, remote: str) -> str:
        code, out, _ = self._post("/read", {"path": remote})
        return out if code == 200 else ""
