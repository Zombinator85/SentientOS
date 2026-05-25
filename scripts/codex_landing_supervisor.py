from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_landing_supervisor import (
    CodexLandingSupervisorRequest,
    evaluate_landing_supervisor,
    load_json_file,
)


def _matrix_text(args: argparse.Namespace) -> str:
    if args.matrix_json and args.matrix_json_path:
        raise SystemExit("Provide exactly one of --matrix-json or --matrix-json-path")
    if args.matrix_json_path:
        return Path(args.matrix_json_path).read_text(encoding="utf-8")
    if args.matrix_json:
        p = Path(args.matrix_json)
        return p.read_text(encoding="utf-8") if p.exists() else args.matrix_json
    raise SystemExit("One of --matrix-json or --matrix-json-path is required")


def _print(result: dict[str, object], summary: bool) -> None:
    if summary:
        decision = result.get("decision")
        report = result.get("report")
        if not isinstance(decision, dict) or not isinstance(report, dict):
            raise SystemExit("Landing supervisor result payload is malformed")
        print(json.dumps({"status": decision.get("status"), "reasons": report.get("reasons")}, indent=2))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("evaluate", "summarize", "repair-plan"):
        s = sub.add_parser(name)
        s.add_argument("--title", required=True)
        s.add_argument("--intended-commit-title", required=True)
        s.add_argument("--matrix-json")
        s.add_argument("--matrix-json-path")
        s.add_argument("--baseline-json")
        s.add_argument("--changed-file", action="append", default=[])
        s.add_argument("--output")
        s.add_argument("--summary", action="store_true")
        s.add_argument("--landing-gate-status", choices=("passed", "failed", "blocked", "missing"))

    a = p.parse_args(argv)
    baseline = load_json_file(a.baseline_json) if a.baseline_json else None
    gate_result = None
    if a.landing_gate_status == "passed":
        gate_result = {"decision": "pr_metadata_allowed"}
    elif a.landing_gate_status in {"failed", "blocked"}:
        gate_result = {"decision": "pr_metadata_blocked"}
    req = CodexLandingSupervisorRequest(title=a.title, intended_commit_title=a.intended_commit_title, matrix_json_text=_matrix_text(a), changed_files=tuple(a.changed_file), baseline_summary=baseline, pr_landing_gate_result=gate_result)
    result = evaluate_landing_supervisor(req).to_dict()
    if a.output:
        Path(a.output).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    _print(result, a.summary or a.cmd in {"summarize", "repair-plan"})
    return 0 if result["decision"]["status"] in {"ready_to_commit", "ready_for_pr_metadata"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
