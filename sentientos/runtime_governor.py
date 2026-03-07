from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque

from sentientos.audit_trust_runtime import evaluate_audit_trust, write_audit_trust_artifacts
from sentientos.federated_governance import get_controller as get_federated_governance_controller
from sentientos.pulse_trust_epoch import get_manager as get_trust_epoch_manager


@dataclass(frozen=True)
class PressureSnapshot:
    cpu: float
    io: float
    thermal: float
    gpu: float
    composite: float
    sampled_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "cpu": self.cpu,
            "io": self.io,
            "thermal": self.thermal,
            "gpu": self.gpu,
            "composite": self.composite,
            "sampled_at": self.sampled_at,
        }


@dataclass(frozen=True)
class GovernorDecision:
    action_class: str
    allowed: bool
    mode: str
    reason: str
    subject: str
    scope: str
    origin: str
    sampled_pressure: PressureSnapshot
    reason_hash: str
    correlation_id: str
    action_priority: int
    action_family: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action_class": self.action_class,
            "allowed": self.allowed,
            "mode": self.mode,
            "reason": self.reason,
            "subject": self.subject,
            "scope": self.scope,
            "origin": self.origin,
            "sampled_pressure": self.sampled_pressure.to_dict(),
            "reason_hash": self.reason_hash,
            "correlation_id": self.correlation_id,
            "action_priority": self.action_priority,
            "action_family": self.action_family,
        }


@dataclass(frozen=True)
class ActionProfile:
    action_class: str
    priority: int
    family: str
    local_safety: bool
    deferrable: bool


@dataclass(frozen=True)
class PostureRuleEvaluation:
    dimension: str
    reason: str
    restriction_class: str
    blocks: bool
    precedence: int
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "reason": self.reason,
            "restriction_class": self.restriction_class,
            "blocks": self.blocks,
            "precedence": self.precedence,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RuntimePosture:
    effective_posture: str
    dominant_dimension: str
    dominant_reason: str
    dominant_restriction_class: str
    enforce_block: bool
    escalation_ladder: list[str]
    active_dimensions: dict[str, object]
    reason_chain: list[PostureRuleEvaluation]

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_posture": self.effective_posture,
            "dominant_dimension": self.dominant_dimension,
            "dominant_reason": self.dominant_reason,
            "dominant_restriction_class": self.dominant_restriction_class,
            "enforce_block": self.enforce_block,
            "escalation_ladder": list(self.escalation_ladder),
            "active_dimensions": dict(self.active_dimensions),
            "reason_chain": [item.to_dict() for item in self.reason_chain],
        }


class RuntimeGovernor:
    """Deterministic admissibility layer for runtime control-plane actions."""

    def __init__(self) -> None:
        self._mode = os.getenv("SENTIENTOS_GOVERNOR_MODE", "shadow").strip().lower()
        if self._mode not in {"shadow", "advisory", "enforce"}:
            self._mode = "shadow"
        self._root = Path(os.getenv("SENTIENTOS_GOVERNOR_ROOT", "/glow/governor"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._repo_root = Path(os.getenv("SENTIENTOS_REPO_ROOT", Path.cwd())).resolve()
        self._decisions_path = self._root / "decisions.jsonl"
        self._pressure_path = self._root / "pressure.jsonl"
        self._observability_path = self._root / "observability.jsonl"
        self._budget_path = self._root / "storm_budget.json"
        self._rollup_path = self._root / "rollup.json"

        # budgets
        self._restart_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_RESTART_WINDOW_SECONDS", 300))
        self._repair_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_REPAIR_WINDOW_SECONDS", 600))
        self._federated_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_WINDOW_SECONDS", 120))
        self._critical_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_CRITICAL_WINDOW_SECONDS", 120))
        self._task_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_TASK_WINDOW_SECONDS", 120))
        self._amendment_window = timedelta(seconds=self._env_int("SENTIENTOS_GOVERNOR_AMENDMENT_WINDOW_SECONDS", 300))

        self._restart_limit = self._env_int("SENTIENTOS_GOVERNOR_RESTART_LIMIT", 3)
        self._repair_limit = self._env_int("SENTIENTOS_GOVERNOR_REPAIR_LIMIT", 5)
        self._federated_limit = self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_LIMIT", 20)
        self._critical_limit = self._env_int("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", 50)
        self._task_limit = self._env_int("SENTIENTOS_GOVERNOR_TASK_LIMIT", 128)
        self._amendment_limit = self._env_int("SENTIENTOS_GOVERNOR_AMENDMENT_LIMIT", 16)

        self._contention_window = timedelta(
            seconds=self._env_int("SENTIENTOS_GOVERNOR_CONTENTION_WINDOW_SECONDS", 90)
        )
        self._contention_limit = self._env_int("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", 24)
        self._recovery_reserved_slots = self._env_int("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", 4)
        self._warn_low_priority_limit = self._env_int("SENTIENTOS_GOVERNOR_WARN_LOW_PRIORITY_LIMIT", 8)
        self._storm_federated_limit = self._env_int("SENTIENTOS_GOVERNOR_STORM_FEDERATED_LIMIT", 2)
        self._starvation_streak_threshold = self._env_int("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", 5)
        self._subject_summary_limit = self._env_int("SENTIENTOS_GOVERNOR_SUBJECT_SUMMARY_LIMIT", 16)
        self._noisy_subject_share_threshold = self._env_float("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_SHARE", 0.7)
        self._noisy_subject_min_admits = self._env_int("SENTIENTOS_GOVERNOR_NOISY_SUBJECT_MIN_ADMITS", 3)

        self._pressure_block = self._env_float("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", 0.85)
        self._pressure_warn = self._env_float("SENTIENTOS_GOVERNOR_PRESSURE_WARN", 0.70)
        self._schedule_threshold = self._env_float("SENTIENTOS_GOVERNOR_SCHEDULING_THRESHOLD", 0.45)

        self._restarts: dict[str, Deque[datetime]] = defaultdict(deque)
        self._repairs: dict[str, Deque[datetime]] = defaultdict(deque)
        self._federated_controls: Deque[datetime] = deque()
        self._critical_events: Deque[datetime] = deque()
        self._control_plane_tasks: dict[str, Deque[datetime]] = defaultdict(deque)
        self._amendments: dict[str, Deque[datetime]] = defaultdict(deque)
        self._quarantine: dict[str, bool] = defaultdict(bool)
        self._contention_allowed: Deque[tuple[datetime, str]] = deque()

        self._profiles: dict[str, ActionProfile] = {
            "restart_daemon": ActionProfile("restart_daemon", priority=0, family="recovery", local_safety=True, deferrable=False),
            "repair_action": ActionProfile("repair_action", priority=1, family="recovery", local_safety=True, deferrable=False),
            "federated_control": ActionProfile("federated_control", priority=2, family="federated", local_safety=False, deferrable=True),
            "control_plane_task": ActionProfile("control_plane_task", priority=3, family="control_plane", local_safety=False, deferrable=True),
            "amendment_apply": ActionProfile("amendment_apply", priority=4, family="amendment", local_safety=False, deferrable=True),
            "unknown": ActionProfile("unknown", priority=5, family="unknown", local_safety=False, deferrable=True),
        }
        self._decision_totals: dict[str, int] = defaultdict(int)
        self._family_decisions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._class_decisions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._reason_counts: dict[str, int] = defaultdict(int)
        self._pressure_bands: dict[str, int] = defaultdict(int)
        self._storm_trigger_counts: dict[str, int] = defaultdict(int)
        self._reserved_usage = 0
        self._class_attempts: dict[str, int] = defaultdict(int)
        self._class_allowed: dict[str, int] = defaultdict(int)
        self._class_denied: dict[str, int] = defaultdict(int)
        self._class_denied_streak: dict[str, int] = defaultdict(int)
        self._subject_attempts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._subject_decisions: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self._subject_denied_streak: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._subject_events: Deque[tuple[datetime, str, str, str]] = deque()

    @staticmethod
    def _restriction_class_for_reason(reason: str) -> str:
        if reason.startswith("degraded_audit_trust"):
            return "audit_trust"
        if reason.startswith("federated_"):
            return "federation"
        if reason.startswith("pulse_epoch"):
            return "pulse_epoch"
        if "local_safety" in reason:
            return "local_safety"
        if "storm" in reason:
            return "storm"
        if "starvation" in reason or "fairness" in reason:
            return "fairness"
        if "pressure" in reason:
            return "pressure"
        if "contention" in reason or "reserved" in reason:
            return "contention"
        if "rate_exceeded" in reason or "budget_exceeded" in reason or "quarantined" in reason:
            return "budget"
        if reason == "allowed":
            return "none"
        return "policy"

    def _evaluate_audit_trust_posture(
        self,
        *,
        action_class: str,
        metadata: dict[str, object] | None,
    ) -> tuple[PostureRuleEvaluation, dict[str, object]]:
        trust_state = evaluate_audit_trust(self._repo_root, context=f"governor:{action_class}")
        artifact_paths = write_audit_trust_artifacts(self._repo_root, trust_state, actor="runtime_governor")
        trust_payload = {
            "audit_trust": trust_state.to_dict(),
            "audit_trust_artifacts": artifact_paths,
        }
        reason = "audit_trust_nominal"
        blocks = False
        if trust_state.degraded_audit_trust:
            if action_class == "federated_control":
                reason, blocks = "degraded_audit_trust_federation_blocked", True
            elif action_class == "amendment_apply":
                reason, blocks = "degraded_audit_trust_amendment_deferred", True
            elif action_class == "control_plane_task":
                reason, blocks = "degraded_audit_trust_control_plane_escalation_required", True
            elif action_class == "repair_action":
                action_kind = str((metadata or {}).get("action_kind") or "")
                if action_kind and action_kind != "restart_daemon":
                    reason, blocks = "degraded_audit_trust_repair_escalation_required", True
                else:
                    reason = "degraded_audit_trust_tightened"
            else:
                reason = "degraded_audit_trust_tightened"
        evaluation = PostureRuleEvaluation(
            dimension="audit_trust",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=100,
            details={"degraded_audit_trust": trust_state.degraded_audit_trust, "history_state": trust_state.history_state},
        )
        return evaluation, trust_payload

    def _evaluate_federated_governance_posture(
        self,
        *,
        action_class: str,
        origin: str,
        metadata: dict[str, object] | None,
    ) -> tuple[PostureRuleEvaluation, dict[str, object]]:
        payload = dict(metadata or {})
        governance = payload.get("federated_governance")
        if not isinstance(governance, dict):
            governance = {
                "peer_name": origin,
                "digest_status": "unavailable",
                "digest_reasons": ["governance_not_provided"],
                "epoch_status": "unknown",
                "denial_cause": "none",
                "quorum_required": 1,
                "quorum_present": 1,
                "quorum_satisfied": True,
            }

        reason = "federation_governance_nominal"
        blocks = False
        denial_cause = str(governance.get("denial_cause") or "none")
        digest_status = str(governance.get("digest_status") or "missing")
        epoch_status = str(governance.get("epoch_status") or "unknown")
        quorum_satisfied = bool(governance.get("quorum_satisfied", False))

        if action_class == "federated_control":
            if epoch_status == "unexpected" or denial_cause == "trust_epoch":
                reason, blocks = "federated_unexpected_epoch_blocked", True
            elif digest_status in {"missing", "incompatible"} or denial_cause == "digest_mismatch":
                reason, blocks = "federated_digest_mismatch_blocked", True
            elif not quorum_satisfied or denial_cause == "quorum_failure":
                reason, blocks = "federated_quorum_not_satisfied", True

        evaluation = PostureRuleEvaluation(
            dimension="federated_governance",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=110,
            details=dict(governance),
        )
        return evaluation, {"federated_governance": governance}

    def _evaluate_pulse_epoch_posture(
        self,
        *,
        action_class: str,
        metadata: dict[str, object] | None,
    ) -> tuple[PostureRuleEvaluation, dict[str, object]]:
        manager = get_trust_epoch_manager()
        state = manager.load_state()
        compromise_mode = bool(state.get("compromise_response_mode", False))
        trust_class = str((metadata or {}).get("trust_epoch_classification") or "")
        reason = "pulse_epoch_nominal"
        blocks = False
        if trust_class in {"revoked_epoch", "invalid_signature"}:
            reason, blocks = "pulse_epoch_untrusted_federation_blocked", True
        elif trust_class and trust_class not in {"current_trusted_epoch", "historical_closed_epoch"}:
            reason, blocks = "pulse_epoch_mismatch_escalation_required", True
        elif compromise_mode:
            if action_class in {"federated_control", "amendment_apply", "control_plane_task"}:
                reason, blocks = "pulse_epoch_compromise_restricted", True
            else:
                reason = "pulse_epoch_compromise_tightened"
        evaluation = PostureRuleEvaluation(
            dimension="pulse_trust_epoch",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=105,
            details={
                "active_epoch_id": state.get("active_epoch_id"),
                "revoked_epochs": state.get("revoked_epochs", []),
                "compromise_response_mode": compromise_mode,
            },
        )
        payload = {
            "pulse_trust_epoch": state,
            "trust_epoch_classification": trust_class,
        }
        return evaluation, payload

    def _compose_runtime_posture(
        self,
        *,
        action_class: str,
        scope: str,
        pressure: PressureSnapshot,
        now: datetime,
        evaluations: list[PostureRuleEvaluation],
    ) -> RuntimePosture:
        profile = self._profile_for(action_class)
        contention_total, _ = self._contention_counts(now)
        denied_streak = self._class_denied_streak.get(action_class, 0)
        storm_active = len(self._critical_events) > self._critical_limit
        fairness_eval = PostureRuleEvaluation(
            dimension="fairness_starvation",
            reason="fairness_nominal",
            restriction_class="none",
            blocks=False,
            precedence=55,
            details={"denied_streak": denied_streak, "threshold": self._starvation_streak_threshold},
        )
        if (
            profile.deferrable
            and denied_streak >= self._starvation_streak_threshold
            and pressure.composite >= self._pressure_warn
            and contention_total >= max(1, self._contention_limit - 1)
        ):
            fairness_eval = PostureRuleEvaluation(
                dimension="fairness_starvation",
                reason="deferred_starvation_under_pressure",
                restriction_class="fairness",
                blocks=True,
                precedence=55,
                details={"denied_streak": denied_streak, "threshold": self._starvation_streak_threshold},
            )
        reason_chain = [*evaluations, fairness_eval]
        active_dimensions = {
            "pressure_band": self._pressure_band(pressure),
            "pressure_composite": pressure.composite,
            "storm_active": storm_active,
            "scope": scope,
            "is_federated": scope == "federated" or profile.family == "federated",
            "action_class": action_class,
            "action_family": profile.family,
            "action_priority": profile.priority,
            "deferrable": profile.deferrable,
            "local_safety": profile.local_safety,
            "fairness_denied_streak": denied_streak,
            "fairness_threshold": self._starvation_streak_threshold,
        }
        ranked = sorted(reason_chain, key=lambda item: (-item.precedence, item.reason, item.dimension))
        dominant = ranked[0]
        enforce_block = any(item.blocks for item in reason_chain)
        if enforce_block:
            effective_posture = "restricted"
        elif active_dimensions["pressure_band"] == "warn" or storm_active:
            effective_posture = "constrained"
        else:
            effective_posture = "nominal"
        ladder = sorted({item.restriction_class for item in reason_chain if item.restriction_class != "none"})
        return RuntimePosture(
            effective_posture=effective_posture,
            dominant_dimension=dominant.dimension,
            dominant_reason=dominant.reason,
            dominant_restriction_class=dominant.restriction_class,
            enforce_block=enforce_block,
            escalation_ladder=ladder,
            active_dimensions=active_dimensions,
            reason_chain=ranked,
        )

    @staticmethod
    def _safe_subject(value: str) -> str:
        normalized = value.strip()
        return normalized if normalized else "unknown"

    def _subject_for_action(self, action_class: str, actor: str, payload: dict[str, object]) -> str:
        keys_by_class = {
            "restart_daemon": ("daemon_name", "target", "subject"),
            "repair_action": ("subject", "anomaly_subject", "target"),
            "federated_control": ("peer_subject", "federated_source", "peer_name", "subject", "target"),
            "control_plane_task": ("task_key", "task_origin", "request_type", "subject", "target"),
            "amendment_apply": ("amendment_target", "subject", "target"),
        }
        for key in keys_by_class.get(action_class, ("subject", "target", "daemon_name")):
            value = payload.get(key)
            if value is None:
                continue
            normalized = self._safe_subject(str(value))
            if normalized != "unknown":
                return normalized
        return self._safe_subject(actor)

    @staticmethod
    def _outcome_label(allowed: bool, reason: str) -> str:
        if allowed:
            return "admit"
        if reason.startswith("deferred"):
            return "defer"
        return "deny"

    def _pressure_band(self, pressure: PressureSnapshot) -> str:
        if pressure.composite >= self._pressure_block:
            return "block"
        if pressure.composite >= self._pressure_warn:
            return "warn"
        return "normal"

    def _contending_actions(self, counts: dict[str, int]) -> list[dict[str, object]]:
        rows: list[tuple[int, str, int]] = []
        for action_class, count in counts.items():
            if count <= 0:
                continue
            rows.append((self._profile_for(action_class).priority, action_class, count))
        rows.sort()
        return [{"action_class": action_class, "count": count, "priority": priority} for priority, action_class, count in rows]

    def _starvation_signals(self) -> dict[str, object]:
        classes = sorted(self._profiles)
        denied_streaks = {name: self._class_denied_streak.get(name, 0) for name in classes}
        at_risk = sorted(
            name
            for name in classes
            if self._profile_for(name).deferrable and denied_streaks.get(name, 0) >= self._starvation_streak_threshold
        )
        return {
            "streak_threshold": self._starvation_streak_threshold,
            "denied_streaks": denied_streaks,
            "at_risk_classes": at_risk,
        }

    def _subject_fairness_summary(self) -> dict[str, object]:
        per_class: dict[str, dict[str, object]] = {}
        starved_subjects: list[dict[str, object]] = []
        noisy_subjects: list[dict[str, object]] = []
        denied_while_peers_admitted: list[dict[str, object]] = []

        for action_class in sorted(self._profiles):
            attempts_by_subject = self._subject_attempts.get(action_class, {})
            subjects = sorted(attempts_by_subject)
            if not subjects:
                continue
            class_admits = self._class_decisions.get(action_class, {}).get("admit", 0)
            class_rows: list[dict[str, object]] = []
            for subject in subjects:
                subject_decisions = self._subject_decisions[action_class][subject]
                row = {
                    "subject": subject,
                    "attempts": attempts_by_subject.get(subject, 0),
                    "admit": subject_decisions.get("admit", 0),
                    "defer": subject_decisions.get("defer", 0),
                    "deny": subject_decisions.get("deny", 0),
                    "denied_streak": self._subject_denied_streak[action_class].get(subject, 0),
                }
                class_rows.append(row)

                if row["denied_streak"] >= self._starvation_streak_threshold:
                    starved_subjects.append({"action_class": action_class, **row})

                if (
                    class_admits >= self._noisy_subject_min_admits
                    and len(subjects) > 1
                    and isinstance(row["admit"], int)
                    and class_admits > 0
                ):
                    share = round(row["admit"] / class_admits, 4)
                    if share >= self._noisy_subject_share_threshold:
                        noisy_subjects.append({"action_class": action_class, **row, "admit_share": share})

                peers_admit = class_admits - int(row["admit"])
                if peers_admit > 0 and int(row["deny"]) > 0 and int(row["admit"]) == 0:
                    denied_while_peers_admitted.append({"action_class": action_class, **row, "peer_admit": peers_admit})

            class_rows.sort(key=lambda item: (-int(item["deny"]), -int(item["defer"]), str(item["subject"])))
            per_class[action_class] = {
                "subject_count": len(class_rows),
                "subjects": class_rows[: self._subject_summary_limit],
            }

        def _sort_rows(rows: list[dict[str, object]], key_name: str) -> list[dict[str, object]]:
            return sorted(rows, key=lambda item: (-int(item[key_name]), str(item["action_class"]), str(item["subject"])))

        return {
            "streak_threshold": self._starvation_streak_threshold,
            "summary_limit": self._subject_summary_limit,
            "per_class": per_class,
            "starved_subjects": _sort_rows(starved_subjects, "denied_streak")[: self._subject_summary_limit],
            "noisy_subjects": sorted(
                noisy_subjects,
                key=lambda item: (-float(item["admit_share"]), str(item["action_class"]), str(item["subject"])),
            )[: self._subject_summary_limit],
            "denied_while_peers_admitted": _sort_rows(denied_while_peers_admitted, "deny")[: self._subject_summary_limit],
        }

    def _trim_subject_events(self, now: datetime) -> None:
        cutoff = now - self._contention_window
        while self._subject_events and self._subject_events[0][0] < cutoff:
            self._subject_events.popleft()

    def _queue_pressure_summary(self, now: datetime) -> dict[str, object]:
        self._trim_subject_events(now)
        class_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        family_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        subject_totals: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

        for _, action_class, subject, outcome in self._subject_events:
            class_totals[action_class][outcome] += 1
            family = self._profile_for(action_class).family
            family_totals[family][outcome] += 1
            subject_totals[action_class][subject][outcome] += 1

        class_summary: dict[str, dict[str, int]] = {}
        top_subjects: list[dict[str, object]] = []
        for action_class in sorted(class_totals):
            counts = class_totals[action_class]
            occupancy = counts.get("admit", 0)
            blocked = counts.get("defer", 0) + counts.get("deny", 0)
            retries = max(0, occupancy + blocked - len(subject_totals[action_class]))
            class_summary[action_class] = {
                "admitted_occupancy": occupancy,
                "blocked_pressure": blocked,
                "defer": counts.get("defer", 0),
                "deny": counts.get("deny", 0),
                "retries": retries,
            }
            for subject in sorted(subject_totals[action_class]):
                subject_counts = subject_totals[action_class][subject]
                subj_occupancy = subject_counts.get("admit", 0)
                subj_blocked = subject_counts.get("defer", 0) + subject_counts.get("deny", 0)
                subj_retries = max(0, subj_occupancy + subj_blocked - 1)
                top_subjects.append(
                    {
                        "action_class": action_class,
                        "subject": subject,
                        "admitted_occupancy": subj_occupancy,
                        "blocked_pressure": subj_blocked,
                        "defer": subject_counts.get("defer", 0),
                        "deny": subject_counts.get("deny", 0),
                        "retries": subj_retries,
                    }
                )

        family_summary = {
            family: {
                "admitted_occupancy": counts.get("admit", 0),
                "blocked_pressure": counts.get("defer", 0) + counts.get("deny", 0),
                "defer": counts.get("defer", 0),
                "deny": counts.get("deny", 0),
            }
            for family, counts in sorted(family_totals.items())
        }
        top_subjects.sort(key=lambda item: (-int(item["blocked_pressure"]), -int(item["retries"]), str(item["action_class"]), str(item["subject"])))

        return {
            "window_seconds": int(self._contention_window.total_seconds()),
            "summary_limit": self._subject_summary_limit,
            "class_summary": class_summary,
            "family_summary": family_summary,
            "top_subjects": top_subjects[: self._subject_summary_limit],
        }

    @staticmethod
    def _bounded_counts(values: dict[str, int], *, limit: int = 64) -> dict[str, int]:
        return {key: values[key] for key in sorted(values)[:limit]}

    def _build_rollup(self) -> dict[str, object]:
        starvation = self._starvation_signals()
        fairness = self._subject_fairness_summary()
        queue_pressure = self._queue_pressure_summary(datetime.now(timezone.utc))
        class_summary = {
            action_class: {
                "attempts": self._class_attempts.get(action_class, 0),
                "admit": self._class_decisions.get(action_class, {}).get("admit", 0),
                "defer": self._class_decisions.get(action_class, {}).get("defer", 0),
                "deny": self._class_decisions.get(action_class, {}).get("deny", 0),
                "denied_streak": starvation["denied_streaks"].get(action_class, 0),
            }
            for action_class in sorted(self._profiles)
        }
        family_summary = {
            family: {
                "admit": counts.get("admit", 0),
                "defer": counts.get("defer", 0),
                "deny": counts.get("deny", 0),
            }
            for family, counts in sorted(self._family_decisions.items())
        }
        return {
            "schema_version": 1,
            "mode": self._mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "actions": sum(self._decision_totals.values()),
                "admit": self._decision_totals.get("admit", 0),
                "defer": self._decision_totals.get("defer", 0),
                "deny": self._decision_totals.get("deny", 0),
            },
            "class_summary": class_summary,
            "family_summary": family_summary,
            "storm_trigger_counts": self._bounded_counts(self._storm_trigger_counts),
            "reserved_recovery_slots_used": self._reserved_usage,
            "pressure_band_distribution": {
                "normal": self._pressure_bands.get("normal", 0),
                "warn": self._pressure_bands.get("warn", 0),
                "block": self._pressure_bands.get("block", 0),
            },
            "reason_counts": self._bounded_counts(self._reason_counts),
            "starvation_signals": starvation,
            "subject_fairness": fairness,
            "queue_pressure": queue_pressure,
            "runtime_posture_summary": self._bounded_counts(
                {
                    "restricted": self._reason_counts.get("deferred_contention_limit", 0)
                    + self._reason_counts.get("deferred_reserved_for_recovery", 0)
                    + self._reason_counts.get("deferred_federated_under_storm", 0)
                    + self._reason_counts.get("deferred_for_local_safety_under_pressure", 0)
                    + self._reason_counts.get("degraded_audit_trust_federation_blocked", 0)
                    + self._reason_counts.get("degraded_audit_trust_amendment_deferred", 0)
                    + self._reason_counts.get("degraded_audit_trust_control_plane_escalation_required", 0)
                    + self._reason_counts.get("degraded_audit_trust_repair_escalation_required", 0)
                    + self._reason_counts.get("pulse_epoch_untrusted_federation_blocked", 0)
                    + self._reason_counts.get("pulse_epoch_mismatch_escalation_required", 0)
                    + self._reason_counts.get("pulse_epoch_compromise_restricted", 0),
                    "constrained": self._pressure_bands.get("warn", 0),
                    "nominal": self._pressure_bands.get("normal", 0),
                }
            ),
        }

    def _write_rollup(self) -> None:
        rollup = self._build_rollup()
        self._rollup_path.write_text(json.dumps(rollup, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def admit_action(
        self,
        action_type: str,
        actor: str,
        correlation_id: str,
        metadata: dict[str, object] | None = None,
    ) -> GovernorDecision:
        normalized = action_type.strip().lower()
        profile = self._profile_for(normalized)
        payload = dict(metadata or {})
        subject = self._subject_for_action(normalized, actor, payload)
        scope = str(payload.get("scope") or "local")
        payload.setdefault("action_class", normalized)
        payload.setdefault("action_priority", profile.priority)
        payload.setdefault("action_family", profile.family)

        if normalized == "restart_daemon":
            return self.admit_restart(
                daemon_name=subject,
                scope=scope,
                origin=actor,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "repair_action":
            anomaly_kind = str(payload.get("anomaly_kind") or payload.get("kind") or "unknown")
            return self.admit_repair(
                anomaly_kind=anomaly_kind,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "federated_control":
            return self.admit_federated_control(
                subject=subject,
                origin=actor,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "control_plane_task":
            return self._admit_control_plane_task(
                requester=actor,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "amendment_apply":
            return self._admit_amendment_apply(
                actor=actor,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        return self._decision(
            action_class=normalized,
            allowed=self._mode != "enforce",
            reason="unknown_action_type",
            subject=subject,
            scope=scope,
            origin=actor,
            pressure=self.sample_pressure(),
            metadata=payload,
            correlation_id=correlation_id,
        )

    def sample_pressure(self) -> PressureSnapshot:
        now = datetime.now(timezone.utc)
        cpu = self._read_cpu()
        io = self._read_io()
        thermal = self._read_thermal()
        gpu = self._read_gpu()
        composite = round(min(1.0, max(0.0, 0.4 * cpu + 0.25 * io + 0.2 * thermal + 0.15 * gpu)), 4)
        snapshot = PressureSnapshot(cpu=cpu, io=io, thermal=thermal, gpu=gpu, composite=composite, sampled_at=now.isoformat())
        self._append_jsonl(self._pressure_path, snapshot.to_dict())
        self._publish_governor_state(snapshot)
        return snapshot

    def scheduling_window_open(self) -> bool:
        pressure = self.sample_pressure()
        return pressure.composite <= self._schedule_threshold

    def observe_pulse_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type", ""))
        if event_type.startswith("governor_"):
            return
        priority = str(event.get("priority", "info")).lower()
        if priority == "critical":
            now = datetime.now(timezone.utc)
            self._critical_events.append(now)
            self._trim(self._critical_events, now, self._critical_window)

    def admit_restart(
        self,
        *,
        daemon_name: str,
        scope: str,
        origin: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._restarts[daemon_name]
        dq.append(now)
        self._trim(dq, now, self._restart_window)

        if scope == "federated":
            self._federated_controls.append(now)
            self._trim(self._federated_controls, now, self._federated_window)

        reason = "allowed"
        enforce_block = False
        if self._quarantine[daemon_name]:
            reason = "daemon_quarantined"
            enforce_block = True
        elif len(dq) > self._restart_limit:
            reason = "restart_budget_exceeded"
            self._quarantine[daemon_name] = True
            enforce_block = True
        elif scope == "federated" and len(self._federated_controls) > self._federated_limit:
            reason = "federated_control_rate_exceeded"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="restart_daemon",
            metadata=metadata,
        )
        epoch_eval, epoch_payload = self._evaluate_pulse_epoch_posture(
            action_class="restart_daemon",
            metadata=metadata,
        )

        arbitration_eval = self._evaluate_arbitration(
            action_class="restart_daemon",
            scope=scope,
            pressure=pressure,
            now=now,
        )
        budget_eval = PostureRuleEvaluation(
            dimension="budget_pressure",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=enforce_block,
            precedence=70,
            details={"scope": scope, "restart_attempts": len(dq)},
        )
        posture = self._compose_runtime_posture(
            action_class="restart_daemon",
            scope=scope,
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, arbitration_eval],
        )
        reason = posture.dominant_reason
        enforce_block = posture.enforce_block
        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="restart_daemon",
            allowed=allowed,
            reason=reason,
            subject=daemon_name,
            scope=scope,
            origin=origin,
            pressure=pressure,
            metadata={**(metadata or {}), **trust_payload, **epoch_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="restart_daemon", allowed=allowed, now=now)
        return decision

    def admit_repair(
        self,
        *,
        anomaly_kind: str,
        subject: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._repairs[anomaly_kind]
        dq.append(now)
        self._trim(dq, now, self._repair_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._repair_limit:
            reason = "repair_budget_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="repair_action",
            metadata=metadata,
        )
        epoch_eval, epoch_payload = self._evaluate_pulse_epoch_posture(
            action_class="repair_action",
            metadata=metadata,
        )

        arbitration_eval = self._evaluate_arbitration(
            action_class="repair_action",
            scope="local",
            pressure=pressure,
            now=now,
        )
        budget_eval = PostureRuleEvaluation(
            dimension="budget_pressure",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=enforce_block,
            precedence=70,
            details={"repair_attempts": len(dq), "anomaly_kind": anomaly_kind},
        )
        posture = self._compose_runtime_posture(
            action_class="repair_action",
            scope="local",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, arbitration_eval],
        )
        reason = posture.dominant_reason
        enforce_block = posture.enforce_block
        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="repair_action",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin="codex_healer",
            pressure=pressure,
            metadata={"anomaly_kind": anomaly_kind, **(metadata or {}), **trust_payload, **epoch_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="repair_action", allowed=allowed, now=now)
        return decision

    def admit_federated_control(
        self,
        *,
        subject: str,
        origin: str,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        self._federated_controls.append(now)
        self._trim(self._federated_controls, now, self._federated_window)

        reason = "allowed"
        enforce_block = False
        if len(self._federated_controls) > self._federated_limit:
            reason = "federated_control_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="federated_control",
            metadata=metadata,
        )
        epoch_eval, epoch_payload = self._evaluate_pulse_epoch_posture(
            action_class="federated_control",
            metadata=metadata,
        )
        federation_eval, federation_payload = self._evaluate_federated_governance_posture(
            action_class="federated_control",
            origin=origin,
            metadata=metadata,
        )

        arbitration_eval = self._evaluate_arbitration(
            action_class="federated_control",
            scope="federated",
            pressure=pressure,
            now=now,
        )
        budget_eval = PostureRuleEvaluation(
            dimension="budget_pressure",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=enforce_block,
            precedence=70,
            details={"federated_controls": len(self._federated_controls)},
        )
        posture = self._compose_runtime_posture(
            action_class="federated_control",
            scope="federated",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, federation_eval, arbitration_eval],
        )
        reason = posture.dominant_reason
        enforce_block = posture.enforce_block
        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="federated_control",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="federated",
            origin=origin,
            pressure=pressure,
            metadata={**(metadata or {}), **trust_payload, **epoch_payload, **federation_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="federated_control", allowed=allowed, now=now)
        return decision

    def _admit_control_plane_task(
        self,
        *,
        requester: str,
        subject: str,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
        posture: RuntimePosture | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._control_plane_tasks[requester]
        dq.append(now)
        self._trim(dq, now, self._task_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._task_limit:
            reason = "control_plane_task_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif len(self._critical_events) > self._critical_limit:
            reason = "critical_event_storm_detected"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="control_plane_task",
            metadata=metadata,
        )
        epoch_eval, epoch_payload = self._evaluate_pulse_epoch_posture(
            action_class="control_plane_task",
            metadata=metadata,
        )

        arbitration_eval = self._evaluate_arbitration(
            action_class="control_plane_task",
            scope="local",
            pressure=pressure,
            now=now,
        )
        budget_eval = PostureRuleEvaluation(
            dimension="budget_pressure",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=enforce_block,
            precedence=70,
            details={"requester": requester, "task_attempts": len(dq)},
        )
        posture = self._compose_runtime_posture(
            action_class="control_plane_task",
            scope="local",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, arbitration_eval],
        )
        reason = posture.dominant_reason
        enforce_block = posture.enforce_block
        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="control_plane_task",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin=requester,
            pressure=pressure,
            metadata={**(metadata or {}), **trust_payload, **epoch_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="control_plane_task", allowed=allowed, now=now)
        return decision

    def _admit_amendment_apply(
        self,
        *,
        actor: str,
        subject: str,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
        posture: RuntimePosture | None = None,
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        dq = self._amendments[actor]
        dq.append(now)
        self._trim(dq, now, self._amendment_window)

        reason = "allowed"
        enforce_block = False
        if len(dq) > self._amendment_limit:
            reason = "amendment_rate_exceeded"
            enforce_block = True
        elif pressure.composite >= self._pressure_block:
            reason = "pressure_block"
            enforce_block = True
        elif pressure.composite >= self._pressure_warn:
            reason = "pressure_warn"

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="amendment_apply",
            metadata=metadata,
        )
        epoch_eval, epoch_payload = self._evaluate_pulse_epoch_posture(
            action_class="amendment_apply",
            metadata=metadata,
        )

        arbitration_eval = self._evaluate_arbitration(
            action_class="amendment_apply",
            scope="local",
            pressure=pressure,
            now=now,
        )
        budget_eval = PostureRuleEvaluation(
            dimension="budget_pressure",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=enforce_block,
            precedence=70,
            details={"actor": actor, "amendment_attempts": len(dq)},
        )
        posture = self._compose_runtime_posture(
            action_class="amendment_apply",
            scope="local",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, arbitration_eval],
        )
        reason = posture.dominant_reason
        enforce_block = posture.enforce_block
        allowed = not enforce_block or self._mode != "enforce"
        decision = self._decision(
            action_class="amendment_apply",
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin=actor,
            pressure=pressure,
            metadata={**(metadata or {}), **trust_payload, **epoch_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="amendment_apply", allowed=allowed, now=now)
        return decision

    def _profile_for(self, action_class: str) -> ActionProfile:
        return self._profiles.get(action_class, self._profiles["unknown"])

    def _contention_counts(self, now: datetime) -> tuple[int, dict[str, int]]:
        cutoff = now - self._contention_window
        while self._contention_allowed and self._contention_allowed[0][0] < cutoff:
            self._contention_allowed.popleft()
        counts: dict[str, int] = defaultdict(int)
        for _, action_class in self._contention_allowed:
            counts[action_class] += 1
        return len(self._contention_allowed), counts

    def _evaluate_arbitration(
        self,
        *,
        action_class: str,
        scope: str,
        pressure: PressureSnapshot,
        now: datetime,
    ) -> PostureRuleEvaluation:
        profile = self._profile_for(action_class)
        total, counts = self._contention_counts(now)
        low_priority_count = counts.get("control_plane_task", 0) + counts.get("amendment_apply", 0)
        federated_count = counts.get("federated_control", 0)

        reason = "arbitration_nominal"
        blocks = False
        precedence = 40
        if pressure.composite >= self._pressure_block and scope == "federated" and profile.deferrable:
            reason, blocks, precedence = "deferred_for_local_safety_under_pressure", True, 90
        elif pressure.composite >= self._pressure_warn and profile.priority >= 3 and low_priority_count >= self._warn_low_priority_limit:
            reason, blocks, precedence = "deferred_low_priority_under_pressure", True, 50
        elif (
            (pressure.composite >= self._pressure_warn or len(self._critical_events) > self._critical_limit)
            and profile.family == "federated"
            and federated_count >= self._storm_federated_limit
        ):
            reason, blocks, precedence = "deferred_federated_under_storm", True, 80
        elif profile.family != "recovery":
            remaining = max(0, self._contention_limit - total)
            if remaining <= self._recovery_reserved_slots:
                reason, blocks, precedence = "deferred_reserved_for_recovery", True, 60
        if reason == "arbitration_nominal":
            if profile.family == "recovery" and (pressure.composite >= self._pressure_warn or len(self._critical_events) > self._critical_limit):
                reason, blocks, precedence = "allowed_recovery_precedence", False, 65
            elif total >= self._contention_limit and profile.deferrable:
                reason, blocks, precedence = "deferred_contention_limit", True, 45
            elif total >= self._contention_limit and not profile.deferrable:
                reason, blocks, precedence = "allowed_recovery_contention_override", False, 65

        return PostureRuleEvaluation(
            dimension="arbitration",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=precedence,
            details={
                "contention_total": total,
                "low_priority_count": low_priority_count,
                "federated_count": federated_count,
            },
        )

    def _record_contention(self, *, action_class: str, allowed: bool, now: datetime) -> None:
        if not allowed:
            return
        self._contention_allowed.append((now, action_class))
        self._contention_counts(now)

    def _decision(
        self,
        *,
        action_class: str,
        allowed: bool,
        reason: str,
        subject: str,
        scope: str,
        origin: str,
        pressure: PressureSnapshot,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
        posture: RuntimePosture | None = None,
    ) -> GovernorDecision:
        correlation = correlation_id or hashlib.sha256(
            json.dumps(
                {
                    "action_class": action_class,
                    "subject": subject,
                    "scope": scope,
                    "origin": origin,
                    "reason": reason,
                    "metadata": metadata or {},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        reasoning_payload = {
            "action_class": action_class,
            "allowed": allowed,
            "mode": self._mode,
            "reason": reason,
            "subject": subject,
            "scope": scope,
            "origin": origin,
            "pressure": pressure.to_dict(),
            "metadata": metadata or {},
            "correlation_id": correlation,
        }
        reason_hash = hashlib.sha256(json.dumps(reasoning_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        profile = self._profile_for(action_class)
        now = datetime.now(timezone.utc)
        contention_total, contention_counts = self._contention_counts(now)
        remaining_slots = max(0, self._contention_limit - contention_total)
        pressure_band = self._pressure_band(pressure)
        outcome = self._outcome_label(allowed, reason)

        self._class_attempts[action_class] += 1
        subject_key = self._safe_subject(subject)
        self._subject_attempts[action_class][subject_key] += 1
        if allowed:
            self._class_allowed[action_class] += 1
            self._class_denied_streak[action_class] = 0
            self._subject_denied_streak[action_class][subject_key] = 0
        else:
            self._class_denied[action_class] += 1
            self._class_denied_streak[action_class] += 1
            self._subject_denied_streak[action_class][subject_key] += 1
        self._decision_totals[outcome] += 1
        self._family_decisions[profile.family][outcome] += 1
        self._class_decisions[action_class][outcome] += 1
        self._subject_decisions[action_class][subject_key][outcome] += 1
        self._reason_counts[reason] += 1
        self._pressure_bands[pressure_band] += 1
        self._subject_events.append((now, action_class, subject_key, outcome))
        self._trim_subject_events(now)
        if "storm" in reason:
            self._storm_trigger_counts[reason] += 1
        reserved_for_recovery = profile.family != "recovery" and remaining_slots <= self._recovery_reserved_slots
        reserved_slot_consumed = (
            allowed and profile.family == "recovery" and remaining_slots <= self._recovery_reserved_slots
        )
        if reserved_slot_consumed:
            self._reserved_usage += 1

        starvation_signals = self._starvation_signals()
        subject_fairness = self._subject_fairness_summary()
        queue_pressure = self._queue_pressure_summary(now)
        contention_snapshot = {
            "window_seconds": int(self._contention_window.total_seconds()),
            "contention_limit": self._contention_limit,
            "total_active": contention_total,
            "remaining_slots": remaining_slots,
            "active_class_counts": {name: contention_counts.get(name, 0) for name in sorted(self._profiles)},
            "competing_actions": self._contending_actions(contention_counts),
        }
        reserved_capacity = {
            "reserved_recovery_slots": self._recovery_reserved_slots,
            "reserved_floor_reached": remaining_slots <= self._recovery_reserved_slots,
            "reserved_for_recovery": reserved_for_recovery,
            "used_reserved_recovery_slot": reserved_slot_consumed,
            "total_reserved_recovery_slot_usage": self._reserved_usage,
        }

        decision = GovernorDecision(
            action_class=action_class,
            allowed=allowed,
            mode=self._mode,
            reason=reason,
            subject=subject,
            scope=scope,
            origin=origin,
            sampled_pressure=pressure,
            reason_hash=reason_hash,
            correlation_id=correlation,
            action_priority=profile.priority,
            action_family=profile.family,
        )
        payload = decision.to_dict()
        payload["metadata"] = {
            **(metadata or {}),
            "action_class": action_class,
            "action_priority": profile.priority,
            "action_family": profile.family,
        }
        payload["timestamp"] = now.isoformat()
        payload["decision"] = "allow" if allowed else "deny"
        payload["decision_outcome"] = outcome
        payload["governor_mode"] = self._mode
        payload["pressure_snapshot"] = pressure.to_dict()
        payload["pressure_band"] = pressure_band
        payload["contention_snapshot"] = contention_snapshot
        payload["reserved_capacity"] = reserved_capacity
        payload["starvation_signals"] = starvation_signals
        payload["subject_fairness"] = subject_fairness
        payload["queue_pressure"] = queue_pressure
        payload["runtime_posture"] = (posture or self._compose_runtime_posture(
            action_class=action_class,
            scope=scope,
            pressure=pressure,
            now=now,
            evaluations=[
                PostureRuleEvaluation(
                    dimension="legacy",
                    reason=reason,
                    restriction_class=self._restriction_class_for_reason(reason),
                    blocks=not allowed,
                    precedence=10,
                    details={},
                )
            ],
        )).to_dict()
        payload["dominant_restriction_cause"] = payload["runtime_posture"]["dominant_reason"]
        payload["family_decision_summary"] = {
            "family": profile.family,
            "admit": self._family_decisions[profile.family].get("admit", 0),
            "defer": self._family_decisions[profile.family].get("defer", 0),
            "deny": self._family_decisions[profile.family].get("deny", 0),
        }
        payload["class_decision_summary"] = {
            "action_class": action_class,
            "attempts": self._class_attempts.get(action_class, 0),
            "admit": self._class_decisions[action_class].get("admit", 0),
            "defer": self._class_decisions[action_class].get("defer", 0),
            "deny": self._class_decisions[action_class].get("deny", 0),
            "denied_streak": self._class_denied_streak.get(action_class, 0),
        }
        self._append_jsonl(self._decisions_path, payload)
        observability_payload = {
            "timestamp": now.isoformat(),
            "correlation_id": correlation,
            "action_class": action_class,
            "action_family": profile.family,
            "action_priority": profile.priority,
            "decision": payload["decision"],
            "decision_outcome": outcome,
            "reason": reason,
            "mode": self._mode,
            "pressure_band": pressure_band,
            "pressure_composite": pressure.composite,
            "contention_snapshot": contention_snapshot,
            "reserved_capacity": reserved_capacity,
            "starvation_signals": starvation_signals,
            "subject_fairness": {
                "starved_subjects": subject_fairness["starved_subjects"],
                "noisy_subjects": subject_fairness["noisy_subjects"],
                "denied_while_peers_admitted": subject_fairness["denied_while_peers_admitted"],
            },
            "queue_pressure": queue_pressure,
            "runtime_posture": payload["runtime_posture"],
            "effective_posture": payload["runtime_posture"]["effective_posture"],
            "active_posture_dimensions": payload["runtime_posture"]["active_dimensions"],
            "dominant_restriction_cause": payload["runtime_posture"]["dominant_reason"],
            "class_decision_summary": payload["class_decision_summary"],
            "family_decision_summary": payload["family_decision_summary"],
        }
        self._append_jsonl(self._observability_path, observability_payload)
        self._write_budget_snapshot()
        self._write_rollup()
        self._publish_governor_decision(payload)
        return decision

    def _write_budget_snapshot(self) -> None:
        federation = get_federated_governance_controller()
        local_digest = federation.local_governance_digest().to_dict()
        snapshot = {
            "schema_version": 1,
            "mode": self._mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "federation_governance_digest": local_digest,
            "restart_counts": {name: len(entries) for name, entries in self._restarts.items()},
            "repair_counts": {name: len(entries) for name, entries in self._repairs.items()},
            "federated_controls": len(self._federated_controls),
            "control_plane_task_counts": {name: len(entries) for name, entries in self._control_plane_tasks.items()},
            "amendment_counts": {name: len(entries) for name, entries in self._amendments.items()},
            "critical_events": len(self._critical_events),
            "contention_allowed": len(self._contention_allowed),
            "quarantine": dict(self._quarantine),
            "limits": {
                "restart_limit": self._restart_limit,
                "repair_limit": self._repair_limit,
                "federated_limit": self._federated_limit,
                "critical_limit": self._critical_limit,
                "task_limit": self._task_limit,
                "amendment_limit": self._amendment_limit,
                "contention_limit": self._contention_limit,
                "recovery_reserved_slots": self._recovery_reserved_slots,
                "warn_low_priority_limit": self._warn_low_priority_limit,
                "storm_federated_limit": self._storm_federated_limit,
                "starvation_streak_threshold": self._starvation_streak_threshold,
            },
            "counters": {
                "decision_totals": self._bounded_counts(self._decision_totals),
                "reason_counts": self._bounded_counts(self._reason_counts),
                "pressure_bands": {
                    "normal": self._pressure_bands.get("normal", 0),
                    "warn": self._pressure_bands.get("warn", 0),
                    "block": self._pressure_bands.get("block", 0),
                },
                "reserved_recovery_slots_used": self._reserved_usage,
                "subject_fairness": {
                    "starved_subjects": self._subject_fairness_summary()["starved_subjects"],
                    "noisy_subjects": self._subject_fairness_summary()["noisy_subjects"],
                    "denied_while_peers_admitted": self._subject_fairness_summary()["denied_while_peers_admitted"],
                },
                "queue_pressure": self._queue_pressure_summary(datetime.now(timezone.utc)),
            },
        }
        self._budget_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _publish_governor_state(self, pressure: PressureSnapshot) -> None:
        federation = get_federated_governance_controller()
        digest = federation.local_governance_digest().to_dict()
        self._publish_event(
            "governor_state",
            "info",
            {
                "mode": self._mode,
                "pressure": pressure.to_dict(),
                "scheduling_window_open": pressure.composite <= self._schedule_threshold,
                "federation_governance_digest": digest,
            },
        )

    def _publish_governor_decision(self, payload: dict[str, object]) -> None:
        priority = "info" if bool(payload.get("allowed", False)) else "warning"
        self._publish_event("governor_decision", priority, payload)

    def _publish_event(self, event_type: str, priority: str, payload: dict[str, object]) -> None:
        correlation_id = str(payload.get("correlation_id") or "")
        try:
            from sentientos.daemons import pulse_bus

            pulse_bus.publish(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_daemon": "runtime_governor",
                    "event_type": event_type,
                    "priority": priority,
                    "correlation_id": correlation_id,
                    "payload": payload,
                }
            )
        except Exception:
            # telemetry failures must not break control paths
            return

    @staticmethod
    def _trim(entries: Deque[datetime], now: datetime, window: timedelta) -> None:
        cutoff = now - window
        while entries and entries[0] < cutoff:
            entries.popleft()

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = int(value)
            return max(1, parsed)
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            parsed = float(value)
        except ValueError:
            return default
        return min(1.0, max(0.0, parsed))

    @staticmethod
    def _read_cpu() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_CPU", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import psutil  # type: ignore

            return round(min(1.0, max(0.0, psutil.cpu_percent(interval=0.0) / 100.0)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_io() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_IO", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import shutil

            usage = shutil.disk_usage(Path.cwd())
            return round(min(1.0, max(0.0, usage.used / usage.total)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_thermal() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_THERMAL", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        try:
            import psutil  # type: ignore

            temps = psutil.sensors_temperatures()
            if not temps:
                return 0.0
            current: list[float] = []
            for entries in temps.values():
                for entry in entries:
                    if entry.current is not None:
                        current.append(float(entry.current))
            if not current:
                return 0.0
            max_temp = max(current)
            return round(min(1.0, max(0.0, (max_temp - 30.0) / 70.0)), 4)
        except Exception:
            return 0.0

    @staticmethod
    def _read_gpu() -> float:
        override = os.getenv("SENTIENTOS_GOVERNOR_GPU", "")
        if override:
            try:
                return min(1.0, max(0.0, float(override)))
            except ValueError:
                pass
        return 0.0


_GOVERNOR: RuntimeGovernor | None = None


def get_runtime_governor() -> RuntimeGovernor:
    global _GOVERNOR
    if _GOVERNOR is None:
        _GOVERNOR = RuntimeGovernor()
    return _GOVERNOR


def reset_runtime_governor() -> None:
    global _GOVERNOR
    _GOVERNOR = None
