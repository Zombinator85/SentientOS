from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_pr_landing_gate import build_and_verify_pr_body, verify_pr_landing_gate
from sentientos.codex_pr_validation_evidence import build_validation_section_from_matrix


def _resolve_matrix_json(*, matrix_json: str | None, matrix_json_path: str | None) -> str:
    if matrix_json and matrix_json_path:
        raise SystemExit("Provide exactly one of --matrix-json or --matrix-json-path.")
    if matrix_json_path:
        return Path(matrix_json_path).read_text(encoding="utf-8")
    if matrix_json is None:
        raise SystemExit("One of --matrix-json or --matrix-json-path is required.")
    path = Path(matrix_json)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return matrix_json


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--title", required=True)
    v.add_argument("--intended-commit-title", required=True)
    v.add_argument("--body")
    v.add_argument("--rollup-json")
    v.add_argument("--matrix-json")
    v.add_argument("--matrix-json-path")
    v.add_argument("--bootstrap-summary-json")
    v.add_argument("--strict-mode-policy-json")

    b = sub.add_parser("build-body")
    b.add_argument("--matrix-json")
    b.add_argument("--matrix-json-path")

    g = sub.add_parser("gate")
    g.add_argument("--title", required=True)
    g.add_argument("--intended-commit-title", required=True)
    g.add_argument("--body")
    g.add_argument("--matrix-json")
    g.add_argument("--matrix-json-path")

    a = p.parse_args(argv)
    matrix_json_text = _resolve_matrix_json(matrix_json=a.matrix_json, matrix_json_path=getattr(a, "matrix_json_path", None))
    if a.cmd == "build-body":
        print(build_validation_section_from_matrix(matrix_json_text=matrix_json_text))
        return 0
    if a.cmd == "verify":
        res = verify_pr_landing_gate(proposed_pr_title=a.title, intended_commit_title=a.intended_commit_title, proposed_pr_body=a.body, structured_rollup_json_text=a.rollup_json, matrix_json_text=matrix_json_text, bootstrap_summary_json_text=a.bootstrap_summary_json, strict_mode_policy_json_text=a.strict_mode_policy_json)
    else:
        if a.body:
            res = verify_pr_landing_gate(proposed_pr_title=a.title, intended_commit_title=a.intended_commit_title, proposed_pr_body=a.body, matrix_json_text=matrix_json_text)
        else:
            res = build_and_verify_pr_body(proposed_pr_title=a.title, intended_commit_title=a.intended_commit_title, matrix_json_text=matrix_json_text)
    print(json.dumps(res.to_dict(), indent=2, sort_keys=True))
    return 0 if res.decision == "pr_metadata_allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
