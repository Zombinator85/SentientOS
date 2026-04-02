from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.kernel_admission_provenance import verify_kernel_admission_provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify kernel admission provenance linkage for protected mutations.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--decisions-path", type=Path, default=None)
    parser.add_argument("--lineage-path", type=Path, default=None)
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument("--forge-events-path", type=Path, default=None)
    parser.add_argument("--repair-ledger-path", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", help="fail on legacy covered artifacts as well")
    parser.add_argument("--summary-json-out", type=Path, default=None, help="write compact machine-readable summary JSON")
    parser.add_argument("--summary-only", action="store_true", help="print only compact summary JSON")
    args = parser.parse_args(argv)

    payload = verify_kernel_admission_provenance(
        repo_root=args.repo_root,
        decisions_path=args.decisions_path,
        lineage_path=args.lineage_path,
        manifest_path=args.manifest_path,
        forge_events_path=args.forge_events_path,
        repair_ledger_path=args.repair_ledger_path,
        strict=args.strict,
    )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if args.summary_json_out is not None:
        args.summary_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    to_print = summary if args.summary_only else payload
    print(json.dumps(to_print, indent=2, sort_keys=True))
    return 0 if bool(payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
