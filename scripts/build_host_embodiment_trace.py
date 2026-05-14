#!/usr/bin/env python3
"""Build the deterministic Host Embodiment reviewer demo trace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.host_embodiment_trace import build_host_embodiment_demo_trace, summarize_host_embodiment_trace
from sentientos.host_embodiment_trace_export import (
    serialize_host_embodiment_trace_json,
    serialize_host_embodiment_trace_markdown,
    validate_trace_export_payload,
    write_trace_export_artifact,
)

SCENARIO_ALIASES = {
    "thermal_pwm_demo": "demo-thermal-pwm-non-mutating-ladder",
}


def build_trace_for_scenario(scenario: str):
    if scenario not in SCENARIO_ALIASES:
        raise ValueError(f"unsupported scenario: {scenario}")
    return build_host_embodiment_demo_trace(scenario_id=SCENARIO_ALIASES[scenario])


def _summary_text(trace) -> str:
    summary = summarize_host_embodiment_trace(trace)
    return "\n".join(
        [
            "Host Embodiment Reviewer Demo Trace Summary",
            f"scenario: {summary['scenario_id']}",
            f"status: {summary['trace_status']}",
            f"steps: {summary['step_count']}",
            "reviewer proof only: true",
            "fake/sample telemetry by default: true",
            "pwm presence is not control authority: true",
            "controlled authorization contract is not live grant: true",
            "grant/revocation records schema-only/future-use-only: true",
            "no live authorization / no effect / no host mutation / no network / no provider / no prompt assembly: true",
            f"digest: {summary['digest']}",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic non-mutating host embodiment reviewer trace")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="output format")
    parser.add_argument("--output", help="explicit file path for writing the artifact")
    parser.add_argument("--scenario", choices=tuple(SCENARIO_ALIASES), default="thermal_pwm_demo", help="deterministic demo scenario")
    parser.add_argument("--validate-only", action="store_true", help="validate the generated trace and print no artifact")
    parser.add_argument("--summary", action="store_true", help="print a compact reviewer summary")
    args = parser.parse_args(argv)

    try:
        trace = build_trace_for_scenario(args.scenario)
        result = validate_trace_export_payload(trace)
        if not result.ok:
            print("trace validation failed: " + ", ".join(result.findings), file=sys.stderr)
            return 2
        if args.validate_only:
            return 0
        content = _summary_text(trace) if args.summary else (
            serialize_host_embodiment_trace_markdown(trace) if args.format == "markdown" else serialize_host_embodiment_trace_json(trace)
        )
        if args.output:
            write_trace_export_artifact(args.output, content)
        else:
            print(content, end="")
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"host embodiment trace export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
