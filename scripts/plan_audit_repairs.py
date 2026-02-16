from __future__ import annotations

"""Generate deterministic, machine-readable audit repair plans."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from scripts import verify_audits
from scripts.provenance_hash_chain import GENESIS_PREV_HASH

PLAN_PATH = Path("glow/audits/audit_repair_plan.json")
REPAIR_CHAIN_PATH = Path("glow/audits/repairs/repair_receipts.jsonl")
SCHEMA_VERSION = 1
SAFE_CODES_FOR_REBUILD = frozenset({"hash_mismatch", "chain_prev_mismatch", "genesis_marker_mismatch"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 128), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_receipt(kind: str, artifact_path: Path, payload: dict[str, Any]) -> None:
    REPAIR_CHAIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    artifact_hash = _file_sha256(artifact_path)
    prev_hash = GENESIS_PREV_HASH
    if REPAIR_CHAIN_PATH.exists():
        lines = [line for line in REPAIR_CHAIN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            prev_entry = json.loads(lines[-1])
            prev_hash = str(prev_entry.get("receipt_hash", GENESIS_PREV_HASH))

    receipt_core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "created_at": _utc_now(),
        "artifact": str(artifact_path),
        "artifact_sha256": artifact_hash,
        "prev_receipt_hash": prev_hash,
        "summary": {
            "issues": len(payload.get("issues", [])),
            "repairs": len(payload.get("repairs", [])),
            "applied": len(payload.get("applied", [])),
            "skipped": len(payload.get("skipped", [])),
            "errors": len(payload.get("errors", [])),
        },
    }
    chained = dict(receipt_core)
    chained["receipt_hash"] = hashlib.sha256(_canonical_json_bytes(receipt_core)).hexdigest()
    with REPAIR_CHAIN_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(chained, sort_keys=True) + "\n")


def _repair_for_path(path: str, issues: list[dict[str, str]], counter: int) -> dict[str, Any]:
    codes = sorted({issue.get("code", "unknown") for issue in issues})
    safe = bool(codes) and set(codes).issubset(SAFE_CODES_FOR_REBUILD)
    action = "rebuild_chain" if safe else "manual_required"
    return {
        "repair_id": f"repair-{counter:04d}",
        "action": action,
        "paths": [path],
        "reason_codes": codes or ["unknown"],
        "safe": safe,
    }


def build_plan(target: Path) -> dict[str, Any]:
    issues_by_path, _, _ = verify_audits.verify_audits_detailed(directory=target, quarantine=True, repair=False)
    issue_list: list[dict[str, str]] = []
    for path in sorted(issues_by_path.keys()):
        ordered = sorted(
            issues_by_path[path],
            key=lambda issue: (issue.get("code", "unknown"), issue.get("details", ""), issue.get("expected", "")),
        )
        issue_list.extend(ordered)

    repairs: list[dict[str, Any]] = []
    for idx, path in enumerate(sorted(issues_by_path.keys()), start=1):
        path_issues = issues_by_path[path]
        if path_issues:
            repairs.append(_repair_for_path(path, path_issues, idx))

    plan = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "target": str(target),
        "ok_to_apply": any(repair["safe"] for repair in repairs),
        "issues": issue_list,
        "repairs": repairs,
    }
    return plan


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Create deterministic audit repair plan")
    parser.add_argument("target", nargs="?", default="logs/", help="audit log directory")
    parser.add_argument("--output", default=str(PLAN_PATH), help="output plan JSON path")
    args = parser.parse_args(argv)

    target = Path(args.target)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    plan = build_plan(target)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_receipt("plan", output, plan)
    print(json.dumps({"tool": "plan_audit_repairs", "path": str(output), "repairs": len(plan["repairs"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
