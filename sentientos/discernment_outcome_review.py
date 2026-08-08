from __future__ import annotations

"""Append-only, non-authoritative prospective judgment evaluation artifacts."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sentientos.discernment_synthesis import compare_packets, validate_packet

COMMITMENT_SCHEMA = "sentientos.discernment_commitment.v1"
OUTCOME_SCHEMA = "sentientos.discernment_outcome_evidence.v1"
REVIEW_SCHEMA = "sentientos.discernment_outcome_review.v1"
LONGITUDINAL_SCHEMA = "sentientos.discernment_longitudinal_review.v1"
STANCES = frozenset({"support", "oppose", "suspend"})
CLASSIFICATIONS = frozenset({"supported", "contradicted", "mixed", "indeterminate", "not_yet_observable"})
AUTHORITY_POSTURE = {key: False for key in (
    "executes", "modifies_memory", "modifies_goals", "invokes_maintenance", "creates_commits",
    "publishes", "grants_authority", "mutates_source_artifacts",
)}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item) for item in value]
    return value


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def _seal(payload: dict[str, Any], digest_field: str, id_prefix: str) -> dict[str, Any]:
    payload[digest_field] = _digest(payload)
    payload["artifact_id"] = id_prefix + payload[digest_field][:24]
    return payload


def _validate(artifact: Mapping[str, Any], schema: str, digest_field: str, id_prefix: str) -> None:
    body = dict(artifact)
    artifact_id = body.pop("artifact_id", None)
    claimed = body.pop(digest_field, None)
    if artifact.get("schema_version") != schema or claimed != _digest(body) or artifact_id != id_prefix + str(claimed)[:24]:
        raise ValueError(f"{schema} digest mismatch")
    if artifact.get("authority_posture") != AUTHORITY_POSTURE:
        raise ValueError("forbidden or incomplete authority posture")


def create_commitment(
    packet: Mapping[str, Any], *, committed_at: str, decision_class: str, proposition: str,
    stance: str, confidence: float | None = None, expected_observations: Sequence[str] = (),
    disconfirming_observations: Sequence[str] = (), predicted_consequences: Sequence[str] = (),
    evaluation_horizon: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze packet-derived facts and only caller-supplied concrete forecasts."""
    validate_packet(packet)
    if stance not in STANCES:
        raise ValueError("stance must be support, oppose, or suspend")
    if not decision_class or not proposition:
        raise ValueError("decision class and proposition are required")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between zero and one")
    if stance == "suspend" and confidence is not None:
        raise ValueError("suspended commitments do not require a forced confidence")
    if _timestamp(committed_at) < _timestamp(packet["observed_at"]):
        raise ValueError("commitment cannot predate its packet evidence snapshot")
    rows = cast(Sequence[Mapping[str, Any]], packet.get("surface_contributions", ()))
    payload = {
        "schema_version": COMMITMENT_SCHEMA, "subject_id": packet["subject_id"],
        "source_discernment_packet_digest": packet["packet_digest"], "committed_at": committed_at,
        "decision_class": decision_class, "proposition": proposition, "stance": stance,
        "confidence": confidence, "evidence_available_at_commitment": list(packet["observations_and_evidence"]),
        "evidence_snapshot_digest": _digest({"evidence": packet["observations_and_evidence"], "packet_digest": packet["packet_digest"]}),
        "unresolved_contradictions": list(packet["unresolved_contradictions"]),
        "missing_evidence": sorted({str(item) for row in rows for item in row.get("missing_evidence", ())}),
        "strongest_objection": packet.get("strongest_objection"),
        "what_would_change_judgment": list(packet["what_would_change_judgment"]),
        "expected_observations": list(expected_observations),
        "disconfirming_observations": list(disconfirming_observations),
        "predicted_consequences": list(predicted_consequences),
        "preferred_next_move": packet.get("preferred_next_move"),
        "rejected_next_moves": list(packet["rejected_next_moves"]),
        "evaluation_horizon": _plain(evaluation_horizon or {}),
        "contributing_judgment_surfaces": [row.get("surface_id") for row in rows],
        "component_model_provenance": [{"surface_id": row.get("surface_id"), "source_kind": row.get("source_kind"),
            "component": row.get("component"), "component_version": row.get("component_version"),
            "provenance": _plain(row.get("provenance", {}))} for row in rows],
        "authority_posture": dict(AUTHORITY_POSTURE), "non_authoritative": True,
    }
    return _seal(payload, "commitment_digest", "commitment-")


def validate_commitment(value: Mapping[str, Any]) -> None:
    _validate(value, COMMITMENT_SCHEMA, "commitment_digest", "commitment-")


def create_outcome_evidence(
    commitment: Mapping[str, Any], *, observed_at: str, evidence_references: Sequence[Mapping[str, Any]],
    evidence_provenance: Sequence[Mapping[str, Any]], observed_facts: Sequence[str],
    expected_observations_witnessed: Sequence[str] = (), disconfirming_observations_witnessed: Sequence[str] = (),
    unresolved_or_ambiguous_evidence: Sequence[str] = (), evaluation_horizon_elapsed: bool,
    change_conditions_witnessed: Sequence[str] = (), later_discernment_packet: Mapping[str, Any] | None = None,
    rejected_move_assessments: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    validate_commitment(commitment)
    if _timestamp(observed_at) <= _timestamp(commitment["committed_at"]):
        raise ValueError("outcome evidence must be observed after the prospective commitment")
    expected = set(commitment["expected_observations"])
    disconfirming = set(commitment["disconfirming_observations"])
    changes = set(commitment["what_would_change_judgment"])
    if not set(expected_observations_witnessed) <= expected or not set(disconfirming_observations_witnessed) <= disconfirming:
        raise ValueError("witnessed observation must have been prospectively declared")
    if not set(change_conditions_witnessed) <= changes:
        raise ValueError("witnessed change condition must have been prospectively declared")
    move_assessments = dict(rejected_move_assessments or {})
    if not set(move_assessments) <= set(commitment["rejected_next_moves"]) or not set(move_assessments.values()) <= {"vindicated", "undermined"}:
        raise ValueError("rejected move assessments must bind declared moves and use a supported result")
    later_digest = None
    if later_discernment_packet is not None:
        validate_packet(later_discernment_packet)
        if later_discernment_packet["subject_id"] != commitment["subject_id"]:
            raise ValueError("later packet subject does not match commitment")
        later_digest = later_discernment_packet["packet_digest"]
    payload = {
        "schema_version": OUTCOME_SCHEMA, "commitment_digest": commitment["commitment_digest"],
        "observed_at": observed_at, "evidence_references": _plain(evidence_references),
        "evidence_provenance": _plain(evidence_provenance), "observed_facts": list(observed_facts),
        "expected_observations_witnessed": list(expected_observations_witnessed),
        "disconfirming_observations_witnessed": list(disconfirming_observations_witnessed),
        "unresolved_or_ambiguous_evidence": list(unresolved_or_ambiguous_evidence),
        "evaluation_horizon_elapsed": evaluation_horizon_elapsed,
        "change_conditions_witnessed": list(change_conditions_witnessed),
        "rejected_move_assessments": move_assessments,
        "later_discernment_packet_digest": later_digest,
        "truth_scope": "bounded_observations_not_universal_truth", "authority_posture": dict(AUTHORITY_POSTURE),
        "non_authoritative": True,
    }
    return _seal(payload, "outcome_evidence_digest", "outcome-")


def validate_outcome_evidence(value: Mapping[str, Any]) -> None:
    _validate(value, OUTCOME_SCHEMA, "outcome_evidence_digest", "outcome-")


def _classification(commitment: Mapping[str, Any], outcome: Mapping[str, Any]) -> str:
    expected = bool(outcome["expected_observations_witnessed"])
    disconfirming = bool(outcome["disconfirming_observations_witnessed"])
    ambiguous = bool(outcome["unresolved_or_ambiguous_evidence"])
    if expected and disconfirming:
        return "mixed"
    if disconfirming:
        return "contradicted"
    if expected and not ambiguous:
        return "supported"
    if not outcome["evaluation_horizon_elapsed"]:
        return "not_yet_observable"
    return "indeterminate"


def create_review(commitment: Mapping[str, Any], outcome: Mapping[str, Any], *,
                  source_packet: Mapping[str, Any] | None = None,
                  later_packet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validate_commitment(commitment); validate_outcome_evidence(outcome)
    if outcome["commitment_digest"] != commitment["commitment_digest"]:
        raise ValueError("outcome does not bind commitment")
    comparison = None
    if later_packet is not None:
        if source_packet is None:
            raise ValueError("source packet is required to evaluate a later stance")
        validate_packet(source_packet); validate_packet(later_packet)
        if source_packet["packet_digest"] != commitment["source_discernment_packet_digest"]:
            raise ValueError("source packet does not bind commitment")
        comparison = compare_packets(source_packet, later_packet)
    expected_missed = sorted(set(commitment["expected_observations"]) - set(outcome["expected_observations_witnessed"]))
    changed = bool(comparison and comparison["position_changes"]["changed"])
    new_evidence = bool(comparison and comparison["evidence_added"])
    classification = _classification(commitment, outcome)
    suspended = commitment["stance"] == "suspend"
    payload = {
        "schema_version": REVIEW_SCHEMA, "commitment_digest": commitment["commitment_digest"],
        "outcome_evidence_digest": outcome["outcome_evidence_digest"],
        "confidence_at_commitment_time": commitment.get("confidence"), "outcome_classification": classification,
        "expected_observations_witnessed": list(outcome["expected_observations_witnessed"]),
        "expected_observations_missed": expected_missed,
        "disconfirming_observations_witnessed": list(outcome["disconfirming_observations_witnessed"]),
        "stated_change_conditions_appeared": list(outcome["change_conditions_witnessed"]),
        "later_stance_changed": changed, "later_stance_change_had_new_evidence": bool(changed and new_evidence),
        "unsupported_reversal": bool(changed and not new_evidence),
        "suspension_maintained_appropriately": bool(suspended and classification in {"indeterminate", "not_yet_observable"}),
        "suspension_resolved_by_new_evidence": bool(suspended and classification in {"supported", "contradicted", "mixed"} and (new_evidence or outcome["evidence_references"])),
        "unresolved_contradiction_prematurely_collapsed": bool(commitment["unresolved_contradictions"] and changed and not new_evidence),
        "strongest_objection_materially_relevant": bool(commitment.get("strongest_objection") and outcome["disconfirming_observations_witnessed"]),
        "preferred_move_predicted_consequences_observed": bool(commitment.get("preferred_next_move") and set(commitment["predicted_consequences"]) & set(outcome["observed_facts"])),
        "rejected_move_rejection_assessment": dict(outcome["rejected_move_assessments"]),
        "stance_preflight": _plain(comparison["stance_preflight"]) if comparison else None,
        "preserved_commitment": _plain(commitment), "preserved_outcome_evidence": _plain(outcome),
        "source_precedence": "none_universal", "authority_posture": dict(AUTHORITY_POSTURE), "non_authoritative": True,
    }
    return _seal(payload, "review_digest", "review-")


def validate_review(value: Mapping[str, Any]) -> None:
    _validate(value, REVIEW_SCHEMA, "review_digest", "review-")
    if value.get("outcome_classification") not in CLASSIFICATIONS:
        raise ValueError("invalid outcome classification")


def create_longitudinal_report(reviews: Sequence[Mapping[str, Any]], *, generated_at: str) -> dict[str, Any]:
    for review in reviews:
        validate_review(review)
    rows = sorted(reviews, key=lambda row: str(row["review_digest"]))
    bands: dict[str, dict[str, int]] = {}
    for row in rows:
        confidence = row.get("confidence_at_commitment_time")
        band = "not_applicable" if confidence is None else "low" if confidence < .4 else "medium" if confidence < .75 else "high"
        history = bands.setdefault(band, {})
        classification = str(row["outcome_classification"]); history[classification] = history.get(classification, 0) + 1
    def count(key: str) -> int:
        return sum(bool(row[key]) for row in rows)
    classifications = [row["outcome_classification"] for row in rows]
    payload = {
        "schema_version": LONGITUDINAL_SCHEMA, "generated_at": generated_at,
        "review_digests": [row["review_digest"] for row in rows], "count_evaluable_commitments": len(rows),
        "count_still_indeterminate_or_not_observable": sum(value in {"indeterminate", "not_yet_observable"} for value in classifications),
        "confidence_band_outcome_history": bands, "evidence_backed_revisions": sum(bool(row["later_stance_changed"] and row["later_stance_change_had_new_evidence"]) for row in rows),
        "unsupported_reversals": count("unsupported_reversal"),
        "successful_suspensions_pending_evidence": count("suspension_maintained_appropriately"),
        "suspensions_later_resolved_by_new_evidence": count("suspension_resolved_by_new_evidence"),
        "contradictions_preserved_until_evidence_arrived": sum(bool(row["preserved_commitment"]["unresolved_contradictions"] and not row["unresolved_contradiction_prematurely_collapsed"]) for row in rows),
        "premature_contradiction_collapse": count("unresolved_contradiction_prematurely_collapsed"),
        "objections_later_supported_by_evidence": count("strongest_objection_materially_relevant"),
        "preferred_moves_with_observed_predicted_consequences": count("preferred_move_predicted_consequences_observed"),
        "rejected_move_rejection_history": {
            "vindicated": sum(list(row["rejected_move_rejection_assessment"].values()).count("vindicated") for row in rows),
            "undermined": sum(list(row["rejected_move_rejection_assessment"].values()).count("undermined") for row in rows),
            "not_evaluable": sum(not row["rejected_move_rejection_assessment"] for row in rows),
        },
        "composite_score": None, "composite_score_prohibited": True, "source_precedence": "none_universal",
        "authority_posture": dict(AUTHORITY_POSTURE), "non_authoritative": True,
    }
    return _seal(payload, "longitudinal_report_digest", "longitudinal-")


class OutcomeReviewCustody:
    """Externally rooted append-only files; it is not live memory or authority."""

    _KINDS = {COMMITMENT_SCHEMA: ("commitments", "commitment_digest", validate_commitment),
              OUTCOME_SCHEMA: ("outcomes", "outcome_evidence_digest", validate_outcome_evidence),
              REVIEW_SCHEMA: ("reviews", "review_digest", validate_review)}

    def __init__(self, root: str | Path): self.root = Path(root)

    def append(self, artifact: Mapping[str, Any]) -> Path:
        schema = str(artifact.get("schema_version"))
        if schema not in self._KINDS: raise ValueError("unsupported custody artifact")
        directory_name, digest_field, validator = self._KINDS[schema]; validator(artifact)
        directory = self.root / directory_name; directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{artifact[digest_field]}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(_plain(artifact), sort_keys=True, indent=2, ensure_ascii=False) + "\n"); stream.flush(); os.fsync(stream.fileno())
        return path

    def inspect(self, digest: str) -> dict[str, Any]:
        matches = list(self.root.glob(f"*/{digest}.json"))
        if len(matches) != 1: raise ValueError("artifact digest not found or ambiguous")
        artifact = json.loads(matches[0].read_text(encoding="utf-8"))
        schema = str(artifact.get("schema_version"))
        if schema not in self._KINDS: raise ValueError("unsupported custody artifact")
        self._KINDS[schema][2](artifact); return cast(dict[str, Any], artifact)
