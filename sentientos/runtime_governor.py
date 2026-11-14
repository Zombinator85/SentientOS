from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Mapping

from sentientos.audit_trust_runtime import evaluate_audit_trust, write_audit_trust_artifacts
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.federated_governance import get_controller as get_federated_governance_controller
from sentientos.host_resource_governor import ACTIONABLE_RESOURCE_PRESSURE_LABELS
from sentientos.foreground_game_detection import (
    CONSERVATIVE_RESOURCE_GOVERNANCE_FAILURE_STATUSES,
)
from sentientos.pulse_trust_epoch import get_manager as get_trust_epoch_manager
from sentientos.trust_ledger import get_trust_ledger

MAX_RETAINED_HOST_RESOURCE_EVIDENCE = 64
MAX_RETAINED_GAME_WORKLOAD_EVIDENCE = 64


def _expected_resource_release_correlation(trigger_kind: str,
        trigger_correlation: str, *, active_invocation_reference: object = None,
        bind_active_invocation: bool = False) -> str:
    context = (trigger_correlation if trigger_kind == "deferred_inference" else
        trigger_kind + ":" + trigger_correlation)
    suffix = hashlib.sha256(context.encode("utf-8")).hexdigest()[:24]
    if not bind_active_invocation:
        return "production-chat-resource-release-" + suffix
    if not isinstance(active_invocation_reference, Mapping):
        return ""
    expected_keys = {"request_id", "request_digest", "correlation_id"}
    if (set(active_invocation_reference) != expected_keys
            or any(not isinstance(active_invocation_reference.get(key), str)
                or not active_invocation_reference.get(key)
                for key in expected_keys)):
        return ""
    reference_digest = hashlib.sha256(json.dumps(dict(active_invocation_reference),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    return "active-resource-release:" + reference_digest + ":" + suffix


def _valid_active_invocation_release_binding(observation: Mapping[str, Any]) -> bool:
    requested = observation.get("active_inference_preemption_requested")
    reference = observation.get("active_inference_request_reference")
    if requested is None and reference is None:
        return True
    if type(requested) is not bool:
        return False
    if not requested:
        return reference is None
    if not isinstance(reference, Mapping):
        return False
    required = {"request_id", "request_digest", "correlation_id"}
    return (set(reference) == required and all(
        isinstance(reference.get(key), str) and bool(reference.get(key))
        for key in required))


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
    evidence_refs: dict[str, object] = field(default_factory=dict)

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
            "evidence_refs": dict(self.evidence_refs),
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
        policy = resolve_policy()
        self._policy_profile = policy.profile
        self._policy_source = policy.source
        self._mode = policy.runtime_governor
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
        self._subject_state_cap = self._env_int("SENTIENTOS_GOVERNOR_SUBJECT_STATE_CAP", 64)
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
            "local_model_inference": ActionProfile("local_model_inference", priority=3, family="local_model", local_safety=True, deferrable=True),
            "local_model_serving": ActionProfile("local_model_serving", priority=3, family="local_model", local_safety=True, deferrable=True),
            "local_model_resource_release": ActionProfile("local_model_resource_release", priority=0, family="local_model", local_safety=True, deferrable=False),
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
        # The observation runtime may publish one validated, read-only host
        # resource evaluation. Its identifiers, pressure labels, measured
        # CPU/RAM/GPU/VRAM values, and sensor coverage are retained as
        # scheduling input, never as host mutation authority.
        self._host_resource_evidence: dict[str, object] | None = None
        self._host_resource_evidence_by_correlation: dict[str, dict[str, object]] = {}
        # Fresh bridge-authenticated game pacing is supplemental scheduling
        # evidence, never a substitute for the host-resource observation epoch.
        self._game_performance_evidence: dict[str, object] | None = None
        # Bridge-authenticated allowlisted game presence remains separate from
        # optional frame pacing evidence; it can prioritize the game when host
        # telemetry is pressured or incomplete without implying process control.
        self._game_workload_evidence: dict[str, object] | None = None
        self._game_workload_evidence_by_message_id: dict[str, dict[str, object]] = {}
        self._resource_evidence_lock = threading.Lock()

    @staticmethod
    def _restriction_class_for_reason(reason: str) -> str:
        if reason.startswith("degraded_audit_trust"):
            return "audit_trust"
        if reason.startswith("runtime_feedback"):
            return "runtime_feedback"
        if reason.startswith("federated_"):
            return "federation"
        if reason.startswith("pulse_epoch"):
            return "pulse_epoch"
        if reason.startswith("peer_trust"):
            return "federation"
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

    def _evaluate_runtime_feedback_posture(
        self,
        *,
        action_class: str,
        metadata: dict[str, object] | None,
    ) -> tuple[PostureRuleEvaluation, dict[str, object]]:
        provided_feedback = (metadata or {}).get("runtime_feedback")
        feedback = dict(provided_feedback) if isinstance(provided_feedback, Mapping) else {}
        runtime_local_degraded = bool(feedback.get("degraded", False))
        evolution_feedback = self._load_evolution_feedback_signal()
        if evolution_feedback["degraded"]:
            feedback["degraded"] = True
            feedback["evolution_signal"] = evolution_feedback

        if not feedback:
            evaluation = PostureRuleEvaluation(
                dimension="runtime_feedback",
                reason="runtime_feedback_missing",
                restriction_class="none",
                blocks=False,
                precedence=20,
                details={
                    "present": False,
                    "evolution_signal_degraded": bool(evolution_feedback["degraded"]),
                    "evolution_signal_reason": evolution_feedback["reason"],
                    "surface_disagreement": False,
                    "runtime_local_degraded": runtime_local_degraded,
                    "reconciliation": evolution_feedback.get("reconciliation", {}),
                },
            )
            return evaluation, {"runtime_feedback": {"present": False}, "evolution_feedback_signal": evolution_feedback}

        degraded = bool(feedback.get("degraded", False))
        reason = "runtime_feedback_nominal"
        blocks = False
        if degraded and action_class in {"control_plane_task", "amendment_apply"}:
            reason, blocks = "runtime_feedback_degraded_maintenance", True
        elif degraded and action_class == "repair_action":
            reason = "runtime_feedback_repair_priority"
        evaluation = PostureRuleEvaluation(
            dimension="runtime_feedback",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=85,
            details={
                "degraded": degraded,
                "source": "runtime_or_evolution_feedback",
                "evolution_signal_degraded": bool(evolution_feedback["degraded"]),
                "evolution_signal_reason": evolution_feedback["reason"],
                "surface_disagreement": runtime_local_degraded != bool(evolution_feedback["degraded"]),
                "runtime_local_degraded": runtime_local_degraded,
                "reconciliation": evolution_feedback.get("reconciliation", {}),
            },
        )
        return evaluation, {"runtime_feedback": dict(feedback), "evolution_feedback_signal": evolution_feedback}

    def _load_evolution_feedback_signal(self) -> dict[str, object]:
        state_path = self._repo_root / "glow/forge/merge_train.json"
        if not state_path.exists():
            return {
                "present": False,
                "degraded": False,
                "reason": "merge_train_state_missing",
                "path": str(state_path),
                "last_error": None,
            }
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "present": True,
                "degraded": False,
                "reason": "merge_train_state_unreadable",
                "path": str(state_path),
                "last_error": None,
            }
        entries_value: object = payload.get("entries") if isinstance(payload, dict) else None
        entries = entries_value if isinstance(entries_value, list) else []
        degraded_errors = {
            "audit_integrity_failed",
            "remote_doctrine_failed",
            "remote_doctrine_corrupt_bundle",
            "remote_doctrine_metadata_mismatch",
            "remote_doctrine_manifest_missing",
            "remote_doctrine_manifest_mismatch",
            "checks_failed",
            "merge_failed",
        }
        typed_entries = [item for item in entries if isinstance(item, dict)]
        latest = typed_entries[-1] if typed_entries else {}
        latest_status = str(latest.get("status") or "")
        latest_error = str(latest.get("last_error") or "")
        stale_integrity_failures = 0
        if typed_entries:
            history = typed_entries[:-1]
            for item in history:
                status = str(item.get("status") or "")
                error = str(item.get("last_error") or "")
                if status in {"held", "failed"} and error in degraded_errors:
                    stale_integrity_failures += 1

        if latest_status in {"held", "failed"} and latest_error in degraded_errors:
            return {
                "present": True,
                "degraded": True,
                "reason": "merge_train_integrity_failure",
                "path": str(state_path),
                "last_error": latest_error,
                "latest_entry_status": latest_status,
                "reconciliation": {
                    "state": "none",
                    "rule": "latest_entry_authoritative",
                    "disagreement_kind": "none",
                },
            }
        if stale_integrity_failures > 0:
            return {
                "present": True,
                "degraded": False,
                "reason": "merge_train_recovered_latest_entry",
                "path": str(state_path),
                "last_error": None,
                "latest_entry_status": latest_status or "unknown",
                "reconciliation": {
                    "state": "reconciled",
                    "rule": "latest_entry_authoritative",
                    "disagreement_kind": "stale_evolution_failure_cleared",
                    "stale_integrity_failure_count": stale_integrity_failures,
                },
            }
        if not typed_entries:
            return {
                "present": True,
                "degraded": False,
                "reason": "merge_train_state_empty",
                "path": str(state_path),
                "last_error": None,
                "latest_entry_status": "none",
                "reconciliation": {
                    "state": "none",
                    "rule": "latest_entry_authoritative",
                    "disagreement_kind": "none",
                },
            }
        return {
            "present": True,
            "degraded": False,
            "reason": "merge_train_nominal",
            "path": str(state_path),
            "last_error": None,
            "latest_entry_status": latest_status or "unknown",
            "reconciliation": {
                "state": "none",
                "rule": "latest_entry_authoritative",
                "disagreement_kind": "none",
            },
        }

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
        compatibility_category = str(governance.get("compatibility_category") or "incompatible")
        epoch_status = str(governance.get("epoch_status") or "unknown")
        quorum_satisfied = bool(governance.get("quorum_satisfied", False))

        if action_class == "federated_control":
            policy = resolve_policy()
            governance_posture = str(governance.get("calibration_posture") or policy.governance_digest)
            governance_action = str(governance.get("calibration_action") or "observe")
            governance_reason = str(governance.get("calibration_reason") or "federated_governance_nominal")
            if epoch_status == "unexpected" and denial_cause in {"trust_epoch", "trust_epoch_advisory", "trust_epoch_observed"}:
                if governance_action == "deny":
                    reason, blocks = "federated_unexpected_epoch_blocked", True
                elif governance_action == "warn":
                    reason = "federated_unexpected_epoch_warning"
                else:
                    reason = "federated_unexpected_epoch_observed"
            elif compatibility_category == "locally_restricted":
                reason, blocks = "federated_locally_restricted", True
            elif digest_status in {"missing", "incompatible"} or denial_cause in {
                "digest_mismatch",
                "digest_mismatch_advisory",
                "digest_mismatch_observed",
            }:
                if governance_action == "deny":
                    reason, blocks = "federated_digest_mismatch_blocked", True
                elif governance_action == "warn":
                    reason = "federated_digest_mismatch_warning"
                else:
                    reason = "federated_digest_mismatch_observed"
            elif denial_cause == "peer_trust_restricted":
                reason, blocks = "federated_peer_trust_restricted", True
            elif not quorum_satisfied or denial_cause in {"quorum_failure", "quorum_warning", "quorum_observed"}:
                if governance_action == "deny":
                    reason, blocks = "federated_quorum_not_satisfied", True
                elif governance_action == "warn":
                    reason = "federated_quorum_warning"
                else:
                    reason = "federated_quorum_observed"
            governance["calibration_posture"] = governance_posture
            governance["calibration_action"] = governance_action
            governance["calibration_reason"] = governance_reason

        evaluation = PostureRuleEvaluation(
            dimension="federated_governance",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=110,
            details=dict(governance),
        )
        return evaluation, {"federated_governance": dict(governance)}

    def _evaluate_peer_trust_posture(
        self,
        *,
        action_class: str,
        origin: str,
    ) -> tuple[PostureRuleEvaluation, dict[str, object]]:
        trust = get_trust_ledger().get_peer_trust(origin)
        reason = "peer_trust_nominal"
        blocks = False
        if action_class == "federated_control":
            if trust.trust_state == "incompatible":
                reason, blocks = "peer_trust_incompatible_blocked", True
            elif trust.trust_state == "quarantined":
                reason, blocks = "peer_trust_quarantined_blocked", True
            elif trust.trust_state == "degraded":
                reason = "peer_trust_degraded_tightened"
            elif trust.trust_state == "watched":
                reason = "peer_trust_watched"
        evaluation = PostureRuleEvaluation(
            dimension="peer_trust",
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=108,
            details=trust.to_dict(),
        )
        return evaluation, {"peer_trust": trust.to_dict()}

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
        pulse_mode = resolve_policy().pulse_trust_epoch
        if trust_class in {"revoked_epoch", "invalid_signature"}:
            if pulse_mode == "enforce":
                reason, blocks = "pulse_epoch_untrusted_federation_blocked", True
            elif pulse_mode == "advisory":
                reason = "pulse_epoch_untrusted_federation_warning"
            else:
                reason = "pulse_epoch_untrusted_federation_observed"
        elif trust_class and trust_class not in {"current_trusted_epoch", "historical_closed_epoch", "retired_epoch_replay_allowed"}:
            if pulse_mode == "enforce":
                reason, blocks = "pulse_epoch_mismatch_escalation_required", True
            elif pulse_mode == "advisory":
                reason = "pulse_epoch_mismatch_warning"
            else:
                reason = "pulse_epoch_mismatch_observed"
        elif compromise_mode:
            if action_class in {"federated_control", "amendment_apply", "control_plane_task"}:
                if pulse_mode == "enforce":
                    reason, blocks = "pulse_epoch_compromise_restricted", True
                elif pulse_mode == "advisory":
                    reason = "pulse_epoch_compromise_warning"
                else:
                    reason = "pulse_epoch_compromise_observed"
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
        payload: dict[str, object] = {
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
        fairness_mode = resolve_policy().subject_fairness
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
                reason=("deferred_starvation_under_pressure" if fairness_mode == "enforce" else "fairness_starvation_warning"),
                restriction_class="fairness",
                blocks=fairness_mode == "enforce",
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
            "restart_daemon": ("subject", "daemon_name", "target", "daemon"),
            "repair_action": ("subject", "anomaly_subject", "anomaly_key", "target"),
            "federated_control": ("subject", "peer_subject", "peer", "federated_source", "peer_name", "target"),
            "control_plane_task": ("subject", "task_key", "task_origin", "request_type", "target"),
            "amendment_apply": ("subject", "amendment_target", "target"),
        }
        global_priority = ("subject", "daemon_name", "peer", "anomaly_key", "target")
        for key in (*keys_by_class.get(action_class, ()), *global_priority):
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
        def _as_int(value: object) -> int:
            return value if isinstance(value, int) else 0

        def _as_float(value: object) -> float:
            return float(value) if isinstance(value, (int, float)) else 0.0

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
                row: dict[str, object] = {
                    "subject": subject,
                    "attempts": attempts_by_subject.get(subject, 0),
                    "admit": subject_decisions.get("admit", 0),
                    "defer": subject_decisions.get("defer", 0),
                    "deny": subject_decisions.get("deny", 0),
                    "denied_streak": self._subject_denied_streak[action_class].get(subject, 0),
                }
                class_rows.append(row)

                denied_streak = _as_int(row.get("denied_streak", 0))
                admit_count = _as_int(row.get("admit", 0))
                deny_count = _as_int(row.get("deny", 0))
                if denied_streak >= self._starvation_streak_threshold:
                    starved_subjects.append({"action_class": action_class, **row})

                if (
                    class_admits >= self._noisy_subject_min_admits
                    and len(subjects) > 1
                    and class_admits > 0
                ):
                    share = round(admit_count / class_admits, 4)
                    if share >= self._noisy_subject_share_threshold:
                        noisy_subjects.append({"action_class": action_class, **row, "admit_share": share})

                peers_admit = class_admits - admit_count
                if peers_admit > 0 and deny_count > 0 and admit_count == 0:
                    denied_while_peers_admitted.append({"action_class": action_class, **row, "peer_admit": peers_admit})

            class_rows.sort(key=lambda item: (-_as_int(item.get("deny", 0)), -_as_int(item.get("defer", 0)), str(item.get("subject", ""))))
            per_class[action_class] = {
                "subject_count": len(class_rows),
                "subjects": class_rows[: self._subject_summary_limit],
            }

        def _sort_rows(rows: list[dict[str, object]], key_name: str) -> list[dict[str, object]]:
            return sorted(rows, key=lambda item: (-_as_int(item.get(key_name, 0)), str(item.get("action_class", "")), str(item.get("subject", ""))))

        return {
            "streak_threshold": self._starvation_streak_threshold,
            "summary_limit": self._subject_summary_limit,
            "per_class": per_class,
            "starved_subjects": _sort_rows(starved_subjects, "denied_streak")[: self._subject_summary_limit],
            "noisy_subjects": sorted(
                noisy_subjects,
                key=lambda item: (-_as_float(item.get("admit_share", 0.0)), str(item.get("action_class", "")), str(item.get("subject", ""))),
            )[: self._subject_summary_limit],
            "denied_while_peers_admitted": _sort_rows(denied_while_peers_admitted, "deny")[: self._subject_summary_limit],
        }

    def _trim_subject_events(self, now: datetime) -> None:
        cutoff = now - self._contention_window
        while self._subject_events and self._subject_events[0][0] < cutoff:
            self._subject_events.popleft()

    def _queue_pressure_summary(self, now: datetime) -> dict[str, object]:
        def _coerce_int(value: object) -> int:
            return value if isinstance(value, int) else 0

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
        top_subjects.sort(
            key=lambda item: (
                -_coerce_int(item.get("blocked_pressure", 0)),
                -_coerce_int(item.get("retries", 0)),
                str(item.get("action_class", "")),
                str(item.get("subject", "")),
            )
        )

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
        federation = get_federated_governance_controller()
        local_digest = federation.local_governance_digest().to_dict()
        quorum_status: dict[str, object] | None = None
        mismatch_report: dict[str, object] | None = None
        try:
            quorum_payload = json.loads((self._root / "quorum_status.json").read_text(encoding="utf-8"))
            if isinstance(quorum_payload, dict):
                quorum_status = quorum_payload
        except (OSError, json.JSONDecodeError):
            quorum_status = None
        try:
            mismatch_payload = json.loads((self._root / "governance_digest_mismatch_report.json").read_text(encoding="utf-8"))
            if isinstance(mismatch_payload, dict):
                mismatch_report = mismatch_payload
        except (OSError, json.JSONDecodeError):
            mismatch_report = None
        starvation = self._starvation_signals()
        fairness = self._subject_fairness_summary()
        queue_pressure = self._queue_pressure_summary(datetime.now(timezone.utc))
        starvation_denied_streaks = starvation.get("denied_streaks")
        denied_streaks = starvation_denied_streaks if isinstance(starvation_denied_streaks, Mapping) else {}
        class_summary = {
            action_class: {
                "attempts": self._class_attempts.get(action_class, 0),
                "admit": self._class_decisions.get(action_class, {}).get("admit", 0),
                "defer": self._class_decisions.get(action_class, {}).get("defer", 0),
                "deny": self._class_decisions.get(action_class, {}).get("deny", 0),
                "denied_streak": int(denied_streaks.get(action_class, 0)),
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
            "policy_profile": self._policy_profile,
            "policy_source": self._policy_source,
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
            "federation_governance": {
                "local_governance_digest": local_digest,
                "quorum_status": quorum_status,
                "latest_digest_mismatch_report": mismatch_report,
            },
        }

    def _write_rollup(self) -> None:
        rollup = self._build_rollup()
        self._rollup_path.write_text(json.dumps(rollup, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        fairness = rollup.get("subject_fairness", {})
        (self._root / "subject_fairness_rollup.json").write_text(
            json.dumps({"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "subject_fairness": fairness}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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
        if normalized == "local_model_inference":
            return self._admit_local_model_inference(
                actor=actor,
                subject=subject,
                metadata=payload,
                correlation_id=correlation_id,
            )
        if normalized == "local_model_serving":
            return self._admit_local_model_serving(
                actor=actor, subject=subject, metadata=payload,
                correlation_id=correlation_id)
        if normalized == "local_model_resource_release":
            return self._admit_local_model_resource_release(
                actor=actor, subject=subject, metadata=payload,
                correlation_id=correlation_id)
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

    def observe_host_resource_evaluation(self, evaluation: object) -> bool:
        """Accept only a valid proposal-only collector evaluation for scheduling."""
        try:
            from sentientos.host_resource_runtime import HostResourceRuntimeEvaluation, validate_evaluation

            if type(evaluation) is not HostResourceRuntimeEvaluation or not validate_evaluation(evaluation).ok:
                return False
            if not evaluation.no_effect_authority or evaluation.plan.effect_authority:
                return False
            evidence: dict[str, object] = {
                "evaluation_id": evaluation.evaluation_id,
                "semantic_digest": evaluation.semantic_digest,
                "epoch_id": evaluation.epoch.epoch_id,
                "observed_at": evaluation.epoch.observed_at,
                "snapshot_id": evaluation.snapshot.snapshot_id,
                "report_id": evaluation.pressure_report.report_id,
                "report_digest": evaluation.policy_decision.report_digest,
                "gpu_telemetry_sources": [
                    {"collector_id": result.collector_id, "status": result.status,
                     "source": result.source[:128]}
                    for result in evaluation.epoch.results
                    if result.collector_id == "nvidia_gpu"
                ],
                "pressure_labels": tuple(evaluation.pressure_report.pressure_labels),
                "cpu_utilization_percent": evaluation.snapshot.cpu_utilization_percent,
                "ram_utilization_percent": evaluation.snapshot.ram_utilization_percent,
                "gpu_utilization_percent": evaluation.snapshot.gpu_utilization_percent,
                "vram_utilization_percent": evaluation.snapshot.vram_utilization_percent,
                "thermal_zone_temperatures_c": dict(
                    evaluation.snapshot.thermal_zone_temperatures_c),
                "gpu_telemetry_available": (
                    evaluation.snapshot.gpu_utilization_percent is not None
                    or evaluation.snapshot.vram_utilization_percent is not None
                ),
                "gpu_telemetry_complete": (
                    evaluation.snapshot.gpu_utilization_percent is not None
                    and evaluation.snapshot.vram_utilization_percent is not None
                ),
                "observation_correlation_id": evaluation.epoch.correlation_id,
            }
            with self._resource_evidence_lock:
                self._host_resource_evidence = evidence
                self._host_resource_evidence_by_correlation[
                    evaluation.epoch.correlation_id] = evidence
                while (len(self._host_resource_evidence_by_correlation)
                       > MAX_RETAINED_HOST_RESOURCE_EVIDENCE):
                    oldest = next(iter(self._host_resource_evidence_by_correlation))
                    del self._host_resource_evidence_by_correlation[oldest]
            return True
        except (ImportError, AttributeError, TypeError, ValueError):
            return False

    def observe_verified_game_performance(self, observation: object) -> bool:
        """Retain one fresh, authenticated Windows game pacing observation."""
        try:
            from sentientos.game_performance_bridge import VerifiedGamePerformanceObservation

            if type(observation) is not VerifiedGamePerformanceObservation:
                return False
            observed_at = datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00"))
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                return False
            source_observed_at = (getattr(observation, "source_observed_at", None)
                or observation.observed_at)
            if not isinstance(source_observed_at, str):
                return False
            source_timestamp = datetime.fromisoformat(
                source_observed_at.replace("Z", "+00:00"))
            if source_timestamp.tzinfo is None or source_timestamp.utcoffset() is None:
                return False
            source_clock_offset = getattr(observation,
                "source_clock_offset_seconds", 0.0)
            if (isinstance(source_clock_offset, bool)
                    or not isinstance(source_clock_offset, (int, float))
                    or not math.isfinite(float(source_clock_offset))
                    or abs(float(source_clock_offset)) > 30.0):
                return False
            if (getattr(observation, "source_observed_at", None) is None
                    and float(source_clock_offset) != 0.0):
                return False
            normalized_source_timestamp = (source_timestamp.astimezone(timezone.utc)
                - timedelta(seconds=float(source_clock_offset)))
            if abs((observed_at.astimezone(timezone.utc)
                    - normalized_source_timestamp).total_seconds()) > 0.002:
                return False
            age = (datetime.now(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds()
            if (age < 0 or age > 10 or observation.status not in {"available", "partial"}
                    or not isinstance(observation.source_id, str) or not observation.source_id
                    or not isinstance(observation.generation_id, str) or not observation.generation_id
                    or type(observation.sequence) is not int or observation.sequence < 1
                    or not isinstance(observation.message_id, str)
                    or re.fullmatch(r"[0-9a-f]{64}", observation.message_id) is None
                    or not isinstance(observation.payload_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", observation.payload_digest) is None
                    or not isinstance(observation.process_id_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", observation.process_id_digest) is None
                    or (observation.process_name_digest is not None
                        and (not isinstance(observation.process_name_digest, str)
                            or re.fullmatch(r"[0-9a-f]{64}",
                                observation.process_name_digest) is None))):
                return False
            p95, hitches = observation.frame_time_p95_ms, observation.hitch_count_over_50ms
            if p95 is not None and (isinstance(p95, bool) or not isinstance(p95, (int, float))
                    or not math.isfinite(float(p95)) or not 0 < p95 <= 10_000):
                return False
            if hitches is not None and (type(hitches) is not int or not 0 <= hitches <= 100_000):
                return False
            process_cpu = observation.process_cpu_percent
            process_rss = observation.process_rss_bytes
            if (process_cpu is not None
                    and (isinstance(process_cpu, bool)
                        or not isinstance(process_cpu, (int, float))
                        or not math.isfinite(float(process_cpu))
                        or not 0 <= float(process_cpu) <= 10_000)):
                return False
            if (process_rss is not None
                    and (type(process_rss) is not int or not 0 <= process_rss <= 2**63 - 1)):
                return False
            if (p95 is None and hitches is None
                    and process_cpu is None and process_rss is None):
                return False
            evidence: dict[str, object] = {
                "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
                "source_observed_at": source_timestamp.astimezone(
                    timezone.utc).isoformat(),
                "source_clock_offset_seconds": float(source_clock_offset),
                "source_id": observation.source_id,
                "generation_id": observation.generation_id,
                "sequence": observation.sequence,
                "message_id": observation.message_id,
                "payload_digest": observation.payload_digest,
                "process_id_digest": observation.process_id_digest,
                "process_name_digest": observation.process_name_digest,
                "frame_time_p95_ms": float(p95) if p95 is not None else None,
                "hitch_count_over_50ms": hitches,
                "process_cpu_percent": (float(process_cpu)
                    if process_cpu is not None else None),
                "process_rss_bytes": process_rss,
            }
            with self._resource_evidence_lock:
                previous = self._game_performance_evidence
                if (previous is not None
                        and previous.get("source_id") == evidence["source_id"]
                        and previous.get("generation_id") == evidence["generation_id"]):
                    previous_sequence = previous.get("sequence")
                    previous_observed_at = previous.get("observed_at")
                    if type(previous_sequence) is not int or not isinstance(
                            previous_observed_at, str):
                        return False
                    previous_timestamp = datetime.fromisoformat(
                        previous_observed_at.replace("Z", "+00:00"))
                    if (previous_timestamp.tzinfo is None
                            or previous_timestamp.utcoffset() is None
                            or observation.sequence <= previous_sequence
                            or observed_at.astimezone(timezone.utc)
                                < previous_timestamp.astimezone(timezone.utc)):
                        return False
                self._game_performance_evidence = evidence
            return True
        except (ImportError, AttributeError, TypeError, ValueError, OverflowError):
            return False

    def current_verified_game_performance_evidence(self) -> dict[str, object] | None:
        """Return the current authenticated game-pacing sample for bounded consumers."""
        with self._resource_evidence_lock:
            evidence = (dict(self._game_performance_evidence)
                if self._game_performance_evidence is not None else None)
        if evidence is None:
            return None
        try:
            observed_at = datetime.fromisoformat(str(evidence["observed_at"]))
            age = (datetime.now(timezone.utc)
                - observed_at.astimezone(timezone.utc)).total_seconds()
        except (KeyError, TypeError, ValueError):
            return None
        return evidence if 0 <= age <= 10 else None

    def observe_verified_game_workload(self, observation: object) -> bool:
        """Retain fresh bridge-verified allowlisted game-presence evidence."""
        try:
            from sentientos.foreground_game_detection import ForegroundGameObservation

            if type(observation) is not ForegroundGameObservation:
                return False
            observed_at = datetime.fromisoformat(
                observation.observed_at.replace("Z", "+00:00"))
            provenance = observation.transport_provenance
            if not isinstance(provenance, Mapping):
                return False
            message_id = provenance.get("message_id")
            source_id = provenance.get("source_id")
            generation_id = provenance.get("generation_id")
            session_id = provenance.get("session_id")
            sequence = provenance.get("sequence")
            envelope_time = provenance.get("envelope_created_at")
            running_names = observation.running_process_name_digests
            if (running_names is not None
                    and (not isinstance(running_names, (tuple, list))
                        or len(running_names) > 32
                        or any(not isinstance(value, str)
                            or re.fullmatch(r"[0-9a-f]{64}", value) is None
                            for value in running_names))):
                return False
            if (observed_at.tzinfo is None or observed_at.utcoffset() is None
                    or observation.status != "available"
                    or type(observation.game_foreground) is not bool
                    or (observation.game_process_running is not None
                        and type(observation.game_process_running) is not bool)
                    or not isinstance(observation.process_name_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", observation.process_name_digest) is None
                    or not isinstance(message_id, str)
                    or re.fullmatch(r"[0-9a-f]{64}", message_id) is None
                    or not isinstance(source_id, str) or not source_id
                    or not isinstance(generation_id, str) or not generation_id
                    or not isinstance(session_id, str) or not session_id
                    or type(sequence) is not int or sequence < 1
                    or not isinstance(envelope_time, str)):
                return False
            age = (datetime.now(timezone.utc)
                - observed_at.astimezone(timezone.utc)).total_seconds()
            if age < 0 or age > 10:
                return False
            evidence: dict[str, object] = {
                "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
                "source_id": source_id, "generation_id": generation_id,
                "session_id": session_id, "sequence": sequence,
                "message_id": message_id,
                "process_name_digest": observation.process_name_digest,
                "game_foreground": observation.game_foreground,
                "game_process_running": observation.game_process_running,
                "running_process_name_digests": tuple(
                    running_names or ()),
            }
            with self._resource_evidence_lock:
                self._game_workload_evidence = evidence
                self._game_workload_evidence_by_message_id[message_id] = evidence
                # The edge sends workload and pacing on one ordered source
                # session. A fresh explicit inactive observation supersedes an
                # older pacing sample from that same source generation; keeping
                # the old sample current would continue to defer GPU serving
                # after the game had ended. Preserve samples from other source
                # generations and any pacing sample observed later in time.
                performance = self._game_performance_evidence
                if (observation.game_foreground is False
                        and observation.game_process_running is False
                        and performance is not None
                        and performance.get("source_id") == source_id
                        and performance.get("generation_id") == generation_id):
                    try:
                        performance_time = datetime.fromisoformat(
                            str(performance["observed_at"]).replace("Z", "+00:00"))
                    except (KeyError, TypeError, ValueError):
                        performance_time = None
                    if (performance_time is not None
                            and performance_time.tzinfo is not None
                            and performance_time.astimezone(timezone.utc)
                                <= observed_at.astimezone(timezone.utc)):
                        self._game_performance_evidence = None
                while (len(self._game_workload_evidence_by_message_id)
                       > MAX_RETAINED_GAME_WORKLOAD_EVIDENCE):
                    oldest = next(iter(self._game_workload_evidence_by_message_id))
                    del self._game_workload_evidence_by_message_id[oldest]
            return True
        except (ImportError, AttributeError, TypeError, ValueError, OverflowError):
            return False

    def _admit_local_model_resource_release(
        self, *, actor: str, subject: str, metadata: dict[str, object] | None,
        correlation_id: str | None,
    ) -> GovernorDecision:
        """Admit a narrowly scoped, fail-safe local model residency release."""
        from sentientos.host_resource_runtime import (
            HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS,
        )

        payload = dict(metadata or {})
        identity_digest = payload.get("model_identity_digest")
        reason_code = payload.get("reason_code")
        valid = (
            payload.get("purpose") == "local_model_resource_release"
            and reason_code in {
                "gaming_mode_entered",
                "development_chat_shutdown",
                "vram_pressure_observed",
                "host_gpu_pressure_observed",
                "host_memory_pressure_observed",
                "verified_game_gpu_pressure",
                "verified_game_host_pressure",
                "verified_game_gpu_model_residency",
                "selected_gaming_profile_gpu_model_residency",
                "verified_game_frame_pressure",
                "selected_gaming_profile_host_pressure",
                "conservative_automatic_profile_host_pressure",
                "rootless_experimental_epistemic_complete",
                "rootless_experimental_developmental_complete",
            }
            and isinstance(identity_digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", identity_digest) is not None
        )
        evidence_ref: dict[str, object] = {"status": "not_required"}
        if reason_code == "vram_pressure_observed":
            observation_value = payload.get("resource_observation")
            evidence_valid = False
            observed_at_text: str | None = None
            age_seconds: float | None = None
            utilization_value: float | None = None
            threshold_value: float | None = None
            if isinstance(observation_value, Mapping):
                def finite_number(value: object) -> float | None:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        numeric = float(value)
                        return numeric if math.isfinite(numeric) else None
                    return None

                expected_observation_fields = {
                    "schema_version", "admission_status", "reason_code",
                    "preload_admission_status", "preload_reason_code",
                    "preload_threshold_percent", "vram_utilization_percent",
                    "observed_at", "release_threshold_percent",
                    "recovery_threshold_percent", "stale_after_seconds",
                }
                raw_observed_at = observation_value.get("observed_at")
                raw_utilization = observation_value.get("vram_utilization_percent")
                raw_threshold = observation_value.get("release_threshold_percent")
                raw_preload_threshold = observation_value.get("preload_threshold_percent")
                raw_recovery_threshold = observation_value.get("recovery_threshold_percent")
                raw_stale_after = observation_value.get("stale_after_seconds")
                utilization_value = finite_number(raw_utilization)
                threshold_value = finite_number(raw_threshold)
                preload_threshold = finite_number(raw_preload_threshold)
                recovery_threshold = finite_number(raw_recovery_threshold)
                stale_after = finite_number(raw_stale_after)
                if isinstance(raw_observed_at, str):
                    observed_at_text = raw_observed_at
                try:
                    parsed_observed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed_observed_at = None
                if parsed_observed_at is not None and parsed_observed_at.tzinfo is not None:
                    age_seconds = (datetime.now(timezone.utc)
                        - parsed_observed_at.astimezone(timezone.utc)).total_seconds()
                if (utilization_value is not None and threshold_value is not None
                        and preload_threshold is not None and recovery_threshold is not None
                        and stale_after is not None):
                    evidence_valid = (
                        set(observation_value) == expected_observation_fields
                        and observation_value.get("schema_version") == "sentientos.gaming_vram_admission_evidence:v1"
                        and observation_value.get("admission_status") == "deferred"
                        and observation_value.get("reason_code") == "vram_pressure"
                        and observation_value.get("preload_admission_status") == "deferred"
                        and observation_value.get("preload_reason_code") == "preload_vram_headroom_insufficient"
                        and 0 <= utilization_value <= 100
                        and 0 <= threshold_value <= utilization_value
                        and 0 <= preload_threshold <= 100
                        and 0 <= recovery_threshold < threshold_value
                        and 0 < stale_after <= 120
                        and parsed_observed_at is not None and parsed_observed_at.tzinfo is not None
                        and age_seconds is not None
                        and 0 <= age_seconds <= min(stale_after, 30.0)
                    )
            valid = valid and evidence_valid
            if evidence_valid:
                assert age_seconds is not None
                evidence_ref = {"status": "current", "observed_at": observed_at_text,
                    "age_seconds": round(age_seconds, 3),
                    "vram_utilization_percent": utilization_value,
                    "release_threshold_percent": threshold_value}
            else:
                evidence_ref = {"status": "missing_stale_malformed_or_below_threshold"}
        elif reason_code == "host_gpu_pressure_observed":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "observation_correlation_id", "host_report_id", "host_report_digest",
                "observed_at", "pressure_labels", "gpu_utilization_percent",
                "vram_utilization_percent", "serving_session_id",
                "model_gpu_layers", "active_inference_preemption_requested",
            }
            evidence_valid = False
            host_gpu_observation_id: str | None = None
            host_gpu_report_id: str | None = None
            host_gpu_source_correlation = None
            host_gpu_value = host_vram_value = None
            host_gpu_release_age_seconds = host_gpu_evidence_age = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                source_value = observation_value.get("trigger_correlation_id")
                host_gpu_source_correlation = (source_value if isinstance(source_value, str)
                    else None)
                observation_value_id = observation_value.get(
                    "observation_correlation_id")
                host_gpu_observation_id = (observation_value_id
                    if isinstance(observation_value_id, str) else None)
                raw_report_id = observation_value.get("host_report_id")
                host_gpu_report_id = (raw_report_id
                    if isinstance(raw_report_id, str) else None)
                raw_observed_at = observation_value.get("observed_at")
                raw_labels = observation_value.get("pressure_labels")

                def finite_percent(value: object) -> float | None:
                    if (isinstance(value, (int, float)) and not isinstance(value, bool)
                            and math.isfinite(float(value))
                            and 0 <= float(value) <= 100):
                        return float(value)
                    return None

                host_gpu_value = finite_percent(observation_value.get(
                    "gpu_utilization_percent"))
                host_vram_value = finite_percent(observation_value.get(
                    "vram_utilization_percent"))
                expected_observation_id = ("local-chat-reconciliation-" +
                    hashlib.sha256(host_gpu_source_correlation.encode(
                        "utf-8")).hexdigest()[:32]
                    if host_gpu_source_correlation is not None else None)
                expected_release_correlation = (_expected_resource_release_correlation(
                    "idle_host_gpu_resource_reconciliation", host_gpu_source_correlation,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if host_gpu_source_correlation is not None else None)
                try:
                    parsed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed_at = None
                if parsed_at is not None and parsed_at.tzinfo is not None:
                    host_gpu_release_age_seconds = (datetime.now(timezone.utc)
                        - parsed_at.astimezone(timezone.utc)).total_seconds()
                with self._resource_evidence_lock:
                    host_evidence = (self._host_resource_evidence_by_correlation.get(
                        host_gpu_observation_id)
                        if host_gpu_observation_id is not None else None)
                try:
                    if host_evidence is not None:
                        host_gpu_evidence_age = (datetime.now(timezone.utc)
                            - datetime.fromisoformat(
                            str(host_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                except (KeyError, TypeError, ValueError):
                    host_gpu_evidence_age = None
                raw_host_labels = (host_evidence.get("pressure_labels")
                    if host_evidence is not None else None)
                host_labels = (set(raw_host_labels)
                    if isinstance(raw_host_labels, (tuple, list, set, frozenset))
                    and all(isinstance(label, str) for label in raw_host_labels) else set())
                raw_digest = observation_value.get("host_report_digest")
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_host_gpu_pressure_release_evidence:v1"
                    and observation_value.get("trigger_kind") ==
                        "idle_host_gpu_resource_reconciliation"
                    and isinstance(host_gpu_source_correlation, str)
                    and host_gpu_source_correlation.startswith(
                        "idle-host-gpu-resource-reconcile-")
                    and 0 < len(host_gpu_source_correlation) <= 256
                    and host_gpu_observation_id == expected_observation_id
                    and correlation_id == expected_release_correlation
                    and actor == "production_chat_host_resource_governor"
                    and subject == actor
                    and payload.get("target_subsystem") == "production_chat"
                    and isinstance(host_gpu_report_id, str)
                    and bool(host_gpu_report_id)
                    and isinstance(raw_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", raw_digest) is not None
                    and isinstance(raw_observed_at, str)
                    and isinstance(raw_labels, (list, tuple))
                    and all(isinstance(label, str) for label in raw_labels)
                    and set(raw_labels) == host_labels
                    and "gpu_pressure" in host_labels
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and observation_value.get(
                        "active_inference_preemption_requested") is False
                    and _valid_active_invocation_release_binding(payload)
                    and type(observation_value.get("model_gpu_layers")) is int
                    and 1 <= observation_value["model_gpu_layers"] <= 256
                    and isinstance(observation_value.get("serving_session_id"), str)
                    and bool(observation_value.get("serving_session_id"))
                    and ((host_gpu_value is not None and host_gpu_value >= 90.0)
                         or (host_vram_value is not None and host_vram_value >= 90.0))
                    and host_gpu_release_age_seconds is not None
                    and 0 <= host_gpu_release_age_seconds <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and host_gpu_evidence_age is not None
                    and 0 <= host_gpu_evidence_age <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and host_evidence is not None
                    and host_evidence.get("observation_correlation_id") == host_gpu_observation_id
                    and host_evidence.get("report_id") == host_gpu_report_id
                    and host_evidence.get("report_digest") == raw_digest
                    and host_evidence.get("observed_at") == raw_observed_at
                    and host_evidence.get("gpu_utilization_percent") == host_gpu_value
                    and host_evidence.get("vram_utilization_percent") == host_vram_value)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current",
                "observation_correlation_id": host_gpu_observation_id,
                "host_report_id": host_gpu_report_id,
                "pressure_labels": observation_value.get("pressure_labels"),
                "gpu_utilization_percent": host_gpu_value,
                "vram_utilization_percent": host_vram_value,
                "age_seconds": round(host_gpu_release_age_seconds, 3)
                    if host_gpu_release_age_seconds is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_malformed_or_unverified_host_gpu_pressure"})
        elif reason_code == "host_memory_pressure_observed":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "observation_correlation_id", "host_report_id", "host_report_digest",
                "observed_at", "pressure_labels", "ram_utilization_percent",
                "serving_session_id", "model_gpu_layers",
                "active_inference_preemption_requested",
            }
            evidence_valid = False
            memory_source_correlation = None
            memory_observation_id = None
            memory_report_id = None
            ram_value = None
            release_age = evidence_age = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_source = observation_value.get("trigger_correlation_id")
                memory_source_correlation = raw_source if isinstance(raw_source, str) else None
                raw_observation_id = observation_value.get("observation_correlation_id")
                memory_observation_id = (raw_observation_id
                    if isinstance(raw_observation_id, str) else None)
                raw_report_id = observation_value.get("host_report_id")
                memory_report_id = raw_report_id if isinstance(raw_report_id, str) else None
                raw_observed_at = observation_value.get("observed_at")
                raw_labels = observation_value.get("pressure_labels")
                raw_ram = observation_value.get("ram_utilization_percent")
                if (isinstance(raw_ram, (int, float)) and not isinstance(raw_ram, bool)
                        and math.isfinite(float(raw_ram)) and 0 <= float(raw_ram) <= 100):
                    ram_value = float(raw_ram)
                expected_observation_id = ("local-chat-reconciliation-" +
                    hashlib.sha256(memory_source_correlation.encode("utf-8")).hexdigest()[:32]
                    if memory_source_correlation is not None else None)
                expected_release_correlation = (_expected_resource_release_correlation(
                    str(observation_value.get("trigger_kind")), memory_source_correlation,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if memory_source_correlation is not None else None)
                try:
                    parsed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                    if parsed_at.tzinfo is not None:
                        release_age = (datetime.now(timezone.utc) -
                            parsed_at.astimezone(timezone.utc)).total_seconds()
                except (TypeError, ValueError):
                    pass
                with self._resource_evidence_lock:
                    host_evidence = (self._host_resource_evidence_by_correlation.get(
                        memory_observation_id) if memory_observation_id is not None else None)
                try:
                    if host_evidence is not None:
                        evidence_age = (datetime.now(timezone.utc) -
                            datetime.fromisoformat(str(host_evidence["observed_at"])).astimezone(
                                timezone.utc)).total_seconds()
                except (KeyError, TypeError, ValueError):
                    pass
                raw_host_labels = (host_evidence.get("pressure_labels")
                    if host_evidence is not None else None)
                host_labels = (set(raw_host_labels)
                    if isinstance(raw_host_labels, (tuple, list, set, frozenset))
                    and all(isinstance(label, str) for label in raw_host_labels) else set())
                raw_digest = observation_value.get("host_report_digest")
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_host_memory_pressure_release_evidence:v1"
                    and observation_value.get("trigger_kind") ==
                        "idle_host_memory_resource_reconciliation"
                    and isinstance(memory_source_correlation, str)
                    and memory_source_correlation.startswith((
                        "idle-host-memory-resource-reconcile-",
                        "idle-host-gpu-resource-reconcile-"))
                    and 0 < len(memory_source_correlation) <= 256
                    and memory_observation_id == expected_observation_id
                    and correlation_id == expected_release_correlation
                    and actor == "production_chat_host_resource_governor"
                    and subject == actor
                    and payload.get("target_subsystem") == "production_chat"
                    and isinstance(memory_report_id, str) and bool(memory_report_id)
                    and isinstance(raw_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", raw_digest) is not None
                    and isinstance(raw_observed_at, str)
                    and isinstance(raw_labels, (list, tuple))
                    and all(isinstance(label, str) for label in raw_labels)
                    and set(raw_labels) == host_labels
                    and "memory_pressure" in host_labels
                    and ram_value is not None and ram_value >= 90.0
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and observation_value.get(
                        "active_inference_preemption_requested") is False
                    and _valid_active_invocation_release_binding(payload)
                    and type(observation_value.get("model_gpu_layers")) is int
                    and 0 <= observation_value["model_gpu_layers"] <= 256
                    and isinstance(observation_value.get("serving_session_id"), str)
                    and bool(observation_value.get("serving_session_id"))
                    and release_age is not None
                    and 0 <= release_age <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and evidence_age is not None
                    and 0 <= evidence_age <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and host_evidence is not None
                    and host_evidence.get("observation_correlation_id") == memory_observation_id
                    and host_evidence.get("report_id") == memory_report_id
                    and host_evidence.get("report_digest") == raw_digest
                    and host_evidence.get("observed_at") == raw_observed_at
                    and host_evidence.get("ram_utilization_percent") == ram_value)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current", "observation_correlation_id": memory_observation_id,
                "host_report_id": memory_report_id, "pressure_labels": observation_value.get(
                    "pressure_labels"), "ram_utilization_percent": ram_value,
                "age_seconds": round(release_age, 3) if release_age is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_malformed_or_unverified_host_memory_pressure"})
        elif reason_code == "verified_game_gpu_pressure":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "observation_correlation_id", "host_report_id", "host_report_digest",
                "observed_at", "pressure_labels", "gpu_utilization_percent",
                "vram_utilization_percent", "game_workload_message_id",
            }
            evidence_valid = False
            source_correlation: str | None = None
            observation_id: str | None = None
            report_id: str | None = None
            game_message_id: str | None = None
            gpu_value: float | None = None
            vram_value: float | None = None
            release_age_seconds: float | None = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_trigger_kind = observation_value.get("trigger_kind")
                raw_source = observation_value.get("trigger_correlation_id")
                raw_observation_id = observation_value.get("observation_correlation_id")
                raw_report_id = observation_value.get("host_report_id")
                raw_report_digest = observation_value.get("host_report_digest")
                raw_observed_at = observation_value.get("observed_at")
                raw_labels = observation_value.get("pressure_labels")
                raw_game_id = observation_value.get("game_workload_message_id")

                def finite_percent(value: object) -> float | None:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        numeric = float(value)
                        if math.isfinite(numeric) and 0 <= numeric <= 100:
                            return numeric
                    return None

                gpu_value = finite_percent(observation_value.get("gpu_utilization_percent"))
                vram_value = finite_percent(observation_value.get("vram_utilization_percent"))
                source_correlation = raw_source if isinstance(raw_source, str) else None
                observation_id = raw_observation_id if isinstance(raw_observation_id, str) else None
                report_id = raw_report_id if isinstance(raw_report_id, str) else None
                game_message_id = raw_game_id if isinstance(raw_game_id, str) else None
                namespace = ("local-chat-inference" if raw_trigger_kind == "deferred_inference"
                    else "local-chat-reconciliation" if raw_trigger_kind == "idle_game_reconciliation"
                    else None)
                expected_id = (namespace + "-" + hashlib.sha256(
                    source_correlation.encode("utf-8")).hexdigest()[:32]
                    if source_correlation is not None and namespace is not None else None)
                expected_release_correlation = (_expected_resource_release_correlation(
                    str(raw_trigger_kind), source_correlation,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if source_correlation is not None else None)
                try:
                    parsed_observed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed_observed_at = None
                if (parsed_observed_at is not None and parsed_observed_at.tzinfo is not None
                        and parsed_observed_at.utcoffset() is not None):
                    release_age_seconds = (datetime.now(timezone.utc)
                        - parsed_observed_at.astimezone(timezone.utc)).total_seconds()
                with self._resource_evidence_lock:
                    host_evidence = (self._host_resource_evidence_by_correlation.get(
                        observation_id) if observation_id is not None else None)
                    game_evidence = (self._game_workload_evidence_by_message_id.get(
                        game_message_id) if game_message_id is not None else None)
                host_age: float | None = None
                if host_evidence is not None:
                    try:
                        host_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(host_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                    except (KeyError, TypeError, ValueError):
                        host_age = None
                game_age: float | None = None
                if game_evidence is not None:
                    try:
                        game_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(game_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                    except (KeyError, TypeError, ValueError):
                        game_age = None
                raw_host_labels = (host_evidence.get("pressure_labels")
                    if host_evidence is not None else None)
                host_labels = (set(raw_host_labels)
                    if isinstance(raw_host_labels, (list, tuple, set, frozenset))
                    and all(isinstance(label, str) for label in raw_host_labels) else set())
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_game_gpu_resource_release_evidence:v2"
                    and raw_trigger_kind in {"deferred_inference", "idle_game_reconciliation"}
                    and isinstance(source_correlation, str) and 0 < len(source_correlation) <= 256
                    and observation_id == expected_id
                    and correlation_id == expected_release_correlation
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and _valid_active_invocation_release_binding(payload)
                    and actor == "production_chat_game_resource_governor"
                    and subject == actor
                    and payload.get("target_subsystem") == "production_chat"
                    and isinstance(report_id, str) and isinstance(raw_report_digest, str)
                    and isinstance(raw_observed_at, str)
                    and isinstance(raw_labels, (list, tuple))
                    and all(isinstance(label, str) for label in raw_labels)
                    and "gpu_pressure" in host_labels
                    and set(raw_labels) == host_labels
                    and game_evidence is not None
                    and isinstance(game_message_id, str)
                    and game_evidence.get("message_id") == game_message_id
                    and (game_evidence.get("game_foreground") is True
                         or game_evidence.get("game_process_running") is True)
                    and release_age_seconds is not None
                    and 0 <= release_age_seconds <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and host_age is not None
                    and 0 <= host_age <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and game_age is not None and 0 <= game_age <= 10
                    and host_evidence is not None
                    and host_evidence.get("observation_correlation_id") == observation_id
                    and host_evidence.get("report_id") == report_id
                    and host_evidence.get("report_digest") == raw_report_digest
                    and host_evidence.get("observed_at") == raw_observed_at
                    and host_evidence.get("gpu_utilization_percent") == gpu_value
                    and host_evidence.get("vram_utilization_percent") == vram_value
                    and ((gpu_value is not None and gpu_value >= 90.0)
                         or (vram_value is not None and vram_value >= 90.0)))
            valid = valid and evidence_valid
            if evidence_valid:
                evidence_ref = {
                    "status": "current", "observation_correlation_id": observation_id,
                    "host_report_id": report_id, "game_workload_message_id": game_message_id,
                    "gpu_utilization_percent": gpu_value,
                    "vram_utilization_percent": vram_value,
                    "age_seconds": (round(release_age_seconds, 3)
                        if release_age_seconds is not None else None),
                }
            else:
                evidence_ref = {"status": "missing_stale_malformed_or_unverified_game_gpu_pressure"}
        elif reason_code == "verified_game_frame_pressure":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "serving_session_id", "game_performance_message_id",
                "game_performance_payload_digest", "game_performance_process_id_digest",
                "game_performance_process_name_digest",
                "game_performance_source_id",
                "game_performance_generation_id", "game_performance_sequence",
                "workload_mode", "game_workload_message_id",
                "observed_at", "frame_time_p95_ms", "hitch_count_over_50ms",
            }
            evidence_valid = False
            frame_age_seconds: float | None = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                source = observation_value.get("trigger_correlation_id")
                message_id = observation_value.get("game_performance_message_id")
                payload_digest = observation_value.get("game_performance_payload_digest")
                process_id_digest = observation_value.get(
                    "game_performance_process_id_digest")
                process_name_digest = observation_value.get(
                    "game_performance_process_name_digest")
                source_id = observation_value.get("game_performance_source_id")
                generation_id = observation_value.get("game_performance_generation_id")
                sequence = observation_value.get("game_performance_sequence")
                session_id = observation_value.get("serving_session_id")
                observed_at = observation_value.get("observed_at")
                p95 = observation_value.get("frame_time_p95_ms")
                hitches = observation_value.get("hitch_count_over_50ms")
                workload_mode = observation_value.get("workload_mode")
                workload_message_id = observation_value.get("game_workload_message_id")
                try:
                    parsed_at = datetime.fromisoformat(
                        observed_at if isinstance(observed_at, str) else "")
                except ValueError:
                    parsed_at = None
                if parsed_at is not None and parsed_at.tzinfo is not None:
                    frame_age_seconds = (datetime.now(timezone.utc)
                        - parsed_at.astimezone(timezone.utc)).total_seconds()
                current = self.current_verified_game_performance_evidence()
                current_workload: dict[str, object] | None = None
                latest_workload: dict[str, object] | None = None
                workload_age_seconds: float | None = None
                workload_matches_process = workload_mode == "gaming" and workload_message_id is None
                if workload_mode == "automatic" and isinstance(workload_message_id, str):
                    with self._resource_evidence_lock:
                        retained = self._game_workload_evidence_by_message_id.get(
                            workload_message_id)
                        latest = self._game_workload_evidence
                        current_workload = dict(retained) if retained is not None else None
                        latest_workload = dict(latest) if latest is not None else None
                    if current_workload is not None:
                        try:
                            workload_stamp = datetime.fromisoformat(
                                str(current_workload["observed_at"]))
                            workload_age_seconds = (datetime.now(timezone.utc)
                                - workload_stamp.astimezone(timezone.utc)).total_seconds()
                        except (KeyError, TypeError, ValueError):
                            workload_age_seconds = None
                    running_digests = (current_workload.get("running_process_name_digests")
                        if current_workload is not None else None)
                    matched_digests: set[str] = set()
                    if current_workload is not None:
                        foreground_digest = current_workload.get("process_name_digest")
                        if current_workload.get("game_foreground") is True:
                            if isinstance(foreground_digest, str):
                                matched_digests.add(foreground_digest)
                        if (current_workload.get("game_process_running") is True
                                and isinstance(running_digests, (tuple, list))
                                and all(isinstance(value, str) for value in running_digests)):
                            matched_digests.update(running_digests)
                    workload_matches_process = bool(
                        current_workload is not None
                        and latest_workload is not None
                        and latest_workload.get("message_id") == workload_message_id
                        and workload_age_seconds is not None
                        and 0 <= workload_age_seconds <= 10
                        and process_name_digest in matched_digests)
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_game_frame_pressure_release_evidence:v3"
                    and observation_value.get("trigger_kind") ==
                        "idle_game_frame_pressure_reconciliation"
                    and isinstance(source, str)
                    and source.startswith("idle-game-frame-pressure-reconcile-")
                    and correlation_id == _expected_resource_release_correlation(
                        "idle_game_frame_pressure_reconciliation", source,
                        active_invocation_reference=payload.get(
                            "active_inference_request_reference"),
                        bind_active_invocation=payload.get(
                            "active_inference_preemption_requested") is True)
                    and actor == "production_chat_game_resource_governor"
                    and subject == actor and payload.get("target_subsystem") == "production_chat"
                    and isinstance(session_id, str)
                    and re.fullmatch(r"serving-session-[0-9a-f]{24}", session_id) is not None
                    and isinstance(message_id, str)
                    and re.fullmatch(r"[0-9a-f]{64}", message_id) is not None
                    and isinstance(payload_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", payload_digest) is not None
                    and isinstance(process_id_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", process_id_digest) is not None
                    and isinstance(process_name_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", process_name_digest) is not None
                    and isinstance(source_id, str) and source_id
                    and isinstance(generation_id, str) and generation_id
                    and type(sequence) is int and sequence > 0
                    and workload_mode in {"automatic", "gaming"}
                    and (workload_message_id is None or
                        (isinstance(workload_message_id, str)
                         and re.fullmatch(r"[0-9a-f]{64}", workload_message_id) is not None))
                    and workload_matches_process
                    and isinstance(observed_at, str)
                    and ((isinstance(p95, (int, float)) and not isinstance(p95, bool)
                          and math.isfinite(float(p95)) and 0 < float(p95) <= 10_000
                          and float(p95) >= 50.0)
                         or (type(hitches) is int and hitches > 0))
                    and frame_age_seconds is not None and 0 <= frame_age_seconds <= 10
                    and isinstance(current, Mapping)
                    and current.get("message_id") == message_id
                    and current.get("payload_digest") == payload_digest
                    and current.get("process_id_digest") == process_id_digest
                    and current.get("process_name_digest") == process_name_digest
                    and current.get("source_id") == source_id
                    and current.get("generation_id") == generation_id
                    and current.get("sequence") == sequence
                    and current.get("observed_at") == observed_at
                    and current.get("frame_time_p95_ms") == p95
                    and current.get("hitch_count_over_50ms") == hitches)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current",
                "game_performance_message_id": observation_value.get(
                    "game_performance_message_id"),
                "game_performance_process_id_digest": observation_value.get(
                    "game_performance_process_id_digest"),
                "game_performance_process_name_digest": observation_value.get(
                    "game_performance_process_name_digest"),
                "workload_mode": observation_value.get("workload_mode"),
                "game_workload_message_id": observation_value.get(
                    "game_workload_message_id"),
                "frame_time_p95_ms": observation_value.get("frame_time_p95_ms"),
                "hitch_count_over_50ms": observation_value.get(
                    "hitch_count_over_50ms"),
                "age_seconds": (round(frame_age_seconds, 3)
                    if frame_age_seconds is not None else None),
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_malformed_or_unverified_game_frame_pressure"})
        elif reason_code == "verified_game_gpu_model_residency":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "game_workload_message_id", "model_gpu_layers", "serving_session_id",
                "active_inference_preemption_requested", "observed_at",
            }
            evidence_valid = False
            residency_age_seconds: float | None = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_trigger = observation_value.get("trigger_correlation_id")
                raw_game_id = observation_value.get("game_workload_message_id")
                raw_observed_at = observation_value.get("observed_at")
                raw_layers = observation_value.get("model_gpu_layers")
                raw_session = observation_value.get("serving_session_id")
                expected_release = (_expected_resource_release_correlation(
                    "idle_game_gpu_residency", raw_trigger,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if isinstance(raw_trigger, str) else None)
                try:
                    parsed = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed = None
                if parsed is not None and parsed.tzinfo is not None:
                    residency_age_seconds = (datetime.now(timezone.utc)
                        - parsed.astimezone(timezone.utc)).total_seconds()
                with self._resource_evidence_lock:
                    game_evidence = (self._game_workload_evidence_by_message_id.get(raw_game_id)
                        if isinstance(raw_game_id, str) else None)
                residency_game_age: float | None = None
                if game_evidence is not None:
                    try:
                        residency_game_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(game_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                    except (KeyError, TypeError, ValueError):
                        residency_game_age = None
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_game_gpu_residency_release_evidence:v1"
                    and observation_value.get("trigger_kind") == "idle_game_gpu_residency"
                    and isinstance(raw_trigger, str) and 0 < len(raw_trigger) <= 256
                    and correlation_id == expected_release
                    and _valid_active_invocation_release_binding(payload)
                    and actor == "production_chat_game_resource_governor"
                    and subject == actor and payload.get("target_subsystem") == "production_chat"
                    and type(raw_layers) is int and 1 <= raw_layers <= 256
                    and isinstance(raw_session, str) and 0 < len(raw_session) <= 128
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and isinstance(raw_observed_at, str)
                    and isinstance(game_evidence, Mapping)
                    and game_evidence.get("message_id") == raw_game_id
                    and (game_evidence.get("game_foreground") is True
                         or game_evidence.get("game_process_running") is True)
                    and residency_age_seconds is not None
                    and 0 <= residency_age_seconds <= 120
                    and residency_game_age is not None
                    and 0 <= residency_game_age <= 10
                    and game_evidence.get("observed_at") == raw_observed_at)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current", "game_workload_message_id": observation_value.get(
                    "game_workload_message_id"), "model_gpu_layers": observation_value.get(
                    "model_gpu_layers"), "serving_session_id": observation_value.get(
                    "serving_session_id"), "active_inference_preemption_requested":
                    observation_value.get("active_inference_preemption_requested"),
                    "age_seconds": round(residency_age_seconds, 3)
                    if residency_age_seconds is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_or_unverified_game_gpu_residency"})
        elif reason_code == "verified_game_host_pressure":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "observation_correlation_id", "host_report_id", "host_report_digest",
                "observed_at", "pressure_labels", "game_workload_message_id",
                "active_inference_preemption_requested",
            }
            evidence_valid = False
            release_age_seconds = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_trigger_kind = observation_value.get("trigger_kind")
                raw_source = observation_value.get("trigger_correlation_id")
                raw_observation_id = observation_value.get("observation_correlation_id")
                raw_report_id = observation_value.get("host_report_id")
                raw_report_digest = observation_value.get("host_report_digest")
                raw_observed_at = observation_value.get("observed_at")
                raw_labels = observation_value.get("pressure_labels")
                raw_game_id = observation_value.get("game_workload_message_id")
                namespace = ("local-chat-inference" if raw_trigger_kind == "deferred_inference"
                    else "local-chat-reconciliation" if raw_trigger_kind == "idle_game_reconciliation"
                    else None)
                source_correlation = raw_source if isinstance(raw_source, str) else None
                expected_id = (namespace + "-" + hashlib.sha256(
                    source_correlation.encode("utf-8")).hexdigest()[:32]
                    if source_correlation is not None and namespace is not None else None)
                cached_inference_sample_id = (
                    raw_trigger_kind == "idle_game_reconciliation"
                    and isinstance(raw_observation_id, str)
                    and re.fullmatch(r"local-chat-inference-[0-9a-f]{32}",
                        raw_observation_id) is not None)
                host_freshness_limit_seconds = (
                    2.0 if cached_inference_sample_id
                    else HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS)
                expected_release_correlation = (_expected_resource_release_correlation(
                    str(raw_trigger_kind), source_correlation,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if source_correlation is not None else None)
                try:
                    parsed_observed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed_observed_at = None
                if parsed_observed_at is not None and parsed_observed_at.tzinfo is not None:
                    release_age_seconds = (datetime.now(timezone.utc)
                        - parsed_observed_at.astimezone(timezone.utc)).total_seconds()
                with self._resource_evidence_lock:
                    host_evidence = (self._host_resource_evidence_by_correlation.get(
                        raw_observation_id) if isinstance(raw_observation_id, str) else None)
                    game_evidence = (self._game_workload_evidence_by_message_id.get(
                        raw_game_id) if isinstance(raw_game_id, str) else None)
                host_age = None
                game_age = None
                try:
                    if host_evidence is not None:
                        host_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(host_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                    if game_evidence is not None:
                        game_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(game_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                except (KeyError, TypeError, ValueError):
                    host_age = game_age = None
                raw_host_labels = (host_evidence.get("pressure_labels")
                    if host_evidence is not None else None)
                host_labels = (set(raw_host_labels)
                    if isinstance(raw_host_labels, (tuple, list, set, frozenset))
                    and all(isinstance(label, str) for label in raw_host_labels) else set())
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_game_host_resource_release_evidence:v1"
                    and raw_trigger_kind in {"deferred_inference", "idle_game_reconciliation"}
                    and isinstance(source_correlation, str) and 0 < len(source_correlation) <= 256
                    and (raw_observation_id == expected_id or cached_inference_sample_id)
                    and correlation_id == expected_release_correlation
                    and _valid_active_invocation_release_binding(payload)
                    and actor == "production_chat_game_resource_governor"
                    and subject == actor and payload.get("target_subsystem") == "production_chat"
                    and isinstance(raw_report_id, str)
                    and isinstance(raw_report_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", raw_report_digest) is not None
                    and isinstance(raw_observed_at, str)
                    and isinstance(raw_labels, (list, tuple))
                    and all(isinstance(label, str) for label in raw_labels)
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and bool(host_labels.intersection(ACTIONABLE_RESOURCE_PRESSURE_LABELS))
                    and set(raw_labels) == host_labels
                    and host_evidence is not None
                    and host_evidence.get("observation_correlation_id") == raw_observation_id
                    and host_evidence.get("report_id") == raw_report_id
                    and host_evidence.get("report_digest") == raw_report_digest
                    and host_evidence.get("observed_at") == raw_observed_at
                    and host_age is not None and 0 <= host_age <=
                        host_freshness_limit_seconds
                    and game_evidence is not None
                    and game_evidence.get("message_id") == raw_game_id
                    and (game_evidence.get("game_foreground") is True
                         or game_evidence.get("game_process_running") is True)
                    and release_age_seconds is not None
                    and 0 <= release_age_seconds <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and game_age is not None and 0 <= game_age <= 10)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current",
                "observation_correlation_id": observation_value.get("observation_correlation_id"),
                "host_report_id": observation_value.get("host_report_id"),
                "game_workload_message_id": observation_value.get("game_workload_message_id"),
                "pressure_labels": observation_value.get("pressure_labels"),
                "active_inference_preemption_requested": observation_value.get(
                    "active_inference_preemption_requested"),
                "age_seconds": round(release_age_seconds, 3)
                    if release_age_seconds is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_malformed_or_unverified_game_host_pressure"})
        elif reason_code in {"selected_gaming_profile_host_pressure",
                "conservative_automatic_profile_host_pressure"}:
            observation_value = payload.get("resource_observation")
            selected_profile = reason_code == "selected_gaming_profile_host_pressure"
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "observation_correlation_id", "host_report_id", "host_report_digest",
                "observed_at", "pressure_labels", "workload_mode",
                "workload_mode_source", "workload_observation_status",
            }
            if not selected_profile:
                expected_fields |= {"configured_mode"}
            evidence_valid = False
            profile_release_age_seconds: float | None = None
            profile_host_age: float | None = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_trigger = observation_value.get("trigger_kind")
                raw_source = observation_value.get("trigger_correlation_id")
                raw_observation_id = observation_value.get("observation_correlation_id")
                raw_report_id = observation_value.get("host_report_id")
                raw_report_digest = observation_value.get("host_report_digest")
                raw_observed_at = observation_value.get("observed_at")
                raw_labels = observation_value.get("pressure_labels")
                source = raw_source if isinstance(raw_source, str) else None
                expected_observation_id = ("local-chat-reconciliation-" + hashlib.sha256(
                    source.encode("utf-8")).hexdigest()[:32] if source is not None else None)
                expected_release_correlation = (_expected_resource_release_correlation(
                    str(raw_trigger), source,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if source is not None else None)
                try:
                    parsed_at = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed_at = None
                if parsed_at is not None and parsed_at.tzinfo is not None:
                    profile_release_age_seconds = (datetime.now(timezone.utc)
                        - parsed_at.astimezone(timezone.utc)).total_seconds()
                with self._resource_evidence_lock:
                    host_evidence = (self._host_resource_evidence_by_correlation.get(
                        raw_observation_id) if isinstance(raw_observation_id, str) else None)
                try:
                    if host_evidence is not None:
                        profile_host_age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                            str(host_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
                except (KeyError, TypeError, ValueError):
                    profile_host_age = None
                raw_host_labels = (host_evidence.get("pressure_labels")
                    if host_evidence is not None else None)
                host_labels = (set(raw_host_labels)
                    if isinstance(raw_host_labels, (tuple, list, set, frozenset))
                    and all(isinstance(label, str) for label in raw_host_labels) else set())
                expected_source_prefix = None
                if isinstance(raw_trigger, str):
                    expected_source_prefix = {
                        "gaming_profile_resource_reconciliation": (
                            "idle-game-resource-reconcile-"),
                        "active_gaming_profile_resource_reconciliation": (
                            "active-gaming-profile-resource-reconcile-"),
                        "conservative_automatic_gaming_resource_reconciliation": (
                            "automatic-game-resource-reconcile-"),
                        "active_conservative_automatic_gaming_resource_reconciliation": (
                            "active-automatic-game-resource-reconcile-"),
                    }.get(raw_trigger)
                conservative_source = observation_value.get("workload_mode_source")
                expected_workload_source = (
                    "operator_selected" if selected_profile else conservative_source)
                expected_workload_status = ("not_requested" if selected_profile else
                    observation_value.get("workload_observation_status"))
                expected_schema = (
                    "sentientos.production_gaming_profile_host_resource_release_evidence:v1"
                    if selected_profile else
                    "sentientos.production_conservative_automatic_gaming_host_resource_release_evidence:v1")
                evidence_valid = bool(
                    observation_value.get("schema_version") == expected_schema
                    and expected_source_prefix is not None
                    and isinstance(source, str)
                    and source.startswith(expected_source_prefix)
                    and 0 < len(source) <= 256
                    and raw_observation_id == expected_observation_id
                    and correlation_id == expected_release_correlation
                    and _valid_active_invocation_release_binding(payload)
                    and actor == "production_chat_workload_resource_governor"
                    and subject == actor and payload.get("target_subsystem") == "production_chat"
                    and observation_value.get("workload_mode") == "gaming"
                    and observation_value.get("workload_mode_source") == expected_workload_source
                    and observation_value.get("workload_observation_status") == expected_workload_status
                    and (selected_profile or expected_workload_status in
                        CONSERVATIVE_RESOURCE_GOVERNANCE_FAILURE_STATUSES)
                    and (selected_profile or (
                        observation_value.get("configured_mode") == "automatic"
                        and conservative_source in {
                            "foreground_observation_unavailable_conservative_gaming",
                            "game_process_observation_unavailable_conservative_gaming"}))
                    and isinstance(raw_report_id, str)
                    and isinstance(raw_report_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", raw_report_digest) is not None
                    and isinstance(raw_observed_at, str)
                    and isinstance(raw_labels, (tuple, list))
                    and all(isinstance(label, str) for label in raw_labels)
                    and bool(host_labels.intersection(ACTIONABLE_RESOURCE_PRESSURE_LABELS))
                    and set(raw_labels) == host_labels
                    and host_evidence is not None
                    and host_evidence.get("observation_correlation_id") == raw_observation_id
                    and host_evidence.get("report_id") == raw_report_id
                    and host_evidence.get("report_digest") == raw_report_digest
                    and host_evidence.get("observed_at") == raw_observed_at
                    and profile_release_age_seconds is not None
                    and 0 <= profile_release_age_seconds <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS
                    and profile_host_age is not None
                    and 0 <= profile_host_age <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current",
                "observation_correlation_id": observation_value.get("observation_correlation_id"),
                "host_report_id": observation_value.get("host_report_id"),
                "pressure_labels": observation_value.get("pressure_labels"),
                "workload_mode": "gaming",
                "workload_mode_source": observation_value.get("workload_mode_source"),
                "configured_mode": ("gaming" if selected_profile else "automatic"),
                "workload_observation_status": observation_value.get(
                    "workload_observation_status"),
                "age_seconds": round(profile_release_age_seconds, 3)
                    if profile_release_age_seconds is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_malformed_or_unbound_gaming_profile_host_pressure"})
        elif reason_code == "selected_gaming_profile_gpu_model_residency":
            observation_value = payload.get("resource_observation")
            expected_fields = {
                "schema_version", "trigger_kind", "trigger_correlation_id",
                "model_gpu_layers", "serving_session_id", "workload_mode",
                "workload_mode_source", "workload_observation_status",
                "active_inference_preemption_requested", "observed_at",
            }
            evidence_valid = False
            profile_age_seconds: float | None = None
            if (isinstance(observation_value, Mapping)
                    and set(observation_value) == expected_fields):
                raw_trigger = observation_value.get("trigger_correlation_id")
                raw_observed_at = observation_value.get("observed_at")
                raw_layers = observation_value.get("model_gpu_layers")
                raw_session = observation_value.get("serving_session_id")
                expected_correlation = (_expected_resource_release_correlation(
                    "idle_gaming_profile_gpu_residency", raw_trigger,
                    active_invocation_reference=payload.get(
                        "active_inference_request_reference"),
                    bind_active_invocation=payload.get(
                        "active_inference_preemption_requested") is True)
                    if isinstance(raw_trigger, str) else None)
                try:
                    parsed = datetime.fromisoformat(
                        raw_observed_at if isinstance(raw_observed_at, str) else "")
                except ValueError:
                    parsed = None
                if parsed is not None and parsed.tzinfo is not None:
                    profile_age_seconds = (datetime.now(timezone.utc)
                        - parsed.astimezone(timezone.utc)).total_seconds()
                evidence_valid = bool(
                    observation_value.get("schema_version") ==
                        "sentientos.production_gaming_profile_gpu_residency_release_evidence:v1"
                    and observation_value.get("trigger_kind") ==
                        "idle_gaming_profile_gpu_residency"
                    and isinstance(raw_trigger, str)
                    and raw_trigger.startswith("idle-gaming-profile-gpu-residency-")
                    and 0 < len(raw_trigger) <= 256
                    and correlation_id == expected_correlation
                    and _valid_active_invocation_release_binding(payload)
                    and actor == "production_chat_workload_resource_governor"
                    and subject == actor and payload.get("target_subsystem") == "production_chat"
                    and type(raw_layers) is int and 1 <= raw_layers <= 256
                    and isinstance(raw_session, str)
                    and re.fullmatch(r"serving-session-[0-9a-f]{24}", raw_session) is not None
                    and observation_value.get("workload_mode") == "gaming"
                    and observation_value.get("workload_mode_source") == "operator_selected"
                    and observation_value.get("workload_observation_status") == "not_requested"
                    and type(observation_value.get(
                        "active_inference_preemption_requested")) is bool
                    and isinstance(raw_observed_at, str)
                    and profile_age_seconds is not None
                    and 0 <= profile_age_seconds <= 120)
            valid = valid and evidence_valid
            evidence_ref = ({
                "status": "current",
                "serving_session_id": observation_value.get("serving_session_id"),
                "model_gpu_layers": observation_value.get("model_gpu_layers"),
                "workload_mode": "gaming",
                "workload_mode_source": "operator_selected",
                "active_inference_preemption_requested": observation_value.get(
                    "active_inference_preemption_requested"),
                "age_seconds": round(profile_age_seconds, 3)
                    if profile_age_seconds is not None else None,
            } if evidence_valid and isinstance(observation_value, Mapping) else {
                "status": "missing_stale_or_unverified_gaming_profile_gpu_residency"})
        payload["resource_observation_evidence"] = evidence_ref
        return self._decision(
            action_class="local_model_resource_release", allowed=valid,
            reason=("model_resource_release_fail_safe" if valid else
                    "model_resource_release_evidence_required"
                    if reason_code in {"verified_game_gpu_model_residency",
                        "selected_gaming_profile_gpu_model_residency"} else
                    "model_resource_release_pressure_evidence_required"
                    if reason_code in {"vram_pressure_observed", "host_gpu_pressure_observed",
                        "host_memory_pressure_observed",
                        "verified_game_gpu_pressure",
                        "verified_game_host_pressure",
                        "verified_game_frame_pressure",
                        "selected_gaming_profile_host_pressure",
                        "conservative_automatic_profile_host_pressure"} else
                    "model_resource_release_request_invalid"),
            subject=subject, scope="local", origin=actor,
            pressure=self.sample_pressure(), metadata=payload,
            correlation_id=correlation_id)

    def _admit_local_model_serving(
        self, *, actor: str, subject: str, metadata: dict[str, object] | None,
        correlation_id: str | None,
    ) -> GovernorDecision:
        payload = dict(metadata or {})
        if payload.get("resource_governance_required") is not True:
            return self._decision(
                action_class="local_model_serving", allowed=True,
                reason="resource_preflight_not_composed", subject=subject,
                scope="local", origin=actor, pressure=self.sample_pressure(),
                metadata={**payload, "resource_observation_evidence": {
                    "status": "not_composed"}}, correlation_id=correlation_id)
        return self._admit_local_model_inference(
            actor=actor, subject=subject, metadata=payload,
            correlation_id=correlation_id, operation_kind="model_serving")

    def _admit_local_model_inference(
        self,
        *,
        actor: str,
        subject: str,
        metadata: dict[str, object] | None,
        correlation_id: str | None,
        operation_kind: str = "inference",
    ) -> GovernorDecision:
        pressure = self.sample_pressure()
        now = datetime.now(timezone.utc)
        payload = dict(metadata or {})
        operation_label = "serving" if operation_kind == "model_serving" else "inference"
        purpose = str(payload.get("purpose") or "")
        foreground = purpose == "local_user_chat"
        requested_observation_id = payload.get("host_resource_observation_id")
        namespace = payload.get("host_resource_observation_namespace")
        if namespace not in {"local-chat-inference", "local-chat-serving",
                "local-chat-reconciliation"}:
            namespace = "local-chat-inference"
        expected_observation_id = (str(namespace) + "-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
            if isinstance(correlation_id, str) else None)
        with self._resource_evidence_lock:
            if isinstance(requested_observation_id, str):
                exact_evidence = (self._host_resource_evidence_by_correlation.get(
                    requested_observation_id)
                    if requested_observation_id == expected_observation_id else None)
                evidence = dict(exact_evidence) if exact_evidence is not None else None
            else:
                evidence = (dict(self._host_resource_evidence)
                    if self._host_resource_evidence is not None else None)
            game_evidence = dict(self._game_performance_evidence) if self._game_performance_evidence is not None else None
            game_workload = (dict(self._game_workload_evidence)
                if self._game_workload_evidence is not None else None)
        evidence_age_seconds: float | None = None
        evidence_ref: dict[str, object] = {"status": "unavailable"}
        labels: set[str] = set()
        if evidence is not None:
            # Match the observation owner's cache contract. Admission must not
            # treat a correlated retry sample as current after the coordinator
            # itself would have aged it out.
            from sentientos.host_resource_runtime import (
                HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS,
            )

            try:
                observed_at = datetime.fromisoformat(str(evidence["observed_at"]))
                evidence_age_seconds = (now - observed_at).total_seconds()
            except (KeyError, TypeError, ValueError):
                evidence_age_seconds = None
            if (evidence_age_seconds is not None
                    and 0 <= evidence_age_seconds <= HOST_RESOURCE_EVIDENCE_MAX_AGE_SECONDS):
                raw_labels = evidence.get("pressure_labels")
                if isinstance(raw_labels, (tuple, list)) and all(
                        isinstance(label, str) for label in raw_labels):
                    labels = set(raw_labels)
                    raw_thermal_temperatures = evidence.get(
                        "thermal_zone_temperatures_c")
                    thermal_temperatures = (
                        dict(raw_thermal_temperatures)
                        if isinstance(raw_thermal_temperatures, Mapping) else {})
                    evidence_ref = {
                        "status": "current",
                        "evaluation_id": evidence["evaluation_id"],
                        "semantic_digest": evidence.get("semantic_digest"),
                        "epoch_id": evidence["epoch_id"],
                        "snapshot_id": evidence["snapshot_id"],
                        "report_id": evidence["report_id"],
                        "report_digest": evidence["report_digest"],
                        "observation_correlation_id": evidence[
                            "observation_correlation_id"],
                        "observed_at": evidence.get("observed_at"),
                        "pressure_labels": sorted(labels),
                        "cpu_utilization_percent": evidence.get("cpu_utilization_percent"),
                        "gpu_utilization_percent": evidence.get("gpu_utilization_percent"),
                        "vram_utilization_percent": evidence.get("vram_utilization_percent"),
                        "ram_utilization_percent": evidence.get("ram_utilization_percent"),
                        "thermal_zone_temperatures_c": thermal_temperatures,
                        "gpu_telemetry_available": evidence.get("gpu_telemetry_available"),
                        "gpu_telemetry_complete": evidence.get("gpu_telemetry_complete"),
                        "gpu_telemetry_sources": evidence.get("gpu_telemetry_sources", []),
                        "age_seconds": round(evidence_age_seconds, 3),
                    }
                else:
                    evidence_ref = {"status": "invalid", "reason": "pressure_labels_invalid"}
            else:
                evidence_ref = {"status": "stale_or_invalid", "age_seconds": evidence_age_seconds}

        pressure_reasons = labels.intersection({"cpu_pressure", "memory_pressure", "gpu_pressure", "thermal_pressure"})
        execution_profile = payload.get("model_execution_profile")
        gpu_layers: int | None = None
        gpu_profile_digest: str | None = None
        accelerator_route: str | None = None
        if isinstance(execution_profile, Mapping):
            raw_layers = execution_profile.get("gpu_layers")
            raw_profile_digest = execution_profile.get("configuration_digest")
            raw_route = execution_profile.get("accelerator_route")
            profile_engine = execution_profile.get("engine")
            if (set(execution_profile) == {"schema_version", "engine", "accelerator_route",
                                           "gpu_layers", "configuration_digest"}
                    and execution_profile.get("schema_version") == "sentientos.model_execution_profile:v1"
                    and profile_engine in {"llama_cpp", "transformers"}
                    and raw_route in {"cpu", "gpu", "unknown"}
                    and ((profile_engine == "llama_cpp" and type(raw_layers) is int
                          and 0 <= raw_layers <= 256
                          and raw_route == ("gpu" if raw_layers else "cpu"))
                         or (profile_engine == "llama_cpp" and raw_layers is None
                             and raw_route == "unknown")
                         or (profile_engine == "transformers" and raw_layers is None))
                    and isinstance(raw_profile_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", raw_profile_digest)):
                gpu_layers = raw_layers if type(raw_layers) is int else None
                accelerator_route = str(raw_route)
                gpu_profile_digest = raw_profile_digest
        gpu_offload_requested = accelerator_route == "gpu"
        gpu_telemetry_required = accelerator_route in {"gpu", "unknown"}
        game_pressure = False
        game_evidence_ref: dict[str, object] = {"status": "unavailable"}
        if game_evidence is not None:
            try:
                game_age = (now - datetime.fromisoformat(
                    str(game_evidence["observed_at"])).astimezone(timezone.utc)).total_seconds()
            except (KeyError, TypeError, ValueError):
                game_age = None
            if game_age is not None and 0 <= game_age <= 10:
                p95 = game_evidence.get("frame_time_p95_ms")
                hitches = game_evidence.get("hitch_count_over_50ms")
                game_pressure = ((isinstance(p95, (int, float)) and p95 >= 50.0)
                                 or (type(hitches) is int and hitches > 0))
                game_evidence_ref = {
                    "status": "current", "source_id": game_evidence["source_id"],
                    "generation_id": game_evidence["generation_id"],
                    "sequence": game_evidence["sequence"],
                    "message_id": game_evidence["message_id"],
                    "payload_digest": game_evidence["payload_digest"],
                    "process_id_digest": game_evidence["process_id_digest"],
                    "process_name_digest": game_evidence.get("process_name_digest"),
                    "source_observed_at": game_evidence.get("source_observed_at"),
                    "frame_time_p95_ms": p95,
                    "hitch_count_over_50ms": hitches,
                    "process_cpu_percent": game_evidence.get("process_cpu_percent"),
                    "process_rss_bytes": game_evidence.get("process_rss_bytes"),
                    "age_seconds": round(game_age, 3),
                }
            else:
                game_evidence_ref = {"status": "stale_or_invalid", "age_seconds": game_age}
        game_workload_ref: dict[str, object] = {"status": "unavailable", "game_active": False}
        if game_workload is not None:
            try:
                workload_age = (now - datetime.fromisoformat(
                    str(game_workload["observed_at"])).astimezone(timezone.utc)).total_seconds()
            except (KeyError, TypeError, ValueError):
                workload_age = None
            if workload_age is not None and 0 <= workload_age <= 10:
                game_active = (game_workload.get("game_foreground") is True
                    or game_workload.get("game_process_running") is True)
                game_workload_ref = {
                    "status": "current", "game_active": game_active,
                    "source_id": game_workload["source_id"],
                    "generation_id": game_workload["generation_id"],
                    "session_id": game_workload["session_id"],
                    "sequence": game_workload["sequence"],
                    "message_id": game_workload["message_id"],
                    "process_name_digest": game_workload["process_name_digest"],
                    "game_foreground": game_workload["game_foreground"],
                    "game_process_running": game_workload["game_process_running"],
                    "age_seconds": round(workload_age, 3),
                }
            else:
                game_workload_ref = {"status": "stale_or_invalid",
                    "game_active": False, "age_seconds": workload_age}
        serving_workload = payload.get("serving_workload_evidence")
        requested_game_message_id: str | None = None
        if isinstance(serving_workload, Mapping):
            provenance = serving_workload.get("transport_provenance")
            if isinstance(provenance, Mapping):
                raw_message_id = provenance.get("message_id")
                if isinstance(raw_message_id, str):
                    requested_game_message_id = raw_message_id
        automatic_mode_requested = (
            payload.get("workload_mode") == "automatic"
            or (isinstance(serving_workload, Mapping)
                and serving_workload.get("configured_mode") == "automatic"))
        if operation_kind == "model_serving" and automatic_mode_requested:
            if (game_workload_ref.get("status") != "current"
                    or requested_game_message_id is None
                    or (game_workload is not None
                        and game_workload.get("message_id") != requested_game_message_id)):
                game_workload_ref = {"status": "unavailable_or_unbound",
                    "game_active": False}
        # Host pressure is shared telemetry. It receives game-priority meaning
        # only while fresh authenticated game-presence or game-performance
        # evidence is current; an unverified workload label cannot change admission.
        game_host_pressure = (
            (game_evidence_ref.get("status") == "current"
             or game_workload_ref.get("game_active") is True)
            and bool(pressure_reasons)
        )
        effective_workload_mode = payload.get("effective_workload_mode")
        if effective_workload_mode not in {"normal", "gaming"}:
            effective_workload_mode = payload.get("workload_mode")
        effective_gaming_mode = effective_workload_mode == "gaming"
        workload_evidence = payload.get("workload_evidence")
        if not isinstance(workload_evidence, Mapping):
            workload_evidence = payload.get("serving_workload_evidence")
        workload_profile_ref = {
            "status": "current" if effective_gaming_mode else "not_selected",
            "mode": "gaming" if effective_gaming_mode else "normal",
        }
        if isinstance(workload_evidence, Mapping):
            for key in ("configured_mode", "mode_source", "observation_status",
                    "observed_at", "transport_provenance"):
                value = workload_evidence.get(key)
                if value is not None:
                    workload_profile_ref[key] = value
        gaming_workload_profile_active = (
            effective_gaming_mode
            and (not isinstance(workload_evidence, Mapping)
                 or workload_evidence.get("configured_mode") == "gaming")
        )
        conservative_automatic_gaming_profile = (
            effective_gaming_mode
            and isinstance(workload_evidence, Mapping)
            and workload_evidence.get("configured_mode") == "automatic"
            and workload_evidence.get("mode_source") in {
                "foreground_observation_unavailable_conservative_gaming",
                "game_process_observation_unavailable_conservative_gaming",
            }
        )
        gaming_workload_profile_host_pressure = (
            gaming_workload_profile_active and bool(pressure_reasons)
        )
        conservative_automatic_profile_host_pressure = (
            conservative_automatic_gaming_profile and bool(pressure_reasons)
        )
        verified_game_active = (
            game_evidence_ref.get("status") == "current"
            or game_workload_ref.get("game_active") is True
        )
        optional_model_load_during_game = (
            operation_kind == "model_serving"
            and verified_game_active
        )
        optional_inference_during_game = (
            operation_kind == "inference"
            and verified_game_active
        )
        optional_model_load_in_gaming_profile = (
            operation_kind == "model_serving"
            and (gaming_workload_profile_active
                 or conservative_automatic_gaming_profile)
        )
        automatic_serving_workload_unavailable = (
            operation_kind == "model_serving"
            and automatic_mode_requested
            and game_workload_ref.get("status") != "current")
        conservative_automatic_profile_requires_gpu_telemetry = (
            conservative_automatic_gaming_profile
            and accelerator_route in {None, "unknown"})
        gpu_resource_evidence_incomplete = (
            (gpu_telemetry_required
             or conservative_automatic_profile_requires_gpu_telemetry)
            and evidence_ref.get("status") == "current"
            and evidence is not None
            and evidence.get("gpu_telemetry_complete") is not True
        )
        gpu_telemetry_incomplete = (
            (not foreground or verified_game_active)
            and gpu_resource_evidence_incomplete
        )
        # Background work waits for a completed, fresh observation epoch. An
        # absent or stale epoch is missing evidence, not a measurement of low
        # pressure. Foreground chat keeps its separate request budget except
        # when fresh game evidence makes gaming priority operationally relevant.
        incomplete = evidence_ref.get("status") != "current"
        if evidence_ref.get("status") == "current" and evidence is not None:
            incomplete = (evidence.get("cpu_utilization_percent") is None
                          or evidence.get("ram_utilization_percent") is None)
        gaming_profile_resource_telemetry_incomplete = (
            (gaming_workload_profile_active
             or conservative_automatic_gaming_profile)
            and (incomplete or gpu_resource_evidence_incomplete)
        )
        game_resource_telemetry_incomplete = (
            verified_game_active
            and (evidence_ref.get("status") != "current" or evidence is None
                 or evidence.get("cpu_utilization_percent") is None
                 or evidence.get("ram_utilization_percent") is None
                 or gpu_telemetry_incomplete)
        )

        reason = "allowed"
        blocks = False
        if automatic_serving_workload_unavailable:
            reason, blocks = "deferred_game_workload_observation_unavailable_for_model_serving", True
        elif not foreground and incomplete:
            reason, blocks = "deferred_resource_telemetry_incomplete", True
        elif game_pressure:
            # A verified game-pacing regression is direct evidence that the
            # interactive workload is already affected.  Local chat is still
            # optional model inference, so do not let its foreground purpose
            # bypass this narrower game-priority gate.  This does not grant
            # authority to inspect or control game processes.
            reason, blocks = ("deferred_local_model_" + operation_label
                + "_for_game_frame_pressure", True)
        elif game_host_pressure:
            reason, blocks = ("deferred_local_model_" + operation_label
                + "_under_host_pressure_during_game", True)
        elif gaming_workload_profile_host_pressure:
            # An explicit low-work gaming profile is a separate policy signal
            # from authenticated game-presence evidence. Under current host
            # pressure, defer optional model work without claiming that a game
            # process was independently observed.
            reason, blocks = ("deferred_local_model_" + operation_label
                + "_under_host_pressure_in_gaming_mode", True)
        elif conservative_automatic_profile_host_pressure:
            # Automatic mode deliberately selects a conservative gaming
            # profile when local game detection is unavailable. Honor that
            # profile under shared host pressure without claiming that a game
            # was independently verified as active.
            reason, blocks = ("deferred_local_model_" + operation_label
                + "_under_host_pressure_in_conservative_automatic_mode", True)
        elif (operation_kind == "inference" and foreground and gpu_offload_requested
                and "gpu_pressure" in pressure_reasons):
            # Foreground chat remains optional GPU work. A current device-wide
            # pressure signal is enough to defer this accelerator route even
            # when the competing process cannot be attributed to a game.
            reason, blocks = (
                "deferred_gpu_backed_local_model_inference_under_gpu_pressure", True)
        elif (operation_kind == "inference" and foreground
                and "memory_pressure" in pressure_reasons):
            # Foreground chat remains optional model work. A current host RAM
            # pressure signal also applies to CPU-backed inference, whose model
            # weights and working set compete for the same constrained memory.
            reason, blocks = (
                "deferred_local_model_inference_under_memory_pressure", True)
        elif (operation_kind == "inference" and foreground
                and "cpu_pressure" in pressure_reasons):
            # Inference on either accelerator route still consumes host CPU
            # resources. Keep optional chat behind a host already reporting
            # CPU pressure without controlling or attributing other processes.
            reason, blocks = (
                "deferred_local_model_inference_under_cpu_pressure", True)
        elif (operation_kind == "inference" and foreground
                and "thermal_pressure" in pressure_reasons):
            # Host thermal pressure is inspect-only evidence, but optional
            # inference can yield to it without asserting cooling or hardware
            # control authority.
            reason, blocks = (
                "deferred_local_model_inference_under_thermal_pressure", True)
        elif (operation_kind in {"inference", "model_serving"}
                and gaming_workload_profile_active
                and gaming_profile_resource_telemetry_incomplete):
            # An explicitly selected gaming profile asks SentientOS to keep
            # optional inference behind the interactive workload. Missing
            # resource evidence cannot establish that inference is safe to
            # admit, so fail closed for this profile while preserving the
            # existing foreground-chat behavior in normal mode.
            reason, blocks = "deferred_resource_telemetry_incomplete_in_gaming_mode", True
        elif (operation_kind in {"inference", "model_serving"}
                and conservative_automatic_gaming_profile
                and gaming_profile_resource_telemetry_incomplete):
            reason, blocks = (
                "deferred_resource_telemetry_incomplete_in_conservative_automatic_mode",
                True)
        elif game_resource_telemetry_incomplete:
            reason, blocks = "deferred_resource_telemetry_incomplete_during_game", True
        elif optional_inference_during_game:
            # Optional inference on either route is preempted when authenticated
            # game activity is current. Do not start work that the existing
            # game-priority reconciliation will immediately cancel, even when
            # sampled utilization is nominal. This admission decision does not
            # control the game process or grant telemetry hardware authority.
            reason, blocks = "deferred_local_model_inference_while_game_active", True
        elif optional_model_load_during_game:
            # Loading an optional model can consume CPU, memory, or accelerator
            # resources even when current utilization is nominal. Preserve game
            # priority on both execution routes until authenticated game
            # activity ends; this does not control the game process.
            reason = ("deferred_gpu_model_serving_while_game_active"
                if gpu_offload_requested else
                "deferred_cpu_model_serving_while_game_active")
            blocks = True
        elif optional_model_load_in_gaming_profile:
            # The explicit and conservative gaming profiles prioritize the
            # interactive workload over optional residency on both execution
            # routes, without claiming that a game process was independently
            # observed.
            route = "gpu" if gpu_offload_requested else "cpu"
            profile = ("conservative_automatic_mode"
                if conservative_automatic_gaming_profile else "gaming_mode")
            reason = f"deferred_{route}_model_serving_in_{profile}"
            blocks = True
        elif not foreground and gpu_telemetry_incomplete:
            reason, blocks = "deferred_gpu_offload_telemetry_incomplete", True
        elif not foreground and pressure_reasons:
            if operation_kind == "model_serving" and "memory_pressure" in pressure_reasons:
                # Model loading has a large, persistent host-RAM footprint.
                # Preserve the pressure dimension in the decision evidence so
                # operators can distinguish this admission from GPU/CPU/thermal
                # deferrals without attributing the pressure to another process.
                reason = "deferred_background_model_serving_under_memory_pressure"
            else:
                reason = ("deferred_background_model_serving_under_host_pressure"
                    if operation_kind == "model_serving" else
                    "deferred_background_inference_under_host_pressure")
            blocks = True
        elif not foreground and pressure.composite >= self._pressure_warn:
            reason, blocks = ("deferred_background_model_serving_under_runtime_pressure"
                if operation_kind == "model_serving" else
                "deferred_background_inference_under_runtime_pressure", True)

        preemption = payload.get("active_inference_preemption")
        preemption_requested = preemption is not None
        game_preemption_valid = (
            isinstance(preemption, Mapping)
            and preemption.get("schema_version") ==
                "sentientos.active_inference_preemption:v2"
            and preemption.get("workload_mode") == "automatic"
            and isinstance(preemption.get("serving_session_id"), str)
            and bool(preemption.get("serving_session_id"))
            and isinstance(preemption.get("model_identity_digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", str(
                preemption.get("model_identity_digest"))) is not None
            and game_workload_ref.get("status") == "current"
            and game_workload_ref.get("game_active") is True
            and isinstance(preemption.get("game_workload_message_id"), str)
            and preemption.get("game_workload_message_id") ==
                game_workload_ref.get("message_id")
            and isinstance(preemption.get(
                "active_inference_request_reference"), Mapping)
            and set(preemption["active_inference_request_reference"]) == {
                "request_id", "request_digest", "correlation_id"}
            and all(isinstance(preemption["active_inference_request_reference"].get(key), str)
                and preemption["active_inference_request_reference"].get(key)
                for key in ("request_id", "request_digest", "correlation_id"))
            and preemption.get("active_inference_request_reference")
                == payload.get("active_inference_request_reference")
            and isinstance(correlation_id, str)
            and correlation_id.startswith(
                "active-inference-preemption:" + hashlib.sha256(json.dumps(
                    dict(preemption["active_inference_request_reference"]),
                    sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")).hexdigest() + ":")
        )
        host_pressure_preemption_fields = {
            "schema_version", "preemption_kind", "workload_mode",
            "serving_session_id", "model_identity_digest",
            "observation_correlation_id", "host_report_id", "host_report_digest",
            "pressure_labels", "observed_at",
            "active_inference_request_reference",
        }
        host_pressure_preemption_valid = (
            isinstance(preemption, Mapping)
            and set(preemption) == host_pressure_preemption_fields
            and preemption.get("schema_version") ==
                "sentientos.active_inference_preemption:v3"
            and preemption.get("preemption_kind") == "host_resource_pressure"
            and preemption.get("workload_mode") == "normal"
            and actor == "production_chat_host_resource_governor"
            and subject == actor
            and isinstance(preemption.get("serving_session_id"), str)
            and re.fullmatch(r"serving-session-[0-9a-f]{24}", str(
                preemption.get("serving_session_id"))) is not None
            and isinstance(preemption.get("model_identity_digest"), str)
            and re.fullmatch(r"[0-9a-f]{64}", str(
                preemption.get("model_identity_digest"))) is not None
            and evidence_ref.get("status") == "current"
            and isinstance(preemption.get("observation_correlation_id"), str)
            and preemption.get("observation_correlation_id") ==
                evidence_ref.get("observation_correlation_id")
            and preemption.get("host_report_id") == evidence_ref.get("report_id")
            and preemption.get("host_report_digest") == evidence_ref.get("report_digest")
            and preemption.get("observed_at") == evidence_ref.get("observed_at")
            and isinstance(preemption.get("pressure_labels"), list)
            and preemption.get("pressure_labels") == sorted(pressure_reasons)
            and bool(pressure_reasons)
            and isinstance(preemption.get(
                "active_inference_request_reference"), Mapping)
            and set(preemption["active_inference_request_reference"]) == {
                "request_id", "request_digest", "correlation_id"}
            and all(isinstance(preemption["active_inference_request_reference"].get(key), str)
                and preemption["active_inference_request_reference"].get(key)
                for key in ("request_id", "request_digest", "correlation_id"))
            and preemption.get("active_inference_request_reference")
                == payload.get("active_inference_request_reference")
            and isinstance(correlation_id, str)
            and correlation_id.startswith(
                "active-inference-preemption:" + hashlib.sha256(json.dumps(
                    dict(preemption["active_inference_request_reference"]),
                    sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")).hexdigest() + ":")
        )
        preemption_valid = game_preemption_valid or host_pressure_preemption_valid
        if preemption_requested:
            reason = ("allowed_verified_game_workload_inference_preemption"
                if game_preemption_valid else
                "allowed_host_resource_pressure_inference_preemption"
                if host_pressure_preemption_valid else
                "deferred_active_inference_preemption_game_evidence_unavailable")
            blocks = not preemption_valid

        posture_eval = PostureRuleEvaluation(
            dimension=("host_resource_model_serving_admission"
                if operation_kind == "model_serving" else
                "host_resource_inference_admission"),
            reason=reason,
            restriction_class=self._restriction_class_for_reason(reason),
            blocks=blocks,
            precedence=90 if blocks else 40,
            details={
                "purpose": purpose or "unspecified_background",
                "foreground": foreground,
                "host_resource_evidence": evidence_ref,
                "observed_pressure_labels": sorted(labels),
                "blocking_pressure_labels": sorted(pressure_reasons),
                "model_gpu_offload_requested": gpu_offload_requested,
                "model_gpu_telemetry_required": gpu_telemetry_required,
                "conservative_automatic_profile_requires_gpu_telemetry": (
                    conservative_automatic_profile_requires_gpu_telemetry),
                "model_gpu_layers": gpu_layers,
                "model_accelerator_route": accelerator_route,
                "model_configuration_digest": gpu_profile_digest,
                "optional_model_load_in_gaming_profile": (
                    optional_model_load_in_gaming_profile),
                "optional_gpu_model_load_in_gaming_profile": (
                    optional_model_load_in_gaming_profile and gpu_offload_requested),
                "gpu_telemetry_incomplete_for_model": gpu_telemetry_incomplete,
                "game_performance_evidence": game_evidence_ref,
                "game_workload_evidence": game_workload_ref,
                "game_frame_pressure": game_pressure,
                "host_pressure_during_verified_game": game_host_pressure,
                "gaming_workload_profile_host_pressure": (
                    gaming_workload_profile_host_pressure),
                "conservative_automatic_gaming_profile": (
                    conservative_automatic_gaming_profile),
                "conservative_automatic_profile_host_pressure": (
                    conservative_automatic_profile_host_pressure),
                "gaming_workload_profile_resource_telemetry_incomplete": (
                    gaming_profile_resource_telemetry_incomplete),
                "gaming_workload_profile_model_route_unverified": (
                    accelerator_route in {None, "unknown"}),
                "gaming_workload_profile_evidence": workload_profile_ref,
                "host_resource_telemetry_incomplete_during_game": (
                    game_resource_telemetry_incomplete),
                "active_inference_preemption_requested": preemption_requested,
                "active_inference_preemption_admitted": preemption_valid,
                "active_host_pressure_preemption_admitted":
                    host_pressure_preemption_valid,
            },
        )
        posture = self._compose_runtime_posture(
            action_class=("local_model_serving" if operation_kind == "model_serving"
                else "local_model_inference"),
            scope="local",
            pressure=pressure,
            now=now,
            evaluations=[posture_eval],
        )
        allowed = not blocks or self._mode != "enforce"
        payload["host_resource_evidence"] = evidence_ref
        payload["observed_pressure_labels"] = sorted(labels)
        payload["game_performance_evidence"] = game_evidence_ref
        payload["game_workload_evidence"] = game_workload_ref
        payload["game_frame_pressure"] = game_pressure
        payload["optional_model_load_in_gaming_profile"] = (
            optional_model_load_in_gaming_profile)
        payload["optional_gpu_model_load_in_gaming_profile"] = (
            optional_model_load_in_gaming_profile and gpu_offload_requested)
        payload["host_pressure_during_verified_game"] = game_host_pressure
        payload["gaming_workload_profile_host_pressure"] = (
            gaming_workload_profile_host_pressure)
        payload["gaming_workload_profile_resource_telemetry_incomplete"] = (
            gaming_profile_resource_telemetry_incomplete)
        payload["gaming_workload_profile_evidence"] = workload_profile_ref
        payload["host_resource_telemetry_incomplete_during_game"] = (
            game_resource_telemetry_incomplete)
        decision = self._decision(
            action_class=("local_model_serving" if operation_kind == "model_serving"
                else "local_model_inference"),
            allowed=allowed,
            reason=reason,
            subject=subject,
            scope="local",
            origin=actor,
            pressure=pressure,
            metadata=payload,
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class=("local_model_serving"
            if operation_kind == "model_serving" else "local_model_inference"),
            allowed=allowed, now=now)
        return decision

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
        else:
            reason, enforce_block = self._resolve_budget_reason(
                action_class="restart_daemon",
                pressure=pressure,
                restart_attempts=len(dq),
                federated_attempts=len(self._federated_controls) if scope == "federated" else 0,
            )
            if reason == "restart_budget_exceeded":
                self._quarantine[daemon_name] = True

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
            details={
                "scope": scope,
                "restart_attempts": len(dq),
                "federated_attempts": len(self._federated_controls) if scope == "federated" else 0,
                "critical_events": len(self._critical_events),
            },
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

        reason, enforce_block = self._resolve_budget_reason(
            action_class="repair_action",
            pressure=pressure,
            repair_attempts=len(dq),
        )

        trust_eval, trust_payload = self._evaluate_audit_trust_posture(
            action_class="repair_action",
            metadata=metadata,
        )
        feedback_eval, feedback_payload = self._evaluate_runtime_feedback_posture(
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
            details={
                "repair_attempts": len(dq),
                "anomaly_kind": anomaly_kind,
                "critical_events": len(self._critical_events),
            },
        )
        posture = self._compose_runtime_posture(
            action_class="repair_action",
            scope="local",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, feedback_eval, epoch_eval, arbitration_eval],
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
            metadata={"anomaly_kind": anomaly_kind, **(metadata or {}), **trust_payload, **feedback_payload, **epoch_payload},
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

        reason, enforce_block = self._resolve_budget_reason(
            action_class="federated_control",
            pressure=pressure,
            federated_attempts=len(self._federated_controls),
        )

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
        peer_trust_eval, peer_trust_payload = self._evaluate_peer_trust_posture(
            action_class="federated_control",
            origin=origin,
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
            details={
                "federated_controls": len(self._federated_controls),
                "critical_events": len(self._critical_events),
                "storm_parity": "restart_repair_federated_symmetric",
            },
        )
        posture = self._compose_runtime_posture(
            action_class="federated_control",
            scope="federated",
            pressure=pressure,
            now=now,
            evaluations=[budget_eval, trust_eval, epoch_eval, peer_trust_eval, federation_eval, arbitration_eval],
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
            metadata={**(metadata or {}), **trust_payload, **epoch_payload, **peer_trust_payload, **federation_payload},
            correlation_id=correlation_id,
            posture=posture,
        )
        self._record_contention(action_class="federated_control", allowed=allowed, now=now)
        return decision

    def _resolve_budget_reason(
        self,
        *,
        action_class: str,
        pressure: PressureSnapshot,
        restart_attempts: int = 0,
        repair_attempts: int = 0,
        federated_attempts: int = 0,
    ) -> tuple[str, bool]:
        reason = "allowed"
        enforce_block = False
        if action_class == "restart_daemon" and restart_attempts > self._restart_limit:
            return "restart_budget_exceeded", True
        if action_class == "repair_action" and repair_attempts > self._repair_limit:
            return "repair_budget_exceeded", True
        if action_class in {"restart_daemon", "federated_control"} and federated_attempts > self._federated_limit:
            return "federated_control_rate_exceeded", True
        if len(self._critical_events) > self._critical_limit:
            return "critical_event_storm_detected", True
        if pressure.composite >= self._pressure_block:
            return "pressure_block", True
        if pressure.composite >= self._pressure_warn:
            return "pressure_warn", False
        return reason, enforce_block

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
        feedback_eval, feedback_payload = self._evaluate_runtime_feedback_posture(
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
            evaluations=[budget_eval, trust_eval, feedback_eval, epoch_eval, arbitration_eval],
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
            metadata={**(metadata or {}), **trust_payload, **feedback_payload, **epoch_payload},
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
        feedback_eval, feedback_payload = self._evaluate_runtime_feedback_posture(
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
            evaluations=[budget_eval, trust_eval, feedback_eval, epoch_eval, arbitration_eval],
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
            metadata={**(metadata or {}), **trust_payload, **feedback_payload, **epoch_payload},
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

    def _prune_subject_state(self, action_class: str) -> None:
        attempts = self._subject_attempts.get(action_class, {})
        if len(attempts) <= self._subject_state_cap:
            return
        scored: list[tuple[int, int, str]] = []
        for subject in attempts:
            decisions = self._subject_decisions[action_class][subject]
            score = int(decisions.get("deny", 0)) + int(decisions.get("defer", 0)) + int(decisions.get("admit", 0))
            streak = int(self._subject_denied_streak[action_class].get(subject, 0))
            scored.append((score, streak, subject))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        keep = {subject for _, _, subject in scored[: self._subject_state_cap]}
        self._subject_attempts[action_class] = {k: v for k, v in attempts.items() if k in keep}
        self._subject_denied_streak[action_class] = {k: v for k, v in self._subject_denied_streak[action_class].items() if k in keep}
        self._subject_decisions[action_class] = {k: v for k, v in self._subject_decisions[action_class].items() if k in keep}

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
        self._prune_subject_state(action_class)
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
            evidence_refs={
                key: metadata[key]
                for key in ("host_resource_evidence", "observed_pressure_labels",
                            "game_performance_evidence", "game_workload_evidence",
                            "active_inference_request_reference",
                            "game_frame_pressure", "host_pressure_during_verified_game",
                            "optional_model_load_in_gaming_profile",
                            "optional_gpu_model_load_in_gaming_profile",
                            "gaming_workload_profile_host_pressure",
                            "gaming_workload_profile_resource_telemetry_incomplete",
                            "gaming_workload_profile_evidence",
                            "resource_observation_evidence",
                            "resource_allocation_binding")
                if metadata is not None and key in metadata
            },
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
        payload["enforcement_policy"] = resolve_policy().to_dict()
        payload["pressure_snapshot"] = pressure.to_dict()
        payload["pressure_band"] = pressure_band
        payload["contention_snapshot"] = contention_snapshot
        payload["reserved_capacity"] = reserved_capacity
        payload["starvation_signals"] = starvation_signals
        payload["subject_fairness"] = subject_fairness
        payload["queue_pressure"] = queue_pressure
        runtime_posture = (posture or self._compose_runtime_posture(
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
        payload["runtime_posture"] = runtime_posture
        payload["dominant_restriction_cause"] = str(runtime_posture.get("dominant_reason") or "")
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
            "runtime_posture": runtime_posture,
            "effective_posture": runtime_posture.get("effective_posture"),
            "active_posture_dimensions": runtime_posture.get("active_dimensions"),
            "dominant_restriction_cause": runtime_posture.get("dominant_reason"),
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
        pressure = self.sample_pressure()
        trust_ledger = get_trust_ledger()
        schedule = trust_ledger.build_probe_schedule(
            peer_ids=federation.trusted_peers(),
            pressure_composite=pressure.composite,
            scheduling_window_open=pressure.composite <= self._schedule_threshold,
            storm_active=len(self._critical_events) > self._critical_limit,
        )
        snapshot = {
            "schema_version": 1,
            "mode": self._mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "federation_governance_digest": local_digest,
            "restart_counts": {name: len(entries) for name, entries in self._restarts.items()},
            "repair_counts": {name: len(entries) for name, entries in self._repairs.items()},
            "federated_controls": len(self._federated_controls),
            "federation_probe_schedule": schedule,
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
            import psutil

            cpu_percent = getattr(psutil, "cpu_percent", None)
            if not callable(cpu_percent):
                return 0.0
            measured = cpu_percent(interval=0.0)
            if not isinstance(measured, (int, float)):
                return 0.0
            return round(min(1.0, max(0.0, float(measured) / 100.0)), 4)
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
            import psutil

            sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
            if not callable(sensors_temperatures):
                return 0.0
            temps = sensors_temperatures()
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
    try:
        from sentientos.control_plane_kernel import reset_control_plane_kernel

        reset_control_plane_kernel()
    except Exception:
        # Defensive: runtime governor reset must remain available even if the
        # control-plane kernel is not importable in constrained environments.
        pass
