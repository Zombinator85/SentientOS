from __future__ import annotations

import argparse

try:
    from scripts.cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root
except ModuleNotFoundError:  # script execution fallback
    from cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root

ensure_repo_on_path(__file__)

from sentientos.node_operations import build_incident_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic bounded incident bundle for local triage")
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")
    parser.add_argument("--reason", default="operator_incident_bundle", help="reason included in bundle manifest")
    parser.add_argument("--window", type=int, default=50, help="bounded jsonl collection window")
    parser.add_argument("--json", action="store_true", help="print canonical JSON report")
    args = parser.parse_args(argv)

    payload = build_incident_bundle(resolve_repo_root(args.repo_root), reason=str(args.reason), window=max(1, int(args.window)))
    emit_payload(
        payload,
        as_json=bool(args.json),
        text_renderer=lambda row: (
            f"bundle_path={row.get('bundle_path')} manifest_sha256={row.get('manifest_sha256')} "
            f"included_count={row.get('included_count')}"
        ),
    )
    return exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
