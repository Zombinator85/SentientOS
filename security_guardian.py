from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Security Guardian orchestrates threat modeling, commit scanning, and validation."""
require_admin_banner()
require_lumos_approval()

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from audit_chain import append_entry
from security import ValidationHarness, build_threat_model, scan_repository

LOG_PATH = get_log_path("security_guardian.jsonl", "SECURITY_GUARDIAN_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
AUDIT_CHAIN_PATH = get_log_path("security_guardian_audit.jsonl", "SECURITY_GUARDIAN_AUDIT_LOG")


def _log_json(path: Path, payload: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def run_security_guardian(*, full_scan: bool, write_threat_model: bool, validate: bool) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parent
    threat_model = build_threat_model()
    threat_model_path = threat_model.write() if write_threat_model else None

    findings = scan_repository(repo_root, threat_model, changed_only=not full_scan)
    harness = ValidationHarness(repo_root)
    validations = harness.validate(findings) if validate else []

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "full_scan": full_scan,
        "finding_count": len(findings),
        "confirmed": sum(1 for v in validations if v.status == "confirmed"),
        "skipped": sum(1 for v in validations if v.status == "skipped"),
        "errors": sum(1 for v in validations if v.status == "error"),
        "max_agent_risk": max((agent.risk_score for agent in threat_model.agents), default=0),
        "high_risk_agents": [agent.name for agent in sorted(threat_model.agents, key=lambda a: a.risk_score, reverse=True)[:3]],
        "threat_model_path": str(threat_model_path) if threat_model_path else None,
    }

    payload = {
        "summary": summary,
        "threat_model": threat_model.to_dict(),
        "findings": [finding.to_dict() for finding in findings],
        "validations": [validation.to_dict() for validation in validations],
    }
    _log_json(LOG_PATH, payload)

    append_entry(
        AUDIT_CHAIN_PATH,
        {
            "tool": "security_guardian",
            "full_scan": full_scan,
            "finding_count": summary["finding_count"],
            "confirmed": summary["confirmed"],
            "skipped": summary["skipped"],
            "errors": summary["errors"],
        },
        emotion="focused",
        consent="autonomous-security-review",
    )
    return summary


def _format_output(summary: dict[str, object]) -> str:
    lines = ["Security Guardian Summary"]
    lines.append("-------------------------")
    for key, value in summary.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Run SentientOS security guardian pipeline")
    parser.add_argument("--full", action="store_true", help="Scan entire repository, not just changed files")
    parser.add_argument("--no-validation", action="store_true", help="Skip validation harness stage")
    parser.add_argument(
        "--write-threat-model",
        action="store_true",
        help="Persist the synthesized threat model ledger to the log directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_security_guardian(
        full_scan=args.full,
        write_threat_model=args.write_threat_model,
        validate=not args.no_validation,
    )
    print(_format_output(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
