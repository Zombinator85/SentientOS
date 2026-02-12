from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash
from scripts.read_test_provenance_bundle import read_bundle_runs

DEFAULT_RUN_DIR = Path("glow/test_runs")
DEFAULT_PROVENANCE_DIR = DEFAULT_RUN_DIR / "provenance"
DEFAULT_INPUT_FILE = DEFAULT_RUN_DIR / "test_run_provenance.json"
DEFAULT_OUTPUT_FILE = DEFAULT_RUN_DIR / "test_trend_report.json"
DEFAULT_BUNDLE_DIR = DEFAULT_RUN_DIR / "bundles"
DEFAULT_ARCHIVE_INDEX = DEFAULT_RUN_DIR / "archive_index.jsonl"


@dataclass(frozen=True)
class Thresholds:
    window_size: int
    skip_delta: float
    xfail_delta: float
    executed_drop: float
    passed_drop: float
    exceptional_cluster: int


def _float_arg(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _int_arg(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        return datetime.min
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if "run_intent" not in payload:
        return None
    return payload


def _default_input_dir() -> Path:
    if DEFAULT_PROVENANCE_DIR.exists():
        return DEFAULT_PROVENANCE_DIR
    return DEFAULT_RUN_DIR


def _discover_inputs(input_dir: Path, files: list[Path]) -> list[Path]:
    candidates: set[Path] = set(files)
    if input_dir.exists():
        candidates.update(
            path
            for path in input_dir.glob("*.json")
            if path.is_file() and path.name not in {"test_run_provenance.json", "latest.json"}
        )
    return sorted(candidates)


def _load_archive_index_entries(index_path: Path) -> list[dict[str, Any]]:
    if not index_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _discover_bundle_inputs(
    explicit_bundles: list[Path],
    *,
    bundle_dir: Path | None,
    use_archive_index: bool,
    archive_index: Path,
) -> tuple[list[Path], int]:
    candidates: set[Path] = set(explicit_bundles)
    if bundle_dir and bundle_dir.exists():
        candidates.update(path for path in bundle_dir.glob("*.tar.gz") if path.is_file())

    index_entries_used = 0
    if use_archive_index and archive_index.exists():
        entries = _load_archive_index_entries(archive_index)
        for entry in entries:
            bundle = entry.get("bundle_path")
            if isinstance(bundle, str) and bundle.strip():
                candidates.add(Path(bundle))
                index_entries_used += 1

    existing = sorted(path for path in candidates if path.exists() and path.is_file())
    return existing, index_entries_used


def _verify_contiguous_history(runs: list[dict[str, Any]]) -> tuple[bool, list[dict[str, str]], int]:
    ordered = _ordered_runs_for_analysis(runs)
    continuity_issues: list[dict[str, str]] = []
    discontinuity_count = 0

    for index in range(1, len(ordered)):
        prior = ordered[index - 1]
        current = ordered[index]
        prior_hash = prior.get("provenance_hash")
        prev_hash = current.get("prev_provenance_hash")
        if isinstance(prior_hash, str) and isinstance(prev_hash, str) and prev_hash == prior_hash:
            continue
        discontinuity_count += 1
        continuity_issues.append(
            {
                "prior_file": str(prior.get("_source", "<unknown>")),
                "current_file": str(current.get("_source", "<unknown>")),
                "issue": "history-gap",
            }
        )
    return (discontinuity_count == 0, continuity_issues, discontinuity_count)


def _safe_number(payload: dict[str, Any], key: str) -> float:
    raw = payload.get(key, 0)
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _extract_window_metrics(runs: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "skip_rate_mean": _mean([_safe_number(run, "skip_rate") for run in runs]),
        "xfail_rate_mean": _mean([_safe_number(run, "xfail_rate") for run in runs]),
        "tests_executed_mean": _mean([_safe_number(run, "tests_executed") for run in runs]),
        "tests_passed_mean": _mean([_safe_number(run, "tests_passed") for run in runs]),
    }


def _drop_fraction(prior: float, current: float) -> float:
    if prior <= 0:
        return 0.0
    return max(0.0, (prior - current) / prior)


def _ordered_runs_for_analysis(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        runs,
        key=lambda payload: (
            _parse_timestamp(payload.get("timestamp")),
            str(payload.get("_source", "")),
        ),
    )


def verify_chain(runs: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ordered_runs = _ordered_runs_for_analysis(runs)
    prior_hash: str | None = None

    for index, run in enumerate(ordered_runs):
        source = str(run.get("_source", "<unknown>"))
        hash_algo = run.get("hash_algo")
        prev_hash = run.get("prev_provenance_hash")
        actual_hash = run.get("provenance_hash")

        missing = [
            name
            for name, value in (
                ("hash_algo", hash_algo),
                ("prev_provenance_hash", prev_hash if "prev_provenance_hash" in run else "__missing__"),
                ("provenance_hash", actual_hash),
            )
            if value in (None, "__missing__") and name != "prev_provenance_hash"
        ]
        if "prev_provenance_hash" not in run:
            missing.append("prev_provenance_hash")
        if missing:
            issues.append({"file": source, "issue": f"missing-fields:{','.join(missing)}"})
            prior_hash = None
            continue

        if hash_algo != HASH_ALGO:
            issues.append({"file": source, "issue": "bad-hash-algo"})

        expected_prev = prior_hash if index > 0 else None
        if prev_hash != expected_prev:
            issues.append({"file": source, "issue": "prev-mismatch"})

        if not isinstance(actual_hash, str) or len(actual_hash) != 64:
            issues.append({"file": source, "issue": "missing-fields:provenance_hash"})
            prior_hash = None
            continue

        run_for_hash = dict(run)
        run_for_hash.pop("_source", None)
        expected_hash = compute_provenance_hash(run_for_hash, prev_hash if isinstance(prev_hash, str) else None)
        if actual_hash != expected_hash:
            issues.append({"file": source, "issue": "hash-mismatch"})

        prior_hash = actual_hash

    return {
        "integrity_checked": True,
        "integrity_ok": len(issues) == 0,
        "integrity_issues": issues,
    }


def analyze(
    runs: list[dict[str, Any]],
    thresholds: Thresholds,
    *,
    verify_chain_enabled: bool = False,
    source_stats: dict[str, int] | None = None,
    require_contiguous_history: bool = False,
) -> dict[str, Any]:
    ordered_runs = _ordered_runs_for_analysis(runs)
    latest_runs = ordered_runs[-thresholds.window_size :]
    prior_runs = ordered_runs[-(2 * thresholds.window_size) : -thresholds.window_size]

    current = _extract_window_metrics(latest_runs)
    prior = _extract_window_metrics(prior_runs)

    intents = Counter(str(run.get("run_intent", "unknown")) for run in latest_runs)
    exceptional_count = sum(1 for run in latest_runs if run.get("run_intent") == "exceptional")

    allow_flags_used = {
        "budget_allow_violation": sum(1 for run in latest_runs if bool(run.get("budget_allow_violation"))),
        "allow_nonexecution": sum(1 for run in latest_runs if bool(run.get("allow_nonexecution"))),
        "bypass_env": sum(1 for run in latest_runs if bool(run.get("bypass_env"))),
    }

    reasons: list[str] = []

    if prior_runs and (current["skip_rate_mean"] - prior["skip_rate_mean"]) >= thresholds.skip_delta:
        reasons.append("skip_rate_spike")
    if prior_runs and (current["xfail_rate_mean"] - prior["xfail_rate_mean"]) >= thresholds.xfail_delta:
        reasons.append("xfail_rate_spike")

    executed_drop = _drop_fraction(prior["tests_executed_mean"], current["tests_executed_mean"])
    passed_drop = _drop_fraction(prior["tests_passed_mean"], current["tests_passed_mean"])
    if prior_runs and executed_drop >= thresholds.executed_drop:
        reasons.append("tests_executed_collapse")
    if prior_runs and passed_drop >= thresholds.passed_drop:
        reasons.append("tests_passed_collapse")

    if exceptional_count >= thresholds.exceptional_cluster:
        reasons.append("exceptional_cluster")
    if allow_flags_used["budget_allow_violation"] > 0:
        reasons.append("budget_allow_violation_seen")

    unique_reasons = sorted(set(reasons))
    avoidance_alert = bool(unique_reasons)
    total_checks = 6
    avoidance_score = round(len(unique_reasons) / total_checks, 3)

    report: dict[str, Any] = {
        "schema_version": 1,
        "window_size": thresholds.window_size,
        "runs_analyzed": len(latest_runs),
        "avoidance_alert": avoidance_alert,
        "avoidance_score": avoidance_score,
        "avoidance_reasons": unique_reasons,
        "metrics": {
            **current,
            "exceptional_count": exceptional_count,
            "run_intent_distribution": dict(sorted(intents.items())),
            "allow_flags_used": allow_flags_used,
            "prior_skip_rate_mean": prior["skip_rate_mean"],
            "prior_xfail_rate_mean": prior["xfail_rate_mean"],
            "prior_tests_executed_mean": prior["tests_executed_mean"],
            "prior_tests_passed_mean": prior["tests_passed_mean"],
        },
    }

    deduplicated_runs_total = len(ordered_runs)
    report["sources"] = source_stats or {"live_dir_count": 0, "bundles_count": 0, "index_entries_used": 0}
    report["deduplicated_runs_total"] = deduplicated_runs_total

    if verify_chain_enabled:
        report.update(verify_chain(ordered_runs))
        contiguous_ok, continuity_issues, discontinuity_count = _verify_contiguous_history(ordered_runs)
        report["continuity_checked"] = True
        report["continuity_ok"] = contiguous_ok
        report["continuity_issues"] = continuity_issues
        report["continuity_discontinuity_count"] = discontinuity_count
        if require_contiguous_history and not contiguous_ok:
            report["integrity_ok"] = False
            report["integrity_issues"] = list(report.get("integrity_issues", [])) + continuity_issues
    else:
        report.update(
            {
                "integrity_checked": False,
                "integrity_ok": True,
                "integrity_issues": [],
                "continuity_checked": False,
                "continuity_ok": True,
                "continuity_issues": [],
                "continuity_discontinuity_count": 0,
            }
        )

    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(report, indent=2, sort_keys=True)}\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> str:
    status = "ALERT" if report["avoidance_alert"] else "OK"
    reasons = ", ".join(report["avoidance_reasons"]) if report["avoidance_reasons"] else "none"
    integrity = "OK" if report.get("integrity_ok", True) else "BROKEN"
    return (
        f"Trend analysis [{status}] runs={report['runs_analyzed']} "
        f"window={report['window_size']} score={report['avoidance_score']:.3f} reasons={reasons} "
        f"integrity={integrity}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze test provenance trends for avoidance spikes.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=_default_input_dir(),
        help="Directory containing provenance JSON files.",
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help="Specific provenance JSON file(s) to include. Can be provided multiple times.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE, help="Path to write trend report JSON.")
    parser.add_argument("--window-size", type=_int_arg, default=int(os.getenv("SENTIENTOS_PROVENANCE_WINDOW_SIZE", "20")))
    parser.add_argument("--skip-delta", type=_float_arg, default=float(os.getenv("SENTIENTOS_PROVENANCE_SKIP_DELTA", "0.15")))
    parser.add_argument("--xfail-delta", type=_float_arg, default=float(os.getenv("SENTIENTOS_PROVENANCE_XFAIL_DELTA", "0.10")))
    parser.add_argument(
        "--executed-drop",
        type=_float_arg,
        default=float(os.getenv("SENTIENTOS_PROVENANCE_EXECUTED_DROP", "0.50")),
        help="Relative drop threshold for executed tests (0.50 means 50%% drop).",
    )
    parser.add_argument(
        "--passed-drop",
        type=_float_arg,
        default=float(os.getenv("SENTIENTOS_PROVENANCE_PASSED_DROP", "0.50")),
        help="Relative drop threshold for passed tests (0.50 means 50%% drop).",
    )
    parser.add_argument(
        "--exceptional-cluster",
        type=_int_arg,
        default=int(os.getenv("SENTIENTOS_PROVENANCE_EXCEPTIONAL_CLUSTER", "3")),
    )
    parser.add_argument(
        "--verify-chain",
        action="store_true",
        default=os.getenv("SENTIENTOS_PROVENANCE_VERIFY_CHAIN") == "1",
        help="Verify SHA-256 hash chain across provenance snapshots.",
    )
    parser.add_argument(
        "--bundle",
        action="append",
        type=Path,
        default=[],
        help="Path to provenance bundle archive (tar.gz). Can be provided multiple times.",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help="Directory containing provenance bundles for optional ingestion.",
    )
    parser.add_argument(
        "--archive-index",
        type=Path,
        default=DEFAULT_ARCHIVE_INDEX,
        help="Append-only archive index file used for bundle discovery.",
    )
    parser.add_argument(
        "--use-archive-index",
        dest="use_archive_index",
        action="store_true",
        help="Enable bundle discovery from archive index.",
    )
    parser.add_argument(
        "--no-use-archive-index",
        dest="use_archive_index",
        action="store_false",
        help="Disable bundle discovery from archive index.",
    )
    parser.set_defaults(use_archive_index=DEFAULT_ARCHIVE_INDEX.exists())
    parser.add_argument(
        "--require-contiguous-history",
        action="store_true",
        default=False,
        help="Fail integrity when adjacent runs across all sources do not form a contiguous prev-hash chain.",
    )
    parser.add_argument(
        "--fail-on-alert",
        action="store_true",
        default=os.getenv("SENTIENTOS_CI_FAIL_ON_AVOIDANCE_ALERT") == "1",
        help="Return non-zero when an avoidance alert is emitted.",
    )
    parser.add_argument(
        "--fail-on-integrity-alert",
        action="store_true",
        default=os.getenv("SENTIENTOS_CI_FAIL_ON_INTEGRITY_ALERT") == "1",
        help="Return non-zero when provenance integrity verification fails.",
    )
    args = parser.parse_args(argv)

    input_files = list(args.file)
    discovered = _discover_inputs(args.dir, input_files)
    loaded_runs: list[dict[str, Any]] = []
    for path in discovered:
        payload = _load_json(path)
        if payload is None:
            continue
        payload["_source"] = str(path)
        loaded_runs.append(payload)

    bundle_paths, index_entries_used = _discover_bundle_inputs(
        args.bundle,
        bundle_dir=args.bundle_dir,
        use_archive_index=args.use_archive_index,
        archive_index=args.archive_index,
    )
    bundle_run_count = 0
    for bundle_path in bundle_paths:
        bundle_result = read_bundle_runs(bundle_path)
        bundle_run_count += len(bundle_result.runs)
        loaded_runs.extend(bundle_result.runs)

    deduped_by_hash: dict[str, dict[str, Any]] = {}
    passthrough_runs: list[dict[str, Any]] = []
    for run in loaded_runs:
        run_hash = run.get("provenance_hash")
        if isinstance(run_hash, str) and run_hash:
            if run_hash in deduped_by_hash:
                continue
            deduped_by_hash[run_hash] = run
        else:
            passthrough_runs.append(run)
    loaded_runs = list(deduped_by_hash.values()) + passthrough_runs

    report = analyze(
        loaded_runs,
        Thresholds(
            window_size=args.window_size,
            skip_delta=args.skip_delta,
            xfail_delta=args.xfail_delta,
            executed_drop=args.executed_drop,
            passed_drop=args.passed_drop,
            exceptional_cluster=args.exceptional_cluster,
        ),
        verify_chain_enabled=args.verify_chain,
        source_stats={
            "live_dir_count": len(discovered),
            "bundles_count": len(bundle_paths),
            "index_entries_used": index_entries_used,
        },
        require_contiguous_history=args.require_contiguous_history,
    )
    _write_report(args.output, report)
    print(_summary(report))

    if report["avoidance_alert"] and args.fail_on_alert:
        print("Avoidance alert emitted and fail-on-alert is enabled.")
        return 1
    if report.get("integrity_checked") and not report.get("integrity_ok", True) and args.fail_on_integrity_alert:
        print("Integrity alert emitted and fail-on-integrity-alert is enabled.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
