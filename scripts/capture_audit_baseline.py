from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts import converge_audits, verify_audits

__version__ = "1"
SCHEMA_VERSION = 1
DEFAULT_TARGET = Path("logs")
DEFAULT_OUTPUT = Path("glow/audits/baseline/audit_baseline.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded(value: object) -> str:
    return str(value)[: verify_audits.MAX_ISSUE_LENGTH]


def _iter_audited_files(target: Path) -> list[Path]:
    return sorted(path for path in target.iterdir() if verify_audits._is_log_file(path))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(target: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _iter_audited_files(target):
        items.append(
            {
                "path": path.as_posix(),
                "size": path.stat().st_size,
                "hash": _file_sha256(path),
            }
        )
    return items


def _manifest_fingerprint(manifest: list[dict[str, Any]]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _issues_by_code(issues_by_path: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(issues_by_path):
        for issue in issues_by_path[path]:
            code = str(issue.get("code", "unknown"))
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _issue_tuples(issues_by_path: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    flattened: list[dict[str, str]] = []
    for path in sorted(issues_by_path):
        for issue in issues_by_path[path]:
            flattened.append(
                {
                    "code": _bounded(issue.get("code", "unknown")),
                    "path": _bounded(issue.get("path", path)),
                    "expected": _bounded(issue.get("expected", "")),
                    "actual": _bounded(issue.get("actual", "")),
                }
            )
    return sorted(flattened, key=lambda i: (i["code"], i["path"], i["expected"], i["actual"]))


def _captured_by_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _tool_version() -> str:
    version = str(globals().get("__version__", "")).strip()
    if version:
        return version
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def capture_baseline(*, target: Path, output: Path, accept_manual: bool) -> dict[str, Any]:
    issues_by_path, _, _ = verify_audits.verify_audits_detailed(directory=target, quarantine=True, repair=False)
    convergence_report = converge_audits.run_convergence(target=target, max_iterations=1, apply_repairs=False)
    manual_required = list(convergence_report.get("remaining_manual_issues", []))

    ok = all(not issues for issues in issues_by_path.values())
    if not ok:
        if not accept_manual:
            raise SystemExit("Refusing to capture baseline: audits are unclean. Pass --accept-manual to record explicit acceptance.")
        if not manual_required:
            raise SystemExit("Refusing to capture baseline: audits are unclean but no manual-required issues were identified.")

    captured_at = _iso_now()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": captured_at,
        "captured_at": captured_at,
        "captured_by": _captured_by_commit(),
        "tool_version": _tool_version(),
        "target": f"{target.as_posix().rstrip('/')}/",
        "ok": ok,
        "manual_issues_accepted": bool(accept_manual and not ok),
        "issues_by_code": _issues_by_code(issues_by_path),
        "baseline_fingerprint": "",
        "manifest": _manifest(target),
        "issue_tuples": _issue_tuples(issues_by_path),
        "manual_issues": manual_required,
    }
    payload["baseline_fingerprint"] = _manifest_fingerprint(payload["manifest"])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture deterministic audit baseline snapshot")
    parser.add_argument("target_dir", nargs="?", default=str(DEFAULT_TARGET), help="audit log directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="baseline output path")
    parser.add_argument("--accept-manual", action="store_true", help="allow capture for explicit manual-required issues")
    args = parser.parse_args(argv)

    payload = capture_baseline(target=Path(args.target_dir), output=Path(args.output), accept_manual=args.accept_manual)
    print(json.dumps({"tool": "capture_audit_baseline", "ok": payload["ok"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
