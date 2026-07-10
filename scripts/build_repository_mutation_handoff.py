#!/usr/bin/env python3
"""Build a deterministic repository mutation handoff from explicit proposal JSON."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from sentientos.repository_mutation_handoff import (
    HandoffInputError,
    build_repository_mutation_handoff,
    is_ready_handoff,
    render_handoff_markdown,
    write_handoff_json,
)


def _read_only_revision(repo_root: Path) -> tuple[str, list[str]]:
    try:
        result = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repo_root, capture_output=True, text=True, check=False)
    except OSError:
        return "unknown", ["source_revision_unknown"]
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip(), []
    return "unknown", ["source_revision_unknown"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal-json", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--source-revision")
    parser.add_argument("--created-at", default="1970-01-01T00:00:00+00:00")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        proposal = json.loads(Path(args.proposal_json).read_text(encoding="utf-8"))
        if not isinstance(proposal, dict):
            raise ValueError("proposal JSON must be an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"repository_mutation_handoff_input_error: {exc}", file=sys.stderr)
        return 2

    try:
        repo_root = Path(args.repo_root).resolve()
        source_revision = args.source_revision
        extra_warnings: list[str] = []
        if source_revision is None:
            source_revision, extra_warnings = _read_only_revision(repo_root)
        handoff = build_repository_mutation_handoff(
            proposal,
            repo_root=repo_root,
            source_revision=source_revision,
            created_at=args.created_at,
        )
        handoff["warning_codes"] = sorted(set(handoff.get("warning_codes", [])) | set(extra_warnings))
        write_handoff_json(handoff, args.output)
        if args.markdown_output:
            Path(args.markdown_output).write_text(render_handoff_markdown(handoff), encoding="utf-8")
    except (OSError, HandoffInputError) as exc:
        print(f"repository_mutation_handoff_output_error: {exc}", file=sys.stderr)
        return 2

    if args.summary:
        print(json.dumps({"handoff_status": handoff["handoff_status"], "digest": handoff["digest"]}, sort_keys=True))
    return 0 if is_ready_handoff(handoff) else 1


if __name__ == "__main__":
    raise SystemExit(main())
