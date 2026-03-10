from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.attestation import canonical_json_bytes
from sentientos.node_operations import build_incident_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic bounded incident bundle for local triage")
    parser.add_argument("--reason", default="operator_incident_bundle", help="reason included in bundle manifest")
    parser.add_argument("--window", type=int, default=50, help="bounded jsonl collection window")
    parser.add_argument("--json", action="store_true", help="print canonical JSON report")
    args = parser.parse_args(argv)

    payload = build_incident_bundle(Path.cwd().resolve(), reason=str(args.reason), window=max(1, int(args.window)))
    if args.json:
        print(canonical_json_bytes(payload).decode("utf-8"), end="")
    else:
        print(
            f"bundle_path={payload.get('bundle_path')} manifest_sha256={payload.get('manifest_sha256')} "
            f"included_count={payload.get('included_count')}"
        )
    return int(payload.get("exit_code", 3))


if __name__ == "__main__":
    raise SystemExit(main())
