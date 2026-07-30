from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
import os
import stat
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sentientos.codex_landing_evidence_binding import create_workspace_binding, create_commit_binding, verify_commit_matches_workspace
from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingArtifactFinding,
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingPolicy,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)
from sentientos.task_acceptance import verify as verify_task_acceptance

GENERATED_PREFIXES = ("glow/", "pulse/", "artifacts/codex/")
BLOCKED_PATH_PARTS = ("__pycache__", ".pytest_cache")
MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".wav", ".mp3")
DEFAULT_STAGE_TIMEOUT_SECONDS = 900
DEFAULT_MATRIX_TIMEOUT_SECONDS = 2400
DEFAULT_OVERALL_TIMEOUT_SECONDS = 5400
MAX_OUTPUT_LINES = 40


@dataclass(frozen=True)
class StageRuntime:
    stage_id: str
    command: str
    started_at: float
    completed: bool
    exit_code: int
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    decision_impact: str
    status: str
    timed_out: bool
    configured_timeout_class: str = "generic"
    configured_timeout_seconds: int = 0
    effective_timeout_seconds: int = 0
    overall_deadline_reduced_timeout: bool = False


@dataclass(frozen=True)
class DirtyPathDiagnostic:
    path: str
    git_status: str
    classification: str
    classification_source: str
    tracked: bool
    cleanup_attempted: bool
    cleanup_result: str
    cleanup_reason: str
    recommended_action: str


@dataclass(frozen=True)
class InvocationContext:
    schema_version: str
    invocation_id: str
    requested_sandbox_root: str
    resolved_invocation_root: str
    child_data_root: str
    child_state_root: str
    acceptance_custody_root: str
    child_environment: dict[str, str]
    collision_attempt_count: int
    exclusive_reservation_status: str
    symlink_check_status: str
    requested_root_custody: dict[str, Any]
    directory_custody_initial: dict[str, dict[str, Any]]


INVOCATION_RESERVATION_RETRIES = 4


def _new_invocation_id() -> str:
    """Return an identifier used only for collision-resistant custody naming."""
    return uuid.uuid4().hex


def _assert_no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current /= part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError(f"symlinked_runtime_custody_component:{current}")
        except FileNotFoundError:
            continue


def _directory_identity(path: Path, *, enforce_private_mode: bool) -> dict[str, Any]:
    info = path.lstat()
    kind = "directory" if stat.S_ISDIR(info.st_mode) else "symlink" if stat.S_ISLNK(info.st_mode) else "other"
    mode = stat.S_IMODE(info.st_mode)
    applicable = os.name == "posix"
    record: dict[str, Any] = {
        "path": str(path), "device": info.st_dev, "inode": info.st_ino,
        "type": kind, "mode": f"{mode:04o}" if applicable else None,
        "mode_enforcement": "applicable" if applicable else "not_applicable",
        "mode_status": "private" if applicable and mode == 0o700 else "not_applicable" if not applicable else "mismatch",
    }
    if kind != "directory":
        raise ValueError(f"runtime_custody_component_not_directory:{path}")
    if enforce_private_mode and applicable and mode != 0o700:
        raise ValueError(f"finalizer_owned_directory_mode_mismatch:{path}:{mode:04o}")
    return record


def _private_mkdir(path: Path) -> dict[str, Any]:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        _assert_no_symlink_components(path)
    return _directory_identity(path, enforce_private_mode=True)


def _create_invocation_context(repo_arg: str, sandbox_arg: str | None, binding_id: str) -> InvocationContext:
    repo = Path(repo_arg).resolve()
    requested = Path(sandbox_arg or f"/tmp/sentientos-codex-finalizer/{binding_id}").absolute()
    _assert_no_symlink_components(requested)
    resolved_requested = requested.resolve()
    if resolved_requested == repo or repo in resolved_requested.parents or resolved_requested == repo / ".git" or repo / ".git" in resolved_requested.parents:
        raise ValueError("runtime_root_inside_workspace")
    # The caller-owned requested root retains its existing permissions. Only
    # descendants created by the finalizer have a private-mode contract.
    missing: list[Path] = []
    cursor = requested
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for component in reversed(missing):
        os.mkdir(component, 0o700)
        _assert_no_symlink_components(component)
        _directory_identity(component, enforce_private_mode=False)
    requested_record = _directory_identity(requested, enforce_private_mode=False)
    requested_record["ownership"] = "caller_owned_requested_root"
    invocations = requested / "invocations"
    directory_custody = {"invocations_parent": _private_mkdir(invocations)}
    collisions = 0
    invocation_id = ""
    invocation_root: Path | None = None
    for _ in range(INVOCATION_RESERVATION_RETRIES):
        invocation_id = _new_invocation_id()
        candidate = invocations / invocation_id
        try:
            os.mkdir(candidate, 0o700)
            invocation_root = candidate
            break
        except FileExistsError:
            collisions += 1
    if invocation_root is None:
        raise ValueError(f"invocation_reservation_collisions_exhausted:{collisions}")
    _assert_no_symlink_components(invocation_root)
    directory_custody["invocation_root"] = _directory_identity(invocation_root, enforce_private_mode=True)
    resolved_invocation = invocation_root.resolve(strict=True)
    if resolved_requested not in resolved_invocation.parents or resolved_invocation == repo or repo in resolved_invocation.parents:
        raise ValueError("reserved_invocation_root_outside_requested_sandbox")
    data = invocation_root / "data"
    state = invocation_root / "state"
    acceptance = invocation_root / "task_acceptance"
    for name, directory in (("data", data), ("state", state), ("task_acceptance", acceptance)):
        directory_custody[name] = _private_mkdir(directory)
        _assert_no_symlink_components(directory)
    child = {"SENTIENTOS_DATA_DIR": str(data), "SENTIENTOS_RUNTIME_STATE_ROOT": str(state)}
    return InvocationContext(
        "sentientos.finalizer_invocation_context:v1", invocation_id, str(requested),
        str(resolved_invocation), str(data), str(state), str(acceptance), child,
        collisions, "exclusive_directory_reserved", "all_existing_components_not_symlinks",
        requested_record, directory_custody,
    )


def _terminal_directory_custody(context: InvocationContext) -> tuple[dict[str, dict[str, Any]], list[str]]:
    paths = {
        "invocations_parent": Path(context.requested_sandbox_root) / "invocations",
        "invocation_root": Path(context.resolved_invocation_root),
        "data": Path(context.child_data_root), "state": Path(context.child_state_root),
        "task_acceptance": Path(context.acceptance_custody_root),
    }
    terminal: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for name, path in paths.items():
        try:
            current = _directory_identity(path, enforce_private_mode=True)
            initial = context.directory_custody_initial[name]
            same = current["device"] == initial["device"] and current["inode"] == initial["inode"]
            current["identity_status"] = "unchanged" if same else "replaced"
            terminal[name] = current
            if not same:
                reasons.append(f"finalizer_owned_directory_identity_mismatch:{path}")
        except (OSError, ValueError) as exc:
            terminal[name] = {"path": str(path), "identity_status": "unreadable", "reason": str(exc)}
            reasons.append(str(exc))
    return terminal, reasons


class FinalizerTimeoutError(RuntimeError):
    def __init__(self, stage_id: str, kind: str) -> None:
        super().__init__(f"{kind}_timeout:{stage_id}")
        self.stage_id = stage_id
        self.kind = kind


def _tail(text: str, limit: int = MAX_OUTPUT_LINES) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])


def _progress(enabled: bool, line: str) -> None:
    if enabled:
        print(line, flush=True)


def _run_stage(
    stage_id: str,
    cmd: str,
    required: bool,
    progress: bool,
    stage_timeout_seconds: int,
    overall_deadline: float,
    child_environment: dict[str, str],
) -> tuple[CodexFinalizeLandingCommandResult, StageRuntime]:
    if time.monotonic() >= overall_deadline:
        raise FinalizerTimeoutError(stage_id, "overall")
    _progress(progress, f"[finalizer] stage start: {stage_id}")
    started = time.monotonic()
    remaining = max(1, int(overall_deadline - started))
    timeout_seconds = min(stage_timeout_seconds, remaining)
    timeout_class = "matrix" if stage_id in {"matrix_summary", "stale_evidence_matrix_summary"} else "generic"
    deadline_reduced = timeout_seconds < stage_timeout_seconds
    try:
        env = os.environ.copy()
        env.update(child_environment)
        p = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout_seconds, env=env)
        timed_out = False
        status = "passed" if p.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        stdout_part = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_part = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        combined = stdout_part + "\n" + stderr_part
        runtime = StageRuntime(
            stage_id=stage_id,
            command=cmd,
            started_at=started,
            completed=False,
            exit_code=124,
            duration_seconds=time.monotonic() - started,
            stdout_tail=_tail(combined),
            stderr_tail="",
            decision_impact="required_stage_timeout" if required else "optional_stage_timeout",
            status="timed_out",
            timed_out=True,
            configured_timeout_class=timeout_class,
            configured_timeout_seconds=stage_timeout_seconds,
            effective_timeout_seconds=timeout_seconds,
            overall_deadline_reduced_timeout=deadline_reduced,
        )
        _progress(progress, f"[finalizer] stage end: {stage_id} status=timed_out exit_code=124")
        raise FinalizerTimeoutError(stage_id, "stage") from exc
    duration = time.monotonic() - started
    result = CodexFinalizeLandingCommandResult(
        stage=stage_id,
        command=cmd,
        exit_code=p.returncode,
        output_tail=_tail((p.stdout or "") + "\n" + (p.stderr or "")),
        required=required,
    )
    runtime = StageRuntime(
        stage_id=stage_id,
        command=cmd,
        started_at=started,
        completed=True,
        exit_code=p.returncode,
        duration_seconds=duration,
        stdout_tail=_tail(p.stdout or ""),
        stderr_tail=_tail(p.stderr or ""),
        decision_impact="required" if required else "optional",
        status=status,
        timed_out=timed_out,
        configured_timeout_class=timeout_class,
        configured_timeout_seconds=stage_timeout_seconds,
        effective_timeout_seconds=timeout_seconds,
        overall_deadline_reduced_timeout=deadline_reduced,
    )
    _progress(progress, f"[finalizer] stage end: {stage_id} status={status} exit_code={p.returncode}")
    return result, runtime


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _exclusive_write(path: Path, data: bytes) -> dict[str, Any]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    info = path.stat(follow_symlinks=False)
    return {"device": info.st_dev, "inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode), "size": info.st_size}


def _stable_regular_read(path: Path) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink():
        raise ValueError(f"source_symlink:{path}")
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"source_not_regular_file:{path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"source_changed_during_capture:{path}")
    return b"".join(chunks), {"file_type": "regular", "stable_read": True, "device": before.st_dev, "inode": before.st_ino, "size": before.st_size, "mtime_ns": before.st_mtime_ns}


def _capture_task_acceptance(manifest_arg: str, workspace_root: str, context: InvocationContext) -> dict[str, Any]:
    custody: dict[str, Any] = {
        "schema_version": "sentientos.task_acceptance_custody:v1",
        "capture_status": "task_acceptance_capture_blocked",
        "initial_verification_status": "task_acceptance_blocked",
        "initial_verification_reasons": [],
        "terminal_verification_status": "not_run",
        "terminal_verification_reasons": [],
        "captured_evidence_unchanged": False,
    }
    try:
        repo = Path(workspace_root).resolve()
        manifest = Path(manifest_arg)
        if not manifest.is_absolute():
            manifest = repo / manifest
        manifest_bytes, manifest_source = _stable_regular_read(manifest)
        manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest_payload, dict) or not isinstance(manifest_payload.get("test_provenance_path"), str):
            raise ValueError("manifest_missing_test_provenance_path")
        declared = Path(manifest_payload["test_provenance_path"])
        provenance = declared if declared.is_absolute() else repo / declared
        provenance_bytes, provenance_source = _stable_regular_read(provenance)
        json.loads(provenance_bytes.decode("utf-8"))
        custody_root = Path(context.acceptance_custody_root)
        if custody_root == repo or repo in custody_root.parents:
            raise ValueError("custody_root_inside_workspace")
        captured_manifest = custody_root / "manifest.json"
        captured_provenance = custody_root / "provenance.json"
        manifest_identity = _exclusive_write(captured_manifest, manifest_bytes)
        provenance_identity = _exclusive_write(captured_provenance, provenance_bytes)
        try:
            directory_fd = os.open(custody_root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        repository_sha = str(manifest_payload.get("repository_sha", ""))
        custody.update({
            "capture_status": "task_acceptance_captured",
            "original_manifest_path": str(manifest),
            "original_provenance_path": str(provenance),
            "original_manifest_digest": _sha256(manifest_bytes),
            "original_manifest_byte_length": len(manifest_bytes),
            "original_provenance_digest": _sha256(provenance_bytes),
            "original_provenance_byte_length": len(provenance_bytes),
            "captured_manifest_path": str(captured_manifest),
            "captured_provenance_path": str(captured_provenance),
            "captured_manifest_digest": _sha256(captured_manifest.read_bytes()),
            "captured_manifest_byte_length": captured_manifest.stat().st_size,
            "captured_provenance_digest": _sha256(captured_provenance.read_bytes()),
            "captured_provenance_byte_length": captured_provenance.stat().st_size,
            "repository_sha": repository_sha,
            "acceptance_custody_root": str(custody_root),
            "source_manifest": manifest_source,
            "source_provenance": provenance_source,
            "captured_manifest_identity": manifest_identity,
            "captured_provenance_identity": provenance_identity,
            "captured_file_modes_applicable": os.name == "posix",
            "symlink_check_status": "no_symlinks_followed",
        })
        result = verify_task_acceptance(captured_manifest, captured_provenance, repo_root=repo)
        custody["initial_verification_status"] = result.get("status")
        custody["initial_verification_reasons"] = list(result.get("reasons", []))
        custody["initial_verification"] = result
        return custody
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        custody["initial_verification_reasons"] = [f"invalid_acceptance_input:{exc}"]
        return custody


def _landing_matrix_command(matrix_json_path: str) -> str:
    return " ".join(
        [
            "python",
            "scripts/run_work_item_review_packet_matrix.py",
            "--summary",
            "--output",
            shlex.quote(matrix_json_path),
        ]
    )


def _landing_gate_command(title: str | None, intended_commit_title: str | None, matrix_json_path: str) -> str:
    return " ".join(
        [
            "python",
            "scripts/codex_pr_landing_gate.py",
            "gate",
            "--title",
            shlex.quote(title or ""),
            "--intended-commit-title",
            shlex.quote(intended_commit_title or ""),
            "--matrix-json-path",
            shlex.quote(matrix_json_path),
        ]
    )


def _landing_supervisor_command(title: str | None, intended_commit_title: str | None, matrix_json_path: str) -> str:
    return " ".join(
        [
            "python",
            "scripts/codex_landing_supervisor.py",
            "evaluate",
            "--title",
            shlex.quote(title or ""),
            "--intended-commit-title",
            shlex.quote(intended_commit_title or ""),
            "--matrix-json-path",
            shlex.quote(matrix_json_path),
            "--landing-gate-status",
            "passed",
            "--summary",
        ]
    )


def _git_status() -> list[str]:
    p = subprocess.run("git status --short", shell=True, text=True, capture_output=True)
    return [l.rstrip() for l in p.stdout.splitlines() if l.strip()]


def _git_tracked_changes() -> tuple[str, ...]:
    p = subprocess.run("git diff --name-only --cached && git diff --name-only", shell=True, text=True, capture_output=True)
    names = [line.strip() for line in p.stdout.splitlines() if line.strip()]
    return tuple(sorted(set(names)))


def _strip_fixture_path(path: str) -> str:
    if path.startswith("tests/fixtures/"):
        rest = path[len("tests/fixtures/"):].strip("/")
        return rest.split("/", 1)[0] if rest else ""
    return ""


def _task_slug_from_path(path: str) -> str:
    name = Path(path.rstrip("/")).name
    if path.startswith("sentientos/") and name.endswith(".py"):
        return name[:-3]
    if path.startswith("tests/test_") and name.startswith("test_") and name.endswith(".py"):
        stem = name[:-3]
        if stem.endswith("_script"):
            stem = stem[: -len("_script")]
        return stem[len("test_"):]
    if path.startswith("docs/") and name.endswith(".md"):
        return name[:-3]
    if path.startswith("scripts/") and name.endswith(".py"):
        stem = name[:-3]
        for prefix in ("build_", "plan_", "run_", "verify_", "evaluate_"):
            if stem.startswith(prefix):
                return stem[len(prefix):]
        return stem
    return ""


def _infer_task_slugs(status_lines: list[str], changed_files: tuple[str, ...]) -> frozenset[str]:
    slugs: set[str] = set()
    for path in changed_files:
        slug = _task_slug_from_path(path)
        if slug:
            slugs.add(slug)
    for line in status_lines:
        path = line[3:] if len(line) > 3 else line
        if path.startswith("tests/fixtures/"):
            continue
        slug = _task_slug_from_path(path)
        if slug:
            slugs.add(slug)
    return frozenset(slugs)


def _is_task_scoped_fixture_path(path: str, task_slugs: frozenset[str]) -> bool:
    fixture_slug = _strip_fixture_path(path)
    return bool(fixture_slug and fixture_slug in task_slugs)


def _is_safe_untracked_task_file(path: str, task_slugs: frozenset[str] = frozenset()) -> bool:
    if path == "AGENTS.md":
        return True
    if path.startswith(("sentientos/", "scripts/", "tests/", "docs/")) and path.endswith((".py", ".md")):
        return True
    if path.startswith("tests/fixtures/") and (path.endswith("/") or path.endswith(".json")):
        return _is_task_scoped_fixture_path(path, task_slugs)
    if path.startswith("artifacts/proof_bundles/") and path.endswith(".json"):
        return True
    return False


def _recommended_action(classification: str, path: str) -> str:
    if classification == "generated_runtime_artifact":
        if path == "pulse/audit/privileged_audit.runtime.jsonl":
            return "restore_runtime_audit_artifact"
        return "remove_generated_artifact"
    if classification == "source_change_not_declared":
        return "add_to_task_file_allowlist" if path.startswith(("sentientos/", "scripts/", "tests/", "docs/")) else "explicitly_pass_changed_file"
    return "manual_review_required"


def _classify(status_lines: list[str], changed_files: tuple[str, ...], inferred_untracked_task_files: tuple[str, ...]) -> tuple[CodexFinalizeLandingArtifactFinding, ...]:
    out: list[CodexFinalizeLandingArtifactFinding] = []
    changed_file_set = set(changed_files)
    for line in status_lines:
        is_untracked = line.startswith("??")
        path = line[3:] if len(line) > 3 else line
        if path.startswith(GENERATED_PREFIXES) or any(part in path for part in BLOCKED_PATH_PARTS):
            cls = "generated_runtime_artifact"
            action = "cleanup"
        elif path.lower().endswith(MEDIA_SUFFIXES):
            cls = "unknown_dirty_file"
            action = "block"
        elif path.startswith("pulse/audit/"):
            cls = "versioned_audit_artifact"
            action = "review"
        elif is_untracked and path in set(inferred_untracked_task_files):
            cls = "intended_task_change"
            action = "allow_pre_commit"
        elif (not is_untracked) and path in changed_file_set:
            cls = "intended_task_change"
            action = "allow_pre_commit"
        elif path.endswith((".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".bat")):
            cls = "source_change_not_declared"
            action = "block"
        else:
            cls = "unknown_dirty_file"
            action = "block"
        out.append(CodexFinalizeLandingArtifactFinding(path=path, classification=cls, action=action))
    if not out:
        out.append(CodexFinalizeLandingArtifactFinding(path="", classification="clean", action="none"))
    return tuple(out)


def _collect_dirty_diagnostics(
    status_lines: list[str],
    findings: tuple[CodexFinalizeLandingArtifactFinding, ...],
    classification_source: str,
    cleanup_map: dict[str, tuple[bool, str, str]],
) -> list[DirtyPathDiagnostic]:
    by_path = {item.path: item for item in findings}
    diagnostics: list[DirtyPathDiagnostic] = []
    for line in status_lines:
        git_status = line[:2]
        path = line[3:] if len(line) > 3 else line
        finding = by_path.get(path)
        cleanup_attempted, cleanup_result, cleanup_reason = cleanup_map.get(path, (False, "not_attempted", "not_generated"))
        diagnostics.append(
            DirtyPathDiagnostic(
                path=path,
                git_status=git_status,
                classification=finding.classification if finding else "unknown_dirty_file",
                classification_source=classification_source,
                tracked=not git_status.startswith("??"),
                cleanup_attempted=cleanup_attempted,
                cleanup_result=cleanup_result,
                cleanup_reason=cleanup_reason,
                recommended_action=_recommended_action(finding.classification if finding else "unknown_dirty_file", path),
            )
        )
    return diagnostics


def _cleanup_generated(status_lines: list[str]) -> dict[str, tuple[bool, str, str]]:
    cleanup: dict[str, tuple[bool, str, str]] = {}
    for line in status_lines:
        git_status = line[:2]
        path = line[3:] if len(line) > 3 else line
        is_generated = path.startswith(GENERATED_PREFIXES) or any(part in path for part in BLOCKED_PATH_PARTS) or path == "pulse/audit/privileged_audit.runtime.jsonl"
        if not is_generated:
            continue
        tracked = not git_status.startswith("??")
        if path == "pulse/audit/privileged_audit.runtime.jsonl":
            p = subprocess.run(["git", "restore", "--", path])
            cleanup[path] = (True, "restored" if p.returncode == 0 else "failed", "runtime_audit_restore")
            continue
        if tracked:
            p = subprocess.run(["git", "restore", "--", path])
            cleanup[path] = (True, "restored" if p.returncode == 0 else "failed", "generated_artifact_restore")
        else:
            p = subprocess.run(["git", "clean", "-fd", "--", path])
            cleanup[path] = (True, "removed" if p.returncode == 0 else "failed", "generated_artifact_cleanup")
    return cleanup


def _emit_and_optionally_write(payload: dict[str, object], output: str | None, summary: bool, decision_status: str) -> None:
    if output:
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if summary:
        decision_payload = payload.get("decision")
        reasons = decision_payload.get("reasons", []) if isinstance(decision_payload, dict) else []
        freshness = payload.get("evidence_freshness")
        terminal_refresh_status = "not_required"
        rerun_required = False
        if isinstance(freshness, dict):
            terminal_refresh_status = str(freshness.get("stale_evidence_refresh_result", "not_required"))
            rerun_required = bool(freshness.get("rerun_required", False))
        print(json.dumps({"status": decision_status, "reasons": reasons, "terminal_refresh_status": terminal_refresh_status, "rerun_required": rerun_required}, indent=2))
        print(f"Codex Finalize Landing decision: {decision_status}", flush=True)
    else:
        print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "finalize", "summarize", "hygiene", "validate-evidence"):
        s = sub.add_parser(name)
        s.add_argument("--title", required=False)
        s.add_argument("--intended-commit-title", required=False)
        s.add_argument("--phase", default="pr-metadata")
        s.add_argument("--matrix-json-path", default="/tmp/work_item_review_packet_matrix.json")
        s.add_argument("--workspace-root", default=".")
        s.add_argument("--focused-test-command", action="append", default=[])
        s.add_argument("--targeted-mypy-command", action="append", default=[])
        s.add_argument("--extra-required-command", action="append", default=[])
        s.add_argument("--changed-file", action="append", default=[])
        s.add_argument("--allow-current-tracked-changes", action="store_true")
        s.add_argument("--allow-current-task-files", action="store_true")
        s.add_argument("--allow-docs-bootstrap", action="store_true")
        s.add_argument("--allow-strict-audit-repair", action="store_true")
        s.add_argument("--allow-generated-artifact-cleanup", action="store_true")
        s.add_argument("--allow-stale-evidence-refresh", action="store_true")
        s.add_argument("--max-stale-evidence-refreshes", type=int, default=1)
        s.add_argument("--allow-no-focused-tests", action="store_true")
        s.add_argument("--output")
        s.add_argument("--stage-timeout-seconds", type=int, default=DEFAULT_STAGE_TIMEOUT_SECONDS)
        s.add_argument("--matrix-timeout-seconds", type=int, default=DEFAULT_MATRIX_TIMEOUT_SECONDS)
        s.add_argument("--overall-timeout-seconds", type=int, default=DEFAULT_OVERALL_TIMEOUT_SECONDS)
        s.add_argument("--progress", action="store_true", default=True)
        s.add_argument("--no-progress", action="store_false", dest="progress")
        s.add_argument("--summary", action="store_true")
        s.add_argument("--pre-commit-finalizer-json")
        s.add_argument("--runtime-sandbox-root")
        s.add_argument("--task-acceptance-manifest")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.stage_timeout_seconds <= 0 or a.matrix_timeout_seconds <= 0 or a.overall_timeout_seconds <= 0:
        print(json.dumps({"status": "error", "reason": "timeout_arguments_must_be_positive"}, indent=2))
        return 2
    if a.cmd in {"plan", "summarize", "validate-evidence"}:
        print(json.dumps({"status": "ok", "command": a.cmd}, indent=2))
        return 0
    if a.cmd == "hygiene":
        print(json.dumps({"status": "ok", "git_status": _git_status()}, indent=2))
        return 0

    inferred_changed_files: tuple[str, ...] = ()
    if a.allow_current_tracked_changes:
        if a.phase.replace("_", "-") != "pre-commit":
            print(json.dumps({"status": "error", "reason": "allow_current_tracked_changes_requires_pre_commit"}, indent=2))
            return 2
        inferred_changed_files = _git_tracked_changes()
    inferred_untracked_task_files: tuple[str, ...] = ()
    if a.allow_current_task_files:
        if a.phase.replace("_", "-") != "pre-commit":
            print(json.dumps({"status": "error", "reason": "allow_current_task_files_requires_pre_commit"}, indent=2))
            return 2
        status_lines = _git_status()
        task_slugs = _infer_task_slugs(status_lines, inferred_changed_files + tuple(a.changed_file))
        candidates = []
        for line in status_lines:
            if not line.startswith("??"):
                continue
            path = line[3:] if len(line) > 3 else line
            if _is_safe_untracked_task_file(path, task_slugs):
                candidates.append(path)
        inferred_untracked_task_files = tuple(sorted(set(candidates)))

    runtime_env: dict[str, str] = {}
    invocation_context: InvocationContext | None = None
    runtime_error = ""
    try:
        invocation_context = _create_invocation_context(a.workspace_root, a.runtime_sandbox_root, (a.title or "codex-finalizer").replace("/", "_").replace(" ", "_"))
        runtime_env = invocation_context.child_environment
    except ValueError as exc:
        runtime_error = str(exc)

    req = CodexFinalizeLandingRequest(
        title=a.title or "",
        intended_commit_title=a.intended_commit_title or "",
        phase=a.phase,
        matrix_json_path=a.matrix_json_path,
        focused_test_commands=tuple(a.focused_test_command),
        targeted_mypy_commands=tuple(a.targeted_mypy_command),
        extra_required_commands=tuple(a.extra_required_command),
        changed_files=tuple(a.changed_file),
        inferred_changed_files=inferred_changed_files,
        inferred_tracked_changed_files=inferred_changed_files,
        inferred_untracked_task_files=inferred_untracked_task_files,
        allow_current_tracked_changes=a.allow_current_tracked_changes,
        allow_current_task_files=a.allow_current_task_files,
        dirty_file_classification_source="tracked+untracked_inferred" if (a.allow_current_tracked_changes or a.allow_current_task_files) else "declared",
        allow_no_focused_tests=a.allow_no_focused_tests,
        workspace_root=a.workspace_root,
        summary=a.summary,
    )

    stage_specs: list[tuple[str, str, bool]] = [("preflight_hygiene", "git status --short", True)]
    stage_specs.extend(("focused_tests", c, True) for c in a.focused_test_command)
    stage_specs.extend(("targeted_mypy", c, True) for c in a.targeted_mypy_command)
    exact_matrix_reuse = a.phase.replace("_", "-") in {"post-commit", "pr-metadata"} and bool(a.pre_commit_finalizer_json)
    matrix_stages: list[tuple[str, str, bool]] = [] if exact_matrix_reuse else [("matrix_summary", _landing_matrix_command(a.matrix_json_path), True)]
    stage_specs.extend(
        [
            ("mypy_baseline", "python scripts/check_mypy_baseline.py", True),
            *matrix_stages,
            ("pr_landing_gate", _landing_gate_command(a.title, a.intended_commit_title, a.matrix_json_path), True),
            ("landing_supervisor", _landing_supervisor_command(a.title, a.intended_commit_title, a.matrix_json_path), True),
            ("docs_check_deps", "python scripts/build_docs.py --check-deps", True),
            ("docs_build", "python scripts/build_docs.py", True),
            ("prompt_boundary", "python scripts/verify_context_hygiene_prompt_boundaries.py", True),
            ("strict_audits", "python verify_audits.py --strict", True),
            ("audit_immutability", "python scripts/audit_immutability_verifier.py", True),
        ]
    )

    started = time.monotonic()
    deadline = started + max(1, a.overall_timeout_seconds)
    commands: list[CodexFinalizeLandingCommandResult] = []
    runtime: list[StageRuntime] = []
    decision_status = "finalizer_failed"
    decision_reasons: list[str] = []
    acceptance_custody: dict[str, Any] | None = None
    acceptance_result: dict[str, Any] | None = None
    if a.task_acceptance_manifest and not runtime_error:
        assert invocation_context is not None
        acceptance_custody = _capture_task_acceptance(a.task_acceptance_manifest, a.workspace_root, invocation_context)
        acceptance_result = acceptance_custody.get("initial_verification")
        if not isinstance(acceptance_result, dict):
            acceptance_result = {
                "status": "task_acceptance_blocked",
                "reasons": list(acceptance_custody.get("initial_verification_reasons", ["task_acceptance_capture_blocked"])),
            }
    acceptance_ready = acceptance_result is None or acceptance_result.get("status") == "task_acceptance_ready"
    try:
        if runtime_error:
            decision_status = "repair_required_task_caused"
            decision_reasons = [runtime_error]
        elif not acceptance_ready:
            decision_status = "repair_required_task_caused"
            decision_reasons = list(acceptance_result.get("reasons", ["task_acceptance_blocked"])) if acceptance_result else ["task_acceptance_blocked"]
        else:
            for stage_id, cmd, required in stage_specs:
                timeout = a.matrix_timeout_seconds if stage_id == "matrix_summary" else a.stage_timeout_seconds
                result, stage_runtime = _run_stage(stage_id, cmd, required, a.progress, timeout, deadline, runtime_env)
                commands.append(result)
                runtime.append(stage_runtime)
    except FinalizerTimeoutError as exc:
        decision_status = "environment_blocked" if exc.kind == "overall" else "finalizer_failed"
        decision_reasons = [f"{exc.kind}_timeout:{exc.stage_id}", "rerun_with_higher_timeout_or_fix_hung_stage"]
    except Exception as exc:  # noqa: BLE001
        decision_status = "finalizer_failed"
        decision_reasons = [f"runtime_exception:{type(exc).__name__}"]

    status_before_cleanup = _git_status()
    cleanup_results: dict[str, tuple[bool, str, str]] = {}
    if acceptance_ready and not runtime_error and a.allow_generated_artifact_cleanup:
        _progress(a.progress, "[finalizer] stage start: generated_artifact_cleanup")
        cleanup_results = _cleanup_generated(status_before_cleanup)
        _progress(a.progress, "[finalizer] stage end: generated_artifact_cleanup status=passed exit_code=0")

    status_after_cleanup = _git_status()
    findings = _classify(status_after_cleanup, tuple(a.changed_file) + inferred_changed_files, inferred_untracked_task_files)
    diagnostics = _collect_dirty_diagnostics(status_after_cleanup, findings, req.dirty_file_classification_source, cleanup_results)
    stale_reasons: list[str] = []
    command_map = {item.stage: item for item in commands}
    if command_map.get("strict_audits") and command_map.get("matrix_summary"):
        if command_map["strict_audits"].exit_code == 0 and command_map["matrix_summary"].exit_code != 0:
            stale_reasons.append("matrix_failed_before_strict_audits_healthy")
    # Generated runtime cleanup is excluded from semantic identity and does not by itself stale the matrix.

    refresh_attempted = False
    refresh_status = "not_required"
    refresh_runs = 0
    refresh_failure_reason = ""
    refresh_stage_names: list[str] = []
    rerun_required = False
    if acceptance_ready and not runtime_error and stale_reasons:
        if a.allow_stale_evidence_refresh and a.max_stale_evidence_refreshes > 0:
            refresh_attempted = True
            refresh_status = "attempted"
            refresh_plan = [
                ("stale_evidence_matrix_summary", _landing_matrix_command(a.matrix_json_path), True),
                ("stale_evidence_pr_landing_gate", _landing_gate_command(a.title, a.intended_commit_title, a.matrix_json_path), True),
                ("stale_evidence_landing_supervisor", _landing_supervisor_command(a.title, a.intended_commit_title, a.matrix_json_path), True),
            ]
            # The refresh is intentionally bounded to one pass per finalizer
            # invocation; max_stale_evidence_refreshes controls permission, not
            # recursive retries.
            try:
                for stage_id, cmd, required in refresh_plan[:1 if a.max_stale_evidence_refreshes < 1 else len(refresh_plan)]:
                    timeout = a.matrix_timeout_seconds if stage_id == "stale_evidence_matrix_summary" else a.stage_timeout_seconds
                    result, stage_runtime = _run_stage(stage_id, cmd, required, a.progress, timeout, deadline, runtime_env)
                    commands.append(result)
                    runtime.append(stage_runtime)
                    refresh_runs += 1
                    refresh_stage_names.append(stage_id)
                    if required and result.exit_code != 0:
                        refresh_failure_reason = f"stage_failed:{stage_id}"
                        break
                refresh_status = "failed" if refresh_failure_reason else "succeeded"
            except FinalizerTimeoutError as exc:
                refresh_failure_reason = f"{exc.kind}_timeout:{exc.stage_id}"
                refresh_status = "failed"
            except Exception as exc:  # noqa: BLE001
                refresh_failure_reason = f"runtime_exception:{type(exc).__name__}"
                refresh_status = "failed"
        else:
            refresh_status = "required_not_allowed"
            rerun_required = True

    terminal_cleanup_results: dict[str, tuple[bool, str, str]] = {}
    if acceptance_ready and not runtime_error and refresh_status == "succeeded" and a.allow_generated_artifact_cleanup:
        status_after_refresh_before_cleanup = _git_status()
        terminal_cleanup_results = _cleanup_generated(status_after_refresh_before_cleanup)
        cleanup_results.update(terminal_cleanup_results)

    status_after_refresh = _git_status()
    findings_after_refresh = _classify(status_after_refresh, tuple(a.changed_file) + inferred_changed_files, inferred_untracked_task_files)
    diagnostics_after_refresh = _collect_dirty_diagnostics(status_after_refresh, findings_after_refresh, req.dirty_file_classification_source, cleanup_results)
    generated_dirty_after_refresh = [item.path for item in findings_after_refresh if item.classification == "generated_runtime_artifact"]

    landing_result = evaluate_finalize_landing(
        req,
        tuple(commands),
        findings_after_refresh,
        policy=CodexFinalizeLandingPolicy(
            allow_generated_artifact_cleanup=a.allow_generated_artifact_cleanup,
            allow_stale_evidence_refresh=a.allow_stale_evidence_refresh,
        ),
    )

    if acceptance_custody and acceptance_custody.get("capture_status") == "task_acceptance_captured":
        captured_manifest = Path(str(acceptance_custody["captured_manifest_path"]))
        captured_provenance = Path(str(acceptance_custody["captured_provenance_path"]))
        try:
            manifest_bytes, manifest_terminal_identity = _stable_regular_read(captured_manifest)
            provenance_bytes, provenance_terminal_identity = _stable_regular_read(captured_provenance)
            original_manifest_identity = acceptance_custody["captured_manifest_identity"]
            original_provenance_identity = acceptance_custody["captured_provenance_identity"]
            identity_unchanged = (
                manifest_terminal_identity["device"] == original_manifest_identity["device"]
                and manifest_terminal_identity["inode"] == original_manifest_identity["inode"]
                and provenance_terminal_identity["device"] == original_provenance_identity["device"]
                and provenance_terminal_identity["inode"] == original_provenance_identity["inode"]
            )
            unchanged = (
                identity_unchanged
                and
                _sha256(manifest_bytes) == acceptance_custody["captured_manifest_digest"]
                and len(manifest_bytes) == acceptance_custody["captured_manifest_byte_length"]
                and _sha256(provenance_bytes) == acceptance_custody["captured_provenance_digest"]
                and len(provenance_bytes) == acceptance_custody["captured_provenance_byte_length"]
            )
            acceptance_custody["captured_evidence_unchanged"] = unchanged
            acceptance_custody["terminal_file_identity_status"] = "unchanged" if identity_unchanged else "replaced"
            if unchanged:
                terminal = verify_task_acceptance(captured_manifest, captured_provenance, repo_root=Path(a.workspace_root))
            else:
                terminal = {"status": "task_acceptance_blocked", "reasons": ["captured_acceptance_evidence_changed"]}
        except (OSError, ValueError) as exc:
            acceptance_custody["captured_evidence_unchanged"] = False
            terminal = {"status": "task_acceptance_blocked", "reasons": [f"captured_acceptance_evidence_unreadable:{exc}"]}
            acceptance_custody["terminal_file_identity_status"] = "unreadable"
        acceptance_custody["terminal_verification_status"] = terminal["status"]
        acceptance_custody["terminal_verification_reasons"] = list(terminal.get("reasons", []))
        acceptance_custody["terminal_verification"] = terminal
        for kind in ("manifest", "provenance"):
            original = Path(str(acceptance_custody[f"original_{kind}_path"]))
            exists = original.is_file() and not original.is_symlink()
            acceptance_custody[f"original_{kind}_still_exists"] = exists
            if exists:
                current = original.read_bytes()
                changed = _sha256(current) != acceptance_custody[f"original_{kind}_digest"] or len(current) != acceptance_custody[f"original_{kind}_byte_length"]
            else:
                changed = True
            acceptance_custody[f"original_{kind}_changed_or_disappeared"] = changed
        initial_status = acceptance_custody["initial_verification_status"]
        if terminal["status"] != "task_acceptance_ready" or initial_status != terminal["status"]:
            acceptance_result = terminal

    terminal_directory_custody: dict[str, dict[str, Any]] = {}
    terminal_directory_reasons: list[str] = []
    if invocation_context is not None:
        terminal_directory_custody, terminal_directory_reasons = _terminal_directory_custody(invocation_context)

    if generated_dirty_after_refresh and a.allow_generated_artifact_cleanup:
        decision_status = "generated_artifact_cleanup_incomplete"
        decision_reasons = ["generated_artifacts_remain_after_cleanup", *generated_dirty_after_refresh]
    elif stale_reasons and refresh_status == "required_not_allowed":
        decision_status = "stale_evidence_refresh_required"
        decision_reasons = list(stale_reasons)
    elif refresh_status == "failed":
        decision_status = "stale_evidence_refresh_failed"
        decision_reasons = [refresh_failure_reason or "stale_evidence_refresh_failed"]
    elif not decision_reasons:
        decision_status = landing_result.decision.status
        decision_reasons = list(landing_result.decision.reasons)

    payload = landing_result.to_dict()
    payload["request"] = {
        "title": req.title,
        "intended_commit_title": req.intended_commit_title,
        "phase": req.phase,
        "matrix_json_path": req.matrix_json_path,
        "task_acceptance_manifest": a.task_acceptance_manifest,
    }
    if acceptance_result is not None:
        payload["task_acceptance"] = acceptance_result
    if acceptance_custody is not None:
        payload["task_acceptance_custody"] = acceptance_custody
    payload["dirty_paths"] = [asdict(item) for item in diagnostics_after_refresh]
    payload["dirty_paths_after_cleanup"] = [asdict(item) for item in diagnostics]
    payload["cleanup_actions"] = {k: {"attempted": v[0], "result": v[1], "reason": v[2]} for k, v in cleanup_results.items()}
    payload["runtime"] = {
        "stage_timeout_seconds": a.stage_timeout_seconds,
        "matrix_timeout_seconds": a.matrix_timeout_seconds,
        "overall_timeout_seconds": a.overall_timeout_seconds,
        "stages": [asdict(item) for item in runtime],
        "final_decision": {"status": decision_status, "reasons": decision_reasons},
    }
    # Exact content bindings are semantic evidence; runtime roots are custody metadata only.
    binding_errors = []
    binding_obj = None
    try:
        semantic_status_paths = tuple((line[3:] if len(line) > 3 else line) for line in status_after_refresh if not (line[3:] if len(line) > 3 else line).startswith(("glow/", "pulse/", "artifacts/codex/", "sentientos_data/vow", "sentientos_data/runtime")))
        task_paths = tuple(p for p in (tuple(a.changed_file) + inferred_changed_files + inferred_untracked_task_files) if not p.startswith(("glow/", "pulse/", "artifacts/codex/", "sentientos_data/vow", "sentientos_data/runtime")))
        if not semantic_status_paths and not a.changed_file:
            task_paths = ()
        if a.phase.replace("_", "-") == "pre-commit" and task_paths:
            binding_obj = create_workspace_binding(a.workspace_root, intended_paths=task_paths, intended_commit_title=a.intended_commit_title or a.title or "", focused_test_commands=tuple(a.focused_test_command), targeted_mypy_commands=tuple(a.targeted_mypy_command), matrix_json_path=a.matrix_json_path).to_dict()
            payload["workspace_binding"] = binding_obj
        elif a.pre_commit_finalizer_json:
            pre_payload = json.loads(Path(a.pre_commit_finalizer_json).read_text(encoding="utf-8"))
            workspace_binding = pre_payload.get("workspace_binding", {})
            commit_binding = create_commit_binding(a.workspace_root, workspace_binding=workspace_binding, matrix_json_path=a.matrix_json_path).to_dict()
            verification = verify_commit_matches_workspace(a.workspace_root, workspace_binding, commit_binding).to_dict()
            payload["commit_binding"] = commit_binding
            payload["binding_verification"] = verification
            if verification["status"] != "landing_evidence_binding_ready":
                binding_errors.extend(verification["reasons"])
    except Exception as exc:
        binding_errors.append(str(exc))
    if runtime_error:
        binding_errors.append(runtime_error)
    context_payload = asdict(invocation_context) if invocation_context is not None else None
    child_environment_digest = _sha256(json.dumps(runtime_env, sort_keys=True, separators=(",", ":")).encode())
    payload["runtime_custody"] = {
        "invocation_context": context_payload,
        "child_environment": runtime_env,
        "child_environment_digest": child_environment_digest,
        "process_environment_mutated": False,
        "runtime_error": runtime_error,
        "requested_root": invocation_context.requested_root_custody if invocation_context else None,
        "invocations_parent_path": str(Path(invocation_context.requested_sandbox_root) / "invocations") if invocation_context else None,
        "directory_custody_initial": invocation_context.directory_custody_initial if invocation_context else {},
        "directory_custody_terminal": terminal_directory_custody,
        "mode_enforcement_applicability": "applicable" if os.name == "posix" else "not_applicable",
        "terminal_directory_identity_status": "unchanged" if invocation_context is not None and not terminal_directory_reasons else "blocked",
    }
    payload["evidence_freshness"] = {
        "stale_evidence_reasons": stale_reasons,
        "matrix_execution_mode": "exact_binding_reuse" if exact_matrix_reuse else "executed",
        "reused_matrix_digest": payload.get("workspace_binding", {}).get("matrix_digest") if exact_matrix_reuse else None,
        "reuse_justification": "post-commit exact binding reuse requested with pre-commit finalizer artifact" if exact_matrix_reuse else "matrix executed",
        "stale_evidence_refresh_attempted": refresh_attempted,
        "stale_evidence_refresh_result": refresh_status,
        "refresh_failure_reason": refresh_failure_reason or None,
        "refreshed_matrix_json_path": a.matrix_json_path if refresh_attempted and refresh_status == "succeeded" else None,
        "max_stale_evidence_refreshes": a.max_stale_evidence_refreshes,
        "refresh_stage_runs": refresh_runs,
        "refresh_stages_ran": refresh_stage_names,
        "cleanup_occurred": bool(cleanup_results),
        "cleaned_paths": [path for path, result in cleanup_results.items() if result[1] in {"removed", "restored"}],
        "terminal_cleanup_occurred": bool(terminal_cleanup_results),
        "terminal_cleaned_paths": [path for path, result in terminal_cleanup_results.items() if result[1] in {"removed", "restored"}],
        "rerun_required": rerun_required,
    }
    if binding_errors and decision_status in {"ready_to_commit", "ready_for_pr_metadata"}:
        decision_status = "manual_review_required" if "runtime_root_inside_workspace" in binding_errors else "repair_required_task_caused"
        decision_reasons = binding_errors
    if acceptance_result is not None and acceptance_result.get("status") != "task_acceptance_ready":
        decision_status = "repair_required_task_caused"
        decision_reasons = list(acceptance_result.get("reasons", ["task_acceptance_blocked"]))
    if terminal_directory_reasons:
        decision_status = "repair_required_task_caused"
        decision_reasons = terminal_directory_reasons
    payload["decision"]["status"] = decision_status
    payload["decision"]["reasons"] = decision_reasons
    if a.summary:
        for item in diagnostics_after_refresh[:20]:
            print(
                f"[finalizer] dirty path: {item.git_status} {item.path} "
                f"classification={item.classification} cleanup={item.cleanup_result}"
            )

    _progress(a.progress, f"[finalizer] decision: {decision_status}")
    _emit_and_optionally_write(payload, a.output, a.summary, decision_status)
    return 0 if (a.phase.replace("_", "-") == "pre-commit" and decision_status == "ready_to_commit") or (a.phase.replace("_", "-") in {"post-commit", "pr-metadata"} and decision_status == "ready_for_pr_metadata") else 1


if __name__ == "__main__":
    raise SystemExit(main())
