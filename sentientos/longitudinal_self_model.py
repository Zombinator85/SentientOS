"""Deterministic, non-authoritative longitudinal claims derived from World-State."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_model_authority import atomic_write_json, digest_payload
from .world_state_board import WorldStateFact, WorldStateSnapshot, validate_snapshot

SCHEMA = "sentientos.longitudinal_self_model:v1"
RECONCILIATION_SCHEMA = "sentientos.longitudinal_self_model_reconciliation:v1"
CONFIG_SCHEMA = "sentientos.longitudinal_self_model_runtime_config:v1"
PROJECTION_SCHEMA = "sentientos.cognitive_self_model_projection:v1"
PROJECTION_POLICY = "predicate_then_claim_id:v1"
MAX_PROJECTION_CLAIMS = 32
FALSE_AUTHORITY = {
    "decision_authority": False, "admission_authority": False,
    "execution_authority": False, "adoption_authority": False,
    "policy_authority": False, "goal_authority": False,
    "source_mutation_authority": False, "model_authorship_authority": False,
}
MAX_CLAIMS = 256
MAX_VALUE_BYTES = 4096
FORBIDDEN_PREDICATES = {
    "authority", "permission", "policy", "goal", "adoption", "consciousness",
    "sentience", "identity_continuity", "learning", "improvement",
    "model_authored_claim", "reflection_claim",
}
PAYLOAD_PREDICATES = {
    "software_generation": ("software_generation", "runtime_generation"),
    "cognitive_model_identity": ("cognitive_model_id", "serving_model", "model_id"),
    "developmental_history_boundary": ("developmental_history_boundary",),
    "configuration_identity": ("configuration_id",),
    "capability_identity": ("capability_id",),
    "embodiment.body_identity": ("installation_body_id",),
    "embodiment.body_generation": ("body_generation",),
    "embodiment.avatar_asset_identity": ("avatar_asset_id",),
    "embodiment.rig_identity": ("rig_id",),
    "embodiment.renderer_identity": ("renderer_identity", "renderer_interface_id"),
    "embodiment.sensor_presence": ("present",),
    "embodiment.sensor_health": ("healthy",),
    "embodiment.actuator_availability": ("available",),
    "embodiment.commanded_pose": ("commanded_pose",),
    "embodiment.commanded_expression": ("commanded_expression",),
    "embodiment.renderer_reported_pose": ("renderer_reported_pose",),
    "embodiment.renderer_reported_expression": ("renderer_reported_expression",),
    "embodiment.observed_pose": ("observed_pose",),
    "embodiment.observed_expression": ("observed_expression",),
}


class LongitudinalSelfModelError(ValueError):
    """A fail-closed projection or custody violation."""


@dataclass(frozen=True)
class LongitudinalSelfModelRuntimeConfig:
    enabled: bool
    custody_root: Path
    cognitive_consumption_enabled: bool
    max_projection_claims: int
    allowed_predicates: tuple[str, ...]
    installation_id: str


@dataclass(frozen=True)
class CognitiveSelfModelProjection:
    schema: str
    projection_id: str
    projection_digest: str
    source_reconciliation_id: str
    source_reconciliation_digest: str
    source_reconciliation_generation: int
    source_tick: str
    selected_claims: tuple[Mapping[str, Any], ...]
    selected_claim_ids: tuple[str, ...]
    selected_claim_digests: tuple[str, ...]
    software_generations: tuple[str, ...]
    cognitive_model_identities: tuple[str, ...]
    developmental_history_boundaries: tuple[str, ...]
    projection_policy: str
    authority: Mapping[str, bool]
    read_only: bool = True
    derived_evidence: bool = True
    current_truth: bool = False
    interpretation: bool = False

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("projection_id")
        value.pop("projection_digest")
        return value


def load_runtime_config(path: str | Path) -> LongitudinalSelfModelRuntimeConfig:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LongitudinalSelfModelError("runtime_configuration_unreadable") from exc
    expected = {"schema", "enabled", "custody_root", "cognitive_consumption_enabled",
                "max_projection_claims", "allowed_predicates", "installation_id"}
    if not isinstance(payload, dict) or set(payload) != expected or payload.get("schema") != CONFIG_SCHEMA:
        raise LongitudinalSelfModelError("runtime_configuration_shape_invalid")
    allowed = payload["allowed_predicates"]
    if (not isinstance(payload["enabled"], bool)
            or not isinstance(payload["cognitive_consumption_enabled"], bool)
            or not isinstance(payload["custody_root"], str) or not Path(payload["custody_root"]).is_absolute()
            or not isinstance(payload["installation_id"], str) or not payload["installation_id"]
            or not isinstance(payload["max_projection_claims"], int)
            or not 1 <= payload["max_projection_claims"] <= MAX_PROJECTION_CLAIMS
            or not isinstance(allowed, list) or not allowed
            or any(not isinstance(item, str) or not item or item in FORBIDDEN_PREDICATES for item in allowed)
            or len(allowed) != len(set(allowed))):
        raise LongitudinalSelfModelError("runtime_configuration_values_invalid")
    return LongitudinalSelfModelRuntimeConfig(
        payload["enabled"], Path(payload["custody_root"]), payload["cognitive_consumption_enabled"],
        payload["max_projection_claims"], tuple(sorted(allowed)), payload["installation_id"])


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _bounded(value: Any) -> Any:
    result: Any
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        result = value
    elif isinstance(value, str):
        result = value
    elif isinstance(value, list):
        result = [_bounded(item) for item in value]
    elif isinstance(value, dict) and all(isinstance(key, str) for key in value):
        result = {key: _bounded(value[key]) for key in sorted(value)}
    else:
        raise LongitudinalSelfModelError("claim_value_not_bounded_json")
    if len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) > MAX_VALUE_BYTES:
        raise LongitudinalSelfModelError("claim_value_too_large")
    return result


@dataclass(frozen=True)
class SelfModelClaim:
    claim_id: str
    claim_key: str
    subject_id: str
    subject_kind: str
    predicate: str
    value: Any
    temporal_scope: str
    claim_category: str
    lifecycle_stage: str
    status: str
    freshness: str
    contradiction_state: str
    evidence_strength: str
    source_evidence_ids: tuple[str, ...]
    source_evidence_digests: tuple[str, ...]
    source_fact_ids: tuple[str, ...]
    world_state_snapshot_id: str
    world_state_snapshot_digest: str
    source_observed_at: tuple[str, ...]
    first_supported_generation: int
    last_supported_generation: int
    first_supported_tick: str
    last_supported_tick: str
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    software_generation: str | None = None
    cognitive_model_identity: str | None = None
    developmental_history_boundary: str | None = None
    evidence_bound: bool = True
    current_truth: bool = False
    interpretation: bool = False
    authority: Mapping[str, bool] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.authority is None:
            object.__setattr__(self, "authority", dict(FALSE_AUTHORITY))


@dataclass(frozen=True)
class SelfModelReconciliation:
    schema: str
    reconciliation_id: str
    reconciliation_digest: str
    generation: int
    tick_id: str
    snapshot_id: str
    snapshot_digest: str
    previous_reconciliation_id: str | None
    claims: tuple[SelfModelClaim, ...]
    authority: Mapping[str, bool]


def _claim_key(fact: WorldStateFact, predicate: str) -> str:
    return _digest((fact.subject.subject_id, fact.subject.subject_kind, fact.stage, predicate))


def _claim_id(key: str, value: Any, fact_ids: Sequence[str]) -> str:
    return "self-claim-" + _digest((key, value, sorted(fact_ids)))[7:31]


def _fact_predicates(fact: WorldStateFact) -> list[tuple[str, Any, str]]:
    out = [(f"lifecycle.{fact.stage}.disposition", fact.disposition, "current_state")]
    for predicate, keys in PAYLOAD_PREDICATES.items():
        for key in keys:
            if key in fact.payload:
                out.append((predicate, _bounded(fact.payload[key]), "lineage" if "generation" in predicate or "model" in predicate else "configuration"))
                break
    if fact.effect_proven and "observed_consequence" in fact.payload:
        out.append(("observed_consequence", _bounded(fact.payload["observed_consequence"]), "observed_consequence"))
    return out


def _semantic(reconciliation: SelfModelReconciliation) -> dict[str, Any]:
    value = asdict(reconciliation)
    value.pop("reconciliation_id", None)
    value.pop("reconciliation_digest", None)
    return value


class LongitudinalSelfModelOwner:
    """Append immutable reconciliations; never mutate source evidence or confer authority."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.entries = self.root / "reconciliations"

    def _load(self) -> tuple[SelfModelReconciliation, ...]:
        if not self.entries.exists():
            return ()
        loaded: list[SelfModelReconciliation] = []
        for path in sorted(self.entries.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                claims = tuple(SelfModelClaim(**{
                    **claim,
                    "source_evidence_ids": tuple(claim["source_evidence_ids"]),
                    "source_evidence_digests": tuple(claim["source_evidence_digests"]),
                    "source_fact_ids": tuple(claim["source_fact_ids"]),
                    "source_observed_at": tuple(claim["source_observed_at"]),
                    "supersedes": tuple(claim["supersedes"]),
                    "superseded_by": tuple(claim["superseded_by"]),
                }) for claim in raw.pop("claims"))
                reconciliation = SelfModelReconciliation(claims=claims, **raw)
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                raise LongitudinalSelfModelError("reconciliation_journal_corrupt") from exc
            if reconciliation.schema != RECONCILIATION_SCHEMA or reconciliation.reconciliation_digest != _digest(_semantic(reconciliation)):
                raise LongitudinalSelfModelError("reconciliation_digest_mismatch")
            expected_id = "self-reconciliation-" + reconciliation.reconciliation_digest[7:31]
            if reconciliation.reconciliation_id != expected_id:
                raise LongitudinalSelfModelError("reconciliation_identity_mismatch")
            loaded.append(reconciliation)
        for index, item in enumerate(loaded):
            expected_previous = loaded[index - 1].reconciliation_id if index else None
            if item.generation != index + 1 or item.previous_reconciliation_id != expected_previous:
                raise LongitudinalSelfModelError("reconciliation_chain_invalid")
        return tuple(loaded)

    def history(self) -> tuple[SelfModelReconciliation, ...]:
        return self._load()

    def reconstruct(self, generation: int | None = None) -> SelfModelReconciliation | None:
        history = self._load()
        if not history:
            return None
        if generation is None:
            return history[-1]
        if generation < 1 or generation > len(history):
            raise LongitudinalSelfModelError("generation_not_found")
        return history[generation - 1]

    def cognitive_projection(self, *, before_tick: str, max_claims: int,
                             allowed_predicates: Sequence[str]) -> CognitiveSelfModelProjection | None:
        """Project only a reconciliation completed before ``before_tick``.

        Tick identity equality is rejected mechanically.  The daemon captures this
        projection before reconciling its current World-State, so the selected
        generation cannot be affected by same-tick cognition or writeback.
        """
        if not before_tick or not 1 <= max_claims <= MAX_PROJECTION_CLAIMS:
            raise LongitudinalSelfModelError("invalid_cognitive_projection_boundary")
        history = self._load()
        eligible = [item for item in history if item.tick_id != before_tick]
        if not eligible:
            return None
        source = eligible[-1]
        allowed = set(allowed_predicates)
        claims = sorted((claim for claim in source.claims if claim.predicate in allowed),
                        key=lambda claim: (claim.predicate, claim.claim_id))[:max_claims]
        selected: list[Mapping[str, Any]] = []
        digests: list[str] = []
        for claim in claims:
            bounded = {
                "claim_id": claim.claim_id, "semantic_digest": _digest(asdict(claim)),
                "predicate": claim.predicate, "value": _bounded(claim.value),
                "status": claim.status, "freshness": claim.freshness,
                "contradiction_state": claim.contradiction_state,
                "evidence_strength": claim.evidence_strength,
                "source_evidence_ids": list(claim.source_evidence_ids),
                "source_evidence_digests": list(claim.source_evidence_digests),
                "software_generation": claim.software_generation,
                "cognitive_model_identity": claim.cognitive_model_identity,
                "developmental_history_boundary": claim.developmental_history_boundary,
            }
            selected.append(bounded); digests.append(str(bounded["semantic_digest"]))
        raw = CognitiveSelfModelProjection(
            PROJECTION_SCHEMA, "", "", source.reconciliation_id, source.reconciliation_digest,
            source.generation, source.tick_id, tuple(selected), tuple(c.claim_id for c in claims),
            tuple(digests), tuple(sorted({c.software_generation for c in claims if c.software_generation})),
            tuple(sorted({c.cognitive_model_identity for c in claims if c.cognitive_model_identity})),
            tuple(sorted({c.developmental_history_boundary for c in claims if c.developmental_history_boundary})),
            PROJECTION_POLICY, dict(FALSE_AUTHORITY))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="cognitive-self-model-" + digest[7:31], projection_digest=digest)

    def reconcile(self, snapshot: WorldStateSnapshot, *, tick_id: str) -> SelfModelReconciliation:
        validation = validate_snapshot(snapshot)
        if not validation.valid or snapshot.validation_posture != "valid":
            raise LongitudinalSelfModelError("invalid_world_state_snapshot:" + ",".join(validation.findings))
        if not tick_id or any(snapshot.authority.values()):
            raise LongitudinalSelfModelError("invalid_reconciliation_context")
        for fact in snapshot.facts:
            if (not fact.source.source_id or not fact.source.digest or fact.source.finding != "ok"
                    or not fact.observed_at):
                raise LongitudinalSelfModelError("missing_or_invalid_source_provenance")
            if any(bool(fact.payload.get(key)) for key in FORBIDDEN_PREDICATES):
                raise LongitudinalSelfModelError("authority_or_unsupported_claim_smuggling")

        history = self._load()
        for history_item in history:
            if history_item.snapshot_id == snapshot.snapshot_id:
                if history_item.snapshot_digest != snapshot.digest:
                    raise LongitudinalSelfModelError("snapshot_identity_digest_mismatch")
                return history_item

        generation = len(history) + 1
        previous = history[-1] if history else None
        prior_current = {claim.claim_key: claim for claim in previous.claims if claim.status in {"current", "contradicted", "unresolved"}} if previous else {}
        candidates: dict[str, list[tuple[WorldStateFact, str, Any, str]]] = {}
        for fact in snapshot.facts:
            for predicate, value, category in _fact_predicates(fact):
                if predicate in FORBIDDEN_PREDICATES:
                    raise LongitudinalSelfModelError("unsupported_predicate")
                candidates.setdefault(_claim_key(fact, predicate), []).append((fact, predicate, value, category))
        if sum(len(items) for items in candidates.values()) > MAX_CLAIMS:
            raise LongitudinalSelfModelError("claim_limit_exceeded")

        new_claims: list[SelfModelClaim] = []
        active_ids_by_key: dict[str, tuple[str, ...]] = {}
        conflict_fact_ids = {fid for conflict in snapshot.conflicts for fid in conflict.fact_ids}
        for key, items in sorted(candidates.items()):
            grouped: dict[str, list[tuple[WorldStateFact, str, Any, str]]] = {}
            for item in items:
                grouped.setdefault(json.dumps(item[2], sort_keys=True, separators=(",", ":")), []).append(item)
            contradicted = len(grouped) > 1 or any(item[0].fact_id in conflict_fact_ids for item in items)
            ids: list[str] = []
            for group in grouped.values():
                facts = [item[0] for item in group]
                predicate, value, category = group[0][1], group[0][2], group[0][3]
                cid = _claim_id(key, value, [fact.fact_id for fact in facts]); ids.append(cid)
                prior = prior_current.get(key)
                supersedes = (prior.claim_id,) if prior and prior.value != value else ()
                source_times = tuple(sorted({str(fact.observed_at) for fact in facts}))
                freshnesses = {fact.source.staleness for fact in facts}
                freshness = "stale" if freshnesses & {"stale", "expired", "undated"} else ("aging" if "aging" in freshnesses else "fresh")
                payloads = [fact.payload for fact in facts]
                def context(names: Sequence[str]) -> str | None:
                    vals = {str(payload[name]) for payload in payloads for name in names if name in payload}
                    return next(iter(vals)) if len(vals) == 1 else None
                new_claims.append(SelfModelClaim(
                    cid, key, facts[0].subject.subject_id, facts[0].subject.subject_kind,
                    predicate, value, "historical_and_current", category, facts[0].stage,
                    "contradicted" if contradicted else ("historical" if freshness == "stale" else "current"),
                    freshness, "contradicted" if contradicted else "consistent",
                    min((fact.evidence_strength for fact in facts), default="unknown"),
                    tuple(sorted({fact.source.source_id for fact in facts})),
                    tuple(sorted({fact.source.digest for fact in facts})),
                    tuple(sorted(fact.fact_id for fact in facts)), snapshot.snapshot_id, snapshot.digest,
                    source_times, prior.first_supported_generation if prior and prior.value == value else generation,
                    generation, prior.first_supported_tick if prior and prior.value == value else tick_id, tick_id,
                    supersedes, (), context(("software_generation", "runtime_generation")),
                    context(("cognitive_model_id", "serving_model", "model_id")),
                    context(("developmental_history_boundary",)),
                ))
            active_ids_by_key[key] = tuple(sorted(ids))

        if previous:
            for old in previous.claims:
                replacements = active_ids_by_key.get(old.claim_key, ())
                matching = any(claim.claim_id == old.claim_id for claim in new_claims)
                if not matching:
                    new_claims.append(replace(old, status="historical" if replacements else "withdrawn",
                                              freshness="superseded" if replacements else "stale",
                                              superseded_by=replacements, last_supported_generation=generation - 1))

        shell = SelfModelReconciliation(RECONCILIATION_SCHEMA, "", "", generation, tick_id,
                                        snapshot.snapshot_id, snapshot.digest,
                                        previous.reconciliation_id if previous else None,
                                        tuple(sorted(new_claims, key=lambda claim: (claim.claim_key, claim.claim_id, claim.status))),
                                        dict(FALSE_AUTHORITY))
        dg = _digest(_semantic(shell)); result = replace(shell, reconciliation_id="self-reconciliation-" + dg[7:31], reconciliation_digest=dg)
        self.entries.mkdir(parents=True, exist_ok=True)
        target = self.entries / f"{generation:020d}-{result.reconciliation_id}.json"
        if target.exists():
            raise LongitudinalSelfModelError("reconciliation_path_collision")
        atomic_write_json(target, asdict(result))
        return result


__all__ = ["CONFIG_SCHEMA", "FALSE_AUTHORITY", "CognitiveSelfModelProjection",
           "LongitudinalSelfModelError", "LongitudinalSelfModelOwner", "LongitudinalSelfModelRuntimeConfig",
           "SelfModelClaim", "SelfModelReconciliation", "load_runtime_config"]
