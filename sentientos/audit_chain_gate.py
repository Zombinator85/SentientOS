from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

REPORTS_DIR = Path("glow/forge/audit_reports")
SCHEMA_VERSION = 1


@dataclass(slots=True)
class AuditFirstBreak:
    path: str
    expected_prev_hash: str
    found_prev_hash: str
    line_number: int


@dataclass(slots=True)
class AuditChainVerification:
    status: str
    created_at: str
    break_count: int
    checked_files: int
    first_break: AuditFirstBreak | None = None
    affected_ranges: list[dict[str, object]] | None = None
    suggested_actions: list[str] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "created_at": self.created_at,
            "status": self.status,
            "break_count": self.break_count,
            "checked_files": self.checked_files,
            "affected_ranges": self.affected_ranges or [],
            "suggested_actions": self.suggested_actions or [],
        }
        if self.first_break is not None:
            payload["first_break"] = {
                "path": self.first_break.path,
                "expected_prev_hash": self.first_break.expected_prev_hash,
                "found_prev_hash": self.first_break.found_prev_hash,
                "line_number": self.first_break.line_number,
            }
        else:
            payload["first_break"] = None
        return payload


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _report_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _hash_entry(timestamp: str, data: object, prev_hash: str) -> str:
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def _is_log_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.suffix.lower() not in {".jsonl", ".json", ".log", ""}:
        return False
    try:
        first = path.read_text(encoding="utf-8", errors="ignore").lstrip().splitlines()[0]
    except Exception:
        return False
    return first.startswith("{") and "timestamp" in first and "data" in first


def _configured_log_paths(repo_root: Path) -> list[Path]:
    config = repo_root / "config/master_files.json"
    if config.exists():
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            paths: list[Path] = []
            for raw in payload.keys():
                p = Path(str(raw))
                if not p.is_absolute():
                    p = repo_root / p
                if _is_log_file(p):
                    paths.append(p)
            if paths:
                return sorted(paths)
    logs_dir = repo_root / "logs"
    return sorted(path for path in logs_dir.glob("*.jsonl") if _is_log_file(path))


def verify_audit_chain(repo_root: Path, *, paths: list[Path] | None = None) -> AuditChainVerification:
    root = repo_root.resolve()
    files = sorted(paths) if paths is not None else _configured_log_paths(root)
    if not files:
        return AuditChainVerification(status="unknown", created_at=_iso_now(), break_count=0, checked_files=0)

    break_count = 0
    first_break: AuditFirstBreak | None = None
    affected_ranges: list[dict[str, object]] = []
    prev_hash = "0" * 64

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in text.splitlines() if line.strip()]
        for idx, line in enumerate(lines, 1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                break_count += 1
                if first_break is None:
                    first_break = AuditFirstBreak(path=str(path.relative_to(root)), expected_prev_hash=prev_hash, found_prev_hash="<invalid-json>", line_number=idx)
                affected_ranges.append({"path": str(path.relative_to(root)), "start_line": idx, "end_line": len(lines)})
                break
            if not isinstance(entry, dict):
                break_count += 1
                if first_break is None:
                    first_break = AuditFirstBreak(path=str(path.relative_to(root)), expected_prev_hash=prev_hash, found_prev_hash="<non-object>", line_number=idx)
                affected_ranges.append({"path": str(path.relative_to(root)), "start_line": idx, "end_line": len(lines)})
                break
            found_prev = str(entry.get("prev_hash", "<missing>"))
            if found_prev != prev_hash:
                break_count += 1
                if first_break is None:
                    first_break = AuditFirstBreak(path=str(path.relative_to(root)), expected_prev_hash=prev_hash, found_prev_hash=found_prev, line_number=idx)
                affected_ranges.append({"path": str(path.relative_to(root)), "start_line": idx, "end_line": len(lines)})
                break
            timestamp = entry.get("timestamp")
            data = entry.get("data")
            if not isinstance(timestamp, str) or data is None:
                break_count += 1
                if first_break is None:
                    first_break = AuditFirstBreak(path=str(path.relative_to(root)), expected_prev_hash=prev_hash, found_prev_hash=found_prev, line_number=idx)
                affected_ranges.append({"path": str(path.relative_to(root)), "start_line": idx, "end_line": len(lines)})
                break
            expected = _hash_entry(timestamp, data, prev_hash)
            current = entry.get("rolling_hash") or entry.get("hash")
            if current != expected:
                break_count += 1
                if first_break is None:
                    first_break = AuditFirstBreak(path=str(path.relative_to(root)), expected_prev_hash=prev_hash, found_prev_hash=found_prev, line_number=idx)
                affected_ranges.append({"path": str(path.relative_to(root)), "start_line": idx, "end_line": len(lines)})
                break
            prev_hash = str(current)

    status = "ok" if break_count == 0 else "broken"
    suggestions = [
        "python scripts/verify_audits.py --strict",
        "python scripts/audit_chain_doctor.py --repair-index-only",
    ]
    if break_count:
        suggestions.append("python scripts/audit_chain_doctor.py --diagnose-only")
    return AuditChainVerification(
        status=status,
        created_at=_iso_now(),
        break_count=break_count,
        checked_files=len(files),
        first_break=first_break,
        affected_ranges=affected_ranges[:20],
        suggested_actions=suggestions,
    )


def write_audit_chain_report(repo_root: Path, result: AuditChainVerification) -> Path:
    report_dir = repo_root / REPORTS_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"audit_chain_report_{_report_tag()}.json"
    report_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


def latest_audit_chain_report(repo_root: Path) -> Path | None:
    reports = sorted((repo_root / REPORTS_DIR).glob("audit_chain_report_*.json"), key=lambda item: item.name)
    return reports[-1] if reports else None


def maybe_verify_audit_chain(repo_root: Path, *, context: str) -> tuple[AuditChainVerification | None, bool, bool, str | None]:
    _ = context
    enforce = os.getenv("SENTIENTOS_AUDIT_CHAIN_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_AUDIT_CHAIN_WARN", "0") == "1"
    if not enforce and not warn:
        return None, False, False, None
    result = verify_audit_chain(repo_root)
    report_path = write_audit_chain_report(repo_root, result)
    rel = str(report_path.relative_to(repo_root))
    return result, enforce and not result.ok, warn and not enforce and not result.ok, rel
