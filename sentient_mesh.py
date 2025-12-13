"""Sentient Mesh cognitive scheduler and council orchestrator."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from council_adapters.base_voice import MeshVoice, VoiceExchange

__all__ = [
    "MeshJob",
    "MeshNodeState",
    "MeshSnapshot",
    "SentientMesh",
]

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
    emotion: Mapping[str, float] = field(default_factory=dict)
    dream_state: Mapping[str, object] = field(default_factory=dict)
    advisory_only: bool = False
    attributes: Mapping[str, object] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, object]:
        return {
            "node_id": self.node_id,
            "capabilities": sorted(self.capabilities),
            "trust": round(self.trust, 3),
            "load": round(self.load, 3),
            "emotion": dict(self.emotion),
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
            if emotion is not None:
                state.emotion = dict(emotion)
            if dream_state is not None:
                state.dream_state = dict(dream_state)
            if advisory_only is not None:
                state.advisory_only = bool(advisory_only)
            if attributes is not None:
                state.attributes = dict(attributes)
            state.last_updated = time.time()
            return state

    def remove_node(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)

    # -- council transcript handling -------------------------------------
    def _session_records(self, job_id: str) -> List[VoiceExchange]:
        return self._sessions.setdefault(job_id, [])

    def _append_exchange(self, job_id: str, exchange: VoiceExchange) -> None:
        records = self._session_records(job_id)
        records.append(exchange)
        if len(records) > 120:
            del records[:-120]
        path = self._root / f"{job_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(exchange.to_dict(), sort_keys=True, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")

    # -- scheduling -------------------------------------------------------
    def cycle(self, jobs: Sequence[MeshJob]) -> MeshSnapshot:
        timestamp = time.time()
        with self._lock:
            for state in self._nodes.values():
                state.trust *= 0.9
            assignments: Dict[str, Optional[str]] = {}
            trust_vector: Dict[str, float] = {
                node_id: state.trust for node_id, state in self._nodes.items()
            }
            emotion_matrix: Dict[str, Dict[str, float]] = {
                node_id: {k: float(v) for k, v in state.emotion.items()}
                for node_id, state in self._nodes.items()
            }
            sessions_summary: Dict[str, List[Dict[str, object]]] = {}
            jobs_payload: List[Dict[str, object]] = []

            for job in jobs:
                weights_before_job = {
                    state.node_id: (float(state.trust), float(state.load))
                    for state in self._nodes.values()
                }
                for key in job.metadata.keys():
                    lowered = str(key).lower()
                    if any(token in lowered for token in ("reward", "utility", "score", "bias", "emotion", "trust")):
                        raise RuntimeError(
                            "NO_GRADIENT_INVARIANT violated: action routing received gradient-bearing metadata"
                        )
                target = self._select_node(job)
                weights_after_selection = {
                    state.node_id: (float(state.trust), float(state.load))
                    for state in self._nodes.values()
                }
                if weights_after_selection != weights_before_job:
                    raise RuntimeError(
                        "NO_GRADIENT_INVARIANT violated: selection weights mutated by metadata during routing"
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
                    "timestamp": time.time(),
                    "assignments": {},
                    "trust_vector": {node: state.trust for node, state in self._nodes.items()},
                    "emotion_matrix": {
                        node: {k: float(v) for k, v in state.emotion.items()}
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
                for key, value in state.emotion.items():
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
