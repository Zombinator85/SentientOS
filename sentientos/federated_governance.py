"""Deterministic governance digest and quorum evaluation for federation actions."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from sentientos.audit_trust_runtime import evaluate_audit_trust
from sentientos.daemons import pulse_bus
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.pulse_trust_epoch import get_manager as get_trust_epoch_manager
from sentientos.trust_ledger import get_trust_ledger


@dataclass(frozen=True)
class GovernanceDigest:
    digest: str
    components: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {"digest": self.digest, "components": dict(self.components)}


@dataclass(frozen=True)
class PeerDigestEvaluation:
    peer_name: str
    trusted_peer: bool
    digest_status: str
    compatibility_category: str
    digest_reasons: list[str]
    epoch_status: str
    epoch_id: str
    action_impact: str
    quorum_required: int
    quorum_present: int
    quorum_satisfied: bool
    missing_peers: list[str]
    compatible_peers: list[str]
    peer_trust_state: str
    peer_trust_reasons: list[str]
    peer_quorum_eligible: bool
    protocol_compatibility: str
    replay_horizon_classification: str
    equivocation_classification: str
    denial_cause: str
    calibration_posture: str
    calibration_action: str
    calibration_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "peer_name": self.peer_name,
            "trusted_peer": self.trusted_peer,
            "digest_status": self.digest_status,
            "compatibility_category": self.compatibility_category,
            "digest_reasons": list(self.digest_reasons),
            "epoch_status": self.epoch_status,
            "epoch_id": self.epoch_id,
            "action_impact": self.action_impact,
            "quorum_required": self.quorum_required,
            "quorum_present": self.quorum_present,
            "quorum_satisfied": self.quorum_satisfied,
            "missing_peers": list(self.missing_peers),
            "compatible_peers": list(self.compatible_peers),
            "peer_trust_state": self.peer_trust_state,
            "peer_trust_reasons": list(self.peer_trust_reasons),
            "peer_quorum_eligible": self.peer_quorum_eligible,
            "protocol_compatibility": self.protocol_compatibility,
            "replay_horizon_classification": self.replay_horizon_classification,
            "equivocation_classification": self.equivocation_classification,
            "denial_cause": self.denial_cause,
            "calibration_posture": self.calibration_posture,
            "calibration_action": self.calibration_action,
            "calibration_reason": self.calibration_reason,
        }


class FederatedGovernanceController:
    """Computes governance digests and evaluates bounded quorum requirements."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._trusted_peers: set[str] = set()
        self._quorum_votes: dict[str, set[str]] = {}
        self._quorum_requirements: dict[str, int] = {
            "low_impact_advisory": max(1, self._env_int("SENTIENTOS_FEDERATION_QUORUM_LOW", 1)),
            "medium_impact_coordination": max(1, self._env_int("SENTIENTOS_FEDERATION_QUORUM_MEDIUM", 1)),
            "high_impact_control": max(2, self._env_int("SENTIENTOS_FEDERATION_QUORUM_HIGH", 2)),
        }
        self._governor_root = Path(os.getenv("SENTIENTOS_GOVERNOR_ROOT", "/glow/governor"))
        self._federation_root = Path(os.getenv("SENTIENTOS_FEDERATION_ROOT", "/glow/federation"))
        self._peer_digests: dict[str, dict[str, object]] = {}

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> str | None:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    @staticmethod
    def _canonical_digest(payload: Mapping[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _action_impact_for_event(event: Mapping[str, object]) -> str:
        payload = event.get("payload")
        action = ""
        event_type = str(event.get("event_type") or "").strip().lower()
        if isinstance(payload, dict):
            action = str(payload.get("action") or payload.get("event_action") or "").strip().lower()
        restart_actions = {"restart_daemon"}
        lineage_actions = {"lineage_rewrite", "lineage_rebind"}
        governance_actions = {"rotate_keys", "amendment_apply", "governance_update"}
        if action in restart_actions or event_type in {"restart_request"}:
            return "high_impact_control"
        if action in lineage_actions:
            return "high_impact_control"
        if action in governance_actions or event_type in {"federated_control"}:
            return "high_impact_control"
        if action in {"synchronize", "sync_state", "coordination_hint", "coordination_update"}:
            return "medium_impact_coordination"
        return "low_impact_advisory"

    @staticmethod
    def _git_sha(repo_root: Path) -> str:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return ""
        return completed.stdout.strip()

    def _json_fingerprint(self, path: Path) -> str | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return self._sha256_text(encoded)

    @staticmethod
    def _compatibility_for_action(impact: str) -> set[str]:
        if impact == "high_impact_control":
            return {"exact_match", "compatible_family"}
        if impact == "medium_impact_coordination":
            return {"exact_match", "compatible_family", "patch_drift"}
        return {"exact_match", "compatible_family", "patch_drift", "incompatible", "epoch_mismatch", "locally_restricted"}

    @staticmethod
    def _posture_action(posture: str) -> str:
        if posture == "enforce":
            return "deny"
        if posture == "advisory":
            return "warn"
        return "observe"

    def local_governance_digest(self) -> GovernanceDigest:
        repo_root = Path(os.getenv("SENTIENTOS_REPO_ROOT", Path.cwd())).resolve()
        manifest_path = Path(os.getenv("SENTIENTOS_IMMUTABLE_MANIFEST", "/vow/immutable_manifest.json"))
        invariants_path = Path(os.getenv("SENTIENTOS_INVARIANTS_PATH", "/vow/invariants.yaml"))
        audit = evaluate_audit_trust(repo_root, context="federation_governance_digest")
        epoch_state = get_trust_epoch_manager().load_state()

        policy = resolve_policy()
        governor_mode = policy.runtime_governor
        pulse_schema_fp = self._json_fingerprint(repo_root / "glow/pulse/baseline/pulse_schema_baseline.json")
        self_model_schema_fp = self._json_fingerprint(repo_root / "glow/self/baseline/self_model_baseline.json")
        perception_schema_fp = self._json_fingerprint(repo_root / "glow/perception/baseline/perception_schema_baseline.json")
        federation_identity_fp = self._json_fingerprint(
            repo_root / "glow/federation/baseline/federation_identity_baseline.json"
        )
        components: dict[str, object] = {
            "schema_version": 1,
            "manifest_sha256": self._sha256_file(manifest_path),
            "manifest_identity": str(manifest_path),
            "invariants_sha256": self._sha256_file(invariants_path),
            "invariants_identity": str(invariants_path),
            "audit_trust_posture": {
                "degraded_audit_trust": audit.degraded_audit_trust,
                "history_state": audit.history_state,
                "reanchor_required": bool(audit.degraded_audit_trust),
            },
            "pulse_trust_epoch": {
                "active_epoch_id": str(epoch_state.get("active_epoch_id") or ""),
                "compromise_response_mode": bool(epoch_state.get("compromise_response_mode", False)),
                "revoked_epochs": sorted(
                    str(item)
                    for item in epoch_state.get("revoked_epochs", [])
                    if isinstance(item, str)
                ),
            },
            "governor_posture": {
                "mode": governor_mode,
                "profile": policy.profile,
                "federated_window_seconds": self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_WINDOW_SECONDS", 120),
                "federated_limit": self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_LIMIT", 20),
            },
            "schema_fingerprints": {
                "pulse_schema": pulse_schema_fp,
                "self_model_schema": self_model_schema_fp,
                "perception_schema": perception_schema_fp,
            },
            "pulse_protocol_identity": pulse_bus.pulse_protocol_identity(),
            "federation_replay_policy": {
                "policy_version": "federation_replay_v1",
                "window_seconds": self._env_int("SENTIENTOS_FEDERATION_REPLAY_WINDOW_SECONDS", 1200),
                "tolerance_seconds": self._env_int("SENTIENTOS_FEDERATION_REPLAY_WINDOW_TOLERANCE_SECONDS", 120),
            },
            "federation_identity_digest": federation_identity_fp,
            "git_sha": self._git_sha(repo_root),
        }
        digest = self._canonical_digest(components)
        out = GovernanceDigest(digest=digest, components=components)
        self._write_local_digest(out)
        self._write_quorum_policy()
        return out

    def set_trusted_peers(self, peers: set[str]) -> None:
        with self._lock:
            self._trusted_peers = {item for item in peers if item}
        self._write_quorum_policy()

    def trusted_peers(self) -> list[str]:
        with self._lock:
            return sorted(self._trusted_peers)

    def evaluate_peer_event(self, peer_name: str, event: Mapping[str, object]) -> PeerDigestEvaluation:
        local = self.local_governance_digest()
        trusted = peer_name in self._trusted_peers
        peer_trust = get_trust_ledger().get_peer_trust(peer_name)
        trust_state = peer_trust.trust_state
        trust_reasons = list(peer_trust.trust_reasons)
        quorum_eligible = trust_state in {"trusted", "watched", "degraded"}
        protocol_posture = event.get("federation_protocol_posture")
        protocol_compatibility = "unknown"
        replay_horizon_classification = "unknown"
        equivocation_classification = "no_equivocation_evidence"
        if isinstance(protocol_posture, Mapping):
            protocol_compatibility = str(protocol_posture.get("protocol_compatibility") or "unknown")
            replay_horizon_classification = str(protocol_posture.get("replay_horizon_classification") or "unknown")
            equivocation_classification = str(protocol_posture.get("equivocation_classification") or "no_equivocation_evidence")
        action_impact = self._action_impact_for_event(event)
        quorum_required = self._quorum_requirements[action_impact]

        peer_digest_raw = event.get("governance_digest")
        if peer_digest_raw is None and isinstance(event.get("payload"), dict):
            peer_digest_raw = event["payload"].get("governance_digest")  # type: ignore[index]

        digest_status = "missing"
        compatibility_category = "incompatible"
        digest_reasons: list[str] = []
        peer_digest_value = ""
        peer_components: dict[str, object] = {}
        if isinstance(peer_digest_raw, dict):
            peer_digest_value = str(peer_digest_raw.get("digest") or "")
            components = peer_digest_raw.get("components")
            if isinstance(components, dict):
                peer_components = dict(components)
            if peer_digest_value:
                if peer_digest_value == local.digest:
                    digest_status = "compatible"
                    compatibility_category = "exact_match"
                else:
                    digest_status = "incompatible"
                    family_keys = (
                        "manifest_sha256",
                        "invariants_sha256",
                        "federation_identity_digest",
                    )
                    family_match = all(peer_components.get(key) == local.components.get(key) for key in family_keys)
                    posture_keys = ("governor_posture", "audit_trust_posture", "schema_fingerprints")
                    posture_match = all(peer_components.get(key) == local.components.get(key) for key in posture_keys)
                    if family_match and posture_match:
                        compatibility_category = "patch_drift"
                    elif family_match:
                        compatibility_category = "compatible_family"
                    else:
                        compatibility_category = "incompatible"
                    for key in family_keys + posture_keys + ("pulse_trust_epoch",):
                        if peer_components.get(key) != local.components.get(key):
                            digest_reasons.append(f"{key}_mismatch")
            else:
                digest_reasons.append("peer_digest_missing")
        else:
            digest_reasons.append("peer_digest_missing")

        epoch_id = str(event.get("pulse_epoch_id") or "")
        local_epoch = str(
            ((local.components.get("pulse_trust_epoch") or {}) if isinstance(local.components.get("pulse_trust_epoch"), dict) else {}).get("active_epoch_id")
            or ""
        )
        epoch_status = "expected" if not epoch_id or epoch_id == local_epoch or epoch_id == "legacy" else "unexpected"
        if epoch_status == "unexpected":
            compatibility_category = "epoch_mismatch"

        if not quorum_eligible:
            compatibility_category = "locally_restricted"

        action_key = self._action_key(event, action_impact)
        quorum_present = 0
        compatible_peers: list[str] = []
        allowed_categories = self._compatibility_for_action(action_impact)
        with self._lock:
            if (
                trusted
                and quorum_eligible
                and epoch_status == "expected"
                and compatibility_category in allowed_categories
                and compatibility_category != "locally_restricted"
            ):
                votes = self._quorum_votes.setdefault(action_key, set())
                votes.add(peer_name)
            votes = self._quorum_votes.get(action_key, set())
            compatible_peers = sorted(votes)
            quorum_present = len(compatible_peers)

        required_peers = sorted(self._trusted_peers)
        missing_peers = [item for item in required_peers if item not in compatible_peers]
        quorum_satisfied = quorum_present >= quorum_required

        policy = resolve_policy()
        quorum_mode = policy.federated_quorum
        digest_mode = policy.governance_digest
        denial_cause = "none"
        calibration_reason = "federated_governance_nominal"
        calibration_action = "observe"
        calibration_posture = "shadow"
        if not trusted:
            denial_cause = "untrusted_peer"
            calibration_reason = "untrusted_peer"
            calibration_action = "deny"
            calibration_posture = "enforce"
        elif not quorum_eligible:
            denial_cause = "peer_trust_restricted"
            calibration_reason = "peer_trust_restricted"
            calibration_action = "deny"
            calibration_posture = "enforce"
        elif protocol_compatibility == "incompatible_protocol":
            denial_cause = "protocol_incompatibility"
            calibration_reason = "protocol_incompatibility"
            calibration_action = "deny"
            calibration_posture = "enforce"
        elif replay_horizon_classification in {"incompatible_replay_policy", "peer_too_stale_for_replay_horizon"}:
            denial_cause = "replay_window_mismatch"
            calibration_reason = replay_horizon_classification
            calibration_action = "deny"
            calibration_posture = "enforce"
        elif equivocation_classification in {
            "confirmed_equivocation",
            "protocol_claim_conflict",
            "replay_claim_conflict",
        }:
            denial_cause = "equivocation_evidence"
            calibration_reason = equivocation_classification
            calibration_action = "deny"
            calibration_posture = "enforce"
        elif epoch_status == "unexpected":
            calibration_posture = policy.pulse_trust_epoch
            calibration_action = self._posture_action(calibration_posture)
            calibration_reason = "pulse_epoch_mismatch"
            if calibration_action == "deny":
                denial_cause = "trust_epoch"
            elif calibration_action == "warn":
                denial_cause = "trust_epoch_advisory"
            else:
                denial_cause = "trust_epoch_observed"
        else:
            digest_mismatch = (
                compatibility_category in {"incompatible", "epoch_mismatch", "locally_restricted", "patch_drift"}
                or digest_status == "missing"
            )
            if digest_mismatch:
                calibration_posture = digest_mode
                calibration_action = self._posture_action(calibration_posture)
                calibration_reason = "governance_digest_mismatch"
                if calibration_action == "deny" and action_impact == "high_impact_control":
                    denial_cause = "digest_mismatch"
                elif calibration_action == "warn":
                    denial_cause = "digest_mismatch_advisory"
                else:
                    denial_cause = "digest_mismatch_observed"
            elif not quorum_satisfied and quorum_required > 1:
                calibration_posture = quorum_mode
                calibration_action = self._posture_action(calibration_posture)
                calibration_reason = "federation_quorum_unsatisfied"
                if calibration_action == "deny":
                    denial_cause = "quorum_failure"
                elif calibration_action == "warn":
                    denial_cause = "quorum_warning"
                else:
                    denial_cause = "quorum_observed"

        evaluation = PeerDigestEvaluation(
            peer_name=peer_name,
            trusted_peer=trusted,
            digest_status=digest_status,
            compatibility_category=compatibility_category,
            digest_reasons=sorted(set(digest_reasons)),
            epoch_status=epoch_status,
            epoch_id=epoch_id,
            action_impact=action_impact,
            quorum_required=quorum_required,
            quorum_present=quorum_present,
            quorum_satisfied=quorum_satisfied,
            missing_peers=missing_peers,
            compatible_peers=compatible_peers,
            peer_trust_state=trust_state,
            peer_trust_reasons=trust_reasons,
            peer_quorum_eligible=quorum_eligible,
            protocol_compatibility=protocol_compatibility,
            replay_horizon_classification=replay_horizon_classification,
            equivocation_classification=equivocation_classification,
            denial_cause=denial_cause,
            calibration_posture=calibration_posture,
            calibration_action=calibration_action,
            calibration_reason=calibration_reason,
        )
        self._record_peer_digest(peer_name, peer_digest_value, peer_components, evaluation)
        self._append_quorum_decision(evaluation, action_key=action_key, policy=policy.to_dict())
        get_trust_ledger().record_governance_evaluation(peer_name, evaluation.to_dict(), actor="federated_governance")
        return evaluation

    def _action_key(self, event: Mapping[str, object], impact: str) -> str:
        payload = event.get("payload")
        subject = ""
        action = ""
        if isinstance(payload, dict):
            subject = str(payload.get("daemon") or payload.get("daemon_name") or payload.get("target") or "")
            action = str(payload.get("action") or "")
        correlation = str(event.get("correlation_id") or event.get("event_hash") or "")
        raw = {
            "impact": impact,
            "correlation_id": correlation,
            "event_type": str(event.get("event_type") or ""),
            "action": action,
            "subject": subject,
        }
        return self._canonical_digest(raw)

    def _write_local_digest(self, digest: GovernanceDigest) -> None:
        payload = {
            "schema_version": 1,
            "generated_at": self._now(),
            **digest.to_dict(),
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            (root / "governance_digest.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _write_quorum_policy(self) -> None:
        action_class_map = {
            "advisory": "low_impact_advisory",
            "coordination_update": "medium_impact_coordination",
            "restart_daemon": "high_impact_control",
            "lineage_rewrite": "high_impact_control",
            "governance_update": "high_impact_control",
        }
        payload = {
            "schema_version": 1,
            "updated_at": self._now(),
            "requirements": dict(sorted(self._quorum_requirements.items())),
            "trusted_peers": sorted(self._trusted_peers),
            "action_classes": dict(sorted(action_class_map.items())),
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            (root / "federation_quorum_policy.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _record_peer_digest(
        self,
        peer_name: str,
        peer_digest: str,
        peer_components: Mapping[str, object],
        evaluation: PeerDigestEvaluation,
    ) -> None:
        self._peer_digests[peer_name] = {
            "peer_name": peer_name,
            "peer_digest": peer_digest,
            "peer_components": dict(peer_components),
            "last_seen_at": self._now(),
            "digest_status": evaluation.digest_status,
            "digest_reasons": list(evaluation.digest_reasons),
            "epoch_status": evaluation.epoch_status,
            "peer_trust_state": evaluation.peer_trust_state,
            "peer_trust_reasons": list(evaluation.peer_trust_reasons),
            "peer_quorum_eligible": evaluation.peer_quorum_eligible,
            "compatibility_category": evaluation.compatibility_category,
            "protocol_compatibility": evaluation.protocol_compatibility,
            "replay_horizon_classification": evaluation.replay_horizon_classification,
            "equivocation_classification": evaluation.equivocation_classification,
            "denial_cause": evaluation.denial_cause,
        }
        payload = {
            "schema_version": 1,
            "updated_at": self._now(),
            "peers": [self._peer_digests[name] for name in sorted(self._peer_digests)],
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            (root / "peer_governance_digests.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _append_quorum_decision(self, evaluation: PeerDigestEvaluation, *, action_key: str, policy: Mapping[str, object]) -> None:
        payload = {
            "schema_version": 1,
            "timestamp": self._now(),
            "action_key": action_key,
            "enforcement_policy": dict(policy),
            **evaluation.to_dict(),
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            with (root / "quorum_decisions.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
            (root / "quorum_status.json").write_text(json.dumps({
                "schema_version": 1,
                "updated_at": self._now(),
                "trusted_peers": sorted(self._trusted_peers),
                "requirements": dict(sorted(self._quorum_requirements.items())),
                "pending_actions": len(self._quorum_votes),
                "last_decision": payload,
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if evaluation.digest_status in {"missing", "incompatible"}:
                (root / "governance_digest_mismatch_report.json").write_text(json.dumps({
                    "schema_version": 1,
                    "updated_at": self._now(),
                    "peer_name": evaluation.peer_name,
                    "digest_status": evaluation.digest_status,
                    "compatibility_category": evaluation.compatibility_category,
                    "digest_reasons": evaluation.digest_reasons,
                    "action_impact": evaluation.action_impact,
                    "denial_cause": evaluation.denial_cause,
                }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


_CONTROLLER = FederatedGovernanceController()


def get_controller() -> FederatedGovernanceController:
    return _CONTROLLER


def reset_controller() -> None:
    global _CONTROLLER
    _CONTROLLER = FederatedGovernanceController()
