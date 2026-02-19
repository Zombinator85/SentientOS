from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AuditDriftFinding:
    category: str
    file: str
    summary: str
    line_range: str | None = None
    details: str | None = None


@dataclass(frozen=True)
class AuditReconcileResult:
    status: Literal["clean", "drift", "repaired", "needs_decision"]
    findings: list[AuditDriftFinding]
    artifacts_written: list[str]


def parse_audit_drift_output(text: str) -> AuditReconcileResult:
    findings: list[AuditDriftFinding] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line and ".json" in line:
            head, summary = line.split(":", 1)
            parts = head.split(":")
            file_part = parts[0]
            line_range = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
            findings.append(
                AuditDriftFinding(
                    category="verify_output",
                    file=file_part,
                    line_range=line_range,
                    summary=summary.strip() or "audit drift reported",
                    details=line,
                )
            )
    if not findings and text.strip():
        findings.append(AuditDriftFinding(category="verify_output", file="logs/privileged_audit.jsonl", summary="audit drift reported", details=text.strip()[:500]))
    if not findings:
        return AuditReconcileResult(status="clean", findings=[], artifacts_written=[])
    return AuditReconcileResult(status="drift", findings=findings, artifacts_written=[])


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(f"non-object entry in {path}")
        rows.append(payload)
    return rows


def _canonical_entry(entry: dict[str, object]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _canonical_sort_key(entry: dict[str, object]) -> tuple[str, str, str]:
    timestamp = str(entry.get("timestamp", ""))
    rolling_hash = str(entry.get("rolling_hash") or entry.get("hash") or "")
    return (timestamp, rolling_hash, _canonical_entry(entry))


def reconcile_privileged_audit(repo_root: Path, mode: Literal["check", "repair"]) -> AuditReconcileResult:
    target = repo_root / "logs/privileged_audit.jsonl"
    if not target.exists():
        finding = AuditDriftFinding(category="missing_file", file="logs/privileged_audit.jsonl", summary="privileged audit log missing")
        return AuditReconcileResult(status="needs_decision", findings=[finding], artifacts_written=[])

    try:
        rows = _load_jsonl(target)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        finding = AuditDriftFinding(category="parse_error", file="logs/privileged_audit.jsonl", summary="unable to parse privileged audit log", details=str(exc))
        return AuditReconcileResult(status="needs_decision", findings=[finding], artifacts_written=[])

    canonical_text_in_order = "".join(f"{_canonical_entry(item)}\n" for item in rows)
    current_text = target.read_text(encoding="utf-8")

    if current_text == canonical_text_in_order:
        return AuditReconcileResult(status="clean", findings=[], artifacts_written=[])

    if [ _canonical_sort_key(item) for item in rows ] == sorted(_canonical_sort_key(item) for item in rows):
        finding = AuditDriftFinding(
            category="formatting_drift",
            file="logs/privileged_audit.jsonl",
            summary="non-canonical serialization detected",
            details="deterministic canonicalization available without reordering",
        )
        if mode == "repair":
            target.write_text(canonical_text_in_order, encoding="utf-8")
            return AuditReconcileResult(status="repaired", findings=[finding], artifacts_written=[str(target.relative_to(repo_root))])
        return AuditReconcileResult(status="drift", findings=[finding], artifacts_written=[])

    finding = AuditDriftFinding(
        category="substantive_drift",
        file="logs/privileged_audit.jsonl",
        summary="substantive privileged audit drift requires explicit operator decision",
        details="missing entries or altered hashes detected",
    )
    return AuditReconcileResult(status="needs_decision", findings=[finding], artifacts_written=[])


def result_to_json(result: AuditReconcileResult) -> dict[str, object]:
    return {
        "status": result.status,
        "findings": [asdict(item) for item in result.findings],
        "artifacts_written": result.artifacts_written,
    }
