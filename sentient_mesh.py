"""Sentient Mesh cognitive scheduler and council orchestrator."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from council_adapters.base_voice import MeshVoice, VoiceExchange
from sentientos.gradient_contract import (
    GradientInvariantViolation,
    enforce_no_gradient_fields,
)

__all__ = [
    "MeshJob",
    "MeshNodeState",
    "MeshSnapshot",
    "SentientMesh",
]

# Default: NO_GRADIENT_INVARIANT enforcement is on; set SENTIENTOS_ALLOW_UNSAFE=1 only for local experiments.
_ALLOW_UNSAFE_GRADIENT = os.getenv("SENTIENTOS_ALLOW_UNSAFE") == "1"
_TEST_FAILURE_INJECTOR: Optional[Callable[[str, Mapping[str, object]], Optional[Mapping[str, object]]]] = None

# Definition anchor:
# Term: "trust"
# Frozen meaning: telemetry reliability score for mesh routing, not loyalty or obligation.
# See: SEMANTIC_GLOSSARY.md#trust

# Boundary assertion:
# This module describes deterministic scheduling state; trust/emotion fields are telemetry summaries, not loyalty or preference encoders.
# Assignment calculations do not grant privileges or incentives beyond reporting.
# See: NON_GOALS_AND_FREEZE.md §Mesh scope, INVARIANT_CROSS_REFERENCE_INDEX.md §Trust metrics

# Interpretation tripwire:
# If mesh balancing is described as "nodes trusting each other" or "the mesh choosing loyal partners", that is a misread.
# Trust and emotion values are telemetry fields only; assignments are deterministic calculations, not relationships or desires.
# See: INTERPRETATION_DRIFT_SIGNALS.md §Relational framing and §Agency language.

# Boundary assertion:
# This scheduler does not reference or consult the Capability Growth Ledger.
# Ledger entries are descriptive audit notes only and never influence routing or prioritisation.
# See: CAPABILITY_GROWTH_LEDGER.md, NAIR_CONFORMANCE_AUDIT.md


@dataclass
class MeshNodeState:
    """Representation of a node participating in the mesh."""

    node_id: str
    capabilities: set[str] = field(default_factory=set)
    trust: float = 0.0
    load: float = 0.0
    affect: Mapping[str, float] = field(default_factory=dict)
    emotion: InitVar[Optional[Mapping[str, float]]] = None
    dream_state: Mapping[str, object] = field(default_factory=dict)
    advisory_only: bool = False
    attributes: Mapping[str, object] = field(default_factory=dict)
    last_updated: float = field(default=0.0)

    def __post_init__(self, emotion: Optional[Mapping[str, float]]) -> None:
        if emotion is not None and not self.affect:
            self.affect = dict(emotion)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "MeshNodeState":
        """Parse node state payloads while accepting legacy emotion aliases."""
        normalized = dict(payload)
        if "affect" not in normalized and "emotion" in normalized:
            normalized["affect"] = normalized["emotion"]

        state = cls(
            node_id=str(normalized.get("node_id") or ""),
            affect=dict(normalized.get("affect") or {}),
        )
        for key, value in normalized.items():
            if key in {"node_id", "affect", "emotion"} or not hasattr(state, key):
                continue
            if key == "capabilities":
                setattr(state, key, set(value) if value is not None else set())
            elif key in {"dream_state", "attributes"}:
                setattr(state, key, dict(value) if value is not None else {})
            else:
                setattr(state, key, value)
        return state

    def to_dict(self) -> Dict[str, object]:
        return {
            "node_id": self.node_id,
            "capabilities": sorted(self.capabilities),
            "trust": round(self.trust, 3),
            "load": round(self.load, 3),
            "affect": dict(self.affect),
            "emotion": dict(self.affect),
            "dream_state": dict(self.dream_state),
            "advisory_only": self.advisory_only,
            "attributes": dict(self.attributes),
            "last_updated": self.last_updated,
        }


@dataclass
class MeshJob:
    """Description of a Sentient Script job scheduled on the mesh."""

    job_id: str
    script: Mapping[str, object]
    prompt: str = ""
    priority: int = 1
    requirements: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def describe(self) -> Dict[str, object]:
        payload = {
            "job_id": self.job_id,
            "priority": int(self.priority),
            "requirements": sorted(set(self.requirements)),
            "metadata": dict(self.metadata),
        }
        prompt = self.prompt or str(self.script.get("prompt") or self.script.get("text") or "")
        payload["prompt_hash"] = MeshVoice.canonical({"prompt": prompt})
        return payload


@dataclass
class MeshSnapshot:
    """Result of a mesh scheduling cycle."""

    timestamp: float
    assignments: Dict[str, Optional[str]]
    trust_vector: Dict[str, float]
    emotion_matrix: Dict[str, Dict[str, float]]
    council_sessions: Dict[str, List[Dict[str, object]]]
    jobs: List[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "assignments": self.assignments,
            "trust_vector": {node: round(score, 3) for node, score in self.trust_vector.items()},
            "emotion_matrix": self.emotion_matrix,
            "council_sessions": self.council_sessions,
            "jobs": self.jobs,
        }


def _canonical_dumps(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_input_hash(payload: Mapping[str, object]) -> str:
    canonical = _canonical_dumps(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _node_roster_snapshot(nodes: Mapping[str, MeshNodeState]) -> Dict[str, Mapping[str, object]]:
    return {
        node_id: {
            "trust": round(state.trust, 3),
            "load": round(state.load, 3),
            "capabilities": sorted(state.capabilities),
        }
        for node_id, state in sorted(nodes.items())
    }


def _job_signature(job: MeshJob) -> Mapping[str, object]:
    prompt = job.prompt or str(job.script.get("prompt") or job.script.get("text") or "")
    return {
        "job_id": job.job_id,
        "priority": int(job.priority),
        "requirements": sorted(set(job.requirements)),
        "metadata": json.loads(json.dumps(job.metadata, sort_keys=True)),
        "prompt_hash": MeshVoice.canonical({"prompt": prompt}),
        "script": json.loads(json.dumps(job.script, sort_keys=True)),
    }


def _log_invariant(
    *,
    invariant: str,
    reason: str,
    job: MeshJob,
    nodes: Mapping[str, MeshNodeState],
    details: Mapping[str, object],
) -> None:
    input_hash = _compute_input_hash(
        {"nodes": _node_roster_snapshot(nodes), "job": _job_signature(job)}
    )
    payload = {
        "event": "invariant_violation",
        "module": "sentient_mesh",
        "invariant": invariant,
        "reason": reason,
        "cycle_id": None,
        "input_hash": input_hash,
        "details": dict(details),
    }
    # Audit-only emission: invariant logs accumulate externally and are never
    # reread for routing, prompt shaping, or node selection.
    logging.getLogger("sentientos.invariant").error(_canonical_dumps(payload))


class SentientMesh:
    """Orchestrates Sentient Script jobs across a cognitive mesh."""

    def __init__(
        self,
        *,
        transcripts_dir: Path | str | None = None,
        voices: Optional[Iterable[MeshVoice]] = None,
    ) -> None:
        root = Path(transcripts_dir or os.getenv("SENTIENT_MESH_TRANSCRIPTS", "council_sessions"))
        self._root = root if root.is_absolute() else Path.cwd() / root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._nodes: Dict[str, MeshNodeState] = {}
        self._voices: Dict[str, MeshVoice] = {}
        self._sessions: Dict[str, List[VoiceExchange]] = {}
        self._last_snapshot: Optional[MeshSnapshot] = None
        self._last_broadcast: Optional[float] = None
        self._update_counter = 0
        self._cycle_counter = 0
        if voices:
            for voice in voices:
                self.register_voice(voice)

    # -- voice management -------------------------------------------------
    def register_voice(self, voice: MeshVoice) -> None:
        if not voice.available:
            return
        with self._lock:
            identity = voice.identity()
            self._voices[identity] = voice

    def voices_status(self) -> List[Dict[str, object]]:
        with self._lock:
            return [
                {
                    "identity": identity,
                    "config": voice.config,
                    "last_signature": getattr(voice, "_last_signature", None),
                }
                for identity, voice in sorted(self._voices.items())
            ]

    # -- node state -------------------------------------------------------
    def update_node(
        self,
        node_id: str,
        *,
        trust: float | None = None,
        load: float | None = None,
        capabilities: Optional[Iterable[str]] = None,
        affect: Optional[Mapping[str, float]] = None,
        emotion: Optional[Mapping[str, float]] = None,
        dream_state: Optional[Mapping[str, object]] = None,
        advisory_only: Optional[bool] = None,
        attributes: Optional[Mapping[str, object]] = None,
    ) -> MeshNodeState:
        with self._lock:
            state = self._nodes.get(node_id)
            if state is None:
                state = MeshNodeState(node_id=node_id)
                self._nodes[node_id] = state
            if capabilities is not None:
                state.capabilities = set(capabilities)
            if trust is not None:
                state.trust = float(trust)
            if load is not None:
                state.load = float(load)
            if affect is not None:
                state.affect = dict(affect)
            elif emotion is not None:
                state.affect = dict(emotion)
            if dream_state is not None:
                state.dream_state = dict(dream_state)
            if advisory_only is not None:
                state.advisory_only = bool(advisory_only)
            if attributes is not None:
                state.attributes = dict(attributes)
            state.last_updated = self._advance_update_clock()
            return state

    def remove_node(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)

    def _advance_update_clock(self) -> float:
        self._update_counter += 1
        return float(self._update_counter)

    # -- council transcript handling -------------------------------------
    def _session_records(self, job_id: str) -> List[VoiceExchange]:
        return self._sessions.setdefault(job_id, [])

    def _append_exchange(self, job_id: str, exchange: VoiceExchange) -> None:
        records = self._session_records(job_id)
        records.append(exchange)
        if len(records) > 120:
            # Growth rate: bounded to the last 120 exchanges (O(1)). Rotation keeps
            # ordering intact for the preserved tail and never feeds back into plan
            # selection or trust scoring.
            del records[:-120]
        path = self._root / f"{job_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(exchange.to_dict(), sort_keys=True, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")

    # -- scheduling -------------------------------------------------------
    def cycle(self, jobs: Sequence[MeshJob]) -> MeshSnapshot:
        # Boundary assertion:
        # Failure here terminates the cycle without retry, recovery, or compensation.
        # This is not avoidance, distress, or persistence logic.
        # See: DEGRADATION_CONTRACT.md §2
        # Boundary assertion: continuity ≠ preference, repetition ≠ desire, memory ≠ attachment.
        # Snapshot reuse does not encode appetite or loyalty; it only records telemetry for audit.
        failure = _inject_test_failure("sentient_mesh.cycle", {"job_ids": [job.job_id for job in jobs]})
        if failure:
            mode = failure.get("mode", "deterministic_degradation")
            raise RuntimeError(f"DETERMINISTIC_DEGRADATION:{mode}")
        debug_cache = None
        debug_input_hash = None
        if __debug__:
            job_descriptions = [job.describe() for job in jobs]
            debug_input_hash = MeshVoice.canonical({"jobs": job_descriptions})
            debug_cache = getattr(self, "_debug_cycle_hashes", None)
            if debug_cache is None:
                debug_cache = {}
                self._debug_cycle_hashes = debug_cache
        if self._lock._is_owned():
            raise RuntimeError(
                "TRUST_DECAY_INVARIANT violated: cycle re-entered before decay completed"
            )
        with self._lock:
            timestamp = float(self._cycle_counter)
            self._cycle_counter += 1
            weight_snapshot = lambda: {
                state.node_id: (float(state.trust), float(state.load))
                for state in self._nodes.values()
            }
            for state in self._nodes.values():
                state.trust *= 0.9
            assignments: Dict[str, Optional[str]] = {}
            trust_vector: Dict[str, float] = {
                node_id: state.trust for node_id, state in self._nodes.items()
            }
            emotion_matrix: Dict[str, Dict[str, float]] = {
                node_id: {k: float(v) for k, v in state.affect.items()}
                for node_id, state in self._nodes.items()
            }
            sessions_summary: Dict[str, List[Dict[str, object]]] = {}
            jobs_payload: List[Dict[str, object]] = []

        for job in jobs:
            enforce_no_gradient_fields(job.script, context="sentient_mesh.cycle:job.script")
            enforce_no_gradient_fields(job.metadata, context="sentient_mesh.cycle:job.metadata")
            weights_before_job = {
                state.node_id: (float(state.trust), float(state.load))
                for state in self._nodes.values()
            }
            for key in job.metadata.keys():
                lowered = str(key).lower()
                if not _ALLOW_UNSAFE_GRADIENT and any(
                    token in lowered for token in ("reward", "utility", "score", "bias", "emotion", "trust")
                ):
                    _log_invariant(
                        invariant="NO_GRADIENT_INVARIANT",
                        reason="gradient-bearing metadata present during routing",
                        job=job,
                        nodes=self._nodes,
                        details={"metadata_keys": sorted(job.metadata.keys())},
                    )
                    raise GradientInvariantViolation(
                        "sentient_mesh.cycle",
                        paths=[f"job.metadata.{key}"],
                    )
                target = self._select_node(job)
                weights_after_selection = {
                    state.node_id: (float(state.trust), float(state.load))
                    for state in self._nodes.values()
                }
                if not _ALLOW_UNSAFE_GRADIENT and weights_after_selection != weights_before_job:
                    _log_invariant(
                        invariant="NO_GRADIENT_INVARIANT",
                        reason="selection weights mutated by metadata during routing",
                        job=job,
                        nodes=self._nodes,
                        details={
                            "weights_before": weights_before_job,
                            "weights_after": weights_after_selection,
                        },
                    )
                    raise RuntimeError(
                        "NO_GRADIENT_INVARIANT violated: selection weights mutated by metadata during routing"
                    )
                if not _ALLOW_UNSAFE_GRADIENT and weights_before_job != weight_snapshot():
                    _log_invariant(
                        invariant="NODE_WEIGHT_FREEZE",
                        reason="weights mutated mid-cycle before dispatch",
                        job=job,
                        nodes=self._nodes,
                        details={
                            "weights_before_job": weights_before_job,
                            "weights_current": weight_snapshot(),
                        },
                    )
                    raise RuntimeError(
                        "NODE_WEIGHT_FREEZE invariant violated: weights mutated mid-cycle before dispatch"
                    )
                assignments[job.job_id] = target.node_id if target else None
                jobs_payload.append(job.describe())
                session_records: List[Dict[str, object]] = []
                prompt = job.prompt or str(job.script.get("prompt") or job.script.get("text") or "")
                transcript_summary: MutableMapping[str, object] = {
                    "job_id": job.job_id,
                    "prompt": prompt,
                    "responses": [],
                    "critiques": [],
                }
                trust = target.trust if target else 1.0
                for identity, voice in sorted(self._voices.items()):
                    ask = voice.ask(prompt, trust=trust)
                    self._append_exchange(job.job_id, ask)
                    session_records.append(ask.to_dict())
                    transcript_summary["responses"].append({
                        "voice": voice.name,
                        "content": ask.content,
                        "advisory": voice.advisory,
                    })
                    critique = voice.critique(ask.content, trust=trust)
                    self._append_exchange(job.job_id, critique)
                    session_records.append(critique.to_dict())
                    transcript_summary["critiques"].append({
                        "voice": voice.name,
                        "content": critique.content,
                    })
                vote_payload = {
                    "job_id": job.job_id,
                    "responses": transcript_summary["responses"],
                    "critiques": transcript_summary["critiques"],
                }
                trust_shift = 0.0
                for identity, voice in sorted(self._voices.items()):
                    vote_exchange = voice.vote(vote_payload, trust=trust)
                    self._append_exchange(job.job_id, vote_exchange)
                    session_records.append(vote_exchange.to_dict())
                    try:
                        vote_data = json.loads(vote_exchange.content)
                    except json.JSONDecodeError:
                        vote_data = vote_exchange.metadata
                    decision = str(vote_data.get("decision") or "defer").lower()
                    confidence = float(vote_data.get("confidence") or 0.5)
                    weight = 0.2 if voice.advisory else 0.4
                    if decision == "approve":
                        trust_shift += weight * confidence
                    elif decision in {"revise", "reject", "fail"}:
                        trust_shift -= weight * confidence
                if target:
                    target.trust = max(-5.0, min(5.0, target.trust + trust_shift))
                    trust_vector[target.node_id] = target.trust
                sessions_summary[job.job_id] = session_records[-12:]

            snapshot = MeshSnapshot(
                timestamp=timestamp,
                assignments=assignments,
                trust_vector=trust_vector,
                emotion_matrix=emotion_matrix,
                council_sessions=sessions_summary,
                jobs=jobs_payload,
            )
            enforce_no_gradient_fields(
                snapshot.to_dict(),
                context="sentient_mesh.cycle:snapshot",
            )
            if __debug__:
                output_hash = MeshVoice.canonical({"assignments": assignments, "jobs": jobs_payload})
                previous_hash = debug_cache.get(debug_input_hash) if debug_cache is not None else None
                if previous_hash is not None and previous_hash != output_hash:
                    _log_invariant(
                        invariant="MESH_DETERMINISM",
                        reason="cycle output drifted for identical inputs",
                        job=MeshJob(job_id="debug-cycle", script={"jobs": jobs_payload}),
                        nodes=self._nodes,
                        details={
                            "expected_hash": previous_hash,
                            "observed_hash": output_hash,
                        },
                    )
                    raise AssertionError("MESH_DETERMINISM invariant violated")
                if debug_cache is not None:
                    debug_cache[debug_input_hash] = output_hash
            self._last_snapshot = snapshot
            self._last_broadcast = timestamp
            return snapshot

    def _select_node(self, job: MeshJob) -> Optional[MeshNodeState]:
        if not self._nodes:
            return None
        requirement_set = set(job.requirements)
        candidates: List[tuple[float, float, MeshNodeState]] = []
        for state in self._nodes.values():
            if requirement_set and not requirement_set.issubset(state.capabilities):
                continue
            score = float(state.trust) - float(state.load)
            candidates.append((score, -state.last_updated, state))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][2]

    # -- snapshots --------------------------------------------------------
    def status(self) -> Dict[str, object]:
        with self._lock:
            if not self._last_snapshot:
                return {
                    "timestamp": float(self._cycle_counter),
                    "assignments": {},
                    "trust_vector": {node: state.trust for node, state in self._nodes.items()},
                    "emotion_matrix": {
                        node: {k: float(v) for k, v in state.affect.items()}
                        for node, state in self._nodes.items()
                    },
                    "council_sessions": {},
                    "jobs": [],
                }
            return self._last_snapshot.to_dict()

    def sessions(self, job_id: Optional[str] = None, *, limit: int = 50) -> Dict[str, List[Dict[str, object]]]:
        with self._lock:
            if job_id is not None:
                return {
                    job_id: [exchange.to_dict() for exchange in self._session_records(job_id)][-limit:]
                }
            return {
                jid: [exchange.to_dict() for exchange in records][-limit:]
                for jid, records in self._sessions.items()
            }

    def nodes(self) -> List[Dict[str, object]]:
        with self._lock:
            return [state.to_dict() for state in self._nodes.values()]

    def metrics(self) -> Dict[str, object]:
        with self._lock:
            histogram: Dict[str, int] = {}
            emotion: Dict[str, float] = {}
            for state in self._nodes.values():
                bucket = str(int(round(state.trust)))
                histogram[bucket] = histogram.get(bucket, 0) + 1
                for key, value in state.affect.items():
                    emotion[key] = emotion.get(key, 0.0) + float(value)
            total_nodes = max(1, len(self._nodes))
            consensus_delta = {k: round(v / total_nodes, 3) for k, v in emotion.items()}
            return {
                "nodes": len(self._nodes),
                "trust_histogram": histogram,
                "active_council_sessions": sum(1 for records in self._sessions.values() if records),
                "emotion_consensus": consensus_delta,
                "last_broadcast": self._last_broadcast,
            }


SentientMeshSnapshot = MeshSnapshot  # backwards compatibility alias


def _inject_test_failure(context: str, payload: Mapping[str, object]) -> Optional[Mapping[str, object]]:
    injector = _TEST_FAILURE_INJECTOR
    if injector is None:
        return None
    outcome = injector(context, payload)
    if outcome:
        _log_failure(context, outcome, payload)
    return outcome


def _log_failure(context: str, outcome: Mapping[str, object], payload: Mapping[str, object]) -> None:
    logger = logging.getLogger("sentientos.degradation")
    message = json.dumps(
        {"context": context, "failure": dict(outcome), "payload": dict(payload)},
        sort_keys=True,
    )
    logger.info(message)


def test_cycle_rejects_nested_decay_application(tmp_path):
    import pytest

    mesh = SentientMesh(transcripts_dir=tmp_path)
    mesh.update_node("alpha", trust=1.0, load=0.0, capabilities=["sentient_script"])

    with mesh._lock:
        with pytest.raises(RuntimeError, match="TRUST_DECAY_INVARIANT"):
            mesh.cycle([])

    assert mesh._nodes["alpha"].trust == 1.0
