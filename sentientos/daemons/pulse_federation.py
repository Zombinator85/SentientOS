"""Federated propagation and ingestion for the pulse bus."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Sequence, cast

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from . import pulse_bus
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.federated_governance import get_controller as get_federated_governance_controller
from sentientos.pulse_trust_epoch import get_manager as get_trust_epoch_manager
from sentientos.runtime_governor import get_runtime_governor
from sentientos.trust_ledger import get_trust_ledger

logger = logging.getLogger(__name__)

_KEYS_DIR_ENV = "PULSE_FEDERATION_KEYS_DIR"
_DEFAULT_KEYS_DIR = Path("/glow/federation_keys")
_REQUEST_TIMEOUT_SECONDS = 5
_FEDERATION_ENDPOINT = "/pulse/federation"


@dataclass(frozen=True)
class _Peer:
    name: str
    endpoint: str

    def api_base(self) -> str:
        base = self.endpoint.strip()
        if not base:
            return ""
        if "://" not in base:
            base = f"http://{base}"
        return base.rstrip("/")


_ENABLED = False
_PEER_MAP: dict[str, _Peer] = {}
_PEER_KEYS: dict[str, VerifyKey] = {}
_SUBSCRIPTION: pulse_bus.PulseSubscription | None = None
_REPLAY_CACHE_LIMIT = int(os.getenv("PULSE_FEDERATION_REPLAY_CACHE_SIZE", "2048"))
_SEEN_EVENT_HASHES: set[str] = set()
_SEEN_EVENT_ORDER: deque[str] = deque()
_PEER_PROTOCOL_POSTURE: dict[str, dict[str, object]] = {}
_PEER_EQUIVOCATION_EVIDENCE: dict[str, deque[dict[str, object]]] = {}
_PEER_CLAIM_WINDOWS: dict[str, dict[str, object]] = {}
_EQUIVOCATION_WINDOW_SECONDS = max(60, int(os.getenv("SENTIENTOS_FEDERATION_EQUIVOCATION_WINDOW_SECONDS", "600")))
_EQUIVOCATION_EVIDENCE_LIMIT = max(32, int(os.getenv("SENTIENTOS_FEDERATION_EQUIVOCATION_EVIDENCE_LIMIT", "256")))
_REPLAY_WINDOW_SECONDS = max(60, int(os.getenv("SENTIENTOS_FEDERATION_REPLAY_WINDOW_SECONDS", "1200")))
_REPLAY_WINDOW_TOLERANCE_SECONDS = max(0, int(os.getenv("SENTIENTOS_FEDERATION_REPLAY_WINDOW_TOLERANCE_SECONDS", "120")))
_REPLAY_POLICY_VERSION = "federation_replay_v1"
_PROTOCOL_COMPAT_MIN_VERSION = os.getenv("SENTIENTOS_FEDERATION_PROTOCOL_MIN_VERSION", "2.0.0")
_PROTOCOL_DEPRECATED_MIN_VERSION = os.getenv("SENTIENTOS_FEDERATION_PROTOCOL_DEPRECATED_MIN_VERSION", "1.9.0")
_ACCEPT_DEPRECATED_PROTOCOL = os.getenv("SENTIENTOS_FEDERATION_ACCEPT_DEPRECATED_PROTOCOL", "1") not in {"0", "false", "False"}


def _keys_dir() -> Path:
    override = os.getenv(_KEYS_DIR_ENV)
    if override:
        return Path(override)
    return _DEFAULT_KEYS_DIR


def _federation_runtime_root() -> Path:
    return Path(os.getenv("SENTIENTOS_FEDERATION_ROOT", "/glow/federation"))


def _sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", value.strip())
    return sanitized or "peer"


def _parse_semver(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return None
    if major < 0 or minor < 0 or patch < 0:
        return None
    return major, minor, patch


def _claims_window_key(timestamp: str) -> str:
    dt = pulse_bus._parse_timestamp(timestamp)
    slot = int(dt.timestamp()) // _EQUIVOCATION_WINDOW_SECONDS
    return f"{slot:010d}"


def _policy_fingerprint(policy: Mapping[str, object]) -> str:
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _local_replay_policy() -> dict[str, object]:
    return {
        "policy_version": _REPLAY_POLICY_VERSION,
        "window_seconds": _REPLAY_WINDOW_SECONDS,
        "tolerance_seconds": _REPLAY_WINDOW_TOLERANCE_SECONDS,
    }


def _local_protocol_identity() -> dict[str, object]:
    identity = pulse_bus.pulse_protocol_identity()
    identity["replay_policy"] = _local_replay_policy()
    return identity


def _classify_protocol_compatibility(
    peer_claim: Mapping[str, object] | None,
) -> tuple[str, list[str], dict[str, object]]:
    local = _local_protocol_identity()
    local_semver = _parse_semver(local.get("protocol_version"))
    peer = dict(peer_claim) if isinstance(peer_claim, Mapping) else {}
    if not peer:
        return "incompatible_protocol", ["missing_protocol_claim"], local
    peer_semver = _parse_semver(peer.get("protocol_version"))
    if peer_semver is None or local_semver is None:
        return "incompatible_protocol", ["invalid_protocol_version"], local
    if peer.get("schema_family") != local.get("schema_family"):
        return "incompatible_protocol", ["schema_family_mismatch"], local
    peer_policy = peer.get("replay_policy")
    local_policy = local.get("replay_policy")
    if not isinstance(peer_policy, Mapping) or not isinstance(local_policy, Mapping):
        return "incompatible_protocol", ["missing_replay_policy"], local
    if peer_policy.get("policy_version") != local_policy.get("policy_version"):
        return "incompatible_protocol", ["replay_policy_version_mismatch"], local
    peer_fp = str(peer.get("protocol_fingerprint") or "")
    local_fp = str(local.get("protocol_fingerprint") or "")
    if peer_semver == local_semver and peer_fp == local_fp:
        return "exact_protocol_match", [], local
    major, minor, _ = peer_semver
    local_major, local_minor, _ = local_semver
    min_semver = _parse_semver(_PROTOCOL_COMPAT_MIN_VERSION)
    deprecated_min = _parse_semver(_PROTOCOL_DEPRECATED_MIN_VERSION)
    if major == local_major and minor == local_minor:
        return "patch_compatible", ["patch_or_fingerprint_drift"], local
    if (
        major == local_major
        and min_semver is not None
        and peer_semver >= min_semver
        and minor <= local_minor
    ):
        return "compatible_family", ["family_minor_drift"], local
    if (
        _ACCEPT_DEPRECATED_PROTOCOL
        and deprecated_min is not None
        and major == local_major
        and deprecated_min <= peer_semver < (min_semver or local_semver)
    ):
        return "deprecated_but_accepted", ["deprecated_protocol_family"], local
    return "incompatible_protocol", ["unsupported_protocol_version"], local


def _classify_replay_horizon(
    event: Mapping[str, object],
    peer_claim: Mapping[str, object] | None,
) -> tuple[str, dict[str, object]]:
    policy = _local_replay_policy()
    peer_policy = (
        dict(peer_claim.get("replay_policy"))
        if isinstance(peer_claim, Mapping) and isinstance(peer_claim.get("replay_policy"), Mapping)
        else {}
    )
    peer_version = str(peer_policy.get("policy_version") or "")
    if peer_version and peer_version != _REPLAY_POLICY_VERSION:
        return "incompatible_replay_policy", {"local_policy": policy, "peer_policy": peer_policy}
    peer_window = int(peer_policy.get("window_seconds") or _REPLAY_WINDOW_SECONDS)
    peer_tolerance = int(peer_policy.get("tolerance_seconds") or _REPLAY_WINDOW_TOLERANCE_SECONDS)
    if abs(peer_window - _REPLAY_WINDOW_SECONDS) > max(_REPLAY_WINDOW_TOLERANCE_SECONDS, peer_tolerance):
        return "incompatible_replay_policy", {"local_policy": policy, "peer_policy": peer_policy}
    ts = pulse_bus._parse_timestamp(str(event.get("timestamp", "")))
    age_seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    compatible_horizon = min(_REPLAY_WINDOW_SECONDS, peer_window) + max(_REPLAY_WINDOW_TOLERANCE_SECONDS, peer_tolerance)
    max_horizon = max(_REPLAY_WINDOW_SECONDS, peer_window) + max(_REPLAY_WINDOW_TOLERANCE_SECONDS, peer_tolerance)
    if age_seconds <= compatible_horizon:
        return "peer_within_compatible_replay_horizon", {"age_seconds": age_seconds, "accepted_horizon_seconds": compatible_horizon}
    if age_seconds <= max_horizon:
        return "peer_outside_accepted_replay_horizon", {"age_seconds": age_seconds, "accepted_horizon_seconds": compatible_horizon}
    return "peer_too_stale_for_replay_horizon", {"age_seconds": age_seconds, "accepted_horizon_seconds": compatible_horizon}


def _normalize_peer(entry: object) -> _Peer | None:
    if isinstance(entry, str):
        endpoint = entry.strip()
        if not endpoint:
            return None
        name = _sanitize_name(endpoint)
        return _Peer(name=name, endpoint=endpoint)
    if isinstance(entry, dict):
        raw_name = entry.get("name") or entry.get("id") or entry.get("peer")
        raw_endpoint = (
            entry.get("url")
            or entry.get("endpoint")
            or entry.get("address")
            or entry.get("host")
        )
        endpoint = str(raw_endpoint or "").strip()
        if not endpoint:
            return None
        name_value = str(raw_name or endpoint)
        name = _sanitize_name(name_value)
        return _Peer(name=name, endpoint=endpoint)
    return None


def _record_equivocation(
    *,
    peer_name: str,
    classification: str,
    reason: str,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "peer_name": peer_name,
        "classification": classification,
        "reason": reason,
        "evidence": dict(evidence),
    }
    cache = _PEER_EQUIVOCATION_EVIDENCE.setdefault(peer_name, deque(maxlen=_EQUIVOCATION_EVIDENCE_LIMIT))
    cache.append(payload)
    root = _federation_runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "equivocation_evidence.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def _classify_equivocation(
    *,
    peer_name: str,
    event: Mapping[str, object],
    protocol_claim: Mapping[str, object] | None,
) -> tuple[str, list[dict[str, object]]]:
    evidence_rows: list[dict[str, object]] = []
    correlation = str(event.get("correlation_id") or event.get("event_hash") or pulse_bus.compute_event_hash(dict(event)))
    event_hash = str(event.get("event_hash") or pulse_bus.compute_event_hash(dict(event)))
    window = _claims_window_key(str(event.get("timestamp") or datetime.now(timezone.utc).isoformat()))
    peer_claims = _PEER_CLAIM_WINDOWS.setdefault(peer_name, {})
    prev_hash = str(peer_claims.get(f"correlation:{correlation}") or "")
    if prev_hash and prev_hash != event_hash:
        evidence_rows.append(
            _record_equivocation(
                peer_name=peer_name,
                classification="confirmed_equivocation",
                reason="same_correlation_conflicting_event_hash",
                evidence={"correlation_id": correlation, "previous_hash": prev_hash, "event_hash": event_hash},
            )
        )
    peer_claims[f"correlation:{correlation}"] = event_hash
    protocol_fp = (
        str(protocol_claim.get("protocol_fingerprint") or _policy_fingerprint(protocol_claim))
        if isinstance(protocol_claim, Mapping)
        else ""
    )
    protocol_key = f"protocol:{window}"
    prev_protocol_fp = str(peer_claims.get(protocol_key) or "")
    if prev_protocol_fp and protocol_fp and prev_protocol_fp != protocol_fp:
        evidence_rows.append(
            _record_equivocation(
                peer_name=peer_name,
                classification="protocol_claim_conflict",
                reason="conflicting_protocol_fingerprint_within_window",
                evidence={"window": window, "previous_protocol_fingerprint": prev_protocol_fp, "protocol_fingerprint": protocol_fp},
            )
        )
    if protocol_fp:
        peer_claims[protocol_key] = protocol_fp
    replay_policy = (
        dict(protocol_claim.get("replay_policy"))
        if isinstance(protocol_claim, Mapping) and isinstance(protocol_claim.get("replay_policy"), Mapping)
        else {}
    )
    replay_fp = _policy_fingerprint(replay_policy) if replay_policy else ""
    replay_key = f"replay:{window}"
    prev_replay_fp = str(peer_claims.get(replay_key) or "")
    if prev_replay_fp and replay_fp and prev_replay_fp != replay_fp:
        evidence_rows.append(
            _record_equivocation(
                peer_name=peer_name,
                classification="replay_claim_conflict",
                reason="conflicting_replay_policy_within_window",
                evidence={"window": window, "previous_replay_fingerprint": prev_replay_fp, "replay_fingerprint": replay_fp},
            )
        )
    if replay_fp:
        peer_claims[replay_key] = replay_fp
    gov_digest_raw = event.get("governance_digest")
    gov_digest = ""
    if isinstance(gov_digest_raw, Mapping):
        gov_digest = str(gov_digest_raw.get("digest") or "")
    digest_key = f"digest:{window}"
    prev_digest = str(peer_claims.get(digest_key) or "")
    if prev_digest and gov_digest and prev_digest != gov_digest:
        evidence_rows.append(
            _record_equivocation(
                peer_name=peer_name,
                classification="weak_equivocation_signal",
                reason="conflicting_governance_digest_within_window",
                evidence={"window": window, "previous_digest": prev_digest, "governance_digest": gov_digest},
            )
        )
    if gov_digest:
        peer_claims[digest_key] = gov_digest
    classification = "no_equivocation_evidence"
    if any(row["classification"] == "confirmed_equivocation" for row in evidence_rows):
        classification = "confirmed_equivocation"
    elif any(row["classification"] == "protocol_claim_conflict" for row in evidence_rows):
        classification = "protocol_claim_conflict"
    elif any(row["classification"] == "replay_claim_conflict" for row in evidence_rows):
        classification = "replay_claim_conflict"
    elif evidence_rows:
        classification = "weak_equivocation_signal"
    return classification, evidence_rows


def _write_protocol_posture() -> None:
    root = _federation_runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    peers = []
    for name in sorted(_PEER_PROTOCOL_POSTURE):
        peers.append(dict(_PEER_PROTOCOL_POSTURE[name]))
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "local_protocol_identity": _local_protocol_identity(),
        "local_replay_policy": _local_replay_policy(),
        "peers": peers,
    }
    (root / "pulse_protocol_posture.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    equivocation_summary = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "peer_summaries": [
            {
                "peer_name": peer_name,
                "evidence_count": len(rows),
                "latest_classification": rows[-1]["classification"] if rows else "no_equivocation_evidence",
            }
            for peer_name, rows in sorted(_PEER_EQUIVOCATION_EVIDENCE.items())
        ],
    }
    (root / "equivocation_summary.json").write_text(
        json.dumps(equivocation_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def configure(*, enabled: bool, peers: Iterable[object] | None = None) -> None:
    """Configure federation state and subscriptions for the pulse bus."""

    global _ENABLED, _PEER_MAP

    _ENABLED = bool(enabled)
    normalized: dict[str, _Peer] = {}
    if peers is not None:
        for entry in peers:
            peer = _normalize_peer(entry)
            if peer is None:
                continue
            normalized[peer.name] = peer
    _PEER_MAP = normalized
    _PEER_PROTOCOL_POSTURE.clear()
    _load_peer_keys()
    get_federated_governance_controller().set_trusted_peers(set(_PEER_MAP.keys()))
    _update_subscription()
    _write_protocol_posture()


def reset() -> None:
    """Disable federation support and drop cached peer state."""

    global _ENABLED, _PEER_MAP, _PEER_KEYS, _SUBSCRIPTION

    _ENABLED = False
    _PEER_MAP = {}
    _PEER_KEYS = {}
    get_federated_governance_controller().set_trusted_peers(set())
    _SEEN_EVENT_HASHES.clear()
    _SEEN_EVENT_ORDER.clear()
    _PEER_PROTOCOL_POSTURE.clear()
    _PEER_CLAIM_WINDOWS.clear()
    _PEER_EQUIVOCATION_EVIDENCE.clear()
    if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
        _SUBSCRIPTION.unsubscribe()
    _SUBSCRIPTION = None


def is_enabled() -> bool:
    """Return whether federation support is currently enabled."""

    return _ENABLED and bool(_PEER_MAP)


def peers() -> Sequence[str]:
    """Return the configured federation peer names."""

    return tuple(_PEER_MAP.keys())


def verify_remote_signature(event: pulse_bus.PulseEvent, peer_name: str) -> bool:
    """Return ``True`` when ``event`` is signed by ``peer_name``."""

    key = _PEER_KEYS.get(peer_name)
    if key is None:
        return False
    signature = event.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    payload = pulse_bus._serialize_for_signature(event)
    result = get_trust_epoch_manager().classify_epoch(
        event,
        actor="pulse_federation",
        peer_name=peer_name,
    )
    if not result.trusted:
        get_trust_ledger().record_epoch_classification(
            peer_name,
            classification=result.classification,
            actor="pulse_federation_signature",
        )
        if resolve_policy().pulse_trust_epoch == "enforce":
            return False
    peer_epoch = event.get("pulse_epoch_id")
    if isinstance(peer_epoch, str) and peer_epoch and peer_epoch not in {"legacy", result.active_epoch_id} and resolve_policy().pulse_trust_epoch == "enforce":
        return False
    try:
        key.verify(payload, base64.b64decode(signature))
        return True
    except (BadSignatureError, binascii.Error, ValueError):
        return False


def ingest_remote_event(event: pulse_bus.PulseEvent, peer_name: str) -> pulse_bus.PulseEvent:
    """Validate and ingest ``event`` from ``peer_name`` into the local bus."""

    if not _ENABLED:
        raise RuntimeError("Pulse federation is disabled")
    peer = _PEER_MAP.get(peer_name)
    if peer is None:
        raise ValueError(f"Unknown federation peer: {peer_name}")
    correlation_id = str(event.get("correlation_id") or pulse_bus.compute_event_hash(event))
    if not verify_remote_signature(event, peer_name):
        pulse_bus.ingest_untrusted(
            event,
            source_peer=peer_name,
            reason="invalid_federated_signature",
            classification="reject",
        )
        _record_federation_ingest(
            peer_name=peer_name,
            event=event,
            classification="rejected_signature",
            decision="deny",
            reason="invalid_federated_signature",
            correlation_id=correlation_id,
        )
        raise ValueError(f"Invalid signature from federation peer: {peer_name}")
    trust = get_trust_epoch_manager().classify_epoch(
        event,
        actor="pulse_federation_ingest",
        peer_name=peer_name,
    )
    payload = copy.deepcopy(event)
    event_payload = payload.get("payload")
    payload_action = ""
    if isinstance(event_payload, dict):
        payload_action = str(event_payload.get("action") or "").lower()
    requires_control_gate = payload_action == "restart_daemon"

    if not trust.trusted:
        get_trust_ledger().record_epoch_classification(
            peer_name,
            classification=trust.classification,
            actor="pulse_federation_ingest",
        )
        if requires_control_gate:
            decision = get_runtime_governor().admit_action(
                "federated_control",
                peer_name,
                str(event.get("correlation_id") or pulse_bus.compute_event_hash(event)),
                metadata={
                    "subject": f"{peer_name}:epoch",
                    "scope": "federated",
                    "event_type": str(event.get("event_type", "")),
                    "trust_epoch_classification": trust.classification,
                    "trust_epoch_id": trust.epoch_id,
                },
            )
            if resolve_policy().pulse_trust_epoch == "enforce" and not decision.allowed:
                _record_federation_ingest(
                    peer_name=peer_name,
                    event=event,
                    classification="rejected_epoch",
                    decision="deny",
                    reason=f"epoch:{trust.classification}",
                    correlation_id=correlation_id,
                )
                raise ValueError(f"Federated epoch denied for {peer_name}: {trust.classification}")
    protocol_claim = payload.get("pulse_protocol")
    protocol_compatibility, protocol_reasons, local_protocol = _classify_protocol_compatibility(
        protocol_claim if isinstance(protocol_claim, Mapping) else None
    )
    replay_classification, replay_detail = _classify_replay_horizon(
        payload,
        protocol_claim if isinstance(protocol_claim, Mapping) else None,
    )
    equivocation_classification, equivocation_rows = _classify_equivocation(
        peer_name=peer_name,
        event=payload,
        protocol_claim=protocol_claim if isinstance(protocol_claim, Mapping) else None,
    )
    _PEER_PROTOCOL_POSTURE[peer_name] = {
        "peer_name": peer_name,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "protocol_compatibility": protocol_compatibility,
        "protocol_reasons": protocol_reasons,
        "replay_horizon_classification": replay_classification,
        "replay_horizon_detail": replay_detail,
        "equivocation_classification": equivocation_classification,
        "equivocation_evidence_count": len(equivocation_rows),
        "peer_protocol_identity": dict(protocol_claim) if isinstance(protocol_claim, Mapping) else {},
        "local_protocol_identity": local_protocol,
    }
    _write_protocol_posture()
    if protocol_compatibility == "incompatible_protocol":
        _record_federation_ingest(
            peer_name=peer_name,
            event=payload,
            classification="denied_protocol_incompatibility",
            decision="deny",
            reason=f"protocol:{','.join(protocol_reasons) or 'incompatible'}",
            correlation_id=correlation_id,
        )
        raise ValueError(f"Federated protocol incompatible for {peer_name}")
    if replay_classification in {"incompatible_replay_policy", "peer_too_stale_for_replay_horizon"}:
        _record_federation_ingest(
            peer_name=peer_name,
            event=payload,
            classification="denied_replay_horizon",
            decision="deny",
            reason=f"replay:{replay_classification}",
            correlation_id=correlation_id,
        )
        raise ValueError(f"Federated replay policy/horizon denied for {peer_name}: {replay_classification}")
    if replay_classification == "peer_outside_accepted_replay_horizon":
        _record_federation_ingest(
            peer_name=peer_name,
            event=payload,
            classification="dropped_historical_signed",
            decision="drop",
            reason="signed_but_outside_control_horizon",
            correlation_id=correlation_id,
        )
        return payload
    if equivocation_classification in {
        "confirmed_equivocation",
        "protocol_claim_conflict",
        "replay_claim_conflict",
    }:
        _record_federation_ingest(
            peer_name=peer_name,
            event=payload,
            classification="denied_equivocation",
            decision="deny",
            reason=f"equivocation:{equivocation_classification}",
            correlation_id=correlation_id,
        )
        get_trust_ledger().record_control_attempt(
            peer_name,
            allowed=False,
            reason=f"equivocation:{equivocation_classification}",
            actor="pulse_federation_ingest",
        )
        raise ValueError(f"Federated equivocation denied for {peer_name}: {equivocation_classification}")
    payload["federation_protocol_posture"] = {
        "protocol_compatibility": protocol_compatibility,
        "protocol_reasons": list(protocol_reasons),
        "replay_horizon_classification": replay_classification,
        "replay_horizon_detail": dict(replay_detail),
        "equivocation_classification": equivocation_classification,
    }
    governance = get_federated_governance_controller()
    evaluation = governance.evaluate_peer_event(peer_name, payload)
    trust_ledger = get_trust_ledger()
    if evaluation.denial_cause in {
        "digest_mismatch",
        "digest_mismatch_advisory",
        "digest_mismatch_observed",
        "quorum_failure",
        "quorum_warning",
        "quorum_observed",
        "trust_epoch",
        "trust_epoch_advisory",
        "trust_epoch_observed",
    }:
        decision = get_runtime_governor().admit_action(
            "federated_control",
            peer_name,
            str(payload.get("correlation_id") or pulse_bus.compute_event_hash(payload)),
                metadata={
                    "subject": f"{peer_name}:federation",
                    "scope": "federated",
                    "event_type": str(payload.get("event_type", "")),
                    "federated_governance": evaluation.to_dict(),
                    "federated_denial_cause": evaluation.denial_cause,
                    "protocol_compatibility": protocol_compatibility,
                    "replay_horizon_classification": replay_classification,
                    "equivocation_classification": equivocation_classification,
                },
            )
        if not decision.allowed or evaluation.calibration_action == "deny":
            trust_ledger.record_control_attempt(
                peer_name,
                allowed=False,
                reason=f"{evaluation.denial_cause}/{decision.reason}",
                actor="pulse_federation_ingest",
            )
            _record_federation_ingest(
                peer_name=peer_name,
                event=payload,
                classification="denied_governance",
                decision="deny",
                reason=f"{evaluation.denial_cause}/{decision.reason}",
                correlation_id=correlation_id,
            )
            raise ValueError(
                f"Federated action denied for {peer_name}: "
                f"{evaluation.denial_cause}/{decision.reason}"
            )
    candidate_hash = str(payload.get("event_hash") or pulse_bus.compute_event_hash(payload))
    correlation_id = str(payload.get("correlation_id") or candidate_hash)
    if _is_duplicate_event_hash(candidate_hash):
        logger.info("Suppressed duplicate federated pulse event hash=%s peer=%s", candidate_hash, peer_name)
        trust_ledger.record_replay_signal(peer_name, actor="pulse_federation_ingest", event_hash=candidate_hash)
        _record_federation_ingest(
            peer_name=peer_name,
            event=payload,
            classification="suppressed_replay",
            decision="drop",
            reason="duplicate_event_hash",
            correlation_id=correlation_id,
        )
        return payload
    if isinstance(event_payload, dict):
        action = str(event_payload.get("action", "")).lower()
        if action == "restart_daemon":
            daemon_subject = str(
                event_payload.get("daemon")
                or event_payload.get("daemon_name")
                or event_payload.get("target")
                or "unknown"
            )
            decision = get_runtime_governor().admit_action(
                "federated_control",
                peer_name,
                correlation_id,
                metadata={
                    "subject": daemon_subject,
                    "peer_name": peer_name,
                    "federated_source": f"{peer_name}:{daemon_subject}",
                    "peer_subject": f"{peer_name}:{daemon_subject}",
                    "event_type": str(payload.get("event_type", "")),
                    "scope": "federated",
                    "federated_governance": evaluation.to_dict(),
                    "federated_denial_cause": evaluation.denial_cause,
                    "protocol_compatibility": protocol_compatibility,
                    "replay_horizon_classification": replay_classification,
                    "equivocation_classification": equivocation_classification,
                },
            )
            if not decision.allowed:
                trust_ledger.record_control_attempt(
                    peer_name,
                    allowed=False,
                    reason=decision.reason,
                    actor="pulse_federation_ingest",
                )
                _record_federation_ingest(
                    peer_name=peer_name,
                    event=payload,
                    classification="denied_governor",
                    decision="deny",
                    reason=decision.reason,
                    correlation_id=correlation_id,
                )
                raise ValueError(
                    f"Runtime governor denied federated control event from {peer_name}: {decision.reason}"
                )
    ingested = pulse_bus.ingest_verified(payload, source_peer=peer_name)
    get_runtime_governor().observe_pulse_event(ingested)
    trust_ledger.record_control_attempt(
        peer_name,
        allowed=True,
        reason="ingested",
        actor="pulse_federation_ingest",
    )
    _record_federation_ingest(
        peer_name=peer_name,
        event=ingested,
        classification="accepted_verified",
        decision="allow",
        reason=f"verified_ingest/{protocol_compatibility}/{replay_classification}/{equivocation_classification}",
        correlation_id=correlation_id,
    )
    _remember_event_hash(candidate_hash)
    return ingested


def _is_duplicate_event_hash(event_hash: str) -> bool:
    return bool(event_hash) and event_hash in _SEEN_EVENT_HASHES


def _remember_event_hash(event_hash: str) -> None:
    if not event_hash or event_hash in _SEEN_EVENT_HASHES:
        return
    _SEEN_EVENT_HASHES.add(event_hash)
    _SEEN_EVENT_ORDER.append(event_hash)
    while len(_SEEN_EVENT_ORDER) > max(_REPLAY_CACHE_LIMIT, 128):
        old = _SEEN_EVENT_ORDER.popleft()
        _SEEN_EVENT_HASHES.discard(old)


def _record_federation_ingest(
    *,
    peer_name: str,
    event: pulse_bus.PulseEvent,
    classification: str,
    decision: str,
    reason: str,
    correlation_id: str,
) -> None:
    runtime_root = _federation_runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)
    event_hash = str(event.get("event_hash") or pulse_bus.compute_event_hash(event))
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "peer_name": peer_name,
        "classification": classification,
        "decision": decision,
        "reason": reason,
        "event_hash": event_hash,
        "event_type": str(event.get("event_type", "")),
        "correlation_id": correlation_id or event_hash,
    }
    with (runtime_root / "ingest_classifications.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def request_recent_events(minutes: int) -> List[pulse_bus.PulseEvent]:
    """Request recent pulse history from all peers and ingest new events."""

    if not is_enabled():
        return []
    collected: List[pulse_bus.PulseEvent] = []
    for peer in _PEER_MAP.values():
        endpoint = peer.api_base()
        if not endpoint:
            continue
        try:
            response = _http_get(
                f"{endpoint}{_FEDERATION_ENDPOINT}",
                params={"minutes": minutes},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:  # pragma: no cover - network failures best-effort
            logger.warning("Failed to request pulse replay from peer %s", peer.name, exc_info=True)
            continue
        for event in _extract_events(response):
            try:
                ingested = ingest_remote_event(event, peer.name)
            except ValueError:
                logger.warning(
                    "Rejected invalid federated event from peer %s", peer.name, exc_info=True
                )
                continue
            collected.append(ingested)
    return collected


def _load_peer_keys() -> None:
    global _PEER_KEYS

    directory = _keys_dir()
    _PEER_KEYS = {}
    if not directory.exists():
        return
    for peer in _PEER_MAP.values():
        key_path = directory / f"{peer.name}.pub"
        try:
            key_bytes = key_path.read_bytes()
        except FileNotFoundError:
            logger.warning("Federation verify key missing for peer %s at %s", peer.name, key_path)
            continue
        try:
            _PEER_KEYS[peer.name] = VerifyKey(key_bytes)
        except Exception as exc:
            logger.warning("Unable to load federation key for %s: %s", peer.name, exc)


def _update_subscription() -> None:
    global _SUBSCRIPTION

    if not is_enabled():
        if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
            _SUBSCRIPTION.unsubscribe()
        _SUBSCRIPTION = None
        return
    if _SUBSCRIPTION is not None and _SUBSCRIPTION.active:
        return
    _SUBSCRIPTION = pulse_bus.subscribe(_handle_local_publish)


def _handle_local_publish(event: pulse_bus.PulseEvent) -> None:
    if not _ENABLED or not _PEER_MAP:
        return
    if str(event.get("source_peer", "local")) != "local":
        return
    if not _payload_is_safe(event):
        logger.warning("Skipping privileged pulse event; payload not federated")
        return
    outbound = copy.deepcopy(event)
    outbound["pulse_protocol"] = _local_protocol_identity()

    for peer in _PEER_MAP.values():
        endpoint = peer.api_base()
        if not endpoint:
            continue
        try:
            _http_post(
                f"{endpoint}{_FEDERATION_ENDPOINT}",
                json=outbound,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:  # pragma: no cover - network failures best-effort
            logger.warning("Failed to forward pulse event to peer %s", peer.name, exc_info=True)


def _payload_is_safe(event: pulse_bus.PulseEvent) -> bool:
    try:
        payload = json.dumps(event, sort_keys=True)
    except (TypeError, ValueError):
        return False
    lowered = payload.lower()
    return "/vow" not in lowered and "newlegacy" not in lowered


def _extract_events(response: object) -> List[pulse_bus.PulseEvent]:
    if response is None:
        return []
    if isinstance(response, list):
        raw = response
    elif hasattr(response, "json") and callable(response.json):
        try:
            raw = response.json()
        except Exception:
            logger.warning("Failed to decode federated replay payload", exc_info=True)
            return []
    else:
        return []
    events: List[pulse_bus.PulseEvent] = []
    for item in raw:
        if isinstance(item, dict):
            events.append(copy.deepcopy(item))
    return events


def _http_post(url: str, *, json: pulse_bus.PulseEvent, timeout: int) -> None:
    requests.post(url, json=json, timeout=timeout)


def _http_get(
    url: str, *, params: Mapping[str, object], timeout: int
) -> requests.Response:
    return requests.get(
        url,
        params=cast(Mapping[str, Any], params),
        timeout=timeout,
    )


__all__ = [
    "configure",
    "reset",
    "is_enabled",
    "peers",
    "verify_remote_signature",
    "ingest_remote_event",
    "request_recent_events",
]
