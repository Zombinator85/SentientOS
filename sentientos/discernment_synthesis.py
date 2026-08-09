from __future__ import annotations

"""Non-authoritative composition of existing judgment surfaces.

This module consumes canonical outputs; it deliberately owns no cognition,
admission, execution, memory, goal, maintenance, publication, or authority path.
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, Sequence, cast

from sentientos.truth.stance_preflight import validate_planned_claim_against_stance

SCHEMA_VERSION = "sentientos.discernment_packet.v1"
SourceKind = Literal[
    "direct_observation", "deterministic_subsystem_inference", "local_model_interpretation",
    "unresolved_contradiction", "operator_position", "external_peer_or_model_position",
]
SOURCE_KINDS = frozenset({"direct_observation", "deterministic_subsystem_inference", "local_model_interpretation",
                          "unresolved_contradiction", "operator_position", "external_peer_or_model_position"})


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return _plain(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _digest(value: Any) -> str:
    raw = json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SurfaceContribution:
    surface_id: str
    source_kind: SourceKind
    component: str
    component_version: str
    position: str
    confidence: float
    evidence_refs: tuple[str, ...] = ()
    interpretation: str | None = None
    alternate_interpretations: tuple[str, ...] = ()
    strongest_objection: str | None = None
    missing_evidence: tuple[str, ...] = ()
    would_change_position: tuple[str, ...] = ()
    proposed_next_move: str | None = None
    proposed_non_moves: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {self.source_kind}")
        if not self.surface_id or not self.component or not self.component_version:
            raise ValueError("surface identity and component version are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")


class LocalModelJudgmentSource(Protocol):
    """Bounded adapter point for an already-governed canonical invocation plane."""

    def discern(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


def contribution_from_epistemic_entry(entry: Any) -> SurfaceContribution:
    """Adapt the canonical EpistemicEntry without reimplementing its reasoning."""
    entry_type = str(entry.entry_type)
    kind: SourceKind = "direct_observation" if entry_type == "observation" else "deterministic_subsystem_inference"
    if entry_type == "contradiction":
        kind = "unresolved_contradiction"
    return SurfaceContribution(
        surface_id=str(entry.entry_id), source_kind=kind,
        component="sentientos.truth.epistemic_orientation.EpistemicLedger",
        component_version="epistemic-orientation.v1", position=str(entry.claim),
        interpretation=str(entry.claim), confidence=float(entry.confidence),
        evidence_refs=tuple(str(x) for x in entry.metadata.get("evidence_refs", ())),
        provenance={"entry_type": entry_type, "source_class": entry.source_class,
                    "confidence_band": list(entry.confidence_band), "since_day": entry.since_day},
    )


def contribution_from_delegated_judgment(judgment: Mapping[str, Any], *, surface_id: str = "delegated-judgment") -> SurfaceContribution:
    position = str(judgment.get("recommended_venue") or judgment.get("delegation_posture") or "insufficient_context")
    raw_confidence = judgment.get("confidence", 0.5)
    confidence = {"low": 0.35, "medium": 0.6, "high": 0.85}.get(str(raw_confidence), raw_confidence)
    return SurfaceContribution(
        surface_id=surface_id, source_kind="deterministic_subsystem_inference",
        component="sentientos.delegated_judgment_fabric.synthesize_delegated_judgment",
        component_version=str(judgment.get("schema_version") or "delegated-judgment.v1"),
        position=position, interpretation=position,
        confidence=float(confidence),
        evidence_refs=tuple(str(x) for x in judgment.get("evidence_refs", ())),
        provenance={"canonical_output_digest": _digest(judgment), "judgment": _plain(judgment)},
    )


def contribution_from_inner_world(output: Any, *, surface_id: str = "inner-world") -> SurfaceContribution:
    """Bounded adapter for a live orchestrator output object or mapping."""
    data = _plain(output)
    if not isinstance(data, Mapping):
        raise ValueError("inner-world output must be structured")
    position = str(data.get("interpretation") or data.get("summary") or data.get("state") or "unresolved")
    return SurfaceContribution(
        surface_id=surface_id, source_kind="deterministic_subsystem_inference",
        component="sentientos.innerworld.orchestrator.InnerWorldOrchestrator",
        component_version=str(data.get("schema_version") or "inner-world.live"), position=position,
        interpretation=position, confidence=float(data.get("confidence") or 0.5),
        evidence_refs=tuple(str(x) for x in data.get("evidence_refs", ())),
        provenance={"canonical_output_digest": _digest(data)},
    )


def context_from_inner_world(output: Any) -> dict[str, Any]:
    """Preserve a live report as context without inventing a proposition or confidence."""
    data = _plain(output)
    if not isinstance(data, Mapping):
        raise ValueError("inner-world output must be structured")
    context_keys = (
        "ethics", "metacog", "meta", "innerworld_reflection", "cognitive_report",
        "workspace_spotlight", "inner_dialogue", "value_drift", "identity",
        "autobiography", "simulation", "qualia",
    )
    context = {key: data[key] for key in context_keys if key in data}
    return {
        "schema_version": "sentientos.inner_world_discernment_context.v1",
        "component": "sentientos.innerworld.orchestrator.InnerWorldOrchestrator",
        "canonical_output_digest": _digest(data),
        "cycle_id": data.get("cycle_id"),
        "structured_context": context,
        "asserts_final_position": False,
    }


def local_model_contribution(source: LocalModelJudgmentSource | None, request: Mapping[str, Any]) -> tuple[SurfaceContribution | None, Mapping[str, Any]]:
    if source is None:
        return None, {"status": "unavailable", "reason": "governed_local_model_source_not_configured", "fabricated": False}
    output = _plain(source.discern(_plain(request)))
    if not isinstance(output, Mapping):
        raise ValueError("governed model output must be an object")
    required = {"interpretation", "confidence"}
    if not required.issubset(output):
        raise ValueError("governed model output lacks required judgment fields")
    provenance = _plain(output.get("provenance") or {})
    if not isinstance(provenance, Mapping) or not provenance.get("invocation_receipt_digest"):
        raise ValueError("local-model judgment requires invocation receipt provenance")
    contribution = SurfaceContribution(
        surface_id=str(output.get("surface_id") or "governed-local-model"),
        source_kind="local_model_interpretation", component=str(output.get("component") or "governed_local_model_invocation"),
        component_version=str(output.get("component_version") or "unknown"), position=str(output["interpretation"]),
        interpretation=str(output["interpretation"]), confidence=float(output["confidence"]),
        evidence_refs=tuple(str(x) for x in output.get("evidence_refs", ())),
        alternate_interpretations=tuple(str(x) for x in output.get("alternate_interpretations", ())),
        strongest_objection=str(output["strongest_objection"]) if output.get("strongest_objection") else None,
        missing_evidence=tuple(str(x) for x in output.get("missing_evidence", ())),
        would_change_position=tuple(str(x) for x in output.get("would_change_position", ())),
        proposed_next_move=str(output["proposed_next_move"]) if output.get("proposed_next_move") else None,
        proposed_non_moves=tuple(str(x) for x in output.get("proposed_non_moves", ())), provenance=provenance,
    )
    return contribution, {"status": "used", "fabricated": False, "surface_id": contribution.surface_id,
                          "invocation_receipt_digest": provenance["invocation_receipt_digest"]}


def _disagreements(contributions: Sequence[SurfaceContribution], rules: Mapping[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SurfaceContribution]] = {}
    for contribution in contributions:
        decision_class = str(contribution.provenance.get("decision_class") or "interpretation")
        grouped.setdefault(decision_class, []).append(contribution)
    result: list[dict[str, Any]] = []
    for decision_class, rows in sorted(grouped.items()):
        positions = {row.position for row in rows}
        if len(positions) < 2:
            continue
        rule = rules.get(decision_class)
        result.append({
            "participants": [r.surface_id for r in rows], "proposition_or_decision_class": decision_class,
            "positions": [{"surface_id": r.surface_id, "position": r.position,
                           "evidence_refs": list(r.evidence_refs), "confidence": r.confidence} for r in rows],
            "reconciliation_law_exists": rule is not None, "reconciliation_law": rule,
            "resolution_occurred": False,
            "unresolved_reason": "no_reconciliation_law" if rule is None else "law_does_not_authorize_automatic_collapse",
        })
    return result


def synthesize_packet(*, subject_id: str, question: str, contributions: Sequence[SurfaceContribution],
                      evaluation_context: Mapping[str, Any], observed_at: str,
                      current_interpretation: str | None = None, epistemic_status: str = "unknown",
                      confidence: float | None = None, volatility: float = 0.0,
                      suspended_conclusions: Sequence[Mapping[str, Any]] = (),
                      value_identity_tensions: Sequence[str] = (), strategic_consequences: Sequence[str] = (),
                      delegated_judgment_posture: str = "unresolved", preferred_next_move: str | None = None,
                      rejected_next_moves: Sequence[str] = (), unresolved_decision_classes: Sequence[str] = (),
                      reconciliation_rules: Mapping[str, str] | None = None,
                      prior_packet_digest: str | None = None,
                      local_model_status: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not subject_id or not question or not observed_at:
        raise ValueError("subject, question, and observed_at are required")
    rows = sorted(contributions, key=lambda row: row.surface_id)
    objections = [r.strongest_objection for r in rows if r.strongest_objection]
    change_evidence = sorted({item for r in rows for item in r.would_change_position})
    evidence = sorted({ref for r in rows for ref in r.evidence_refs})
    contradictions = [r.position for r in rows if r.source_kind == "unresolved_contradiction"]
    alternates = sorted({value for r in rows for value in ((r.position,) + r.alternate_interpretations)
                         if value != current_interpretation})
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "subject_id": subject_id, "question": question,
        "observed_at": observed_at, "evaluation_context": _plain(evaluation_context),
        "prior_packet_digest": prior_packet_digest, "observations_and_evidence": evidence,
        "current_interpretation": current_interpretation, "epistemic_status": epistemic_status,
        "confidence": confidence, "volatility": volatility,
        "unresolved_contradictions": contradictions, "suspended_conclusions": _plain(suspended_conclusions),
        "competing_interpretations": alternates, "strongest_objection": objections[0] if objections else None,
        "what_would_change_judgment": change_evidence, "value_identity_tensions": list(value_identity_tensions),
        "strategic_consequences": list(strategic_consequences),
        "delegated_judgment_posture": delegated_judgment_posture,
        "preferred_next_move": preferred_next_move, "rejected_next_moves": sorted(set(rejected_next_moves)),
        "unresolved_decision_classes": sorted(set(unresolved_decision_classes)),
        "surface_contributions": [_plain(row) for row in rows],
        "disagreements": _disagreements(rows, reconciliation_rules or {}),
        "local_model_contribution": _plain(local_model_status or {"status": "unavailable", "fabricated": False}),
        "authority_posture": {key: False for key in (
            "admits_work", "executes_work", "modifies_goal_graph", "modifies_memory", "mutates_claims_or_stances",
            "invokes_maintenance", "publishes", "creates_commits", "grants_authority")},
        "judgment_record_not_memory_truth": True, "consensus_required": False,
        "source_precedence": "none_universal",
    }
    payload["packet_digest"] = _digest(payload)
    payload["packet_id"] = "discernment-" + payload["packet_digest"][:24]
    return payload


def validate_packet(packet: Mapping[str, Any]) -> None:
    body = dict(packet)
    packet_id = body.pop("packet_id", None)
    claimed = body.pop("packet_digest", None)
    actual = _digest(body)
    if claimed != actual or packet_id != "discernment-" + actual[:24]:
        raise ValueError("discernment packet digest mismatch")
    if any(packet.get("authority_posture", {}).values()):
        raise ValueError("forbidden authority posture")


class DiscernmentCustody:
    """Append-only external/configured custody; never SentientOS memory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def packets_for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        directory = self.root / hashlib.sha256(subject_id.encode()).hexdigest()
        packets: list[dict[str, Any]] = []
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                packet = json.loads(path.read_text(encoding="utf-8")); validate_packet(packet); packets.append(packet)
        return sorted(packets, key=lambda p: (str(p["observed_at"]), str(p["packet_digest"])))

    def append(self, packet: Mapping[str, Any]) -> Path:
        validate_packet(packet)
        prior = self.packets_for_subject(str(packet["subject_id"]))
        expected = prior[-1]["packet_digest"] if prior else None
        if packet.get("prior_packet_digest") != expected:
            raise ValueError("prior packet digest does not bind current subject history")
        directory = self.root / hashlib.sha256(str(packet["subject_id"]).encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{packet['packet_digest']}.json"
        data = json.dumps(_plain(packet), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        return path

    def inspect(self, packet_digest: str) -> dict[str, Any]:
        matches = list(self.root.glob(f"*/{packet_digest}.json"))
        if len(matches) != 1:
            raise ValueError("packet digest not found or ambiguous")
        packet = json.loads(matches[0].read_text(encoding="utf-8")); validate_packet(packet); return cast(dict[str, Any], packet)


def compare_packets(earlier: Mapping[str, Any], later: Mapping[str, Any]) -> dict[str, Any]:
    validate_packet(earlier); validate_packet(later)
    if earlier["subject_id"] != later["subject_id"]:
        raise ValueError("compare requires packets for the same subject")
    old_evidence, new_evidence = set(earlier["observations_and_evidence"]), set(later["observations_and_evidence"])
    added, removed = sorted(new_evidence - old_evidence), sorted(old_evidence - new_evidence)
    changed = earlier.get("current_interpretation") != later.get("current_interpretation")
    def stance_status(value: Any) -> str:
        return {"supported": "provisional_supported"}.get(str(value), str(value))
    old_claim = {"claim_id": earlier["packet_id"], "topic_id": earlier["subject_id"],
                 "epistemic_status": stance_status(earlier["epistemic_status"]), "evidence_ids": sorted(old_evidence),
                 "position": earlier.get("current_interpretation")}
    new_claim = {"claim_id": later["packet_id"], "topic_id": later["subject_id"],
                 "epistemic_status": stance_status(later["epistemic_status"]), "evidence_ids": sorted(new_evidence),
                 "position": later.get("current_interpretation")}
    stance = validate_planned_claim_against_stance(
        planned_claim=new_claim, prior_claims=[old_claim], stance_receipts=[{"active_claim_id": old_claim["claim_id"]}],
        transition_type="supersede_with_new_evidence" if changed else "hold_revision",
        rationale="discernment packet comparison",
    )
    return {
        "schema_version": "sentientos.discernment_comparison.v1", "subject_id": earlier["subject_id"],
        "earlier_packet_digest": earlier["packet_digest"], "later_packet_digest": later["packet_digest"],
        "position_changes": {"changed": changed, "from": earlier.get("current_interpretation"), "to": later.get("current_interpretation")},
        "confidence_changes": {"from": earlier.get("confidence"), "to": later.get("confidence")},
        "contradictions_added": sorted(set(later["unresolved_contradictions"]) - set(earlier["unresolved_contradictions"])),
        "contradictions_resolved": sorted(set(earlier["unresolved_contradictions"]) - set(later["unresolved_contradictions"])),
        "evidence_added": added, "evidence_removed": removed,
        "preferred_move_changed": earlier.get("preferred_next_move") != later.get("preferred_next_move"),
        "rejected_moves_changed": earlier.get("rejected_next_moves") != later.get("rejected_next_moves"),
        "reversal_had_new_evidence": bool(changed and added), "stance_preflight": _plain(stance),
        "non_authoritative": True,
    }


def contribution_from_mapping(value: Mapping[str, Any]) -> SurfaceContribution:
    fields = dict(value)
    for key in ("evidence_refs", "alternate_interpretations", "missing_evidence", "would_change_position", "proposed_non_moves"):
        fields[key] = tuple(fields.get(key, ()))
    return SurfaceContribution(**fields)
