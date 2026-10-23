"""Local semantic review boundary for durably replayed federation peer events.

Authentication and replay establish provenance and ordering. This module applies a
separately pinned local policy to two bounded event shapes and emits only a
review-eligibility receipt. It does not establish truth, resolve remote evidence,
write canonical evidence, admit work, publish Health, plan, or execute.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping, TypeGuard

from .peer_authentication import VerifiedFederationPeerEvent
from .peer_replay_owner import FederationPeerReplayAcceptance

SEMANTIC_POLICY_SCHEMA = "sentientos.federation.peer_semantic_policy:v1"
CLAIM_EVIDENCE_SCHEMA = "sentientos.federation.peer_claim_evidence:v1"
TRIAL_OUTCOME_SCHEMA = "sentientos.federation.peer_trial_outcome:v1"
SEMANTIC_RECEIPT_SCHEMA = "sentientos.federation.peer_semantic_review_receipt:v1"
SUPPORTED_EVENT_SCHEMAS = frozenset({CLAIM_EVIDENCE_SCHEMA, TRIAL_OUTCOME_SCHEMA})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PEER_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_EVIDENCE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_MAX_POLICY_BYTES = 262_144
_MAX_PEERS = 4096
_MAX_EVIDENCE_REFS = 32
_CLAIM_STATUSES = frozenset({"supported", "refuted", "uncertain", "unknown"})
_TRIAL_OUTCOMES = frozenset({"positive", "adverse", "mixed", "inconclusive"})


class FederationPeerSemanticAcceptanceError(ValueError):
    """A malformed local semantic policy or replay provenance value."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise FederationPeerSemanticAcceptanceError("semantic_policy_content_invalid") from exc


def semantic_policy_digest_for(value: Mapping[str, object]) -> str:
    """Hash a semantic policy body, excluding only its derived policy digest."""
    body = dict(value)
    body.pop("policy_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise FederationPeerSemanticAcceptanceError("semantic_policy_nonfinite_number")


@dataclass(frozen=True, slots=True, init=False)
class FederationPeerSemanticAcceptancePolicy:
    """Read-only peer/schema allowlist created only from locally pinned bytes."""

    policy_version: int
    policy_digest: str
    _rules: Mapping[str, frozenset[str]]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("semantic policies must be created from locally pinned canonical bytes")

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        *,
        expected_policy_version: int,
        expected_policy_digest: str,
    ) -> FederationPeerSemanticAcceptancePolicy:
        if type(expected_policy_version) is not int or expected_policy_version < 1:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_expected_version_invalid")
        if (not isinstance(expected_policy_digest, str)
                or _DIGEST.fullmatch(expected_policy_digest) is None):
            raise FederationPeerSemanticAcceptanceError("semantic_policy_expected_digest_invalid")
        if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_POLICY_BYTES:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_size_invalid")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except FederationPeerSemanticAcceptanceError:
            raise
        except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_load_failed") from exc
        expected_fields = {"schema", "policy_version", "peers", "policy_digest"}
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_fields_invalid")
        if value.get("schema") != SEMANTIC_POLICY_SCHEMA:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_schema_invalid")
        version = value.get("policy_version")
        if type(version) is not int or version != expected_policy_version:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_version_mismatch")
        computed = semantic_policy_digest_for(value)
        canonical = _canonical(value)
        if (value.get("policy_digest") != computed
                or computed != expected_policy_digest):
            raise FederationPeerSemanticAcceptanceError("semantic_policy_digest_mismatch")
        if canonical != raw:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_not_canonical")
        peers = value.get("peers")
        if not isinstance(peers, list) or len(peers) > _MAX_PEERS:
            raise FederationPeerSemanticAcceptanceError("semantic_policy_peers_invalid")
        rules: dict[str, frozenset[str]] = {}
        for row in peers:
            if not isinstance(row, dict) or set(row) != {"peer_id", "accepted_event_schemas"}:
                raise FederationPeerSemanticAcceptanceError("semantic_policy_peer_fields_invalid")
            peer_id = row.get("peer_id")
            schemas = row.get("accepted_event_schemas")
            if not isinstance(peer_id, str) or _PEER_ID.fullmatch(peer_id) is None:
                raise FederationPeerSemanticAcceptanceError("semantic_policy_peer_id_invalid")
            if peer_id in rules:
                raise FederationPeerSemanticAcceptanceError("semantic_policy_peer_duplicate")
            if (not isinstance(schemas, list) or len(schemas) > len(SUPPORTED_EVENT_SCHEMAS)
                    or any(not isinstance(item, str) or item not in SUPPORTED_EVENT_SCHEMAS
                           for item in schemas)
                    or len(set(schemas)) != len(schemas)):
                raise FederationPeerSemanticAcceptanceError("semantic_policy_schemas_invalid")
            rules[peer_id] = frozenset(schemas)
        policy = object.__new__(cls)
        object.__setattr__(policy, "policy_version", version)
        object.__setattr__(policy, "policy_digest", computed)
        object.__setattr__(policy, "_rules", MappingProxyType(rules))
        return policy

    def allows(self, *, peer_id: str, event_schema: str) -> bool:
        """Return true only for an exact locally pinned peer/schema pair."""
        return event_schema in self._rules.get(peer_id, frozenset())


@dataclass(frozen=True, slots=True)
class FederationPeerSemanticAcceptanceReceipt:
    """Bounded interpretation receipt; acceptance grants local review eligibility only."""

    schema: str
    decision: str
    reason_code: str
    peer_id: str
    signing_key_id: str
    endpoint: str
    sequence: int
    replay_record_digest: str
    event_digest: str
    catalog_version: int
    catalog_digest: str
    policy_version: int
    policy_digest: str
    event_schema: str | None = None
    semantic_kind: str | None = None
    submitted_claim: str | None = None
    experiment_id: str | None = None
    submitted_epistemic_status: str | None = None
    submitted_outcome: str | None = None
    submitted_summary: str | None = None
    remote_evidence_refs: tuple[str, ...] = ()
    local_review_only: bool = True
    remote_evidence_resolved_locally: bool = False
    claim_truth_established: bool = False
    canonical_evidence_admitted: bool = False
    health_publication_permitted: bool = False
    work_admission_permitted: bool = False
    planning_permitted: bool = False
    execution_permitted: bool = False
    decision_power: str = "none"


def _is_bounded_text(value: object, *, maximum: int) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and value == value.strip()
        and not any(ord(char) < 32 and char not in "\n\t" for char in value)
    )


def _evidence_refs(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) > _MAX_EVIDENCE_REFS:
        return None
    if any(not isinstance(item, str) or _EVIDENCE_REF.fullmatch(item) is None for item in value):
        return None
    refs = tuple(value)
    if len(set(refs)) != len(refs):
        return None
    return refs


def _provenance(
    replay: FederationPeerReplayAcceptance,
) -> tuple[VerifiedFederationPeerEvent, str]:
    if not isinstance(replay, FederationPeerReplayAcceptance):
        raise FederationPeerSemanticAcceptanceError("semantic_replay_receipt_required")
    event = replay.verified_event
    if not isinstance(event, VerifiedFederationPeerEvent):
        raise FederationPeerSemanticAcceptanceError("semantic_verified_event_required")
    if (type(replay.sequence) is not int or replay.sequence < 1
            or replay.sequence != event.sequence or type(replay.created) is not bool
            or not isinstance(replay.record_digest, str)
            or _DIGEST.fullmatch(replay.record_digest) is None
            or not isinstance(event.peer_id, str) or _PEER_ID.fullmatch(event.peer_id) is None
            or not isinstance(event.signing_key_id, str) or not event.signing_key_id
            or not isinstance(event.endpoint, str) or not event.endpoint
            or type(event.catalog_version) is not int or event.catalog_version < 1
            or not isinstance(event.catalog_digest, str) or _DIGEST.fullmatch(event.catalog_digest) is None
            or not isinstance(event.event_digest, str) or _DIGEST.fullmatch(event.event_digest) is None
            or not isinstance(event.event, Mapping)):
        raise FederationPeerSemanticAcceptanceError("semantic_replay_provenance_invalid")
    return event, replay.record_digest


def _receipt(
    *,
    decision: str,
    reason: str,
    event: VerifiedFederationPeerEvent,
    record_digest: str,
    policy: FederationPeerSemanticAcceptancePolicy,
    event_schema: str | None = None,
    semantic_kind: str | None = None,
    claim: str | None = None,
    experiment_id: str | None = None,
    epistemic_status: str | None = None,
    outcome: str | None = None,
    summary: str | None = None,
    refs: tuple[str, ...] = (),
) -> FederationPeerSemanticAcceptanceReceipt:
    return FederationPeerSemanticAcceptanceReceipt(
        schema=SEMANTIC_RECEIPT_SCHEMA,
        decision=decision,
        reason_code=reason,
        peer_id=event.peer_id,
        signing_key_id=event.signing_key_id,
        endpoint=event.endpoint,
        sequence=event.sequence,
        replay_record_digest=record_digest,
        event_digest=event.event_digest,
        catalog_version=event.catalog_version,
        catalog_digest=event.catalog_digest,
        policy_version=policy.policy_version,
        policy_digest=policy.policy_digest,
        event_schema=event_schema,
        semantic_kind=semantic_kind,
        submitted_claim=claim,
        experiment_id=experiment_id,
        submitted_epistemic_status=epistemic_status,
        submitted_outcome=outcome,
        submitted_summary=summary,
        remote_evidence_refs=refs,
    )


def accept_peer_event_for_local_review(
    replay: FederationPeerReplayAcceptance,
    *,
    policy: FederationPeerSemanticAcceptancePolicy,
) -> FederationPeerSemanticAcceptanceReceipt:
    """Classify a durably replayed event under a separate local semantic policy.

    A successful result means only that a recognized, locally permitted shape
    may be offered for local review. Remote references remain unresolved and
    remote classifications remain submitter claims.
    """
    if not isinstance(policy, FederationPeerSemanticAcceptancePolicy):
        raise FederationPeerSemanticAcceptanceError("semantic_policy_required")
    event, record_digest = _provenance(replay)
    payload = event.event
    event_schema = payload.get("schema")
    if not isinstance(event_schema, str):
        return _receipt(
            decision="rejected", reason="semantic_event_schema_missing",
            event=event, record_digest=record_digest, policy=policy,
        )
    if not policy.allows(peer_id=event.peer_id, event_schema=event_schema):
        return _receipt(
            decision="rejected", reason="semantic_peer_or_schema_not_permitted",
            event=event, record_digest=record_digest, policy=policy,
            event_schema=event_schema,
        )
    if event_schema == CLAIM_EVIDENCE_SCHEMA:
        if set(payload) != {"schema", "claim", "epistemic_status", "evidence_refs"}:
            return _receipt(
                decision="rejected", reason="semantic_claim_fields_invalid",
                event=event, record_digest=record_digest, policy=policy,
                event_schema=event_schema,
            )
        claim = payload.get("claim")
        status = payload.get("epistemic_status")
        refs = _evidence_refs(payload.get("evidence_refs"))
        if (not _is_bounded_text(claim, maximum=8192)
                or not isinstance(status, str) or status not in _CLAIM_STATUSES
                or refs is None):
            return _receipt(
                decision="rejected", reason="semantic_claim_content_invalid",
                event=event, record_digest=record_digest, policy=policy,
                event_schema=event_schema,
            )
        return _receipt(
            decision="accepted_for_local_review", reason="semantic_claim_review_eligible",
            event=event, record_digest=record_digest, policy=policy,
            event_schema=event_schema, semantic_kind="claim_evidence",
            claim=claim, epistemic_status=status, refs=refs,
        )
    if event_schema == TRIAL_OUTCOME_SCHEMA:
        if set(payload) != {"schema", "experiment_id", "outcome", "summary", "evidence_refs"}:
            return _receipt(
                decision="rejected", reason="semantic_outcome_fields_invalid",
                event=event, record_digest=record_digest, policy=policy,
                event_schema=event_schema,
            )
        experiment_id = payload.get("experiment_id")
        outcome = payload.get("outcome")
        summary = payload.get("summary")
        refs = _evidence_refs(payload.get("evidence_refs"))
        if (not isinstance(experiment_id, str) or _PEER_ID.fullmatch(experiment_id) is None
                or not isinstance(outcome, str) or outcome not in _TRIAL_OUTCOMES
                or not _is_bounded_text(summary, maximum=4096)
                or refs is None):
            return _receipt(
                decision="rejected", reason="semantic_outcome_content_invalid",
                event=event, record_digest=record_digest, policy=policy,
                event_schema=event_schema,
            )
        return _receipt(
            decision="accepted_for_local_review", reason="semantic_outcome_review_eligible",
            event=event, record_digest=record_digest, policy=policy,
            event_schema=event_schema, semantic_kind="trial_outcome",
            experiment_id=experiment_id, outcome=outcome, summary=summary, refs=refs,
        )
    return _receipt(
        decision="rejected", reason="semantic_event_schema_unsupported",
        event=event, record_digest=record_digest, policy=policy,
        event_schema=event_schema,
    )


__all__ = [
    "CLAIM_EVIDENCE_SCHEMA",
    "FederationPeerSemanticAcceptanceError",
    "FederationPeerSemanticAcceptancePolicy",
    "FederationPeerSemanticAcceptanceReceipt",
    "SEMANTIC_POLICY_SCHEMA",
    "SEMANTIC_RECEIPT_SCHEMA",
    "SUPPORTED_EVENT_SCHEMAS",
    "TRIAL_OUTCOME_SCHEMA",
    "accept_peer_event_for_local_review",
    "semantic_policy_digest_for",
]
