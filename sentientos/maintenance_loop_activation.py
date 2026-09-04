"""Operator-owned activation checks for the bounded maintenance watchdog.

This module creates custody directories and evidence only.  It never installs a
scheduler, authenticates a client, or performs Git/publication mutations.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sentientos import maintenance_commit_publication as landing
from sentientos import maintenance_local_codex_foreman as foreman
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_task_authority_lease as authority
from sentientos import maintenance_validation_controller as validation
from sentientos.local_model_production_commissioning import load_activation

ACTIVATION_REPORT_SCHEMA = "sentientos.maintenance_loop_activation_report:v1"
ACTIVATION_RECEIPT_SCHEMA = "sentientos.maintenance_loop_activation_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _safe_external(path: str | Path, repository_root: str | Path) -> Path:
    raw = Path(path).expanduser()
    repo = Path(repository_root).resolve(strict=True)
    if raw.is_symlink() or any(part.is_symlink() for part in [raw, *raw.parents] if part.exists()):
        raise ValueError("custody_root_symlink")
    resolved = raw.resolve(strict=False)
    git = (repo / ".git").resolve(strict=True)
    if _within(resolved, repo) or _within(resolved, git):
        raise ValueError("custody_root_inside_repository")
    return resolved


def init_roots(repository_root: str | Path, roots: Mapping[str, str | Path]) -> dict[str, Any]:
    if set(roots) != {"state", "workspace", "scratch", "inbox"}:
        raise ValueError("explicit_roots_required")
    resolved = {name: _safe_external(path, repository_root) for name, path in roots.items()}
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("conflicting_root_identity")
    records = []
    for name in sorted(resolved):
        path = resolved[name]
        if path.exists():
            if path.is_symlink() or not path.is_dir():
                raise ValueError("unsafe_existing_root")
            status = "verified"
        else:
            path.mkdir(parents=True, mode=0o700)
            status = "created"
        if os.name == "posix":
            mode = stat.S_IMODE(os.lstat(path).st_mode)
            if mode != 0o700:
                raise ValueError("custody_root_permissions")
        records.append({"name": name, "path": str(path), "status": status})
    result = {"schema_version": "sentientos.maintenance_activation_roots:v1", "status": "roots_ready", "roots": records}
    result["roots_digest"] = digest(result)
    return result


def _artifact(value: str | Path | Mapping[str, Any]) -> str | dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value).expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise ValueError("configuration_artifact_invalid")
    return str(path)


def render_config(output: str | Path, *, repository_root: str | Path, state_root: str | Path,
                  workspace_root: str | Path, scratch_root: str | Path, inbox_root: str | Path,
                  standing_grant: str | Path | Mapping[str, Any], selector_policy: str | Path | Mapping[str, Any],
                  foreman_policy: str | Path | Mapping[str, Any], validation_policy: str | Path | Mapping[str, Any],
                  landing_policy: str | Path | Mapping[str, Any], base_sha: str, tracked_base_ref: str,
                  implementation_backend: str, commissioned_local_activation: str | Path | None,
                  maximum_actions: int, maximum_wall_clock_seconds: int,
                  publication_retry_backoff_seconds: int, stop_marker: str | Path | None = None,
                  control_journal: str | Path | None = None, base_cursor_journal: str | Path | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {"schema_version": watchdog.CONFIG_SCHEMA,
        "repository_root": str(Path(repository_root).resolve(strict=True)), "state_root": str(Path(state_root).resolve(strict=True)),
        "workspace_root": str(Path(workspace_root).resolve(strict=True)), "scratch_root": str(Path(scratch_root).resolve(strict=True)),
        "candidate_inbox_roots": [str(Path(inbox_root).resolve(strict=True))], "standing_grant": _artifact(standing_grant),
        "selector_policy": _artifact(selector_policy), "foreman_policy": _artifact(foreman_policy),
        "validation_policy": _artifact(validation_policy), "landing_policy": _artifact(landing_policy),
        "implementation_backend": implementation_backend,
        "commissioned_local_activation": (str(Path(commissioned_local_activation).expanduser().resolve(strict=False)) if commissioned_local_activation else None),
        "commissioned_local_activation_digest": (digest_bytes(Path(commissioned_local_activation).expanduser().read_bytes()) if commissioned_local_activation else None),
        "maximum_active_tasks": 1, "maximum_actions": maximum_actions,
        "maximum_wall_clock_seconds": maximum_wall_clock_seconds,
        "publication_retry_backoff_seconds": publication_retry_backoff_seconds,
        "base_sha": base_sha, "tracked_base_ref": tracked_base_ref}
    for key, value in (("stop_marker", stop_marker), ("control_journal", control_journal), ("base_cursor_journal", base_cursor_journal)):
        if value is not None:
            config[key] = str(Path(value).expanduser().resolve(strict=False))
    config = watchdog.validate_config(config)
    data = canonical_bytes(config) + b"\n"
    destination = Path(output)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != data:
            raise ValueError("configuration_output_conflict")
        write_status = "reused"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        write_status = "created"
    return {"schema_version": "sentientos.maintenance_activation_render:v1", "status": "configuration_ready",
            "output_path": str(destination.resolve()), "configuration_digest": config["config_digest"],
            "bytes_digest": digest_bytes(data), "write_status": write_status}


def run_argv(config_path: str | Path, evaluation_time: str) -> list[str]:
    repo = Path(watchdog.load_config(config_path)["repository_root"])
    return [sys.executable, str(repo / "scripts" / "maintenance_loop_watchdog.py"),
            "--config", str(Path(config_path).resolve()), "--evaluation-time", evaluation_time, "run-bounded"]


def _load(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return cast(dict[str, Any], json.loads(Path(str(value)).read_text(encoding="utf-8")))


def doctor_live(config_path: str | Path, *, evaluation_time: str, probe_remote: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def check(name: str, ok: bool, detail: str = "", warning: bool = False) -> None:
        checks.append({"check": name, "status": "warning" if warning else "passed" if ok else "blocked", "detail": detail})
    try:
        cfg = watchdog.load_config(config_path); check("configuration", True, cfg["config_digest"])
    except Exception as exc:
        cfg = {}; check("configuration", False, type(exc).__name__)
    if cfg:
        repo = Path(cfg["repository_root"]); git = shutil.which("git")
        def git_run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([git or "git", *args], cwd=repo, text=True, capture_output=True, check=False)
        top = git_run("rev-parse", "--show-toplevel"); check("repository_identity", top.returncode == 0 and Path(top.stdout.strip()).resolve() == repo)
        clean = git_run("status", "--porcelain=v1", "--untracked-files=all"); check("canonical_checkout_clean", clean.returncode == 0 and not clean.stdout)
        head = git_run("rev-parse", "HEAD").stdout.strip(); base = str(cfg["base_sha"])
        relation = git_run("merge-base", "--is-ancestor", base, head)
        check("base_sha_relationship", len(base) == 40 and relation.returncode == 0, "head=" + head)
        ref = git_run("rev-parse", "--verify", str(cfg["tracked_base_ref"])); check("tracked_base_ref", ref.returncode == 0)
        for key in ("state_root", "workspace_root", "scratch_root"):
            try:
                p = _safe_external(cfg[key], repo); mode = stat.S_IMODE(os.lstat(p).st_mode)
                check(key, p.is_dir() and not p.is_symlink() and (os.name != "posix" or mode == 0o700))
            except Exception as exc: check(key, False, type(exc).__name__)
        inbox_ok = True
        for item in cfg["candidate_inbox_roots"]:
            try: inbox_ok &= _safe_external(item, repo).is_dir() and os.access(item, os.R_OK | os.X_OK)
            except Exception: inbox_ok = False
        check("candidate_inbox", inbox_ok)
        try:
            grant = _load(cfg["standing_grant"]); gv = authority.verify_grant(grant, evaluation_time=evaluation_time)
            compatible = grant.get("repository_identity") in {str(repo), repo.name} and grant.get("allowed_base_sha") == base
            budgets = all(int(grant.get(k, 0)) > 0 for k in ("maximum_file_count", "maximum_changed_line_count", "maximum_implementation_seconds", "maximum_validation_seconds", "maximum_wall_clock_seconds", "maximum_attempts"))
            check("standing_grant", gv["status"] == "grant_valid" and compatible and budgets and bool(grant.get("landing_terms")), ",".join(gv["reason_codes"]))
        except Exception as exc: grant = {}; check("standing_grant", False, type(exc).__name__)
        try:
            selector = _load(cfg["selector_policy"]); allowed = set(selector.get("allowed_authority_classes", grant.get("allowed_authority_classes", ())))
            check("selector_policy", not allowed - set(grant.get("allowed_authority_classes", ())))
        except Exception as exc: check("selector_policy", False, type(exc).__name__)
        try:
            fc = foreman.LocalCodexForemanConfig.from_mapping(_load(cfg["foreman_policy"]))
            if cfg["implementation_backend"] == "local_codex":
                probe = foreman.probe_local_codex_cli(fc)
                check("implementation_backend", probe["status"] == "capability_probe_ready", "local_codex:" + probe["status"])
                home = fc.codex_home
                check("codex_home", home.exists() and home.is_dir() and not home.is_symlink() and not _within(home.resolve(), repo), str(home))
            else:
                path = Path(str(cfg["commissioned_local_activation"]))
                if digest_bytes(path.read_bytes()) != cfg["commissioned_local_activation_digest"]:
                    raise ValueError("commissioned_local_activation_digest_mismatch")
                model, _ = load_activation(path)
                try: detail = json.dumps(model.active_identity.to_dict(), sort_keys=True)
                finally: model.close()
                check("implementation_backend", True, "commissioned_local:" + detail)
                check("codex_home", True, "not_applicable")
            check("git_executable", fc.git_executable.exists() and subprocess.run([str(fc.git_executable), "--version"], capture_output=True).returncode == 0)
        except Exception as exc: check("implementation_backend", False, type(exc).__name__); check("codex_home", False, "unavailable"); fc = None
        try: validation.ValidationPolicy.from_mapping(_load(cfg["validation_policy"])); check("validation_policy", True)
        except Exception as exc: check("validation_policy", False, type(exc).__name__)
        try:
            lp = landing.seal_landing_policy(_load(cfg["landing_policy"])); client = lp.get("publication_client_executable")
            check("landing_policy", True); check("publication_client", bool(client and Path(str(client)).exists()))
            if probe_remote:
                remote = str(grant.get("landing_terms", {}).get("remote_name", "origin")); remote_ref = str(grant.get("landing_terms", {}).get("base_ref", cfg["tracked_base_ref"]))
                cp = git_run("ls-remote", remote, remote_ref); check("remote_probe", cp.returncode == 0 and bool(cp.stdout.strip()))
            else: check("remote_probe", True, "not_requested")
        except Exception as exc: check("landing_policy", False, type(exc).__name__); check("publication_client", False)
        scanned = watchdog.scan(cfg, evaluation_time=evaluation_time)
        check("stop_marker", not scanned["stop_marker_present"]); check("control_state", not scanned["control"].get("paused"))
        active = scanned["observations"]["active_tasks"]; check("active_task_state", not active)
        lock = Path(cfg["state_root"]) / "watchdog.lock"; lock.touch(exist_ok=True)
        try:
            with lock.open("r+") as handle: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(handle, fcntl.LOCK_UN)
            check("global_lock", True)
        except BlockingIOError: check("global_lock", False, "busy")
        argv = run_argv(config_path, evaluation_time); check("watchdog_cli", Path(argv[1]).is_file())
    blocked = any(c["status"] == "blocked" for c in checks); warned = any(c["status"] == "warning" for c in checks)
    status = "activation_blocked" if blocked else "activation_warning" if warned else "activation_ready"
    report = {"schema_version": ACTIVATION_REPORT_SCHEMA, "status": status, "evaluation_time": evaluation_time,
              "config_digest": cfg.get("config_digest"), "checks": checks,
              "run_argv": run_argv(config_path, evaluation_time) if cfg else []}
    report["report_digest"] = digest(report)
    return report


def _receipt_path(cfg: Mapping[str, Any]) -> Path:
    return Path(str(cfg["state_root"])) / "maintenance_activation_receipts.jsonl"


def smoke_idle(config_path: str | Path, *, evaluation_time: str) -> dict[str, Any]:
    report = doctor_live(config_path, evaluation_time=evaluation_time)
    if report["status"] != "activation_ready":
        raise ValueError("activation_not_ready")
    cfg = watchdog.load_config(config_path)
    if any(Path(p).iterdir() for p in cfg["candidate_inbox_roots"]): raise ValueError("candidate_inbox_not_empty")
    before = watchdog.scan(cfg, evaluation_time=evaluation_time)
    cp = subprocess.run(run_argv(config_path, evaluation_time), cwd=cfg["repository_root"], text=True, capture_output=True, shell=False, check=False)
    try: outcome = json.loads(cp.stdout)
    except ValueError as exc: raise ValueError("watchdog_output_invalid") from exc
    terminal = outcome.get("status") == "idle" or (outcome.get("results") and outcome["results"][-1].get("decision", {}).get("status") == "idle")
    if cp.returncode or not terminal: raise ValueError("idle_smoke_failed")
    receipt_path = _receipt_path(cfg); prior = inspect_activation(receipt_path, missing_ok=True)["receipts"]
    receipt = {"schema_version": ACTIVATION_RECEIPT_SCHEMA, "sequence": len(prior) + 1, "recorded_at": evaluation_time,
        "previous_receipt_digest": prior[-1]["receipt_digest"] if prior else ZERO_DIGEST,
        "config_digest": cfg["config_digest"], "doctor_report_digest": report["report_digest"], "watchdog_argv": run_argv(config_path, evaluation_time),
        "watchdog_result_digest": digest(outcome), "terminal_status": "idle", "candidate_admission_count": 0,
        "implementation_process_count": 0, "validation_command_count": 0, "commit_count": 0,
        "remote_operation_count": 0, "publication_count": 0, "operator_message_relay_count": 0}
    receipt["receipt_digest"] = digest(receipt)
    with receipt_path.open("ab") as handle: handle.write(canonical_bytes(receipt) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return {"schema_version": "sentientos.maintenance_activation_smoke:v1", "status": "idle_smoke_proven",
            "receipt_digest": receipt["receipt_digest"], "receipt_path": str(receipt_path), "watchdog_result": outcome}


def inspect_activation(receipt_path: str | Path, *, missing_ok: bool = False) -> dict[str, Any]:
    path = Path(receipt_path)
    if not path.exists():
        if missing_ok: return {"status": "activation_receipts_ready", "receipts": []}
        raise ValueError("activation_receipts_missing")
    receipts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    previous = ZERO_DIGEST
    for index, receipt in enumerate(receipts, 1):
        claimed = receipt.get("receipt_digest")
        if receipt.get("schema_version") != ACTIVATION_RECEIPT_SCHEMA or receipt.get("sequence") != index or receipt.get("previous_receipt_digest") != previous or claimed != digest({k: v for k, v in receipt.items() if k != "receipt_digest"}):
            raise ValueError("activation_receipt_integrity_failed")
        previous = claimed
    return {"schema_version": "sentientos.maintenance_activation_receipt_inspection:v1", "status": "activation_receipts_ready", "receipts": receipts, "head_digest": previous}


__all__ = ["init_roots", "render_config", "doctor_live", "smoke_idle", "run_argv", "inspect_activation"]
