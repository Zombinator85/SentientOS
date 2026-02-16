from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_test_provenance import _discover_inputs, _load_json, _parse_timestamp, verify_chain
from scripts.verify_pressure_state_chain import verify_pressure_state_chain

DEFAULT_TEST_RUN_DIR = Path("glow/test_runs")
DEFAULT_ROUTING_DIR = Path("glow/routing")
DEFAULT_REPORT_DIR = Path("glow/reports")
DEFAULT_AMENDMENT_LOG = Path("integration/amendment_log.jsonl")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _git_sha(repo_root: Path) -> str:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha[:12]
    head_path = repo_root / ".git" / "HEAD"
    try:
        head_contents = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if head_contents.startswith("ref:"):
        ref_path = repo_root / ".git" / head_contents.split(" ", 1)[1]
        try:
            return ref_path.read_text(encoding="utf-8").strip()[:12]
        except OSError:
            return "unknown"
    return head_contents[:12] or "unknown"


def _discover_latest(paths: list[Path], *, timestamp_getter: Any) -> Path | None:
    existing = [path for path in paths if path.exists() and path.is_file()]
    if not existing:
        return None
    return sorted(existing, key=lambda p: (timestamp_getter(p), p.name))[-1]


def _discover_latest_json(
    candidates: list[Path],
    *,
    timestamp_field: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    existing: list[tuple[Path, dict[str, Any]]] = []
    for path in candidates:
        payload = _read_json(path)
        if payload is None:
            continue
        existing.append((path, payload))
    if not existing:
        return (None, None)
    ordered = sorted(existing, key=lambda item: (_parse_timestamp(item[1].get(timestamp_field)), item[0].name))
    return ordered[-1]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _event_timestamp(event: dict[str, Any]) -> datetime:
    return _parse_timestamp(event.get("timestamp"))


def _discover_bundle_paths(test_run_dir: Path, archive_index_path: Path) -> list[str]:
    bundles_dir = test_run_dir / "bundles"
    candidates: set[str] = set()
    if bundles_dir.exists():
        for path in bundles_dir.glob("*.tar.gz"):
            if path.is_file():
                candidates.add(str(path))
    if archive_index_path.exists():
        for entry in _load_jsonl(archive_index_path):
            bundle_path = entry.get("bundle_path")
            if isinstance(bundle_path, str) and bundle_path:
                candidates.add(bundle_path)
    return sorted(candidates)


def _summarize_failure_digest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = _read_json(path)
    if payload is None:
        return None
    groups = payload.get("failure_groups")
    if not isinstance(groups, list):
        return {"group_count": 0, "top_groups": []}
    top_groups = []
    for group in groups[:3]:
        if not isinstance(group, dict):
            continue
        top_groups.append(
            {
                "count": int(group.get("count", 0)),
                "exception_type": group.get("exception_type"),
                "example_nodeid": group.get("example_nodeid"),
                "short_message": group.get("short_message"),
            }
        )
    return {"group_count": len(groups), "top_groups": top_groups}


def build_forensic_report(
    *,
    repo_root: Path,
    test_run_dir: Path = DEFAULT_TEST_RUN_DIR,
    routing_dir: Path = DEFAULT_ROUTING_DIR,
    amendment_log_path: Path = DEFAULT_AMENDMENT_LOG,
) -> dict[str, Any]:
    provenance_pointer = test_run_dir / "test_run_provenance.json"
    trend_report = test_run_dir / "test_trend_report.json"
    router_report = test_run_dir / "router_telemetry_report.json"
    failure_digest = test_run_dir / "test_failure_digest.json"
    archive_index = test_run_dir / "archive_index.jsonl"

    provenance_payload = _read_json(provenance_pointer)

    provenance_integrity_ok = None
    provenance_integrity_checked = False
    provenance_integrity_error: str | None = None

    try:
        provenance_inputs = _discover_inputs(test_run_dir / "provenance", [])
        runs: list[dict[str, Any]] = []
        for path in provenance_inputs:
            payload = _load_json(path)
            if payload is None:
                continue
            payload["_source"] = str(path)
            runs.append(payload)
        if runs:
            verification = verify_chain(runs)
            provenance_integrity_ok = bool(verification.get("integrity_ok", False))
            provenance_integrity_checked = True
        else:
            provenance_integrity_ok = None
    except Exception as exc:  # pragma: no cover - fail-open safety
        provenance_integrity_checked = False
        provenance_integrity_ok = None
        provenance_integrity_error = str(exc)

    pressure_state_dir = routing_dir / "pressure_state"
    pressure_latest = pressure_state_dir / "latest.json"
    pressure_latest_payload = _read_json(pressure_latest)

    pressure_chain_checked = False
    pressure_chain_ok = None
    pressure_chain_issues: list[str] = []
    pressure_chain_error: str | None = None
    try:
        pressure_verification = verify_pressure_state_chain(pressure_state_dir, events_path=amendment_log_path)
        pressure_chain_checked = True
        pressure_chain_ok = bool(pressure_verification.get("integrity_ok", False))
        issues = pressure_verification.get("issues", [])
        if isinstance(issues, list):
            pressure_chain_issues = [str(item) for item in issues]
    except Exception as exc:  # pragma: no cover - fail-open safety
        pressure_chain_checked = False
        pressure_chain_ok = None
        pressure_chain_error = str(exc)

    events = _load_jsonl(amendment_log_path)
    routing_events: list[dict[str, Any]] = []
    governor_events: list[dict[str, Any]] = []
    for event in events:
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        event_type = metadata.get("event_type")
        if event_type == "proof_budget":
            routing_events.append(event)
        if event_type == "proof_budget_governor":
            governor_events.append(event)

    ordered_routing = sorted(routing_events, key=lambda event: (_event_timestamp(event), str(event.get("proposal_id", ""))))
    ordered_governor = sorted(governor_events, key=lambda event: (_event_timestamp(event), str(event.get("proposal_id", ""))))

    proof_spends: list[float] = []
    for event in ordered_routing:
        metadata = event.get("metadata")
        telemetry = metadata.get("router_telemetry") if isinstance(metadata, dict) else None
        if isinstance(telemetry, dict):
            value = telemetry.get("stage_b_evaluations")
            if isinstance(value, (int, float)):
                proof_spends.append(float(value))

    latest_router_telemetry = None
    if ordered_routing:
        metadata = ordered_routing[-1].get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("router_telemetry"), dict):
            latest_router_telemetry = metadata.get("router_telemetry")

    latest_governor_decision = None
    if ordered_governor:
        metadata = ordered_governor[-1].get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("governor"), dict):
            latest_governor_decision = {
                "timestamp": ordered_governor[-1].get("timestamp"),
                "pipeline": metadata.get("pipeline"),
                "capability": metadata.get("capability"),
                "router_attempt": metadata.get("router_attempt"),
                "governor": metadata.get("governor"),
            }

    router_alerts: list[str] = []
    router_payload = _read_json(router_report)
    if isinstance(router_payload, dict):
        reasons = router_payload.get("avoidance_reasons")
        if isinstance(reasons, list):
            router_alerts.extend(str(reason) for reason in reasons)

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "repo": {
            "git_sha": _git_sha(repo_root),
            "repo_root": str(repo_root),
        },
        "test": {
            "provenance_path": str(provenance_pointer) if provenance_pointer.exists() else None,
            "integrity_ok": provenance_integrity_ok,
            "integrity_checked": provenance_integrity_checked,
            "integrity_error": provenance_integrity_error,
            "run_intent": provenance_payload.get("run_intent") if provenance_payload else None,
            "execution_mode": provenance_payload.get("execution_mode") if provenance_payload else None,
            "tests_executed": provenance_payload.get("tests_executed") if provenance_payload else None,
            "budgets": {
                "allow_violation": provenance_payload.get("budget_allow_violation") if provenance_payload else None,
                "thresholds": provenance_payload.get("budget_thresholds") if provenance_payload else None,
                "violations": provenance_payload.get("budget_violations") if provenance_payload else None,
            },
            "failure_digest_path": str(failure_digest) if failure_digest.exists() else None,
            "failure_summary": _summarize_failure_digest(failure_digest if failure_digest.exists() else None),
        },
        "routing": {
            "events_found": len(ordered_routing),
            "proof_spend_mean": (sum(proof_spends) / len(proof_spends)) if proof_spends else None,
            "latest_router_telemetry": latest_router_telemetry,
            "alerts": sorted(set(router_alerts)),
        },
        "governor": {
            "events_found": len(ordered_governor),
            "latest_decision": latest_governor_decision,
            "pressure_state": {
                "latest_path": str(pressure_latest) if pressure_latest.exists() else None,
                "latest_hash": pressure_latest_payload.get("state_hash") if pressure_latest_payload else None,
                "chain_integrity_checked": pressure_chain_checked,
                "chain_integrity_ok": pressure_chain_ok,
                "issues": pressure_chain_issues,
                "chain_error": pressure_chain_error,
            },
        },
        "artifacts": {
            "trend_report_path": str(trend_report) if trend_report.exists() else None,
            "router_telemetry_report_path": str(router_report) if router_report.exists() else None,
            "bundle_paths": _discover_bundle_paths(test_run_dir, archive_index),
            "archive_index_path": str(archive_index) if archive_index.exists() else None,
        },
    }
    return report


def write_report(
    report: dict[str, Any],
    *,
    output_dir: Path,
    git_sha: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = str(report.get("generated_at", ""))
    stamp = generated_at.replace(":", "").replace("-", "")[:15]
    target = output_dir / f"forensic_report_{stamp}_{git_sha}.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _integrity_failed(report: dict[str, Any]) -> bool:
    test_section = report.get("test", {}) if isinstance(report.get("test"), dict) else {}
    governor_section = report.get("governor", {}) if isinstance(report.get("governor"), dict) else {}
    pressure_state = governor_section.get("pressure_state", {}) if isinstance(governor_section.get("pressure_state"), dict) else {}

    test_checked = bool(test_section.get("integrity_checked"))
    test_ok = test_section.get("integrity_ok")
    pressure_checked = bool(pressure_state.get("chain_integrity_checked"))
    pressure_ok = pressure_state.get("chain_integrity_ok")

    return (test_checked and test_ok is False) or (pressure_checked and pressure_ok is False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate unified forensic run report JSON.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--test-run-dir", type=Path, default=DEFAULT_TEST_RUN_DIR)
    parser.add_argument("--routing-dir", type=Path, default=DEFAULT_ROUTING_DIR)
    parser.add_argument("--amendment-log", type=Path, default=Path(os.getenv("SENTIENTOS_AMENDMENT_LOG_PATH", str(DEFAULT_AMENDMENT_LOG))))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--fail-on-integrity", action="store_true")
    args = parser.parse_args(argv)

    report = build_forensic_report(
        repo_root=args.repo_root,
        test_run_dir=args.test_run_dir,
        routing_dir=args.routing_dir,
        amendment_log_path=args.amendment_log,
    )
    git_sha = _git_sha(args.repo_root)
    report_path = write_report(report, output_dir=args.output_dir, git_sha=git_sha)
    print(json.dumps({"report_path": str(report_path)}, sort_keys=True))

    if args.fail_on_integrity and _integrity_failed(report):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
