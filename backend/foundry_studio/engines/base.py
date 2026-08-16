"""Engine abstraction layer.

Each engine wraps the corresponding Foundry model API.  The worker process
instantiates an engine once per model (loading weights once) and reuses it
for every queued job — mirroring the ``BaseInferenceEngine.initialize/run``
separation used upstream in Foundry.
"""

from __future__ import annotations

import abc
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foundry_studio.db import StudioDB

logger = logging.getLogger("foundry_studio.engine")


@dataclass
class OutputFile:
    """A produced artifact, exposed through the API for download/view."""

    name: str
    path: Path
    kind: str = "file"  # one of: cif | fasta | json | log | zip | pdb | txt
    description: str = ""


@dataclass
class EngineResult:
    """Result of a single job execution."""

    outputs: list[OutputFile] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    log_tail: str = ""


class BaseEngine(abc.ABC):
    """Base class for model engines.

    Lifecycle: ``initialize()`` loads weights once; ``run(job)`` executes one
    job and returns its outputs.  Engines must be defensive: any exception is
    caught by the worker and turned into a failed job with a message key.
    """

    #: Stable model id, e.g. "rfd3".
    model_id: str = ""

    def __init__(self, *, db: StudioDB, workdir: Path, log_path: Path):
        self.db = db
        self.workdir = Path(workdir)
        self.log_path = Path(log_path)
        self.initialized = False
        self._init_error: str | None = None

    # ------------------------------------------------------------------ #
    # Public API used by the worker
    # ------------------------------------------------------------------ #
    def initialize(self) -> None:
        """Load the model. Safe to call multiple times."""
        if self.initialized:
            return
        try:
            self._initialize()
            self.initialized = True
        except Exception as exc:  # noqa: BLE001 - surfaced to the job error
            self._init_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Engine %s failed to initialize", self.model_id)
            raise

    def run(self, job: dict[str, Any]) -> EngineResult:
        """Execute one job. Must be implemented by subclasses."""
        if not self.initialized:
            self.initialize()
        return self._run(job)

    # ------------------------------------------------------------------ #
    # Subclass hooks
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    def _initialize(self) -> None:
        """Heavy setup: instantiate the underlying model engine."""

    @abc.abstractmethod
    def _run(self, job: dict[str, Any]) -> EngineResult:
        """Execute the job and return produced outputs."""

    @staticmethod
    @abc.abstractmethod
    def is_available() -> tuple[bool, str]:
        """Return (available, reason).  Checks imports + checkpoint presence.

        ``available=False`` means the real engine cannot run on this host;
        the runner may then fall back to the simulation engine.
        """

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def job_dir(self, job: dict[str, Any]) -> Path:
        return self.workdir / job["id"]

    def collect_outputs(self, directory: Path) -> list[OutputFile]:
        """Index produced files under ``directory`` into OutputFile entries."""
        outputs: list[OutputFile] = []
        if not directory.is_dir():
            return outputs
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(directory).as_posix()
            kind = _kind_for_path(rel)
            outputs.append(
                OutputFile(
                    name=rel,
                    path=path,
                    kind=kind,
                    description=_describe(kind, rel),
                )
            )
        return outputs

    def ensure_job_dir(self, job: dict[str, Any]) -> Path:
        d = self.job_dir(job)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def job_input_files(
        self, job: dict[str, Any], roles: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """Parse the job's uploaded-file descriptors, optionally filtered by role.

        Uploaded files are stored in the job's ``input_files_json`` column (not
        inside ``params_json``); engines must read them from here.
        """
        try:
            files = json.loads(job.get("input_files_json") or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(files, list):
            return []
        if roles is None:
            return files
        return [f for f in files if f.get("role") in roles]


def _kind_for_path(rel: str) -> str:
    lower = rel.lower()
    if lower.endswith((".cif", ".cif.gz", ".mmcif")):
        return "cif"
    if lower.endswith((".pdb", ".pdb.gz")):
        return "pdb"
    if lower.endswith((".fa", ".fasta", ".fas")):
        return "fasta"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".log"):
        return "log"
    if lower.endswith(".txt"):
        return "txt"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".png", ".jpg", ".jpeg", ".svg")):
        return "image"
    return "file"


def _describe(kind: str, rel: str) -> str:
    descriptions = {
        "cif": "Structure (CIF/PDBx)",
        "pdb": "Structure (PDB)",
        "fasta": "Sequence (FASTA)",
        "json": "Metadata (JSON)",
        "log": "Log",
        "zip": "Archive",
        "image": "Image",
        "txt": "Text",
    }
    return descriptions.get(kind, "File")


def tail_text(path: Path, max_chars: int = 8000) -> str:
    """Return the tail of a text file (used for job log snippets)."""
    try:
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        return text[-max_chars:]
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def make_zip(outputs: list[OutputFile], dest: Path) -> OutputFile:
    """Zip produced outputs into a single archive for download."""
    import zipfile

    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for out in outputs:
            if out.path.is_file():
                zf.write(out.path, arcname=out.name)
    return OutputFile(name=dest.name, path=dest, kind="zip", description="All outputs (ZIP)")
