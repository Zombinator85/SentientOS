from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Literal


RuntimeErrorKind = Literal["malformed_json", "truncated_line", "schema_violation", "chain_break", "unknown"]


@dataclass(frozen=True)
class RuntimeRepairAction:
    kind: str
    source_path: str
    dest_path: str
    line_count: int
    sha_before: str
    sha_after: str
    notes: str


@dataclass(frozen=True)
class AuditDoctorReport:
    status: Literal["repaired", "needs_decision", "failed"]
    baseline_status: str
    runtime_status: str
    actions: list[RuntimeRepairAction]
    docket_path: str | None = None


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_path(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_content(repo_root: Path, path: Path) -> str | None:
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return None
    done = subprocess.run(["git", "show", f"HEAD:{rel.as_posix()}"], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return None
    return done.stdout


def _git_dirty_paths(repo_root: Path) -> list[str]:
    done = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return ["<git-status-failed>"]
    paths: list[str] = []
    for raw in done.stdout.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        entry = line[3:] if len(line) > 3 else line
        paths.append(entry)
    return paths


def _classify_line(raw_line: str, *, is_last: bool, has_final_newline: bool) -> RuntimeErrorKind:
    text = raw_line.strip()
    if not text:
        return "unknown"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if is_last and not has_final_newline:
            return "truncated_line"
        return "malformed_json"
    if not isinstance(payload, dict):
        return "schema_violation"
    if "timestamp" not in payload or "data" not in payload:
        return "schema_violation"
    return "unknown"


def diagnose(repo_root: Path, baseline_path: Path, runtime_path: Path) -> tuple[str, str, dict[str, object]]:
    findings: dict[str, object] = {"runtime_findings": []}

    baseline_status = "ok"
    tracked = _tracked_content(repo_root, baseline_path)
    if tracked is None:
        baseline_status = "needs_decision"
    elif not baseline_path.exists():
        baseline_status = "missing"
    elif baseline_path.read_text(encoding="utf-8") != tracked:
        baseline_status = "drift"

    runtime_status = "ok"
    if runtime_path.exists():
        raw = runtime_path.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()
        final_newline = raw.endswith("\n")
        for idx, line in enumerate(lines, 1):
            if not line.strip():
                continue
            kind = _classify_line(line, is_last=idx == len(lines), has_final_newline=final_newline)
            if kind != "unknown":
                runtime_status = "broken"
                cast = findings.setdefault("runtime_findings", [])
                if isinstance(cast, list):
                    cast.append({"line": idx, "kind": kind, "sample": line[:160]})
    return baseline_status, runtime_status, findings


def repair_runtime(repo_root: Path, runtime_path: Path) -> list[RuntimeRepairAction]:
    del repo_root
    actions: list[RuntimeRepairAction] = []
    if not runtime_path.exists():
        return actions

    raw = runtime_path.read_text(encoding="utf-8", errors="replace")
    original_sha = _sha_text(raw)
    lines = raw.splitlines()
    final_newline = raw.endswith("\n")

    kept: list[str] = []
    malformed: list[str] = []
    schema_bad: list[str] = []
    truncated: list[str] = []
    for idx, line in enumerate(lines, 1):
        if not line.strip():
            continue
        kind = _classify_line(line, is_last=idx == len(lines), has_final_newline=final_newline)
        if kind == "malformed_json":
            malformed.append(line)
            continue
        if kind == "truncated_line":
            truncated.append(line)
            continue
        if kind == "schema_violation":
            schema_bad.append(line)
            continue
        kept.append(line)

    quarantine_dir = runtime_path.parent / "quarantine"
    ts = _now_tag()
    if malformed:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        q = quarantine_dir / f"{ts}_malformed.jsonl"
        q.write_text("\n".join(malformed) + "\n", encoding="utf-8")
        actions.append(
            RuntimeRepairAction(
                kind="quarantine_malformed",
                source_path=str(runtime_path),
                dest_path=str(q),
                line_count=len(malformed),
                sha_before=original_sha,
                sha_after=_sha_path(q),
                notes="Malformed JSON runtime lines quarantined without deletion",
            )
        )
    if truncated:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        q = quarantine_dir / f"{ts}_truncated.jsonl"
        q.write_text("\n".join(truncated) + "\n", encoding="utf-8")
        actions.append(
            RuntimeRepairAction(
                kind="quarantine_truncated",
                source_path=str(runtime_path),
                dest_path=str(q),
                line_count=len(truncated),
                sha_before=original_sha,
                sha_after=_sha_path(q),
                notes="Potential crash-truncated tail quarantined for evidence",
            )
        )

    if schema_bad:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        q = quarantine_dir / f"{ts}_schema_violation.jsonl"
        q.write_text("\n".join(schema_bad) + "\n", encoding="utf-8")
        actions.append(
            RuntimeRepairAction(
                kind="quarantine_schema_violation",
                source_path=str(runtime_path),
                dest_path=str(q),
                line_count=len(schema_bad),
                sha_before=original_sha,
                sha_after=_sha_path(q),
                notes="Runtime records missing required schema fields quarantined",
            )
        )

    normalized = "\n".join(kept)
    if kept:
        normalized += "\n"
    if normalized != raw:
        runtime_path.write_text(normalized, encoding="utf-8")
        actions.append(
            RuntimeRepairAction(
                kind="rewrite_runtime_normalized",
                source_path=str(runtime_path),
                dest_path=str(runtime_path),
                line_count=len(kept),
                sha_before=original_sha,
                sha_after=_sha_path(runtime_path),
                notes="Runtime stream rewritten with valid records and normalized trailing newline",
            )
        )
    return actions


def repair_baseline(repo_root: Path, baseline_path: Path) -> tuple[str, RuntimeRepairAction | None]:
    tracked = _tracked_content(repo_root, baseline_path)
    if tracked is None:
        return "needs_decision", None
    if not baseline_path.exists():
        return "needs_decision", None

    current = baseline_path.read_text(encoding="utf-8")
    if current == tracked:
        return "ok", None

    dirty_paths = _git_dirty_paths(repo_root)
    rel = baseline_path.relative_to(repo_root).as_posix()
    unrelated = [item for item in dirty_paths if item != rel]
    if unrelated:
        return "needs_decision", None

    before = _sha_text(current)
    baseline_path.write_text(tracked, encoding="utf-8")
    action = RuntimeRepairAction(
        kind="restore_baseline_to_head",
        source_path=str(baseline_path),
        dest_path=str(baseline_path),
        line_count=len([line for line in tracked.splitlines() if line.strip()]),
        sha_before=before,
        sha_after=_sha_path(baseline_path),
        notes="Baseline restored to canonical git HEAD artifact",
    )
    return "repaired", action


def write_docket(repo_root: Path, runtime_path: Path, actions: list[RuntimeRepairAction], samples: list[str]) -> str:
    ts = _now_tag()
    path = repo_root / "glow" / "forge" / f"audit_docket_{ts}.json"
    payload: dict[str, object] = {
        "kind": "audit_docket",
        "runtime_path": str(runtime_path),
        "quarantine_paths": [a.dest_path for a in actions if "quarantine" in a.kind],
        "counts": {a.kind: a.line_count for a in actions},
        "sha_before": actions[0].sha_before if actions else "",
        "sha_after": _sha_path(runtime_path),
        "samples": [sample[:200] for sample in samples[:5]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(repo_root))


def write_report(repo_root: Path, report: AuditDoctorReport) -> str:
    path = repo_root / "glow" / "forge" / f"audit_doctor_{_now_tag()}.json"
    payload: dict[str, object] = {
        "status": report.status,
        "baseline_status": report.baseline_status,
        "runtime_status": report.runtime_status,
        "actions": [asdict(item) for item in report.actions],
        "docket_path": report.docket_path,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(repo_root))
