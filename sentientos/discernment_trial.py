from __future__ import annotations

"""Participant-neutral custody for blind comparative discernment trials."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.discernment_outcome_review import create_commitment, create_outcome_evidence, create_review

TRIAL_SCHEMA = "sentientos.discernment_trial.v1"
JUDGMENT_SCHEMA = "sentientos.discernment_trial_judgment.v1"
EVIDENCE_SCHEMA = "sentientos.discernment_trial_evidence.v1"
REVIEW_SCHEMA = "sentientos.discernment_trial_review.v1"
COMPARISON_SCHEMA = "sentientos.discernment_trial_comparison.v1"
REVEAL_SCHEMA = "sentientos.discernment_trial_identity_reveal.v1"
STANCES = {"support", "oppose", "suspend"}
NO_AUTHORITY = {key: False for key in (
    "executes", "modifies_memory", "modifies_goals", "invokes_maintenance", "creates_commits",
    "publishes", "schedules", "invokes_providers", "grants_authority",
)}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _sealed(payload: dict[str, Any], field: str) -> dict[str, Any]:
    payload[field] = _digest(payload)
    return payload


def _keys(values: Sequence[str], namespace: str) -> list[str]:
    rows = sorted(set(map(str, values)))
    if any(not row.startswith(namespace + ".") for row in rows):
        raise ValueError("observation key is outside the allowed namespace")
    return rows


class BlindTrialCustody:
    """Append-only protocol custody; filesystem owners remain able to inspect files."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / name

    def _read(self, name: str) -> dict[str, Any]:
        value = json.loads(self._path(name).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("custody artifact must be an object")
        return value

    def _write_once(self, name: str, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(_plain(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n")
            stream.flush(); os.fsync(stream.fileno())

    def create_trial(self, request: Mapping[str, Any]) -> dict[str, Any]:
        slots = sorted(set(map(str, request["opaque_participant_slots"])))
        count = int(request["expected_participant_count"])
        if count < 2 or len(slots) != count or any(not slot for slot in slots):
            raise ValueError("exactly the expected opaque participant slots (at least two) are required")
        question = str(request["question"])
        snapshot = _plain(request["initial_evidence_snapshot"])
        namespace = str(request["allowed_observation_namespace"])
        payload = {
            "schema_version": TRIAL_SCHEMA, "trial_id": str(request["trial_id"]), "question": question,
            "question_digest": _digest(question), "subject_id": str(request["subject_id"]),
            "created_at": str(request["created_at"]), "initial_evidence_snapshot": snapshot,
            "initial_evidence_snapshot_digest": _digest(snapshot), "expected_participant_count": count,
            "opaque_participant_slots": slots, "trial_nonce": str(request["trial_nonce"]),
            "evaluation_horizon": _plain(request["evaluation_horizon"]),
            "allowed_observation_namespace": namespace,
            "allowed_observation_schema": "sentientos.discernment_trial_observation.v1",
            "custody_root_identity": str(request["custody_root_identity"]),
            "no_participant_specific_hints": True, "authority_posture": dict(NO_AUTHORITY),
            "non_authoritative_evaluation_instrument": True,
        }
        artifact = _sealed(payload, "trial_digest"); self._write_once("trial.json", artifact)
        return artifact

    def register_participant(self, opaque_id: str, identity: str) -> dict[str, Any]:
        trial = self._read("trial.json")
        if opaque_id not in trial["opaque_participant_slots"]:
            raise ValueError("unknown opaque participant slot")
        if self._path("judgment-set.json").exists():
            raise ValueError("participant registration is frozen")
        self._write_once(f"identity.{opaque_id}.json", {"opaque_participant_id": opaque_id, "identity": identity})
        return {"opaque_participant_id": opaque_id, "registered": True,
                "question_digest": trial["question_digest"], "evidence_snapshot_digest": trial["initial_evidence_snapshot_digest"]}

    def submit(self, opaque_id: str, request: Mapping[str, Any]) -> dict[str, Any]:
        trial = self._read("trial.json")
        if not self._path(f"identity.{opaque_id}.json").exists():
            raise ValueError("participant is not registered")
        if self._path("judgment-set.json").exists():
            raise ValueError("judgment set is frozen")
        if request.get("stance") not in STANCES:
            raise ValueError("stance must be support, oppose, or suspend")
        confidence = request.get("confidence")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise ValueError("confidence must be between zero and one")
        namespace = trial["allowed_observation_namespace"]
        payload = {
            "schema_version": JUDGMENT_SCHEMA, "opaque_participant_id": opaque_id,
            "trial_digest": trial["trial_digest"], "question_digest": trial["question_digest"],
            "evidence_snapshot_digest": trial["initial_evidence_snapshot_digest"],
            "source_discernment_packet_digest": request.get("source_discernment_packet_digest"),
            "proposition": request.get("proposition"), "interpretation": request.get("interpretation"),
            "stance": request["stance"], "confidence": confidence,
            "strongest_objection": request.get("strongest_objection"),
            "alternate_interpretations": list(request.get("alternate_interpretations", ())),
            "missing_evidence": list(request.get("missing_evidence", ())),
            "what_would_change_judgment": list(request.get("what_would_change_judgment", ())),
            "expected_observation_keys": _keys(request.get("expected_observation_keys", ()), namespace),
            "disconfirming_observation_keys": _keys(request.get("disconfirming_observation_keys", ()), namespace),
            "predicted_consequences": list(request.get("predicted_consequences", ())),
            "preferred_next_move": request.get("preferred_next_move"),
            "rejected_next_moves": list(request.get("rejected_next_moves", ())),
            "unresolved_contradictions": list(request.get("unresolved_contradictions", ())),
            "sealed_at": str(request["sealed_at"]), "authority_posture": dict(NO_AUTHORITY),
        }
        artifact = _sealed(payload, "participant_judgment_digest")
        self._write_once(f"judgment.{opaque_id}.json", artifact)
        self._freeze_if_complete(trial)
        state = self.trial_state()
        return {"opaque_participant_id": opaque_id, "participant_judgment_digest": artifact["participant_judgment_digest"],
                "sealed_count": state["sealed_count"], "expected_participant_count": state["expected_participant_count"],
                "judgment_set_frozen": state["judgment_set_frozen"]}

    def _freeze_if_complete(self, trial: Mapping[str, Any]) -> None:
        rows = [self._read(f"judgment.{slot}.json") for slot in trial["opaque_participant_slots"] if self._path(f"judgment.{slot}.json").exists()]
        if len(rows) == trial["expected_participant_count"]:
            payload = {"trial_digest": trial["trial_digest"], "participant_judgment_digests":
                       {row["opaque_participant_id"]: row["participant_judgment_digest"] for row in rows}}
            self._write_once("judgment-set.json", _sealed(payload, "judgment_set_digest"))

    def trial_state(self) -> dict[str, Any]:
        trial = self._read("trial.json"); frozen = self._path("judgment-set.json").exists()
        sealed = sum(self._path(f"judgment.{slot}.json").exists() for slot in trial["opaque_participant_slots"])
        return {"trial_id": trial["trial_id"], "question_digest": trial["question_digest"],
                "evidence_snapshot_digest": trial["initial_evidence_snapshot_digest"], "sealed_count": sealed,
                "expected_participant_count": trial["expected_participant_count"], "judgment_set_frozen": frozen,
                "evidence_recorded": self._path("evidence.json").exists(), "comparison_sealed": self._path("comparison.json").exists(),
                "identity_revealed": self._path("reveal.json").exists()}

    def inspect(self, kind: str, opaque_id: str | None = None) -> dict[str, Any]:
        if kind == "trial-state": return self.trial_state()
        if kind == "judgment":
            if not self._path("judgment-set.json").exists():
                raise ValueError("peer judgments are unavailable before judgment-set freeze")
            if opaque_id is None: raise ValueError("opaque participant id required")
            return self._read(f"judgment.{opaque_id}.json")
        if kind not in {"trial", "evidence", "comparison", "reveal"}: raise ValueError("unsupported inspection kind")
        return self._read({"trial": "trial.json", "evidence": "evidence.json", "comparison": "comparison.json", "reveal": "reveal.json"}[kind])

    def record_evidence(self, request: Mapping[str, Any]) -> dict[str, Any]:
        trial = self._read("trial.json")
        if not self._path("judgment-set.json").exists(): raise ValueError("judgment set must be frozen before evidence")
        namespace = trial["allowed_observation_namespace"]; observations = []
        for source in request["observations"]:
            row = _plain(source); row["observation_key"] = _keys([row["observation_key"]], namespace)[0]
            required = {"observation_key", "observation_id", "observed_at", "value", "evidence_references", "provenance", "ambiguity"}
            if not required <= set(row): raise ValueError("canonical observation fields are required")
            observations.append(row)
        payload = {"schema_version": EVIDENCE_SCHEMA, "trial_digest": trial["trial_digest"],
                   "judgment_set_digest": self._read("judgment-set.json")["judgment_set_digest"],
                   "observations": sorted(observations, key=lambda row: (row["observation_key"], row["observation_id"])),
                   "evaluation_horizon_elapsed": bool(request["evaluation_horizon_elapsed"]), "authority_posture": dict(NO_AUTHORITY)}
        artifact = _sealed(payload, "trial_evidence_digest"); self._write_once("evidence.json", artifact); return artifact

    def review(self) -> dict[str, Any]:
        trial = self._read("trial.json"); evidence = self._read("evidence.json")
        observed = {row["observation_key"] for row in evidence["observations"]}
        results = []
        for opaque_id in trial["opaque_participant_slots"]:
            judgment = self._read(f"judgment.{opaque_id}.json")
            expected = sorted(set(judgment["expected_observation_keys"]) & observed)
            disconfirming = sorted(set(judgment["disconfirming_observation_keys"]) & observed)
            packet = _trial_packet(trial, judgment)
            commitment = create_commitment(packet, committed_at=judgment["sealed_at"], decision_class="blind_comparative_trial",
                proposition=str(judgment.get("proposition") or judgment.get("interpretation") or "suspended"), stance=judgment["stance"],
                confidence=judgment.get("confidence"), expected_observations=judgment["expected_observation_keys"],
                disconfirming_observations=judgment["disconfirming_observation_keys"], predicted_consequences=judgment["predicted_consequences"],
                evaluation_horizon=trial["evaluation_horizon"])
            outcome = create_outcome_evidence(commitment, observed_at=max(row["observed_at"] for row in evidence["observations"]),
                evidence_references=[ref for row in evidence["observations"] for ref in row["evidence_references"]],
                evidence_provenance=[row["provenance"] for row in evidence["observations"]],
                observed_facts=sorted(observed), expected_observations_witnessed=expected,
                disconfirming_observations_witnessed=disconfirming,
                unresolved_or_ambiguous_evidence=[row["observation_key"] for row in evidence["observations"] if row["ambiguity"]],
                evaluation_horizon_elapsed=evidence["evaluation_horizon_elapsed"],
                change_conditions_witnessed=sorted(set(judgment["what_would_change_judgment"]) & observed))
            generic = create_review(commitment, outcome)
            payload = {"schema_version": REVIEW_SCHEMA, "opaque_participant_id": opaque_id,
                "participant_judgment_digest": judgment["participant_judgment_digest"], "trial_evidence_digest": evidence["trial_evidence_digest"],
                "derived_expected_hits": expected, "derived_disconfirming_hits": disconfirming,
                "outcome_classification": generic["outcome_classification"], "confidence_at_commitment": judgment.get("confidence"),
                "suspension_behavior": {"suspended": judgment["stance"] == "suspend", "resolved_by_requested_evidence": bool(judgment["stance"] == "suspend" and set(judgment["what_would_change_judgment"]) & observed)},
                "evidence_backed_reversal": generic["later_stance_change_had_new_evidence"], "unsupported_reversal": generic["unsupported_reversal"],
                "strongest_objection_relevance": "relevant" if judgment.get("strongest_objection") and disconfirming else "not_yet_evaluable",
                "predicted_consequence_observations": sorted(set(judgment["predicted_consequences"]) & observed),
                "unresolved_ambiguity": list(outcome["unresolved_or_ambiguous_evidence"]), "authority_posture": dict(NO_AUTHORITY)}
            artifact = _sealed(payload, "blind_review_digest"); self._write_once(f"review.{opaque_id}.json", artifact); results.append(artifact)
        return {"reviews": results, "review_set_digest": _digest([row["blind_review_digest"] for row in results])}

    def compare(self) -> dict[str, Any]:
        trial = self._read("trial.json"); rows = []
        if not self._path("judgment-set.json").exists(): raise ValueError("judgment set must be frozen before comparison")
        judgments = {slot: self._read(f"judgment.{slot}.json") for slot in trial["opaque_participant_slots"]}
        reviews = {slot: self._read(f"review.{slot}.json") for slot in trial["opaque_participant_slots"]}
        for slot in trial["opaque_participant_slots"]:
            judgment, review = judgments[slot], reviews[slot]
            peer_expected = set().union(*(set(row["expected_observation_keys"]) for key, row in judgments.items() if key != slot))
            peer_objections = {row.get("strongest_objection") for key, row in judgments.items() if key != slot}
            rows.append({"opaque_participant_id": slot, "stance": judgment["stance"], "confidence": judgment.get("confidence"),
                "outcome_classification": review["outcome_classification"], "forecast_keys_hit": review["derived_expected_hits"],
                "disconfirming_keys_hit": review["derived_disconfirming_hits"],
                "requested_change_evidence_observed": review["suspension_behavior"]["resolved_by_requested_evidence"],
                "strongest_objection_relevance": review["strongest_objection_relevance"],
                "evidence_backed_revisions": review["evidence_backed_reversal"], "unsupported_reversals": review["unsupported_reversal"],
                "suspension_discipline": review["suspension_behavior"],
                "contradiction_preservation_behavior": bool(judgment["unresolved_contradictions"]),
                "predicted_consequence_observations": review["predicted_consequence_observations"],
                "unique_prospectively_useful_observations": sorted(set(judgment["expected_observation_keys"]) - peer_expected),
                "useful_objections_not_raised_by_peers": bool(judgment.get("strongest_objection") and judgment["strongest_objection"] not in peer_objections),
                "overlapping_judgments": sorted(key for key, row in judgments.items() if key != slot and row["stance"] == judgment["stance"])})
        payload = {"schema_version": COMPARISON_SCHEMA, "trial_digest": trial["trial_digest"], "participants": rows,
                   "dimensions_remain_separate": True, "composite_scores_and_rankings_prohibited": True,
                   "identity_inputs_consumed": False, "authority_posture": dict(NO_AUTHORITY)}
        artifact = _sealed(payload, "blind_comparison_digest"); self._write_once("comparison.json", artifact); return artifact

    def reveal(self) -> dict[str, Any]:
        trial = self._read("trial.json")
        if not self._path("comparison.json").exists(): raise ValueError("blind comparison must be sealed before reveal")
        comparison = self._read("comparison.json")
        for slot in trial["opaque_participant_slots"]: self._read(f"review.{slot}.json")
        identities = {slot: self._read(f"identity.{slot}.json")["identity"] for slot in trial["opaque_participant_slots"]}
        payload = {"schema_version": REVEAL_SCHEMA, "trial_digest": trial["trial_digest"],
                   "blind_comparison_digest": comparison["blind_comparison_digest"], "identities": identities,
                   "prior_artifacts_modified": False, "authority_posture": dict(NO_AUTHORITY)}
        artifact = _sealed(payload, "identity_reveal_digest"); self._write_once("reveal.json", artifact); return artifact


def _trial_packet(trial: Mapping[str, Any], judgment: Mapping[str, Any]) -> dict[str, Any]:
    """Minimal valid packet adapter; it contains opaque trial facts, never identity."""
    from sentientos.discernment_synthesis import SurfaceContribution, synthesize_packet
    row = SurfaceContribution(surface_id=str(judgment["opaque_participant_id"]), source_kind="local_model_interpretation",
        component="blind-trial-import", component_version="v1", position=str(judgment.get("interpretation") or "suspended"),
        interpretation=judgment.get("interpretation"), confidence=float(judgment.get("confidence") or 0.0), evidence_refs=(),
        strongest_objection=judgment.get("strongest_objection"), missing_evidence=tuple(judgment["missing_evidence"]),
        would_change_position=tuple(judgment["what_would_change_judgment"]), provenance={"trial_digest": trial["trial_digest"]})
    result: dict[str, Any] = synthesize_packet(subject_id=trial["subject_id"], question=trial["question"], contributions=[row], evaluation_context={},
        observed_at=trial["created_at"], current_interpretation=judgment.get("interpretation"), epistemic_status="suspended" if judgment["stance"] == "suspend" else "contested",
        confidence=judgment.get("confidence"), preferred_next_move=judgment.get("preferred_next_move"),
        rejected_next_moves=judgment["rejected_next_moves"])
    return result
