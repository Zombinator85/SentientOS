"""CI baseline contract helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from sentientos.forge_failures import HarvestResult, harvest_failures

CI_BASELINE_PATH = Path("glow/contracts/ci_baseline.json")


@dataclass(slots=True)
class CiBaselineSnapshot:
    schema_version: int
    generated_at: str
    git_sha: str
    runner: str
    passed: bool
    failed_count: int
    top_clusters: list[dict[str, object]]
    last_green_sha: str | None


@dataclass(slots=True)
class CiBaselineDrift:
    drifted: bool
    drift_type: str
    drift_explanation: str
    failed_delta: int


def emit_ci_baseline(
    *,
    output_path: Path = CI_BASELINE_PATH,
    stdout: str | None = None,
    stderr: str | None = None,
    returncode: int | None = None,
    run_command: bool = True,
) -> CiBaselineSnapshot:
    resolved_stdout = stdout or ""
    resolved_stderr = stderr or ""
    resolved_returncode = returncode

    if run_command and resolved_returncode is None:
        completed = subprocess.run(
            ["python", "-m", "scripts.run_tests", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        resolved_stdout = completed.stdout or ""
        resolved_stderr = completed.stderr or ""
        resolved_returncode = completed.returncode

    harvest = harvest_failures(resolved_stdout, resolved_stderr)
    failed_count = _fallback_failed_count(harvest, f"{resolved_stdout}\n{resolved_stderr}")
    git_sha = _git_sha()
    snapshot = CiBaselineSnapshot(
        schema_version=1,
        generated_at=_iso_now(),
        git_sha=git_sha,
        runner="scripts.run_tests",
        passed=failed_count == 0 and (resolved_returncode == 0 if resolved_returncode is not None else True),
        failed_count=failed_count,
        top_clusters=_top_clusters(harvest),
        last_green_sha=git_sha if failed_count == 0 else _load_last_green_sha(output_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(snapshot), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot


def evaluate_ci_baseline_drift(
    baseline_payload: dict[str, Any] | None,
    *,
    previous_payload: dict[str, Any] | None = None,
    failure_threshold_delta: int = 0,
) -> CiBaselineDrift:
    if not baseline_payload:
        return CiBaselineDrift(
            drifted=True,
            drift_type="baseline_missing",
            drift_explanation="ci baseline artifact missing",
            failed_delta=0,
        )

    passed = bool(baseline_payload.get("passed", False))
    failed_count = _coerce_int(baseline_payload.get("failed_count"))
    previous_failed = _coerce_int(previous_payload.get("failed_count")) if isinstance(previous_payload, dict) else 0
    failed_delta = failed_count - previous_failed

    if not passed:
        return CiBaselineDrift(
            drifted=True,
            drift_type="tests_failing",
            drift_explanation=f"scripts.run_tests gate failing (failed_count={failed_count})",
            failed_delta=failed_delta,
        )

    if failed_delta > failure_threshold_delta:
        return CiBaselineDrift(
            drifted=True,
            drift_type="failed_count_regression",
            drift_explanation=f"failed_count regressed by {failed_delta} (threshold={failure_threshold_delta})",
            failed_delta=failed_delta,
        )

    return CiBaselineDrift(drifted=False, drift_type="none", drift_explanation="ci baseline clean", failed_delta=failed_delta)


def parse_summary_failed_count(output: str) -> int | None:
    patterns = [
        r"(?P<count>\d+)\s+failed",
        r"tests_failed=(?P<count>\d+)",
    ]
    for line in output.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return int(match.group("count"))
    return None


def _top_clusters(harvest: HarvestResult, *, limit: int = 5) -> list[dict[str, object]]:
    ranked = sorted(harvest.clusters, key=lambda cluster: cluster.count, reverse=True)
    payload: list[dict[str, object]] = []
    for cluster in ranked[:limit]:
        payload.append(
            {
                "signature": f"{cluster.signature.error_type}:{cluster.signature.message_digest}",
                "count": cluster.count,
                "nodeid": cluster.signature.nodeid,
            }
        )
    return payload


def _fallback_failed_count(harvest: HarvestResult, output: str) -> int:
    if harvest.total_failed:
        return harvest.total_failed
    parsed = parse_summary_failed_count(output)
    return parsed if parsed is not None else 0


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _load_last_green_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("last_green_sha")
    return value if isinstance(value, str) and value else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""
