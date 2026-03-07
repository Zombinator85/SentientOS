"""Deterministic governance digest and quorum evaluation for federation actions."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from sentientos.audit_trust_runtime import evaluate_audit_trust
from sentientos.pulse_trust_epoch import get_manager as get_trust_epoch_manager


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
    digest_reasons: list[str]
    epoch_status: str
    epoch_id: str
    action_impact: str
    quorum_required: int
    quorum_present: int
    quorum_satisfied: bool
    missing_peers: list[str]
    compatible_peers: list[str]
    denial_cause: str

    def to_dict(self) -> dict[str, object]:
        return {
            "peer_name": self.peer_name,
            "trusted_peer": self.trusted_peer,
            "digest_status": self.digest_status,
            "digest_reasons": list(self.digest_reasons),
            "epoch_status": self.epoch_status,
            "epoch_id": self.epoch_id,
            "action_impact": self.action_impact,
            "quorum_required": self.quorum_required,
            "quorum_present": self.quorum_present,
            "quorum_satisfied": self.quorum_satisfied,
            "missing_peers": list(self.missing_peers),
            "compatible_peers": list(self.compatible_peers),
            "denial_cause": self.denial_cause,
        }


class FederatedGovernanceController:
    """Computes governance digests and evaluates bounded quorum requirements."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._trusted_peers: set[str] = set()
        self._quorum_votes: dict[str, set[str]] = {}
        self._quorum_requirements: dict[str, int] = {
            "low": max(1, self._env_int("SENTIENTOS_FEDERATION_QUORUM_LOW", 1)),
            "medium": max(1, self._env_int("SENTIENTOS_FEDERATION_QUORUM_MEDIUM", 1)),
            "high": max(2, self._env_int("SENTIENTOS_FEDERATION_QUORUM_HIGH", 2)),
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
        high_actions = {"restart_daemon", "rotate_keys", "amendment_apply", "lineage_rewrite"}
        medium_actions = {"sync", "coordination", "reconcile", "replay"}
        if action in high_actions or event_type in {"restart_request", "federated_control"}:
            return "high"
        if action in medium_actions or event_type in {"coordination", "federation_sync"}:
            return "medium"
        return "low"

    def local_governance_digest(self) -> GovernanceDigest:
        repo_root = Path(os.getenv("SENTIENTOS_REPO_ROOT", Path.cwd())).resolve()
        manifest_path = Path(os.getenv("SENTIENTOS_IMMUTABLE_MANIFEST", "/vow/immutable_manifest.json"))
        invariants_path = Path(os.getenv("SENTIENTOS_INVARIANTS_PATH", "/vow/invariants.yaml"))
        audit = evaluate_audit_trust(repo_root, context="federation_governance_digest")
        epoch_state = get_trust_epoch_manager().load_state()

        governor_mode = os.getenv("SENTIENTOS_GOVERNOR_MODE", "shadow").strip().lower()
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
                "federated_window_seconds": self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_WINDOW_SECONDS", 120),
                "federated_limit": self._env_int("SENTIENTOS_GOVERNOR_FEDERATED_LIMIT", 20),
            },
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

    def evaluate_peer_event(self, peer_name: str, event: Mapping[str, object]) -> PeerDigestEvaluation:
        local = self.local_governance_digest()
        trusted = peer_name in self._trusted_peers
        action_impact = self._action_impact_for_event(event)
        quorum_required = self._quorum_requirements[action_impact]

        peer_digest_raw = event.get("governance_digest")
        if peer_digest_raw is None and isinstance(event.get("payload"), dict):
            peer_digest_raw = event["payload"].get("governance_digest")  # type: ignore[index]

        digest_status = "missing"
        digest_reasons: list[str] = []
        peer_digest_value = ""
        peer_components: dict[str, object] = {}
        if isinstance(peer_digest_raw, dict):
            peer_digest_value = str(peer_digest_raw.get("digest") or "")
            components = peer_digest_raw.get("components")
            if isinstance(components, dict):
                peer_components = dict(components)
            if peer_digest_value:
                digest_status = "compatible" if peer_digest_value == local.digest else "incompatible"
                if digest_status == "incompatible":
                    for key in (
                        "manifest_sha256",
                        "invariants_sha256",
                        "pulse_trust_epoch",
                        "governor_posture",
                        "audit_trust_posture",
                    ):
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

        action_key = self._action_key(event, action_impact)
        quorum_present = 0
        compatible_peers: list[str] = []
        with self._lock:
            if trusted and digest_status == "compatible" and epoch_status == "expected":
                votes = self._quorum_votes.setdefault(action_key, set())
                votes.add(peer_name)
            votes = self._quorum_votes.get(action_key, set())
            compatible_peers = sorted(votes)
            quorum_present = len(compatible_peers)

        required_peers = sorted(self._trusted_peers)
        missing_peers = [item for item in required_peers if item not in compatible_peers]
        quorum_satisfied = quorum_present >= quorum_required

        denial_cause = "none"
        if not trusted:
            denial_cause = "untrusted_peer"
        elif epoch_status == "unexpected":
            denial_cause = "trust_epoch"
        elif digest_status in {"missing", "incompatible"} and action_impact == "high":
            denial_cause = "digest_mismatch"
        elif not quorum_satisfied and quorum_required > 1:
            denial_cause = "quorum_failure"

        evaluation = PeerDigestEvaluation(
            peer_name=peer_name,
            trusted_peer=trusted,
            digest_status=digest_status,
            digest_reasons=sorted(set(digest_reasons)),
            epoch_status=epoch_status,
            epoch_id=epoch_id,
            action_impact=action_impact,
            quorum_required=quorum_required,
            quorum_present=quorum_present,
            quorum_satisfied=quorum_satisfied,
            missing_peers=missing_peers,
            compatible_peers=compatible_peers,
            denial_cause=denial_cause,
        )
        self._record_peer_digest(peer_name, peer_digest_value, peer_components, evaluation)
        self._append_quorum_decision(evaluation, action_key=action_key)
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
        payload = {
            "schema_version": 1,
            "updated_at": self._now(),
            "requirements": dict(sorted(self._quorum_requirements.items())),
            "trusted_peers": sorted(self._trusted_peers),
            "action_classes": {
                "low": "federated_advisory",
                "medium": "federated_coordination",
                "high": "federated_control",
            },
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

    def _append_quorum_decision(self, evaluation: PeerDigestEvaluation, *, action_key: str) -> None:
        payload = {
            "schema_version": 1,
            "timestamp": self._now(),
            "action_key": action_key,
            **evaluation.to_dict(),
        }
        for root in (self._governor_root, self._federation_root):
            root.mkdir(parents=True, exist_ok=True)
            with (root / "federation_quorum_decisions.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")


_CONTROLLER = FederatedGovernanceController()


def get_controller() -> FederatedGovernanceController:
    return _CONTROLLER


def reset_controller() -> None:
    global _CONTROLLER
    _CONTROLLER = FederatedGovernanceController()
