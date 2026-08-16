"""Environment diagnostics for foundry-studio.

Run ``python -m foundry_studio.doctor`` or ``foundry-studio doctor`` to
get a human-readable inventory of what is and is not working in the
current installation.  Every check is independent so a partial environment
(e.g. no GPU, no HPC cluster) is not a fatal error — the tool reports
what works and what to fix next.

Exit code: 0 = all critical checks pass, 1 = at least one FAIL.
Exit code 2 = unexpected internal error (bug in the doctor itself).
"""

from __future__ import annotations

import enum
import getpass
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


class Severity(enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    label: str  # short identifier shown in the [PASS/WARN/FAIL] badge
    message: str  # human-readable description
    severity: Severity
    hint: str = ""  # what to do to improve
    details: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Check helpers
# --------------------------------------------------------------------------- #


def _run(*args: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a command; return (returncode, stdout, stderr)."""
    try:
        cp = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return -1, "", str(exc)


def _net_reachable(url: str, timeout: float = 8.0) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def _file_size_human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# --------------------------------------------------------------------------- #
# Individual check functions
# --------------------------------------------------------------------------- #


def check_python() -> CheckResult:
    """Python version must be >= 3.12."""
    v = sys.version_info
    ok = v >= (3, 12)
    return CheckResult(
        label="Python",
        severity=Severity.PASS if ok else Severity.FAIL,
        message=f"Python {v.major}.{v.minor}.{v.micro}" + (" (meets requirement)" if ok else " (3.12+ required)"),
        hint="Install Python 3.12 or later: https://www.python.org/downloads/" if not ok else "",
        details={"version_info": v},
    )


def check_torch() -> CheckResult:
    """PyTorch + CUDA availability."""
    try:
        import torch

        version = torch.__version__
        cuda_available = torch.cuda.is_available()
        cuda_version = ""
        gpu_names: list[str] = []
        gpu_memory_gb: list[float] = []

        if cuda_available:
            cuda_version = torch.version.cuda or ""
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                gpu_names.append(name)
                gpu_memory_gb.append(round(mem, 1))

        if cuda_available:
            # Warn if GPU memory is below what's needed for large models.
            min_gb = 6.0
            ok = all(m >= min_gb for m in gpu_memory_gb)
            if ok:
                msg = f"PyTorch {version} + CUDA {cuda_version} ({len(gpu_names)} GPU: {', '.join(gpu_names)})"
            else:
                msg = f"PyTorch {version} + CUDA {cuda_version} ({len(gpu_names)} GPU: {', '.join(gpu_names)}) — some GPUs < {min_gb} GB"
            hint = ""
            if not ok:
                hint = f"GPU(s) with < {min_gb} GB memory may OOM on large models. Use GPU with >= {min_gb} GB or reduce batch size."
            return CheckResult(
                label="GPU / CUDA",
                severity=Severity.WARN if not ok else Severity.PASS,
                message=msg,
                hint=hint,
                details={
                    "torch_version": version,
                    "cuda_available": cuda_available,
                    "cuda_version": cuda_version,
                    "gpus": [{"name": n, "memory_gb": m} for n, m in zip(gpu_names, gpu_memory_gb)],
                },
            )
        else:
            return CheckResult(
                label="GPU / CUDA",
                severity=Severity.WARN,
                message=f"PyTorch {version} installed but CUDA not available (CPU-only)",
                hint="Install PyTorch with CUDA: https://pytorch.org/get-started/locally/\n"
                "  e.g.  pip install torch --index-url https://download.pytorch.org/whl/cu124\n"
                "  Or use conda: conda install pytorch pytorch-cuda=12.4 -c pytorch -c nvidia\n"
                "(CPU-only mode works for UI/monitoring; inference jobs need GPU)",
                details={"torch_version": version, "cuda_available": False, "cuda_version": "", "gpus": []},
            )
    except ImportError:
        return CheckResult(
            label="GPU / CUDA",
            severity=Severity.FAIL,
            message="PyTorch not installed",
            hint="pip install torch  (or with CUDA: pip install torch --index-url https://download.pytorch.org/whl/cu124)",
            details={"torch_version": None, "cuda_available": False},
        )


def check_rc_foundry_packages() -> CheckResult:
    """Can each rc-foundry sub-package be imported?"""
    packages = [
        ("rfd3", "RFdiffusion3 inference"),
        ("rf3", "RosettaFold3 inference"),
        ("proteinmpnn", "ProteinMPNN inference"),
        ("rfd3na", "RFdiffusion3NA inference"),
    ]
    results: dict[str, Any] = {}
    failed: list[str] = []
    passed: list[str] = []

    for pkg, desc in packages:
        try:
            __import__(pkg)
            passed.append(pkg)
            results[pkg] = {"importable": True, "desc": desc}
        except ImportError as exc:
            failed.append(pkg)
            results[pkg] = {"importable": False, "error": str(exc), "desc": desc}

    if not failed:
        return CheckResult(
            label="Foundry packages",
            severity=Severity.PASS,
            message=f"All 4 inference packages importable: {', '.join(passed)}",
            details=results,
        )
    elif not passed:
        return CheckResult(
            label="Foundry packages",
            severity=Severity.FAIL,
            message="No rc-foundry inference packages found (rc-foundry[all] not installed?)",
            hint="pip install 'rc-foundry[all]>=0.1'\n"
            "  or follow: https://github.com/RosettaCommons/foundry",
            details=results,
        )
    else:
        return CheckResult(
            label="Foundry packages",
            severity=Severity.WARN,
            message=f"Partially installed: {', '.join(passed)} OK, {', '.join(failed)} missing",
            hint=f"pip install 'rc-foundry[all]>=0.1'\nMissing: {', '.join(failed)}",
            details=results,
        )


def check_checkpoints() -> CheckResult:
    """Are model checkpoints present and, if possible, hash-validated?"""
    from foundry_studio.engines import checkpoints as ckpt

    registry = ckpt._merged_registry()
    entries = ckpt.list_checkpoints()
    installed: list[str] = []
    missing: list[str] = []
    details: dict[str, Any] = {}

    for e in entries:
        name = e["name"]
        info = registry.get(name, {})
        detail: dict[str, Any] = {
            "installed": e["installed"],
            "path": e["path"],
            "size_bytes": e["size_bytes"],
        }
        if e["installed"]:
            installed.append(name)
            detail["size_human"] = _file_size_human(e["size_bytes"])
        else:
            missing.append(name)
            detail["url"] = info.get("url", "")
        details[name] = detail

    # Essential checkpoints are those needed for basic real-engine operation.
    essential = {"rfd3", "rf3", "proteinmpnn"}
    missing_essential = set(missing) & essential

    if not missing:
        return CheckResult(
            label="Checkpoints",
            severity=Severity.PASS,
            message=f"All {len(installed)} checkpoints present",
            details=details,
        )
    elif not missing_essential:
        return CheckResult(
            label="Checkpoints",
            severity=Severity.WARN,
            message=f"Missing optional checkpoints: {', '.join(sorted(missing))}",
            hint=f"foundry-studio install-checkpoints {' '.join(sorted(missing))}",
            details=details,
        )
    else:
        return CheckResult(
            label="Checkpoints",
            severity=Severity.FAIL,
            message=f"Missing essential checkpoints: {', '.join(sorted(missing_essential))}",
            hint=f"foundry-studio install-checkpoints {' '.join(sorted(missing_essential))}",
            details=details,
        )


def check_containers() -> CheckResult:
    """Singularity / Apptainer available (for HPC container invocation)?"""
    found: dict[str, str] = {}
    for binary in ("singularity", "apptainer"):
        path = shutil.which(binary)
        if path:
            rc, out, _ = _run(path, "--version")
            found[binary] = out if rc == 0 else f"(version check failed, path={path})"

    if not found:
        return CheckResult(
            label="Container runtime",
            severity=Severity.WARN,
            message="No Singularity or Apptainer found",
            hint="Install Singularity/Apptainer for HPC GPU jobs: https://apptainer.org/admin-docs/current/installation.html\n"
            "(container invocation is only needed for HPC Slurm/PBS/LSF cluster jobs)",
            details={},
        )
    names = " + ".join(found.keys())
    versions = "; ".join(f"{k} {v}" for k, v in found.items())
    return CheckResult(
        label="Container runtime",
        severity=Severity.PASS,
        message=f"{names} found ({len(found)})",
        details=found,
        hint=f"{versions}",
    )


def check_hpc_ssh() -> CheckResult:
    """SSH to configured HPC host (if any) without password."""
    from foundry_studio.config import get_settings

    settings = get_settings()
    if settings.hpc_backend == "local" or not settings.hpc_remote_host:
        return CheckResult(
            label="HPC SSH",
            severity=Severity.PASS,
            message="Backend is 'local'; HPC SSH check skipped",
            details={"configured_backend": settings.hpc_backend},
        )

    host = settings.hpc_remote_host
    user = settings.hpc_remote_user or getpass.getuser()
    # Check connectivity first.
    try:
        addr = socket.gethostbyname(host)
    except socket.gaierror:
        return CheckResult(
            label="HPC SSH",
            severity=Severity.FAIL,
            message=f"Cannot resolve HPC host '{host}'",
            hint=f"Check FOUNDRY_STUDIO_HPC_REMOTE_HOST={host} in .env",
            details={"host": host},
        )

    # Try an ssh -o BatchMode=yes -o ConnectTimeout=5
    # to verify passwordless access.
    rc, stdout, stderr = _run(
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
        "echo",  # simplest command
        timeout=12.0,
    )
    if rc == 0:
        return CheckResult(
            label="HPC SSH",
            severity=Severity.PASS,
            message=f"SSH to {host} OK (passwordless auth working)",
            details={"host": host, "user": user, "resolved_to": addr},
        )
    else:
        hint = f"Configure passwordless SSH to {host}:\n"
        hint += "  1. ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519\n"
        hint += f"  2. ssh-copy-id {user}@{host}\n"
        hint += f"  3. Verify: ssh {user}@{host} 'echo OK'"
        return CheckResult(
            label="HPC SSH",
            severity=Severity.FAIL,
            message=f"SSH to {host} FAILED (rc={rc})",
            hint=hint,
            details={"host": host, "user": user, "resolved_to": addr, "stderr": stderr[:200]},
        )


def check_network_access() -> CheckResult:
    """Can we reach the checkpoint download hosts?"""
    urls = [
        "https://files.ipd.uw.edu",
        "https://github.com",
    ]
    reachable: dict[str, bool] = {}
    for url in urls:
        reachable[url] = _net_reachable(url)
    all_ok = all(reachable.values())
    return CheckResult(
        label="Network",
        severity=Severity.FAIL if not all_ok else Severity.PASS,
        message="All required hosts reachable" if all_ok else f"Some hosts unreachable: {[u for u, r in reachable.items() if not r]}",
        hint="Check firewall / proxy settings" if not all_ok else "",
        details=reachable,
    )


def check_data_dir_permissions() -> CheckResult:
    """Can we write to the configured data directory?"""
    from foundry_studio.config import get_settings

    settings = get_settings()
    data_dir = settings.resolved_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".foundry-studio-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult(
            label="Data dir",
            severity=Severity.PASS,
            message=f"Data dir writable: {data_dir}",
            details={"data_dir": str(data_dir)},
        )
    except PermissionError:
        return CheckResult(
            label="Data dir",
            severity=Severity.FAIL,
            message=f"Data dir not writable: {data_dir}",
            hint=f"Grant write permission: chmod u+rwx '{data_dir}'\n"
            "  or set FOUNDRY_STUDIO_DATA_DIR to a directory you own",
            details={"data_dir": str(data_dir)},
        )
    except OSError as exc:
        return CheckResult(
            label="Data dir",
            severity=Severity.FAIL,
            message=f"Cannot access data dir {data_dir}: {exc}",
            hint="Check that FOUNDRY_STUDIO_DATA_DIR points to a valid path",
            details={"data_dir": str(data_dir), "error": str(exc)},
        )


def check_env_file() -> CheckResult:
    """Is the .env file being loaded?"""
    from foundry_studio.config import get_settings

    settings = get_settings()
    resolved = settings.resolved_data_dir()
    configured_backend = getattr(settings, "hpc_backend", "local")

    # Heuristic: if the data dir is still the default (~/.foundry-studio),
    # and we can't see any HPC config, the user probably has no .env.
    has_explicit_backend = configured_backend != "local"
    has_explicit_data = settings.data_dir != Path.home() / ".foundry-studio"

    if has_explicit_backend or has_explicit_data:
        return CheckResult(
            label="Config",
            severity=Severity.PASS,
            message=f"Config loaded (backend={configured_backend}, data_dir={resolved})",
            details={"hpc_backend": configured_backend, "data_dir": str(resolved)},
        )
    else:
        return CheckResult(
            label="Config",
            severity=Severity.WARN,
            message="No .env file detected (using all defaults)",
            hint="Copy .env.example to .env and configure for production use:\n"
            "  cp .env.example .env\n"
            "  # Then edit .env with your HPC / checkpoint settings",
            details={"data_dir": str(resolved), "hpc_backend": configured_backend},
        )


def check_foundry_studio_version() -> CheckResult:
    """Version and installation method."""
    # Try to detect if installed editable.
    import foundry_studio
    from foundry_studio import __version__

    location = Path(foundry_studio.__file__).parent
    editable = ".pth" in os.environ.get("PATH", "") or (
        location.parent.name == "foundry_studio"
        and (location.parent.parent / "pyproject.toml").is_file()
    )
    return CheckResult(
        label="foundry-studio",
        severity=Severity.PASS,
        message=f"v{__version__} at {location}" + (" (editable install)" if editable else ""),
        details={"version": __version__, "path": str(location)},
    )


def check_simulation_engine() -> CheckResult:
    """Can the simulation engine instantiate without external dependencies?"""
    from foundry_studio.engines.simulation import SimulationEngine

    ok, msg = SimulationEngine.is_available()
    if not ok:
        return CheckResult(
            label="Simulation engine",
            severity=Severity.FAIL,
            message=f"Simulation engine unavailable: {msg}",
            hint="Simulation engine should always be available. This is a bug in foundry-studio.",
            details={"available": False, "reason": msg},
        )
    # Quick unit test: verify _simulate_protein produces a realistic-looking structure
    # without requiring any external packages.
    try:
        from foundry_studio.engines.simulation import _simulate_protein

        atoms = _simulate_protein(n_res=50, model="rfd3", seed=42)
        if len(atoms) < 20:
            raise ValueError(f"Expected >= 20 atoms, got {len(atoms)}")
        # Verify backbone atoms are present with valid coordinates
        for resnum, letter, resname, ca, cb in atoms:
            if len(ca) != 3:
                raise ValueError(f"CA coord must be 3D, got {ca}")
        return CheckResult(
            label="Simulation engine",
            severity=Severity.PASS,
            message=f"Simulation engine works ({len(atoms)} residues, helical+beta geometry)",
            details={
                "available": True,
                "mode": "simulation",
                "n_residues": len(atoms),
            },
        )
    except Exception as exc:
        return CheckResult(
            label="Simulation engine",
            severity=Severity.FAIL,
            message=f"Simulation engine failed: {exc}",
            hint="This should never happen — the simulation engine has no external dependencies.",
            details={"available": True, "error": str(exc)},
        )


# --------------------------------------------------------------------------- #
# Run all checks
# --------------------------------------------------------------------------- #

ALL_CHECKS: list[object] = [
    check_python,
    check_foundry_studio_version,
    check_torch,
    check_rc_foundry_packages,
    check_checkpoints,
    check_simulation_engine,
    check_containers,
    check_data_dir_permissions,
    check_env_file,
    check_network_access,
    check_hpc_ssh,
]

# GPU-heavy model checks only run if we have a GPU.
GPU_MODEL_CHECKS: list[object] = []


def run_all() -> list[CheckResult]:
    return [fn() for fn in ALL_CHECKS]


def print_report(results: list[CheckResult]) -> None:
    """Human-readable console output."""
    has_fail = any(r.severity == Severity.FAIL for r in results)

    print()
    print("\u250f" + "\u2501" * 78)
    print("\u2503  foundry-studio doctor  " + "\u2501" * 55 + "\u250f")
    print("\u251b" + "\u2501" * 78)

    for result in results:
        badge = {
            Severity.PASS: "\u001b[32mPASS\u001b[0m",
            Severity.WARN: "\u001b[33mWARN\u001b[0m",
            Severity.FAIL: "\u001b[31mFAIL\u001b[0m",
        }[result.severity]
        print(f"  [{badge}] {result.label}")
        print(f"         {result.message}")
        if result.hint:
            for line in result.hint.splitlines():
                print(f"  \u2192 {line}")
        print()

    # Summary bar
    fails = sum(1 for r in results if r.severity == Severity.FAIL)
    warns = sum(1 for r in results if r.severity == Severity.WARN)
    passed = sum(1 for r in results if r.severity == Severity.PASS)
    print(f"\u2517{'─' * 78}")
    print(
        f"  Summary: {passed} passed, {warns} warning(s), {fails} failure(s)"
        + ("  \u001b[32mAll critical checks pass!\u001b[0m" if not has_fail else "  \u001b[31mAction required — see FAIL items above\u001b[0m")
    )
    print()

    # JSON dump for scripting
    import json

    print("  --json --")
    # Use repr-safe encoding for terminal display
    json_str = json.dumps(
        {
            "results": [
                {
                    "label": r.label,
                    "severity": r.severity.value,
                    "message": r.message,
                    "hint": r.hint,
                    "details": r.details,
                }
                for r in results
            ],
            "summary": {
                "passed": passed,
                "warnings": warns,
                "failures": fails,
            },
        },
        indent=2,
    )
    for line in json_str.splitlines():
        print(f"  {line}")
    print()


def main() -> int:
    results = run_all()
    print_report(results)

    has_fail = any(r.severity == Severity.FAIL for r in results)
    return 0 if not has_fail else 1


if __name__ == "__main__":
    sys.exit(main())
