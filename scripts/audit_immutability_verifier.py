#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_|\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/

from __future__ import annotations

"""Sanctuary Privilege Routine: Do not remove. See doctrine for details."""

import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from logging_config import get_log_path
from scripts import tooling_status
from sentientos import immutability

DEFAULT_MANIFEST = immutability.DEFAULT_MANIFEST_PATH
LEDGER_PATH = get_log_path("audit_immutability.jsonl")
RESULT_PATH = Path("glow/audits/audit_immutability_result.json")
SCHEMA_VERSION = "1.0"
MAX_ISSUES = 20
MAX_ISSUE_LENGTH = 200
PRIVILEGED_PATHS = [
    Path("NEWLEGACY.txt"),
    Path("vow/init.py"),
    Path("vow/config.yaml"),
    Path("init.py"),
    Path("privilege.py"),
]


@dataclass
class AuditCheckOutcome:
    status: str
    reason: str | None = None
    recorded_events: list[dict] | None = None

    def __bool__(self) -> bool:
        return self.status in {"passed", "skipped"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bounded_issues(issues: list[str]) -> list[str]:
    return [issue[:MAX_ISSUE_LENGTH] for issue in issues[:MAX_ISSUES]]


def write_result(*, ok: bool, issues: list[str], error: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _iso_now(),
        "tool": "audit_immutability_verifier",
        "ok": ok,
        "issues": _bounded_issues(issues),
        "error": error,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def log_event(entry: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def load_manifest(manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    return immutability.read_manifest(manifest_path)


def verify_once(
    manifest_path: Path = DEFAULT_MANIFEST,
    allow_missing_manifest: bool = False,
    logger: Callable[[dict], None] = log_event,
) -> AuditCheckOutcome:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    recorded: list[dict] = []

    def _record(entry: dict) -> None:
        recorded.append(entry)
        logger(entry)

    try:
        manifest = load_manifest(manifest_path)
    except FileNotFoundError:
        if not allow_missing_manifest:
            failure = {
                "event": "immutability_check",
                "status": "failed",
                "reason": "manifest_missing",
                "ts": ts,
                "manifest": str(manifest_path),
            }
            _record(failure)
            return AuditCheckOutcome("failed", reason="manifest_missing", recorded_events=recorded)
        warning = {
            "event": "immutability_check",
            "status": "skipped",
            "reason": "manifest_missing_allowed",
            "ts": ts,
            "manifest": str(manifest_path),
        }
        _record(warning)
        return AuditCheckOutcome("skipped", reason="manifest_missing_allowed", recorded_events=recorded)
    except Exception as exc:
        error_event = {
            "event": "immutability_check",
            "status": "error",
            "reason": str(exc),
            "ts": ts,
            "manifest": str(manifest_path),
        }
        _record(error_event)
        return AuditCheckOutcome("error", reason=str(exc), recorded_events=recorded)

    ok = True
    for file, info in manifest["files"].items():
        path = Path(file)
        status = "tampered"
        if path.exists() and _hash_file(path) == info.get("sha256"):
            status = "verified"
        else:
            ok = False
            _record({"event": "tamper_detected", "file": file, "ts": ts})
        _record({"event": "immutability_check", "file": file, "status": status, "ts": ts})
    outcome = "passed" if ok else "failed"
    reason = None if ok else "tamper_detected"
    return AuditCheckOutcome(outcome, reason=reason, recorded_events=recorded)




def _forge_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_preflight_docket(*, status: str, reason: str, manifest_path: Path, ensure_output: dict[str, object] | None = None) -> Path:
    docket = {
        "kind": "audit_docket",
        "tool": "audit_immutability_verifier",
        "status": status,
        "reason": reason,
        "manifest_path": str(manifest_path),
        "ensure_output": ensure_output,
        "generated_at": _iso_now(),
    }
    docket_path = Path("glow/forge") / f"audit_docket_{_forge_timestamp()}.json"
    docket_path.parent.mkdir(parents=True, exist_ok=True)
    docket_path.write_text(json.dumps(docket, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return docket_path


def _ensure_manifest_if_missing(manifest_path: Path) -> tuple[bool, dict[str, object] | None]:
    if manifest_path.exists():
        return True, None
    try:
        from sentientos import vow_artifacts

        payload = vow_artifacts.ensure_vow_artifacts(manifest_path=manifest_path)
    except Exception as exc:  # pragma: no cover - defensive
        _write_preflight_docket(status="failed", reason=f"ensure_failed:{exc}", manifest_path=manifest_path)
        return False, None

    if not manifest_path.exists():
        _write_preflight_docket(
            status="failed",
            reason="ensure_failed:manifest_missing_after_ensure",
            manifest_path=manifest_path,
            ensure_output=payload,
        )
        return False, payload

    return True, payload
def run_loop(
    stop: threading.Event,
    logger: Callable[[dict], None] = log_event,
    interval: int = 3600,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> None:
    while not stop.is_set():
        verify_once(manifest_path=manifest_path, logger=logger)
        if stop.wait(interval):
            break


def update_manifest(
    files: Iterable[str | Path] = PRIVILEGED_PATHS,
    manifest_path: Path = DEFAULT_MANIFEST,
    env_var: str = "LUMOS_VEIL_CONFIRM",
) -> None:
    if os.getenv(env_var) != "1":
        raise PermissionError("veil/confirm required")
    normalized = [str(Path(p)) for p in files]
    immutability.update_manifest(normalized, manifest_path=manifest_path)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify immutable manifest file hashes")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="manifest path")
    parser.add_argument(
        "--allow-missing-manifest",
        action="store_true",
        help="allow degraded environments to skip when the manifest is unavailable",
    )
    args = parser.parse_args(argv)

    issues: list[str] = []
    try:
        ensure_ok, _ = _ensure_manifest_if_missing(args.manifest)
        if not ensure_ok:
            issues.append("manifest_ensure_failed")
            write_result(ok=False, issues=issues, error="manifest_ensure_failed")
            print(
                json.dumps(
                    {
                        "tool": "audit_immutability_verifier",
                        "status": "error",
                        "reason": "manifest_ensure_failed",
                    },
                    sort_keys=True,
                )
            )
            return 1

        result = verify_once(
            manifest_path=args.manifest,
            allow_missing_manifest=args.allow_missing_manifest,
        )
        if result.reason:
            issues.append(result.reason)
        if result.recorded_events:
            for entry in result.recorded_events:
                if entry.get("event") == "tamper_detected":
                    issues.append(f"tamper_detected:{entry.get('file', '<unknown>')}")

        summary = tooling_status.render_result(
            "audit_immutability_verifier", status=result.status, reason=result.reason
        )
        print(json.dumps(summary, sort_keys=True))

        ok = result.status in {"passed", "skipped"}
        write_result(ok=ok, issues=issues, error=None)
        if result.status in {"failed", "error"}:
            return 1
        return 0
    except Exception as exc:  # pragma: no cover - defensive
        message = str(exc)
        write_result(ok=False, issues=issues, error=message)
        print(
            json.dumps(
                {
                    "tool": "audit_immutability_verifier",
                    "status": "error",
                    "reason": message,
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
