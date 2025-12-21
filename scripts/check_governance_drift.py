"""Fail CI when governance-critical code changes without checklist acknowledgement."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping


CRITICAL_PATHS = [
    Path("task_admission.py"),
    Path("task_executor.py"),
    Path("advisory_connector.py"),
    Path("sentientos/autonomy/state.py"),
    Path("sentient_mesh.py"),
    Path("sentient_autonomy.py"),
    Path("sentientosd.py"),
    Path("sentientos/runtime/shell.py"),
    Path("sentientos/runtime/bootstrap.py"),
    Path("sentientos/determinism.py"),
]

CHECKLIST_PATH = Path("docs/governance_claims_checklist.md")
STATE_PATH = Path(".governance_drift_state.json")


def _file_digest(path: Path) -> str:
    text = path.read_bytes()
    return hashlib.sha256(text).hexdigest()


def _load_state() -> Mapping[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(digests: Mapping[str, str]) -> None:
    STATE_PATH.write_text(json.dumps(digests, indent=2, sort_keys=True), encoding="utf-8")


def _compute_digests(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): _file_digest(path) for path in paths if path.exists()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ack-governance-drift",
        action="store_true",
        help="Acknowledge governance-critical drift after updating the checklist.",
    )
    args = parser.parse_args(argv)

    missing = [path for path in CRITICAL_PATHS if not path.exists()]
    if missing:
        sys.stderr.write(f"Critical governance paths missing: {', '.join(str(p) for p in missing)}\n")
        return 1

    current = _compute_digests(CRITICAL_PATHS)
    state = _load_state()
    checklist_digest = _file_digest(CHECKLIST_PATH) if CHECKLIST_PATH.exists() else ""

    if not state:
        _save_state({**current, "checklist": checklist_digest})
        return 0

    drift = {
        path: digest
        for path, digest in current.items()
        if digest != state.get(path)
    }
    checklist_changed = checklist_digest != state.get("checklist")

    if drift and not checklist_changed and not args.ack_governance_drift:
        sys.stderr.write(
            "Governance-critical files changed without checklist update. "
            "Update docs/governance_claims_checklist.md and re-run with "
            "--ack-governance-drift to record the change.\n"
        )
        return 1

    if args.ack_governance_drift:
        _save_state({**current, "checklist": checklist_digest})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
