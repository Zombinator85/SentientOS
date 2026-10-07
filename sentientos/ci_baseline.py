"""CI baseline contract helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any, cast

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
    failure_signatures: list[dict[str, object]]
    failure_signatures_complete: bool
    repository_health_status: str
    last_green_sha: str | None


@dataclass(slots=True)
class CiBaselineDrift:
    drifted: bool
    drift_type: str
    drift_explanation: str
    failed_delta: int
    repository_health_status: str = "unknown"
    task_regression_status: str = "comparison_incomplete"
    matched_preexisting_failures: list[dict[str, object]] | None = None
    new_failures: list[dict[str, object]] | None = None
    retired_failures: list[dict[str, object]] | None = None


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
        failure_signatures=[
            {
                "signature": cluster.signature.semantic_signature,
                "nodeid": cluster.signature.nodeid,
                "exception_type": cluster.signature.error_type,
                "message_digest": cluster.signature.message_digest,
                "count": cluster.count,
            }
            for cluster in sorted(harvest.clusters, key=lambda item: item.signature.semantic_signature)
        ],
        failure_signatures_complete=(
            failed_count == sum(cluster.count for cluster in harvest.clusters)
            and (resolved_returncode in (None, 0, 1))
        ),
        repository_health_status="green" if failed_count == 0 and resolved_returncode in (None, 0) else "red",
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
    health = str(baseline_payload.get("repository_health_status") or ("green" if passed else "red"))
    current = _signature_counts(baseline_payload.get("failure_signatures"))
    if current is None and failed_count == 0:
        current = {}
    previous_count = _coerce_int(previous_payload.get("failed_count")) if isinstance(previous_payload, dict) else 0
    previous = _signature_counts(previous_payload.get("failure_signatures")) if isinstance(previous_payload, dict) else None
    if previous is None and previous_count == 0:
        previous = {}
    if (
        current is None
        or (failed_count > 0 and baseline_payload.get("failure_signatures_complete") is not True)
        or (previous_payload is not None and previous is None)
        or (previous_payload is not None and previous_count > 0 and previous_payload.get("failure_signatures_complete") is not True)
    ):
        return CiBaselineDrift(
            drifted=True,
            drift_type="comparison_incomplete",
            drift_explanation="signature-aware failure evidence is missing or invalid",
            failed_delta=failed_delta,
            repository_health_status=health,
            task_regression_status="comparison_incomplete",
        )
    if previous is None:
        return CiBaselineDrift(
            drifted=failed_count > 0,
            drift_type="baseline_missing" if failed_count > 0 else "none",
            drift_explanation="no prior signature baseline is available",
            failed_delta=failed_delta,
            repository_health_status=health,
            task_regression_status="comparison_incomplete" if failed_count > 0 else "no_regression",
        )
    matched, new, retired = _compare_signature_counts(previous, current)
    if new:
        return CiBaselineDrift(True, "failure_signature_regression", "new or increased semantic failure signatures", failed_delta, health, "regression_detected", matched, new, retired)
    if retired:
        return CiBaselineDrift(False, "failure_signatures_improved", "semantic failure debt retired or reduced", failed_delta, health, "improved", matched, new, retired)
    if current:
        return CiBaselineDrift(False, "matched_preexisting_debt", "all current semantic failures match the prior signature multiset", failed_delta, health, "no_regression", matched, new, retired)
    return CiBaselineDrift(False, "none", "ci baseline clean", failed_delta, health, "no_regression", matched, new, retired)


def _signature_counts(value: object) -> dict[str, dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    result: dict[str, dict[str, object]] = {}
    for row in value:
        if not isinstance(row, dict):
            return None
        signature, nodeid, count = row.get("signature"), row.get("nodeid"), row.get("count")
        if not isinstance(signature, str) or not signature or not isinstance(nodeid, str) or not isinstance(count, int) or isinstance(count, bool) or count < 1 or signature in result:
            return None
        result[signature] = {"signature": signature, "nodeid": nodeid, "count": count}
    return result


def _compare_signature_counts(
    previous: dict[str, dict[str, object]], current: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    matched: list[dict[str, object]] = []
    new: list[dict[str, object]] = []
    retired: list[dict[str, object]] = []
    for signature in sorted(set(previous) | set(current)):
        before, after = previous.get(signature), current.get(signature)
        if before and after:
            before_count = cast(int, before["count"])
            after_count = cast(int, after["count"])
            common = min(before_count, after_count)
            matched.append({"signature": signature, "nodeid": after["nodeid"], "count": common})
            delta = after_count - before_count
            if delta > 0:
                new.append({"signature": signature, "nodeid": after["nodeid"], "count": delta})
            elif delta < 0:
                retired.append({"signature": signature, "nodeid": before["nodeid"], "count": -delta})
        elif after:
            new.append(dict(after))
        elif before:
            retired.append(dict(before))
    return matched, new, retired


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
                "semantic_signature": cluster.signature.semantic_signature,
                "count": cluster.count,
                "nodeid": cluster.signature.nodeid,
            }
        )
    return payload


def _fallback_failed_count(harvest: HarvestResult, output: str) -> int:
    if harvest.total_failed:
        return int(harvest.total_failed)
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
