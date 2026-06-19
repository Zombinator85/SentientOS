#!/usr/bin/env python3
"""Build the SentientOS reviewer first-run proof bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.reviewer_proof_bundle import (
    build_reviewer_proof_bundle_payload,
    summarize_reviewer_proof_bundle_manifest,
    validate_reviewer_proof_bundle_manifest,
    write_reviewer_proof_bundle,
)


def _summary_text(summary: dict[str, object], output_dir: str) -> str:
    return "\n".join(
        [
            "SentientOS Reviewer First-Run Proof Bundle",
            f"output_dir: {output_dir}",
            f"manifest_id: {summary['manifest_id']}",
            f"scenario: {summary['scenario_id']}",
            f"status: {summary['bundle_status']}",
            f"artifacts: {summary['artifact_count']}",
            f"proof commands listed: {summary['proof_command_count']}",
            f"proof commands executed: {summary['proof_commands_executed']}",
            "metadata only: true",
            "reviewer proof only: true",
            "fake/sample telemetry by default: true",
            "live host collection performed: false",
            "live authorization / effects / host mutation / network / provider / prompt assembly: false",
            f"digest: {summary['digest']}",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only SentientOS reviewer proof bundle")
    parser.add_argument("--output-dir", required=True, help="explicit local output directory for bundle files")
    parser.add_argument("--scenario", choices=("thermal_pwm_demo", "work_item_attestation"), default="thermal_pwm_demo", help="deterministic reviewer scenario")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00", help="deterministic creation timestamp")
    parser.add_argument("--verify", action="store_true", help="run bounded in-process metadata verification when supported by the selected scenario")
    parser.add_argument("--no-verify", action="store_true", help="list proof commands without running them (default)")
    parser.add_argument("--summary", action="store_true", help="print compact summary after writing")
    parser.add_argument("--manifest-only", action="store_true", help="write only bundle_manifest.json")
    parser.add_argument("--force", action="store_true", help="overwrite existing bundle files within output directory")
    args = parser.parse_args(argv)

    if args.verify and args.scenario != "work_item_attestation":
        print("--verify is supported only for --scenario work_item_attestation; inspect proof_commands.json and run commands separately", file=sys.stderr)
        return 2
    if not str(args.output_dir):
        print("output directory is required", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir)
    if str(args.output_dir).strip() == "":
        print("output directory is required", file=sys.stderr)
        return 2
    try:
        payload = build_reviewer_proof_bundle_payload(scenario=args.scenario, created_at=args.created_at, verify=args.verify)
        manifest = payload["manifest"]
        validation = validate_reviewer_proof_bundle_manifest(manifest)
        if not validation.ok:
            print("reviewer proof bundle validation failed: " + ", ".join(validation.findings), file=sys.stderr)
            return 2
        write_reviewer_proof_bundle(output_dir, payload, force=args.force, manifest_only=args.manifest_only)
        summary = summarize_reviewer_proof_bundle_manifest(manifest)
        print(_summary_text(summary, str(output_dir)), end="")
        return 0
    except (OSError, TypeError, ValueError, FileExistsError) as exc:
        print(f"reviewer proof bundle failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
