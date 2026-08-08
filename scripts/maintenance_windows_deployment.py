#!/usr/bin/env python3
"""Operator CLI for inert Windows maintenance wake deployment artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from sentientos import maintenance_windows_deployment as deployment


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("write-template"); template.add_argument("--output", required=True)
    for name in ("render", "verify"):
        item = sub.add_parser(name); item.add_argument("--manifest", required=True); item.add_argument("--output-directory")
    for name in ("inspect", "print-install-command", "print-uninstall-command", "print-preflight-command"):
        item = sub.add_parser(name); item.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "write-template":
            target = Path(args.output); data = deployment.canonical_json_bytes(deployment.template())
            if target.exists() and target.read_bytes() != data: raise ValueError("conflicting_output:" + str(target))
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            result: dict[str, Any] = {"status": "windows_deployment_ready", "path": str(target), "scheduler_mutation_performed": False}
        else:
            cfg = deployment.load_manifest(args.manifest)
            if args.command == "render": result = deployment.render(cfg, args.output_directory or cfg["deployment_output_directory"])
            elif args.command == "verify": result = deployment.verify(cfg, args.output_directory or cfg["deployment_output_directory"])
            else: result = getattr(deployment, args.command.replace("-", "_"))(cfg)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "windows_deployment_blocked", "reason_codes": [str(exc)], "scheduler_mutation_performed": False}
    print(deployment.canonical_json_bytes(result).decode(), end="")
    return 0 if result.get("status") == "windows_deployment_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
