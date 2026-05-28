from __future__ import annotations

import argparse
import sys

from sentientos.codex_pr_metadata_guard import CodexPrMetadataGuardRequest, evaluate_pr_metadata_guard, result_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate local finalizer proof artifacts before PR metadata/make_pr.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--title", required=True)
    verify.add_argument("--intended-commit-title", required=True)
    verify.add_argument("--pre-commit-finalizer-json", default="")
    verify.add_argument("--pr-metadata-finalizer-json", required=True)
    verify.add_argument("--matrix-json-path", required=True)
    verify.add_argument("--validation-only", action="store_true")
    verify.add_argument("--workspace-root", default=".")
    verify.add_argument("--summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd != "verify":
        return 2
    result = evaluate_pr_metadata_guard(
        CodexPrMetadataGuardRequest(
            title=args.title,
            intended_commit_title=args.intended_commit_title,
            pre_commit_finalizer_json=args.pre_commit_finalizer_json,
            pr_metadata_finalizer_json=args.pr_metadata_finalizer_json,
            matrix_json_path=args.matrix_json_path,
            validation_only=args.validation_only,
            workspace_root=args.workspace_root,
        )
    )
    sys.stdout.write(result_json(result))
    if args.summary:
        print(f"Codex PR metadata guard decision: {result.status}")
        for reason in result.reasons:
            print(f"- {reason}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
