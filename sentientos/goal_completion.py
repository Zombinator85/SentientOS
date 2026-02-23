from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Protocol

from sentientos import artifact_catalog
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize


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

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "goal_id": self.goal_id,
            "check_name": self.check_name,
            "checked_at": self.checked_at,
            "done": self.done,
            "progress": round(max(0.0, min(1.0, self.progress)), 3),
            "status": self.status,
            "evidence_paths": list(self.evidence_paths),
            "notes": list(self.notes),
            "reason_stack": list(self.reason_stack),
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

    def latest(self, kind: str) -> dict[str, object] | None:
        return artifact_catalog.latest(self.repo_root, kind)

    def latest_for_goal(self, kind: str) -> dict[str, object] | None:
        rows = artifact_catalog.recent(self.repo_root, kind, limit=100)
        for row in reversed(rows):
            links = row.get("links") if isinstance(row.get("links"), dict) else {}
            if str(links.get("goal_id") or "") == self.goal_id:
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
    name: str
    required_kinds: tuple[str, ...]

    def eval(self, ctx: CompletionContext) -> CompletionResult: ...


class _ForgeLastRunOkCheck:
    name = "check_forge_last_run_ok"
    required_kinds = ("work_run",)

    def eval(self, ctx: CompletionContext) -> CompletionResult:
        entry = ctx.latest_for_goal("work_run") or ctx.latest("work_run")
        now = _iso_now()
        if entry is None:
            return _result(ctx.goal_id, self.name, now, False, 0.0, "unknown", (), (), ("artifact_missing",))
        payload, reasons = ctx.load_normalized(entry)
        summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
        status = str((payload or {}).get("status") or summary.get("status") or "unknown")
        gate_failures = int(summary.get("integrity_gate_failures", 0)) if isinstance(summary.get("integrity_gate_failures"), int) else 0
        done = status == "ok" and gate_failures == 0
        reason_stack = tuple(sorted(set(reasons + (() if done else ("verify_failed",)))))
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.5, "ok" if done else "blocked", _evidence(entry), (), reason_stack)


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
        status = str((payload or {}).get("status") or (row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("status") or "unknown")
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
        payload = artifact_catalog.load_catalog_artifact(ctx.repo_root, row) or {}
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
                summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
                done = bool(summary.get("included_mypy_forge", False)) and str(summary.get("status") or "") == "ok"
        return _result(ctx.goal_id, self.name, now, done, 1.0 if done else 0.3, "ok" if done else "unknown", _evidence(row), (), (() if done else ("verify_failed",)))


_REGISTRY: dict[str, CompletionCheck] = {
    "check_forge_last_run_ok": _ForgeLastRunOkCheck(),
    "check_integrity_baseline_ok": _IntegrityBaselineCheck(),
    "check_federation_ok": _FederationCheck(),
    "check_witnesses_ok": _WitnessesCheck(),
    "check_mypy_forge_ok": _MypyForgeCheck(),
}


def get_check(name: str) -> CompletionCheck | None:
    return _REGISTRY.get(name)


def eval_check(name: str, ctx: CompletionContext) -> CompletionResult:
    check = get_check(name)
    now = _iso_now()
    if check is None:
        return _result(ctx.goal_id, name, now, False, 0.0, "error", (), (), ("unknown_check",))
    return check.eval(ctx)


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
        schema_version=1,
        links={"goal_id": result.goal_id, "check_name": result.check_name, "work_run_id": work_run_id, "incident_id": incident_id},
        summary=summary,
        ts=result.checked_at,
    )
    return str(path.relative_to(root))


def _result(goal_id: str, check_name: str, checked_at: str, done: bool, progress: float, status: str, evidence_paths: tuple[str, ...], notes: tuple[str, ...], reason_stack: tuple[str, ...]) -> CompletionResult:
    return CompletionResult(
        schema_version=1,
        goal_id=goal_id,
        check_name=check_name,
        checked_at=checked_at,
        done=done,
        progress=round(max(0.0, min(1.0, progress)), 3),
        status=status,
        evidence_paths=tuple(sorted(set(evidence_paths))),
        notes=tuple(sorted(set(notes))),
        reason_stack=tuple(sorted(set(reason_stack))),
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
