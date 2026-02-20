from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from sentientos.audit_sink import resolve_audit_paths


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
        if line.endswith(": valid") or line.endswith("No mismatches."):
            continue
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("tool") == "verify_audits" and payload.get("status") == "passed":
                continue
        if ":" in line and ".json" in line:
            if "privileged_audit" not in line and "runtime" not in line:
                continue
            head, summary = line.split(":", 1)
            findings.append(AuditDriftFinding(category="verify_output", file=head, summary=summary.strip() or "audit drift reported", details=line))
    if not findings and text.strip():
        findings.append(AuditDriftFinding(category="verify_output", file="logs/privileged_audit.jsonl", summary="audit drift reported", details=text.strip()[:500]))
    if not findings:
        return AuditReconcileResult(status="clean", findings=[], artifacts_written=[])
    return AuditReconcileResult(status="drift", findings=findings, artifacts_written=[])


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_head_text(repo_root: Path, path: Path) -> str | None:
    rel = path.relative_to(repo_root)
    completed = subprocess.run(["git", "show", f"HEAD:{rel.as_posix()}"], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    return completed.stdout


def _append_runtime_events(runtime_path: Path, lines: list[str]) -> None:
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    with runtime_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line.rstrip("\n") + "\n")


def _git_dirty_paths(repo_root: Path) -> list[str]:
    done = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        return ["<git-status-failed>"]
    return [line[3:] if len(line) > 3 else line for line in done.stdout.splitlines() if line.strip()]


def reconcile_privileged_audit(repo_root: Path, mode: Literal["check", "repair"]) -> AuditReconcileResult:
    sink = resolve_audit_paths(repo_root)
    baseline = sink.baseline_path
    runtime = sink.runtime_path

    if not baseline.exists():
        finding = AuditDriftFinding(category="missing_file", file=str(baseline.relative_to(repo_root)), summary="privileged audit baseline missing")
        return AuditReconcileResult(status="needs_decision", findings=[finding], artifacts_written=[])

    baseline_text = baseline.read_text(encoding="utf-8")
    baseline_lines = [line for line in baseline_text.splitlines() if line.strip()]
    head_text = _git_head_text(repo_root, baseline)
    if head_text is None:
        return AuditReconcileResult(status="needs_decision", findings=[AuditDriftFinding(category="baseline_untracked", file=str(baseline.relative_to(repo_root)), summary="unable to resolve canonical baseline from git HEAD")], artifacts_written=[])

    head_lines = [line for line in head_text.splitlines() if line.strip()]
    before_sha = _sha256_text(baseline_text)
    head_sha = _sha256_text(head_text)

    if baseline_text == head_text:
        return AuditReconcileResult(status="clean", findings=[], artifacts_written=[])

    appended_lines = 0
    likely_writer = "unknown"
    if len(baseline_lines) >= len(head_lines) and baseline_lines[: len(head_lines)] == head_lines:
        appended = baseline_lines[len(head_lines) :]
        appended_lines = len(appended)
        if appended:
            try:
                sample = json.loads(appended[-1])
                likely_writer = str(sample.get("tool") or sample.get("source") or sample.get("actor") or "unknown")
            except Exception:
                likely_writer = "unknown"

        findings = [
            AuditDriftFinding(
                category="substantive_drift",
                file=str(baseline.relative_to(repo_root)),
                summary="baseline was appended with runtime-like events",
                details=(
                    f"baseline_sha_before={before_sha}; baseline_sha_after={head_sha}; "
                    f"appended_lines={appended_lines}; likely_writer={likely_writer}; "
                    f"proposed_action=move_appended_lines_to_runtime:{runtime}"
                ),
            )
        ]
        if mode == "repair":
            rel_baseline = baseline.relative_to(repo_root).as_posix()
            dirty = _git_dirty_paths(repo_root)
            unrelated = [item for item in dirty if item != rel_baseline]
            if unrelated:
                findings.append(
                    AuditDriftFinding(
                        category="needs_decision",
                        file=str(baseline.relative_to(repo_root)),
                        summary="repo has unrelated local modifications; refusing baseline overwrite",
                        details=f"dirty_paths={','.join(unrelated[:10])}",
                    )
                )
                return AuditReconcileResult(status="needs_decision", findings=findings, artifacts_written=[])
            _append_runtime_events(runtime, appended)
            baseline.write_text(head_text, encoding="utf-8")
            return AuditReconcileResult(
                status="repaired",
                findings=findings,
                artifacts_written=[str(runtime.relative_to(repo_root)), str(baseline.relative_to(repo_root))],
            )
        return AuditReconcileResult(status="needs_decision", findings=findings, artifacts_written=[])

    finding = AuditDriftFinding(
        category="substantive_drift",
        file=str(baseline.relative_to(repo_root)),
        summary="baseline diverged from canonical audit artifact",
        details=f"baseline_sha_before={before_sha}; baseline_sha_after={head_sha}; appended_lines={appended_lines}; proposed_action=docket_and_stop",
    )
    return AuditReconcileResult(status="needs_decision", findings=[finding], artifacts_written=[])


def result_to_json(result: AuditReconcileResult) -> dict[str, object]:
    return {"status": result.status, "findings": [asdict(item) for item in result.findings], "artifacts_written": result.artifacts_written}
