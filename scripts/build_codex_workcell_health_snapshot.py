#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_health_snapshot import (
    CodexWorkcellHealthSnapshotError,
    CodexWorkcellHealthSnapshotRequest,
    build_codex_workcell_health_snapshot,
    render_codex_workcell_health_snapshot_markdown,
    write_codex_workcell_health_snapshot_json,
    write_codex_workcell_health_snapshot_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell health snapshot from supplied JSON artifacts.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    for arg in ("architecture-json", "matrix-json", "pre-commit-finalizer-json", "pr-metadata-finalizer-json", "pr-metadata-guard-json", "lifecycle-summary-json", "lifecycle-doctor-json", "evidence-index-json", "evidence-appendix-sidecar-json", "beneficial-trait-doctrine-json"):
        parser.add_argument(f"--{arg}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        snapshot = build_codex_workcell_health_snapshot(CodexWorkcellHealthSnapshotRequest(
            architecture_json=args.architecture_json,
            matrix_json=args.matrix_json,
            pre_commit_finalizer_json=args.pre_commit_finalizer_json,
            pr_metadata_finalizer_json=args.pr_metadata_finalizer_json,
            pr_metadata_guard_json=args.pr_metadata_guard_json,
            lifecycle_summary_json=args.lifecycle_summary_json,
            lifecycle_doctor_json=args.lifecycle_doctor_json,
            evidence_index_json=args.evidence_index_json,
            evidence_appendix_sidecar_json=args.evidence_appendix_sidecar_json,
            beneficial_trait_doctrine_json=args.beneficial_trait_doctrine_json,
        ))
    except CodexWorkcellHealthSnapshotError as exc:
        print(f"codex_workcell_health_snapshot_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_health_snapshot_json(snapshot, args.output)
    if args.markdown_output:
        write_codex_workcell_health_snapshot_markdown(render_codex_workcell_health_snapshot_markdown(snapshot), args.markdown_output)
    if args.summary:
        print(json.dumps({"workcell_health_snapshot_id": snapshot["workcell_health_snapshot_id"], "metadata_only": True, "cockpit_snapshot_only": True, "output": args.output, "markdown_output": args.markdown_output, "supplied_input_count": snapshot["provenance_summary"]["input_digest_count"], "missing_input_count": len(snapshot["missing_inputs"]), "pressure_signal_count": len(snapshot["observed_pressure_signals"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
