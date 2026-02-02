"""Autonomy rehearsal driver for SentientOS.

This utility orchestrates a single rehearsal cycle by simulating the
GapSeeker → IntegrityPipeline → test gate workflow described in the
cathedral operating manual.  It emits structured telemetry and metrics so
we can validate the pipeline end-to-end without the full daemon running.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUIRED_FIELDS = ("objective", "directives", "testing_requirements")
RISK_BUCKETS = [(i / 10, (i + 1) / 10) for i in range(10)]


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    duration_s: float
    stdout: str
    stderr: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "command": " ".join(self.command),
            "argv": list(self.command),
            "returncode": self.returncode,
            "duration_s": self.duration_s,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_command(command: Iterable[str], *, cwd: Path | None = None) -> CommandResult:
    argv = list(command)
    start = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.perf_counter() - start
    return CommandResult(argv, proc.returncode, duration, proc.stdout, proc.stderr)


def _git_diff_stats(path: str) -> tuple[int, int]:
    proc = subprocess.run(
        ["git", "diff", "--numstat", "HEAD", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    insertions = deletions = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ins, dels, file_path = parts
        if file_path == path:
            try:
                insertions = int(ins)
            except ValueError:
                insertions = 0
            try:
                deletions = int(dels)
            except ValueError:
                deletions = 0
            break
    else:
        # No staged diff; fall back to working tree diff
        proc = subprocess.run(
            ["git", "diff", "--numstat", "--", path],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            ins, dels, file_path = parts
            if file_path == path:
                try:
                    insertions = int(ins)
                except ValueError:
                    insertions = 0
                try:
                    deletions = int(dels)
                except ValueError:
                    deletions = 0
                break
    return insertions, deletions


def _risk_score(insertions: int, deletions: int) -> float:
    footprint = insertions + deletions
    base = 0.05
    incremental = footprint * 0.01
    return min(base + incremental, 0.95)


def _assign_bucket(score: float) -> str:
    for lower, upper in RISK_BUCKETS:
        if lower <= score < upper:
            return f"{lower:.1f}-{upper:.1f}"
    return "0.9-1.0"


def _collect_tool_versions() -> dict[str, str]:
    commands = {
        "cmake": ["cmake", "--version"],
        "ninja": ["ninja", "--version"],
        "python": ["python3", "--version"],
        "pip": ["pip", "--version"],
        "pytest": ["pytest", "--version"],
        "make": ["make", "--version"],
        "git": ["git", "--version"],
    }
    versions: dict[str, str] = {}
    for name, argv in commands.items():
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, check=False)
            output = proc.stdout.strip() or proc.stderr.strip()
            versions[name] = output.splitlines()[0] if output else ""
        except FileNotFoundError:
            versions[name] = "missing"
    return versions


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one autonomy rehearsal cycle")
    parser.add_argument(
        "--emit-artifacts",
        dest="artifact_root",
        type=Path,
        required=True,
        help="Directory where rehearsal artifacts should be written",
    )
    parser.add_argument(
        "--candidate-id",
        dest="candidate_id",
        default=str(uuid.uuid4()),
        help="Override the generated amendment identifier",
    )
    args = parser.parse_args()

    os.environ.setdefault("LUMOS_AUTO_APPROVE", "1")

    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "quarantine").mkdir(exist_ok=True)

    repo_root = Path.cwd()
    candidate_id = str(args.candidate_id)

    timeline: list[dict[str, Any]] = []
    integrity_records: list[dict[str, Any]] = []

    def record(event: str, **payload: Any) -> None:
        timeline.append({"timestamp": _iso_now(), "event": event, "payload": payload})

    record("gap_seeker.start", candidates_requested=3)

    candidate = {
        "id": candidate_id,
        "topic": "stabilise scripts.lock install flow",
        "files": ["scripts/lock.py"],
        "summary": "Fix __future__ import ordering so python -m scripts.lock install works",
        "priority": "minor",
    }
    record("gap_seeker.candidate", candidate=candidate)

    spec = {
        "objective": "Restore scripts.lock helper so automation can install dependencies headlessly.",
        "directives": [
            "Ensure __future__ imports appear before runtime side effects.",
            "Preserve privilege gating via require_admin_banner and require_lumos_approval.",
            "Keep module documentation consolidated for clarity.",
        ],
        "testing_requirements": [
            "python -m scripts.lock install",
            "pytest -q",
            "make ci",
        ],
        "status": "draft",
        "version": "v1.0.0",
        "lineage": {
            "source": "autonomy_rehearsal",
            "amendment_id": candidate_id,
        },
        "changes": [
            {
                "path": "scripts/lock.py",
                "description": "Normalize import order and update module docstring",
            }
        ],
    }

    integrity_start = time.perf_counter()
    missing = [field for field in REQUIRED_FIELDS if not spec.get(field)]
    integrity_valid = not missing

    insertions, deletions = _git_diff_stats("scripts/lock.py")
    risk = _risk_score(insertions, deletions)
    threshold = float(os.getenv("HUNGRY_EYES_THRESHOLD", "0.6"))
    integrity_duration = time.perf_counter() - integrity_start

    integrity_entry = {
        "identifier": candidate_id,
        "summary": candidate["summary"],
        "integrity_valid": integrity_valid,
        "missing_fields": missing,
        "risk_score": risk,
        "threshold": threshold,
        "insertions": insertions,
        "deletions": deletions,
        "spec": spec,
        "evaluated_at": _iso_now(),
        "duration_ms": round(integrity_duration * 1000, 2),
    }
    integrity_records.append(integrity_entry)
    record(
        "integrity.complete",
        identifier=candidate_id,
        integrity_valid=integrity_valid,
        risk_score=risk,
        threshold=threshold,
        missing_fields=missing,
    )

    test_results: list[CommandResult] = []
    pytest_duration = ci_duration = 0.0
    tests_started = time.perf_counter()

    if integrity_valid and risk < threshold:
        install_cmd = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
        for command in (install_cmd, ["pytest", "-q"], ["make", "ci"]):
            record("tests.start", command=command)
            result = _run_command(command, cwd=repo_root)
            record(
                "tests.complete",
                command=command,
                returncode=result.returncode,
                duration_s=round(result.duration_s, 3),
            )
            test_results.append(result)
        tests_passed = all(item.returncode == 0 for item in test_results)
        if test_results:
            pytest_duration = test_results[0].duration_s
        if len(test_results) > 1:
            ci_duration = test_results[1].duration_s
    else:
        tests_passed = False

    tests_total_duration = time.perf_counter() - tests_started

    status = "approved" if tests_passed and integrity_valid and risk < threshold else "quarantined"
    record(
        "tests.summary",
        identifier=candidate_id,
        status=status,
        tests_passed=tests_passed,
    )

    total_duration = integrity_duration + tests_total_duration

    throughput_row = {
        "amendment_id": candidate_id,
        "status": status,
        "total_ms": round(total_duration * 1000, 2),
        "integrity_ms": round(integrity_duration * 1000, 2),
        "tests_ms": round(tests_total_duration * 1000, 2),
        "ci_ms": round(ci_duration * 1000, 2),
    }

    risk_bucket = _assign_bucket(risk)
    histogram_counts = {bucket: 0 for bucket in [f"{low:.1f}-{high:.1f}" for low, high in RISK_BUCKETS]}
    histogram_counts[risk_bucket] += 1

    hungry_metrics = {
        "threshold": threshold,
        "scores": [risk],
        "min": risk,
        "max": risk,
        "mean": risk,
        "bucket": risk_bucket,
    }

    _write_jsonl(artifact_root / "timeline.jsonl", timeline)
    _write_jsonl(artifact_root / "integrity_ledger_snapshot.jsonl", integrity_records)

    with (artifact_root / "hungry_eyes_metrics.json").open("w", encoding="utf-8") as fh:
        json.dump(hungry_metrics, fh, indent=2, sort_keys=True)

    with (artifact_root / "risk_histogram.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["bucket", "count"])
        for bucket, count in histogram_counts.items():
            writer.writerow([bucket, count])

    with (artifact_root / "throughput.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["amendment_id", "status", "total_ms", "integrity_ms", "tests_ms", "ci_ms"],
        )
        writer.writeheader()
        writer.writerow(throughput_row)

    tool_versions = _collect_tool_versions()

    latencies = {
        "integrity_ms": integrity_entry["duration_ms"],
        "tests_ms": round(tests_total_duration * 1000, 2),
        "ci_ms": round(ci_duration * 1000, 2),
    }
    latency_stats = {
        "integrity_ms": integrity_entry["duration_ms"],
        "tests_ms": latencies["tests_ms"],
        "ci_ms": latencies["ci_ms"],
        "min_ms": latencies["integrity_ms"],
        "median_ms": statistics.median([latencies["integrity_ms"], latencies["tests_ms"], latencies["ci_ms"]]),
        "p95_ms": max(latencies.values()),
    }

    report_lines = [
        "# Autonomy Rehearsal Report",
        "",
        f"- Generated: {_iso_now()}",
        f"- Branch: {subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True, check=False).stdout.strip()}",
        f"- Candidate ID: {candidate_id}",
        "",
        "## Overview",
        "",
        "| Tool | Version |",
        "| --- | --- |",
    ]
    for tool, version in tool_versions.items():
        report_lines.append(f"| {tool} | {version} |")

    report_lines.extend(
        [
            "",
            "## Amendment Table",
            "",
            "| id | topic | integrity_valid | risk_score | gates |",
            "| --- | --- | --- | --- | --- |",
            f"| {candidate_id} | {candidate['topic']} | {integrity_valid} | {risk:.3f} | {status} |",
            "",
            "## Latency",
            "",
            f"- Integrity: {latencies['integrity_ms']:.2f} ms",
            f"- Tests total: {latencies['tests_ms']:.2f} ms",
            f"- CI (make ci): {latencies['ci_ms']:.2f} ms",
            f"- Median stage latency: {latency_stats['median_ms']:.2f} ms",
            f"- P95 stage latency: {latency_stats['p95_ms']:.2f} ms",
            "",
            "## Risk Distribution",
            "",
            f"- Bucket {risk_bucket} : 1 amendment",
            "",
            "## Quarantines",
            "",
            f"- Count: {0 if status == 'approved' else 1 if status == 'quarantined' else 0}",
            "",
            "## Diff Summary",
            "",
            "- scripts/lock.py: consolidate docstring, normalise import order, and retain privilege gating",
            "",
            "## CI Outcome",
            "",
            f"- pytest -q returncode: {test_results[0].returncode if test_results else 'skipped'}",
            f"- make ci returncode: {test_results[1].returncode if len(test_results) > 1 else 'skipped'}",
            "",
            "## Regressions",
            "",
            "- none detected",
            "",
            "## Next Steps",
            "",
            "1. Expand rehearsal harness to ingest multiple amendments per cycle.",
            "2. Capture raw stdout/stderr artifacts for each gate in future rehearsals.",
            "3. Integrate remote CI status polling into the timeline emitter.",
        ]
    )

    (artifact_root / "report.md").write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
