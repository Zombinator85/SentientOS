#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from sentientos.codex_workcell_memory_candidate_bundle import (
    CodexWorkcellMemoryCandidateBundleError,
    CodexWorkcellMemoryCandidateBundleRequest,
    build_codex_workcell_memory_candidate_bundle,
    render_codex_workcell_memory_candidate_bundle_markdown,
    write_codex_workcell_memory_candidate_bundle_json,
    write_codex_workcell_memory_candidate_bundle_markdown,
)

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a metadata-only Codex workcell memory candidate bundle.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--summary", action="store_true")
    for arg in ("memory-contract-json", "architecture-json", "health-snapshot-json", "pulse-contract-json", "daemon-recommendation-contract-json", "matrix-json", "pre-commit-finalizer-json", "pr-metadata-finalizer-json", "pr-metadata-guard-json", "evidence-index-json", "appendix-sidecar-json", "doctrine-map-json"):
        parser.add_argument(f"--{arg}")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        bundle = build_codex_workcell_memory_candidate_bundle(CodexWorkcellMemoryCandidateBundleRequest(**{k: getattr(args, k) for k in CodexWorkcellMemoryCandidateBundleRequest.__dataclass_fields__}))
    except CodexWorkcellMemoryCandidateBundleError as exc:
        print(f"codex_workcell_memory_candidate_bundle_error: {exc}", file=sys.stderr)
        return 2
    write_codex_workcell_memory_candidate_bundle_json(bundle, args.output)
    if args.markdown_output:
        write_codex_workcell_memory_candidate_bundle_markdown(render_codex_workcell_memory_candidate_bundle_markdown(bundle), args.markdown_output)
    if args.summary:
        print(json.dumps({"memory_candidate_bundle_id": bundle["memory_candidate_bundle_id"], "metadata_only": True, "candidate_bundle_only": True, "output": args.output, "markdown_output": args.markdown_output, "candidate_ledger_entry_count": bundle["candidate_chain_summary"]["candidate_ledger_entry_count"], "candidate_glow_item_count": bundle["candidate_archive_summary"]["candidate_glow_item_count"], "provided_input_count": sum(1 for item in bundle["input_summaries"].values() if item.get("provided"))}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
