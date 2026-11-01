from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping, Protocol

from sentientos import artifact_catalog
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize
from sentientos.work_plan import WorkPlanError, load_work_plan, load_work_run


@dataclass(frozen=True, slots=True)
class CompletionResult:
    schema_version: int
    goal_id: str
    check_name: str
    checked_at: str
    done: bool
    progress: float
    status: str
    evidence_paths: tuple[str, ...]
    notes: tuple[str, ...]
    reason_stack: tuple[str, ...]
    evidence_digest: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "goal_id": self.goal_id,
            "check_name": self.check_name,
            "checked_at": self.checked_at,
            "done": self.done,
            "progress": round(max(0.0, min(1.0, self.progress)), 3),
            "status": self.status,
            "evidence_paths": list(self.evidence_paths),
            "notes": list(self.notes),
            "reason_stack": list(self.reason_stack),
            **({"evidence_digest": self.evidence_digest} if self.evidence_digest else {}),
        }


@dataclass(frozen=True, slots=True)
class CompletionContext:
    repo_root: Path
    goal_id: str
    operating_mode: str
    pressure_level: int
    posture: str
    quarantine_active: bool
    risk_budget_summary: dict[str, object]
    work_run_id: str | None = None
    work_run_evidence_digest: str | None = None

    def latest(self, kind: str) -> dict[str, object] | None:
        return artifact_catalog.latest(self.repo_root, kind)

    def latest_for_goal(self, kind: str) -> dict[str, object] | None:
        rows = artifact_catalog.recent(self.repo_root, kind, limit=100)
        for row in reversed(rows):
            raw_links = row.get("links")
            links: dict[str, object] = raw_links if isinstance(raw_links, dict) else {}
            goal_ids = links.get("goal_ids")
            if (str(links.get("goal_id") or "") == self.goal_id
                    or isinstance(goal_ids, list) and self.goal_id in goal_ids):
                return row
        return None

    def load_normalized(self, entry: dict[str, object] | None, *, fallback_schema: str | None = None) -> tuple[dict[str, object] | None, tuple[str, ...]]:
        if entry is None:
            return (None, ("artifact_missing",))
        payload = artifact_catalog.load_catalog_artifact(self.repo_root, entry)
        if payload is None:
            return (None, ("artifact_missing",))
        schema_name = str(entry.get("schema_name") or fallback_schema or "")
        if not schema_name:
            return (payload, ())
        try:
            normalized, warnings = normalize(payload, schema_name)
        except SchemaCompatibilityError as exc:
            return (None, (str(exc),))
        reasons = tuple(sorted(str(w) for w in warnings))
        return (normalized, reasons)


class CompletionCheck(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def required_kinds(self) -> tuple[str, ...]: ...

    def eval(self, ctx: CompletionContext) -> CompletionResult: ...


class _ForgeLastRunOkCheck:
    name = "check_forge_last_run_ok"
    required_kinds = ("work_run",)

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        entry = ctx.latest_for_goal("work_run") or ctx.latest("work_run")
        now = _iso_now()
        if entry is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        # Work runs have their own strict loader and are not a schema_registry
        # document. The executor passes the exact persisted run identity after
        # validating it against canonical plan evidence.
        payload = artifact_catalog.load_catalog_artifact(ctx.repo_root, entry)
        reasons: tuple[str, ...] = () if payload is not None else ("artifact_missing",)
        run_payload: dict[str, object] = payload if isinstance(payload, dict) else {}
        raw_summary = entry.get("summary")
        summary: dict[str, object] = raw_summary if isinstance(raw_summary, dict) else {}
        status = str(run_payload.get("status") or summary.get("status") or "unknown")
        gate_failures_value = summary.get("integrity_gate_failures", 0)
        gate_failures = gate_failures_value if isinstance(gate_failures_value, int) else 0
        evidence_digest = _validated_run_evidence(ctx, entry, run_payload)
        bound = evidence_digest is not None
        done = status == "ok" and gate_failures == 0 and bound
        if not bound:
            reasons = tuple(sorted(set(reasons + ("run_evidence_binding_missing",))))
        reason_stack = tuple(sorted(set(reasons + (() if done else ("verify_failed",)))))
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.5, "ok" if done else "blocked", _evidence(entry), (), reason_stack, evidence_digest)


class _IntegrityBaselineCheck:
    name = "check_integrity_baseline_ok"
    required_kinds = ("verify_result",)

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        row = ctx.latest("verify_result")
        now = _iso_now()
        if row is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        payload, reasons = ctx.load_normalized(row, fallback_schema=SchemaName.FORGE_REPORT)
        p = payload or {}
        checks = [
            bool(p.get("receipt_chain_ok", False)),
            (not bool(p.get("anchors_enabled", False)) or bool(p.get("receipt_anchors_ok", False))),
            (not bool(p.get("audit_chain_enabled", False)) or bool(p.get("audit_chain_ok", False))),
            (not bool(p.get("rollup_signature_enabled", False)) or bool(p.get("rollup_signature_ok", False))),
        ]
        passed = sum(1 for x in checks if x)
        done = passed == len(checks)
        reason_stack = list(reasons)
        if not done:
            reason_stack.append("verify_failed")
        return _result(ctx.goal_id, self.name, now, done, passed / float(len(checks)), "ok" if done else "blocked", _evidence(row), (), tuple(sorted(set(reason_stack))))


class _FederationCheck:
    name = "check_federation_ok"
    required_kinds = ("federation_snapshot",)

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        row = ctx.latest("federation_snapshot")
        now = _iso_now()
        if row is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        payload, reasons = ctx.load_normalized(row, fallback_schema=SchemaName.INTEGRITY_SNAPSHOT)
        summary = _mapping_or_empty(row.get("summary"))
        status = str((payload or {}).get("status") or summary.get("status") or "unknown")
        allow_div = os.getenv("SENTIENTOS_FEDERATION_ALLOW_DIVERGENCE", "0") == "1"
        done = status == "ok" or allow_div
        reason_stack = list(reasons)
        if not done:
            reason_stack.append("verify_failed")
        if allow_div:
            reason_stack.append("allow_divergence")
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.4, "ok" if done else "blocked", _evidence(row), (), tuple(sorted(set(reason_stack))))


class _WitnessesCheck:
    name = "check_witnesses_ok"
    required_kinds = ("witness_publish",)

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        row = ctx.latest("witness_publish")
        now = _iso_now()
        if row is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        payload = _mapping_or_empty(
            artifact_catalog.load_catalog_artifact(ctx.repo_root, row)
        )
        witness_status = str(payload.get("witness_status") or "unknown")
        rollup_status = str(payload.get("rollup_witness_status") or witness_status)
        anchor_ok = witness_status in {"ok", "disabled"}
        rollup_ok = rollup_status in {"ok", "disabled"}
        done = anchor_ok and rollup_ok
        reasons: list[str] = []
        if not anchor_ok or not rollup_ok:
            reasons.append("verify_failed")
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.5, "ok" if done else "blocked", _evidence(row), (), tuple(sorted(reasons)))


class _MypyForgeCheck:
    name = "check_mypy_forge_ok"
    required_kinds = ("verify_result", "work_run")

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        row = ctx.latest("verify_result")
        now = _iso_now()
        if row is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        payload = artifact_catalog.load_catalog_artifact(ctx.repo_root, row) or {}
        done = bool(payload.get("mypy_forge_ok", False))
        if not done:
            run = ctx.latest_for_goal("work_run")
            if run is not None:
                summary = _mapping_or_empty(run.get("summary"))
                done = bool(summary.get("included_mypy_forge", False)) and str(summary.get("status") or "") == "ok"
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.3, "ok" if done else "unknown", _evidence(row), (), (() if done else ("verify_failed",)))


_REGISTRY: dict[str, CompletionCheck] = {
    "check_forge_last_run_ok": _ForgeLastRunOkCheck(),
    "check_integrity_baseline_ok": _IntegrityBaselineCheck(),
    "check_federation_ok": _FederationCheck(),
    "check_witnesses_ok": _WitnessesCheck(),
    "check_mypy_forge_ok": _MypyForgeCheck(),
}


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    """Treat malformed persisted JSON summaries as absent metadata."""
    return value if isinstance(value, Mapping) else {}


def get_check(name: str) -> CompletionCheck | None:
    return _REGISTRY.get(name)


def eval_check(name: str, ctx: CompletionContext) -> CompletionResult:
    check = get_check(name)
    now = _iso_now()
    if check is None:
        return _result(ctx.goal_id, name, now, False, 0.0, "error", (), (), ("unknown_check",))
    result = check.eval(ctx)
    if not result.done or result.evidence_digest is not None:
        return result
    evidence_digest = _completion_evidence_digest(ctx, result)
    if evidence_digest is None:
        return _result(
            result.goal_id, result.check_name, result.checked_at, False,
            result.progress, "blocked", result.evidence_paths, result.notes,
            tuple(sorted(set(result.reason_stack + (
                "completion_evidence_binding_missing",)))),
        )
    return _result(
        result.goal_id, result.check_name, result.checked_at, True,
        result.progress, result.status, result.evidence_paths, result.notes,
        result.reason_stack, evidence_digest,
    )


def _completion_evidence_digest(
    ctx: CompletionContext, result: CompletionResult,
) -> str | None:
    """Bind non-run completion results to the exact referenced artifact bytes."""
    root = ctx.repo_root.resolve()
    artifacts: list[dict[str, str]] = []
    for relative_path in result.evidence_paths:
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            return None
        content_hasher = hashlib.sha256()
        try:
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    content_hasher.update(chunk)
        except OSError:
            return None
        content_digest = content_hasher.hexdigest()
        artifacts.append({"path": relative_path, "sha256": content_digest})
    if not artifacts:
        return None
    binding = {
        "schema": "sentientos.goal_completion_evidence.v1",
        "goal_id": result.goal_id,
        "check_name": result.check_name,
        "done": result.done,
        "status": result.status,
        "progress": round(max(0.0, min(1.0, result.progress)), 3),
        "reason_stack": list(result.reason_stack),
        "artifacts": artifacts,
    }
    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def persist_completion_result(repo_root: Path, result: CompletionResult, *, work_run_id: str | None = None, incident_id: str | None = None) -> str:
    root = repo_root.resolve()
    ts = _safe_ts(result.checked_at)
    path = root / "glow/forge/completion_checks" / f"check_{ts}_{result.goal_id}_{result.check_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "goal_id": result.goal_id,
        "check_name": result.check_name,
        "done": result.done,
        "status": result.status,
        "progress": result.progress,
    }
    pulse_path = root / "pulse/completion_checks.jsonl"
    pulse_path.parent.mkdir(parents=True, exist_ok=True)
    with pulse_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"checked_at": result.checked_at, **summary, "path": str(path.relative_to(root))}, sort_keys=True) + "\n")
    artifact_catalog.append_catalog_entry(
        root,
        kind="completion_check",
        artifact_id=f"{result.goal_id}:{result.check_name}:{ts}",
        relative_path=str(path.relative_to(root)),
        schema_name="goal_completion_result",
        schema_version=result.schema_version,
        links={"goal_id": result.goal_id, "check_name": result.check_name, "work_run_id": work_run_id, "incident_id": incident_id},
        summary=summary,
        ts=result.checked_at,
    )
    return str(path.relative_to(root))


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validated_run_evidence(
    ctx: CompletionContext,
    run_entry: dict[str, object],
    payload: dict[str, object],
) -> str | None:
    """Reconstruct a persisted run through its canonical plan and evidence."""
    if not isinstance(payload, dict) or payload.get("schema_version") != 3:
        return None
    run_id = payload.get("run_id")
    plan_id = payload.get("plan_id")
    digest = payload.get("evidence_digest")
    if (not isinstance(run_id, str) or not isinstance(plan_id, str)
            or not isinstance(digest, str) or not _valid_digest(digest)
            or run_entry.get("id") != run_id
            or (ctx.work_run_id is not None and ctx.work_run_id != run_id)
            or (ctx.work_run_evidence_digest is not None
                and ctx.work_run_evidence_digest != digest)):
        return None
    plan_entries = [
        row for row in artifact_catalog.recent(ctx.repo_root, "work_plan", limit=1000)
        if row.get("id") == plan_id
    ]
    plan_paths = {row.get("path") for row in plan_entries}
    if not plan_entries or len(plan_paths) != 1:
        return None
    relative_path = next(iter(plan_paths))
    if not isinstance(relative_path, str) or not relative_path:
        return None
    root = ctx.repo_root.resolve()
    plan_path = (root / relative_path).resolve()
    if not plan_path.is_relative_to(root):
        return None
    try:
        plan = load_work_plan(plan_path)
        if plan.plan_id != plan_id or ctx.goal_id not in plan.selected_goals:
            return None
        verified = load_work_run(root, plan, created_at=plan.created_at)
    except (WorkPlanError, OSError, ValueError):
        return None
    if (verified is None or verified.schema_version != 3
            or verified.run_id != run_id or verified.status != payload.get("status")
            or verified.evidence_digest != digest):
        return None
    return digest


def _result(goal_id: str, check_name: str, checked_at: str, done: bool, progress: float, status: str, evidence_paths: tuple[str, ...], notes: tuple[str, ...], reason_stack: tuple[str, ...], evidence_digest: str | None = None) -> CompletionResult:
    return CompletionResult(
        schema_version=2 if evidence_digest else 1,
        goal_id=goal_id,
        check_name=check_name,
        checked_at=checked_at,
        done=done,
        progress=round(max(0.0, min(1.0, progress)), 3),
        status=status,
        evidence_paths=tuple(sorted(set(evidence_paths))),
        notes=tuple(sorted(set(notes))),
        reason_stack=tuple(sorted(set(reason_stack))),
        evidence_digest=evidence_digest,
    )


def _evidence(entry: dict[str, object]) -> tuple[str, ...]:
    path = str(entry.get("path") or "")
    return (path,) if path else ()


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


__all__ = [
    "CompletionCheck",
    "CompletionContext",
    "CompletionResult",
    "eval_check",
    "get_check",
    "persist_completion_result",
]
