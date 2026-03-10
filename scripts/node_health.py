from __future__ import annotations

import argparse

try:
    from scripts.cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root
except ModuleNotFoundError:  # script execution fallback
    from cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root

ensure_repo_on_path(__file__)

from sentientos.node_operations import node_health


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified local node health surface")
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")
    parser.add_argument("--json", action="store_true", help="print canonical JSON health report")
    args = parser.parse_args(argv)

    payload = node_health(resolve_repo_root(args.repo_root))
    emit_payload(
        payload,
        as_json=bool(args.json),
        text_renderer=lambda row: (
            f"health_state={row.get('health_state')} constitution_state={row.get('constitution_state')} "
            f"integrity={row.get('integrity_overall')}"
        ),
    )
    return exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
