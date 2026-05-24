from __future__ import annotations

import argparse
import json

from sentientos.codex_pr_validation_evidence import build_validation_section_from_matrix, verify_pr_validation_evidence


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--title", required=True)
    verify.add_argument("--body", required=True)
    verify.add_argument("--intended-commit-title")
    verify.add_argument("--matrix-json")
    verify.add_argument("--matrix-json-path")
    verify.add_argument("--bootstrap-summary-json")
    verify.add_argument("--explicit-rollup-json")

    build = sub.add_parser("build")
    build.add_argument("--matrix-json")
    build.add_argument("--matrix-json-path")

    a = p.parse_args(argv)
    if a.cmd == "verify":
        result = verify_pr_validation_evidence(
            pr_title=a.title,
            pr_body=a.body,
            intended_commit_title=a.intended_commit_title,
            matrix_json_text=a.matrix_json,
            matrix_json_path=a.matrix_json_path,
            bootstrap_summary_json_text=a.bootstrap_summary_json,
            explicit_rollup_json_text=a.explicit_rollup_json,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.status == "codex_pr_validation_evidence_ready" else 1

    print(build_validation_section_from_matrix(matrix_json_text=a.matrix_json, matrix_json_path=a.matrix_json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
