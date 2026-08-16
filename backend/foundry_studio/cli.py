"""CLI entry point for foundry-studio (`python -m foundry_studio.cli`)."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foundry-studio",
        description="Web UI for RosettaCommons Foundry protein design toolkit",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the API + (if built) frontend server")
    serve.add_argument("--host", default=None, help="Bind host (overrides settings)")
    serve.add_argument("--port", type=int, default=None, help="Bind port (overrides settings)")

    doctor = sub.add_parser(
        "doctor",
        help="Run the environment diagnostics (GPU, CUDA, rc-foundry packages, "
        "checkpoints, HPC connectivity, permissions)",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    install = sub.add_parser("install-checkpoints", help="Install model checkpoints")
    install.add_argument("models", nargs="+", help="e.g. rfd3 rf3 proteinmpnn")

    sub.add_parser("version", help="Print version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        from foundry_studio import __version__

        print(__version__)
        return 0

    if args.command == "install-checkpoints":
        from foundry_studio.engines.checkpoints import install_checkpoint

        for name in args.models:
            print(f"Installing {name} ...")
            try:
                result = install_checkpoint(name)
                print(f"  OK -> {result['path']}")
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}", file=sys.stderr)
                return 1
        return 0

    if args.command == "serve":
        from foundry_studio.app import run_server
        from foundry_studio.config import Settings

        settings = Settings()
        if args.host:
            settings.host = args.host
        if args.port:
            settings.port = args.port
        run_server(settings)
        return 0

    if args.command == "doctor":
        from foundry_studio.doctor import print_report, run_all

        results = run_all()
        if args.json:
            import json

            print(json.dumps({
                "results": [{
                    "label": r.label,
                    "severity": r.severity.value,
                    "message": r.message,
                    "hint": r.hint,
                    "details": r.details,
                } for r in results],
                "summary": {
                    "passed": sum(1 for r in results if r.severity.value == "PASS"),
                    "warnings": sum(1 for r in results if r.severity.value == "WARN"),
                    "failures": sum(1 for r in results if r.severity.value == "FAIL"),
                },
            }, indent=2))
        else:
            print_report(results)
        return 0 if not any(r.severity.value == "FAIL" for r in results) else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
