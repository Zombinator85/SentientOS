from __future__ import annotations

import argparse

try:
    from scripts.cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root
except ModuleNotFoundError:  # script execution fallback
    from cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root

ensure_repo_on_path(__file__)

from sentientos.node_operations import run_bootstrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap local SentientOS node and generate cockpit artifacts")
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")
    parser.add_argument("--reason", default="operator_node_bootstrap", help="operator reason included in restoration provenance")
    parser.add_argument("--seed-minimal", action="store_true", help="seed minimal local-node prerequisites like immutable manifest if missing")
    parser.add_argument("--no-restore", action="store_true", help="skip restoration/re-anchor flow")
    parser.add_argument("--json", action="store_true", help="print canonical JSON report")
    args = parser.parse_args(argv)

    payload = run_bootstrap(resolve_repo_root(args.repo_root), reason=str(args.reason), seed_minimal=bool(args.seed_minimal), allow_restore=not bool(args.no_restore))
    emit_payload(
        payload,
        as_json=bool(args.json),
        text_renderer=lambda row: (
            f"health_state={row.get('health_state')} constitution_state={row.get('constitution_state')} "
            f"report_path={row.get('report_path')}"
        ),
    )
    return exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
