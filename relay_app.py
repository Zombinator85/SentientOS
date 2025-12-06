"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

import base64
import datetime
import hashlib
import ipaddress
import json
import logging
import os
import queue
import random
import secrets
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple
from types import SimpleNamespace

from dotenv import load_dotenv

from sentientos.privilege import require_admin_banner, require_lumos_approval

load_dotenv()

require_admin_banner()
if not (os.getenv("LUMOS_AUTO_APPROVE") == "1" or os.getenv("SENTIENTOS_HEADLESS") == "1"):
    require_lumos_approval()
else:
    print("[Lumos] Blessing auto-approved (headless mode).")

from logging_config import get_log_path

try:
    from flask import Flask, Response, jsonify, request
except ImportError:  # pragma: no cover - runtime fallback
    from flask_stub import Flask, Response, jsonify, request

import epu
import memory_manager as mm
from api import actuator
from emotions import empty_emotion_vector
from emotion_utils import dominant_emotion
from memory_manager import write_mem
from utils import chunk_message
import mem_admin
import mem_export
import memory_governor as governor
import secure_memory_storage as secure_store
from safety_log import count_recent_events, log_event
try:
    import dream_loop
except Exception as exc:  # pragma: no cover - optional dependency for tests
    _logger = logging.getLogger(__name__)
    _logger.warning("[Relay] dream_loop unavailable (%s); using stub.", exc)

    class _DreamLoopStub:
        """Fallback stub when dream_loop dependencies (e.g. psutil) are missing."""

        @staticmethod
        def status() -> Dict[str, Any]:
            return {"active": False, "enabled": False}

        @staticmethod
        def is_enabled() -> bool:
            return False

    dream_loop = _DreamLoopStub()  # type: ignore[assignment]
from nacl.signing import VerifyKey

from sentient_verifier import (
    ConsensusVerdict,
    SentientVerifier,
    VerificationReport,
    Vote,
    merge_votes,
    merkle_root_for_report,
    verify_vote_signatures,
)
try:
    from sentientscript import (
        ScriptExecutionError,
        SentientScriptInterpreter,
        list_script_history,
        load_safety_shadow,
    )
except Exception as exc:  # pragma: no cover - optional dependency for tests
    _logger = logging.getLogger(__name__)
    _logger.warning("[Relay] sentientscript unavailable (%s); using stub.", exc)

    class ScriptExecutionError(RuntimeError):
        pass

    class _StubSigner:
        def sign(self, script: Mapping[str, Any]) -> Mapping[str, Any]:
            return {"signed": True, "script": script}

        def verify(self, script: Mapping[str, Any]) -> bool:
            return True

    class SentientScriptInterpreter:  # type: ignore[override]
        def __init__(self) -> None:
            self.history: List[Mapping[str, Any]] = []
            self.signer = _StubSigner()

        def build_shadow(self, kind: str, text: str) -> Mapping[str, Any]:
            shadow = {"kind": kind, "text": text, "stub": True}
            self.history.append(shadow)
            return shadow

        def load_script(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            return payload

        def execute(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
            raise ScriptExecutionError("SentientScript unavailable in test mode")

    def list_script_history(
        *, limit: int, history: Sequence[Mapping[str, Any]]
    ) -> List[Mapping[str, Any]]:
        return list(history)[-limit:]

    def load_safety_shadow(
        run_id: str, history: Sequence[Mapping[str, Any]]
    ) -> Optional[Mapping[str, Any]]:
        return None

try:
    import requests
except Exception as exc:  # pragma: no cover - optional dependency for tests
    _logger = logging.getLogger(__name__)
    _logger.warning("[Relay] requests unavailable (%s); using stub.", exc)

    class _RequestsStubException(Exception):
        pass

    def _requests_stub_post(*_args: Any, **_kwargs: Any):
        raise _RequestsStubException("requests unavailable")

    requests = SimpleNamespace(post=_requests_stub_post, RequestException=_RequestsStubException)

from distributed_memory import decrypt_reflection_payload, encode_payload, synchronizer
from epu_core import get_global_state
from gpu_autosetup import configure_stt
from node_discovery import discovery
from node_registry import NODE_TOKEN, NodeRecord, RoundRobinRouter, registry
from pairing_service import pairing_service
from stt_service import StreamingTranscriber
from tts_service import TtsStreamer
from watchdog_service import WatchdogService
from webrtc_bridge import WebRTCSessionManager
from verifier_store import VerifierStore
from council_adapters import DeepSeekVoice, LocalVoice, OpenAIVoice
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import MeshJob, MeshSnapshot, SentientMesh


def _initialise_mesh() -> tuple[SentientMesh, SentientAutonomyEngine]:
    voices = [LocalVoice()]
    mesh = SentientMesh(voices=voices)
    for factory in (DeepSeekVoice, OpenAIVoice):
        try:
            mesh.register_voice(factory())
        except Exception as exc:  # pragma: no cover - optional dependencies
            logging.getLogger(__name__).debug(
                "[Mesh] Skipping %s voice: %s", factory.__name__, exc
            )
    autonomy = SentientAutonomyEngine(mesh)
    if os.getenv("SENTIENT_AUTONOMY_ENABLED", "0") == "1":
        autonomy.start()
    governor.set_mesh_metrics_provider(mesh.metrics)
    return mesh, autonomy


app = Flask(__name__)
log_level = os.getenv("RELAY_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
LOGGER = logging.getLogger(__name__)

_MESH, AUTONOMY = _initialise_mesh()

RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")
_REMOTE_TIMEOUT = float(os.getenv("SENTIENTOS_REMOTE_TIMEOUT", "10"))
_NODE_HEADER = "X-Node-Token"
_NODE_ID_HEADER = "X-Node-Id"
_ROLE = os.getenv("SENTIENTOS_ROLE", "core").strip().lower()
_UPSTREAM_CORE = (os.getenv("UPSTREAM_CORE") or "").rstrip("/")
_STREAM_TIMEOUT = float(os.getenv("STREAM_TIMEOUT_S", "30"))
_WEBUI_ENABLED = os.getenv("WEBUI_ENABLED", "1") != "0"
_WEBUI_ROOT = Path(os.getenv("WEBUI_ROOT", "apps/webui"))
if not _WEBUI_ROOT.is_absolute():
    _WEBUI_ROOT = Path.cwd() / _WEBUI_ROOT
_WEBUI_AUTH_MODE = os.getenv("WEBUI_AUTH_MODE", "cookie").lower()
_PROCESS_START = time.time()
_CONSOLE_ENABLED = os.getenv("CONSOLE_ENABLED", "0") != "0"
_VOICE_ENABLED = os.getenv("VOICE_ENABLED", "0") != "0"
_VAD_SENSITIVITY = float(os.getenv("VAD_SENSITIVITY", "0.6"))
_RELAY_HOST = os.getenv("RELAY_HOST", "0.0.0.0")
_RELAY_PORT = int(os.getenv("RELAY_PORT", "3928"))
_ADMIN_TTL = max(60, int(float(os.getenv("ADMIN_SESSION_TTL_MIN", "120")) * 60))
_CSRF_ENABLED = os.getenv("CSRF_ENABLED", "0") != "0"
_ADMIN_ALLOWLIST_RAW = [
    entry.strip()
    for entry in (os.getenv("ADMIN_ALLOWLIST") or "127.0.0.1/32").split(",")
    if entry.strip()
]
_ADMIN_ALLOWLIST: list = []
for entry in _ADMIN_ALLOWLIST_RAW:
    try:
        _ADMIN_ALLOWLIST.append(ipaddress.ip_network(entry, strict=False))
    except ValueError:
        logging.warning("[Admin] Ignoring invalid CIDR entry: %s", entry)

_CONSOLE_ROOT = (_WEBUI_ROOT / "console").resolve()
_PWA_ROOT = (_WEBUI_ROOT / "pwa").resolve()

try:
    _ICE_SERVERS = json.loads(os.getenv("WEBRTC_ICE_SERVERS", "[]"))
    if not isinstance(_ICE_SERVERS, list):
        _ICE_SERVERS = []
except json.JSONDecodeError:
    _ICE_SERVERS = []

NODE_ROUTER = RoundRobinRouter(registry)
WATCHDOG = WatchdogService(interval=float(os.getenv("WATCHDOG_INTERVAL_S", "5")))
if _VOICE_ENABLED:
    _STT_CONFIG = configure_stt()
    _STT_PIPELINE = StreamingTranscriber(vad_sensitivity=_VAD_SENSITIVITY)
    _TTS_PIPELINE = TtsStreamer(voice=os.getenv("TTS_VOICE", "en_US-amy-medium"))
    _WEBRTC_MANAGER = WebRTCSessionManager(ttl_seconds=_ADMIN_TTL, ice_servers=_ICE_SERVERS)
else:
    _STT_CONFIG = None
    _STT_PIPELINE = None
    _TTS_PIPELINE = None
_WEBRTC_MANAGER = None


_VERIFIER_STORE = VerifierStore.default()
_SENTIENT_VERIFIER = SentientVerifier(store=_VERIFIER_STORE)

@dataclass
class _ConsensusState:
    job_id: str
    quorum_k: int
    quorum_n: int
    participants: List[str]
    votes: Dict[str, Vote] = field(default_factory=dict)
    consensus: Optional[ConsensusVerdict] = None
    finalized: bool = False
    rewarded_nodes: Set[str] = field(default_factory=set)
    started_at: float = field(default_factory=time.time)
    status: str = "RUNNING"
    retries_by_node: Dict[str, int] = field(default_factory=dict)
    retry_after: Dict[str, float] = field(default_factory=dict)
    errors_by_node: Dict[str, str] = field(default_factory=dict)
    resumed: bool = False
    last_update: float = field(default_factory=time.time)
    cancel_reason: Optional[str] = None
    forced_by: Optional[str] = None
    force_reason: Optional[str] = None

    def register_vote(self, vote: Vote) -> ConsensusVerdict:
        if self.status != "RUNNING":
            raise RuntimeError("consensus job is not accepting votes")
        self.votes[vote.voter_node] = vote
        updated_participants = set(self.participants)
        updated_participants.add(vote.voter_node)
        self.participants = sorted(updated_participants)
        quorum_n = max(self.quorum_n, len(self.participants))
        merged = merge_votes(tuple(self.votes.values()), self.quorum_k, quorum_n)
        self.consensus = merged
        self.last_update = time.time()
        return merged

    def snapshot(self) -> Dict[str, Any]:
        provisional = "INCONCLUSIVE"
        if self.consensus is not None:
            provisional = self.consensus.final_verdict
        votes_payload = [vote.to_dict() for vote in sorted(self.votes.values(), key=lambda v: (v.voter_node, v.ts))]
        payload: Dict[str, Any] = {
            "job_id": self.job_id,
            "quorum_k": self.quorum_k,
            "quorum_n": self.quorum_n,
            "received": len(self.votes),
            "needed": max(0, self.quorum_k - len(self.votes)),
            "participants": list(self.participants),
            "latest_votes": votes_payload,
            "provisional_verdict": provisional,
            "finalized": self.finalized,
            "status": self.status,
            "last_update": self.last_update,
            "retries_by_node": dict(self.retries_by_node),
            "errors_by_node": {node: err for node, err in self.errors_by_node.items() if err},
            "retry_after": dict(self.retry_after),
            "started_at": self.started_at,
            "resumed": self.resumed,
        }
        if self.cancel_reason:
            payload["cancel_reason"] = self.cancel_reason
        if self.forced_by:
            payload["forced_by"] = self.forced_by
        if self.force_reason:
            payload["force_reason"] = self.force_reason
        if self.consensus is not None and self.consensus.final_verdict != "INCONCLUSIVE":
            payload["final_verdict"] = self.consensus.final_verdict
        return payload

    def to_payload(self) -> Dict[str, Any]:
        payload = self.snapshot()
        payload["votes"] = [vote.to_dict() for vote in self.votes.values()]
        if self.consensus is not None:
            payload["consensus"] = self.consensus.to_dict()
        payload["finalized"] = self.finalized
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "_ConsensusState":
        job_id = str(payload.get("job_id") or "")
        quorum_k = int(payload.get("quorum_k") or 0)
        quorum_n = int(payload.get("quorum_n") or 0)
        participants_obj = payload.get("participants")
        participants = [str(p) for p in participants_obj] if isinstance(participants_obj, Sequence) else []
        votes_payload = payload.get("votes")
        votes: Dict[str, Vote] = {}
        if isinstance(votes_payload, Sequence):
            for entry in votes_payload:
                if isinstance(entry, Mapping):
                    vote = _vote_from_payload(entry)
                    votes[vote.voter_node] = vote
        consensus_payload = payload.get("consensus")
        consensus = _consensus_from_payload(consensus_payload) if isinstance(consensus_payload, Mapping) else None
        rewarded = payload.get("rewarded_nodes")
        rewarded_nodes: Set[str] = set()
        if isinstance(rewarded, Sequence):
            rewarded_nodes = {str(node) for node in rewarded if isinstance(node, str)}
        started_at = payload.get("started_at")
        try:
            started = float(started_at) if started_at is not None else time.time()
        except (TypeError, ValueError):
            started = time.time()
        state = cls(
            job_id=job_id,
            quorum_k=quorum_k,
            quorum_n=quorum_n,
            participants=list(participants),
            votes=votes,
            consensus=consensus,
            finalized=bool(payload.get("finalized")),
            rewarded_nodes=rewarded_nodes,
            started_at=started,
        )
        state.status = str(payload.get("status") or "RUNNING").upper()
        if state.status not in {"RUNNING", "CANCELED", "FINALIZED"}:
            state.status = "RUNNING"
        retries = payload.get("retries_by_node")
        if isinstance(retries, Mapping):
            state.retries_by_node = {str(k): int(v) for k, v in retries.items() if isinstance(k, str)}
        retry_after = payload.get("retry_after")
        if isinstance(retry_after, Mapping):
            mapping: Dict[str, float] = {}
            for key, value in retry_after.items():
                try:
                    mapping[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            state.retry_after = mapping
        errors = payload.get("errors_by_node")
        if isinstance(errors, Mapping):
            state.errors_by_node = {str(k): str(v) for k, v in errors.items() if isinstance(k, str)}
        resumed = payload.get("resumed")
        state.resumed = bool(resumed)
        last_update = payload.get("last_update")
        try:
            state.last_update = float(last_update) if last_update is not None else time.time()
        except (TypeError, ValueError):
            state.last_update = time.time()
        cancel_reason = payload.get("cancel_reason")
        if isinstance(cancel_reason, str):
            state.cancel_reason = cancel_reason
        forced_by = payload.get("forced_by")
        if isinstance(forced_by, str):
            state.forced_by = forced_by
        force_reason = payload.get("force_reason")
        if isinstance(force_reason, str):
            state.force_reason = force_reason
        return state

    def record_retry(self, hostname: str, *, success: bool, error: Optional[str] = None, now: Optional[float] = None) -> None:
        host = str(hostname)
        moment = now if now is not None else time.time()
        if success:
            self.retries_by_node.pop(host, None)
            self.retry_after.pop(host, None)
            if error:
                self.errors_by_node[host] = error
            else:
                self.errors_by_node.pop(host, None)
            self.last_update = moment
            return
        attempts = self.retries_by_node.get(host, 0) + 1
        attempts = min(attempts, _SOLICIT_RETRY_MAX)
        self.retries_by_node[host] = attempts
        if attempts >= _SOLICIT_RETRY_MAX:
            self.retry_after[host] = float("inf")
        else:
            delay = _retry_delay(attempts)
            self.retry_after[host] = moment + delay
        if error:
            self.errors_by_node[host] = error
        self.last_update = moment

    def allows_retry(self, hostname: str, now: Optional[float] = None) -> bool:
        if self.status != "RUNNING":
            return False
        limit = self.retry_after.get(hostname)
        if limit is None:
            return True
        if limit == float("inf"):
            return False
        moment = now if now is not None else time.time()
        return limit <= moment

    def has_exhausted_retries(self, hostname: str) -> bool:
        return self.retries_by_node.get(hostname, 0) >= _SOLICIT_RETRY_MAX

    def cancel(self, *, reason: Optional[str] = None) -> None:
        self.status = "CANCELED"
        self.cancel_reason = reason
        self.force_reason = None
        self.last_update = time.time()

    def mark_finalized(self, *, actor: Optional[str] = None) -> None:
        self.status = "FINALIZED"
        if actor:
            self.forced_by = actor
        self.cancel_reason = None
        self.last_update = time.time()


_CONSENSUS_LOCK = threading.RLock()
_CONSENSUS_STATES: Dict[str, _ConsensusState] = {}
_MESH_RATE_TRACKER: Dict[str, deque] = {}
_MESH_RATE_WINDOW = 60.0
_MESH_RATE_LIMIT = 120
_MAX_MESH_PARTICIPATION = 10
_LOCAL_ACTIVE_SOLICITATIONS: Set[str] = set()

_SOLICIT_RETRY_BASE = 0.5
_SOLICIT_RETRY_FACTOR = 1.6
_SOLICIT_RETRY_JITTER = 0.2
_SOLICIT_RETRY_MAX = 6


def _retry_delay(attempt: int) -> float:
    base = _SOLICIT_RETRY_BASE * (_SOLICIT_RETRY_FACTOR ** max(0, attempt - 1))
    jitter = random.uniform(0.0, _SOLICIT_RETRY_JITTER)
    return base + jitter


def _current_hostname() -> str:
    return registry.local_hostname or socket.gethostname()


def _registry_verify_key(hostname: str) -> Optional[VerifyKey]:
    record = registry.get(hostname)
    if record is None:
        return None
    pubkey = record.capabilities.get("verifier_pubkey")
    if not isinstance(pubkey, str) or not pubkey:
        return None
    try:
        return VerifyKey(base64.b64decode(pubkey))
    except Exception:
        return None


def _canonical_dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _mesh_signature_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": payload.get("job_id"),
        "script_hash": payload.get("script_hash"),
        "quorum_k": payload.get("quorum_k"),
        "quorum_n": payload.get("quorum_n"),
        "requester": payload.get("requester"),
    }


def _verify_mesh_signature(payload: Mapping[str, Any]) -> bool:
    requester = payload.get("requester")
    signature = payload.get("requester_sig")
    if not isinstance(requester, str) or not requester:
        return False
    if not isinstance(signature, str) or not signature:
        return False
    verify_key = _registry_verify_key(requester)
    if verify_key is None:
        return False
    try:
        verify_key.verify(
            _canonical_dump(_mesh_signature_payload(payload)).encode("utf-8"),
            base64.b64decode(signature),
        )
    except Exception:
        return False
    return True


def _mesh_rate_allow(requester: str) -> bool:
    now = time.time()
    history = _MESH_RATE_TRACKER.setdefault(requester, deque())
    while history and now - history[0] > _MESH_RATE_WINDOW:
        history.popleft()
    if len(history) >= _MESH_RATE_LIMIT:
        return False
    history.append(now)
    return True


def _select_consensus_participants(quorum_n: int, requested: Optional[Sequence[str]] = None) -> List[str]:
    participants: List[str] = []
    local_host = _current_hostname()
    if local_host:
        participants.append(local_host)
    if requested:
        for entry in requested:
            if isinstance(entry, str) and entry:
                participants.append(entry)
    if len(participants) < quorum_n:
        for record in registry.iter_remote_nodes(trusted_only=True):
            if record.hostname == local_host:
                continue
            if record.is_suspended:
                continue
            if record.capabilities.get("verifier_capable") is not True:
                continue
            participants.append(record.hostname)
            if len(participants) >= quorum_n:
                break
    unique = []
    seen: Set[str] = set()
    for entry in participants:
        if entry in seen:
            continue
        seen.add(entry)
        unique.append(entry)
        if len(unique) >= quorum_n:
            break
    return sorted(unique)


def _get_or_create_consensus_state(job_id: str, quorum_k: int, quorum_n: int, participants: Sequence[str]) -> _ConsensusState:
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(job_id)
        dirty = False
        if state is None:
            state = _ConsensusState(job_id=job_id, quorum_k=quorum_k, quorum_n=quorum_n, participants=list(participants))
            _CONSENSUS_STATES[job_id] = state
            dirty = True
        else:
            prior_participants = set(state.participants)
            state.quorum_k = quorum_k
            state.quorum_n = max(quorum_n, state.quorum_n)
            state.participants = sorted(set(state.participants) | set(participants))
            if set(state.participants) != prior_participants:
                dirty = True
        if dirty:
            state.last_update = time.time()
            _persist_consensus_state(state)
        return state


def _broadcast_consensus_update(state: _ConsensusState) -> None:
    _notify_admin("verifier_consensus_update", state.snapshot())


def _persist_consensus_state(state: _ConsensusState) -> None:
    try:
        _VERIFIER_STORE.persist_consensus_state(state.job_id, state.to_payload())
    except Exception:  # pragma: no cover - persistence is best effort
        LOGGER.warning("[Consensus] failed to persist state for %s", state.job_id, exc_info=True)


def _ensure_consensus_state(job_id: str) -> Optional[_ConsensusState]:
    state = _CONSENSUS_STATES.get(job_id)
    if state is not None:
        return state
    payload = _VERIFIER_STORE.load_consensus_state(job_id)
    if payload is None:
        return None
    try:
        state = _ConsensusState.from_payload(payload)
    except Exception:  # pragma: no cover - defensive parsing
        LOGGER.warning("[Consensus] failed to parse stored state for %s", job_id, exc_info=True)
        return None
    state.resumed = True
    _CONSENSUS_STATES[job_id] = state
    return state


def _shadow_event(code: str, *, job_id: str, actor: str, reason: Optional[str]) -> None:
    actor_token = actor.strip().replace(" ", "_") or "unknown"
    reason_token = (reason.strip().replace(" ", "_") if reason else "none")
    payload = f"{code}:{job_id}:{actor_token}:{reason_token}"
    log_event(payload[:200])


def _vote_from_payload(payload: Mapping[str, Any]) -> Vote:
    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        metrics_map: Mapping[str, Any] = metrics
    else:
        metrics_map = {}
    return Vote(
        job_id=str(payload.get("job_id") or ""),
        script_hash=str(payload.get("script_hash") or ""),
        local_verdict=str(payload.get("local_verdict") or ""),
        proof_hash=payload.get("proof_hash"),
        merkle_root=payload.get("merkle_root"),
        metrics=metrics_map,
        voter_node=str(payload.get("voter_node") or ""),
        voter_sig=str(payload.get("voter_sig") or ""),
        ts=float(payload.get("ts") or time.time()),
    )


def _consensus_from_payload(payload: Mapping[str, Any]) -> ConsensusVerdict:
    votes_payload = payload.get("votes")
    votes: List[Vote] = []
    if isinstance(votes_payload, Sequence):
        for entry in votes_payload:
            if isinstance(entry, Mapping):
                votes.append(_vote_from_payload(entry))
    finalized_at = payload.get("finalized_at")
    try:
        finalized = float(finalized_at) if finalized_at is not None else None
    except (TypeError, ValueError):
        finalized = None
    return ConsensusVerdict(
        job_id=str(payload.get("job_id") or ""),
        script_hash=str(payload.get("script_hash") or ""),
        quorum_k=int(payload.get("quorum_k") or 0),
        quorum_n=int(payload.get("quorum_n") or 0),
        votes=tuple(votes),
        final_verdict=str(payload.get("final_verdict") or "INCONCLUSIVE"),
        merkle_root=payload.get("merkle_root"),
        bundle_sig=payload.get("bundle_sig"),
        finalized_at=finalized,
    )


def resume_inflight_jobs() -> None:
    stored = _VERIFIER_STORE.list_consensus_states()
    if not stored:
        return
    restored: List[_ConsensusState] = []
    with _CONSENSUS_LOCK:
        for job_id, payload in stored.items():
            status = str(payload.get("status") or "RUNNING").upper()
            if status in {"FINALIZED", "CANCELED"}:
                continue
            try:
                state = _ConsensusState.from_payload(payload)
            except Exception:  # pragma: no cover - defensive parsing
                LOGGER.warning("[Consensus] failed to restore state for %s", job_id, exc_info=True)
                continue
            state.resumed = True
            _CONSENSUS_STATES[job_id] = state
            restored.append(state)
            if state.consensus is not None and state.consensus.final_verdict != "INCONCLUSIVE":
                _maybe_finalise_consensus(state)
            else:
                _persist_consensus_state(state)
    for state in restored:
        LOGGER.info("[Consensus] resumed job %s with %d votes", state.job_id, len(state.votes))
        _broadcast_consensus_update(state)


resume_inflight_jobs()


def _maybe_finalise_consensus(state: _ConsensusState, *, actor: Optional[str] = None) -> Optional[ConsensusVerdict]:
    if state.consensus is None:
        return None
    if state.consensus.final_verdict == "INCONCLUSIVE":
        return None
    if state.finalized and state.consensus.bundle_sig:
        return state.consensus
    signed = _SENTIENT_VERIFIER.sign_consensus(state.consensus)
    state.consensus = signed
    state.finalized = True
    state.mark_finalized(actor=actor)
    _VERIFIER_STORE.store_consensus(signed)
    for vote in state.votes.values():
        if vote.voter_node in state.rewarded_nodes:
            continue
        registry.apply_consensus_outcome(vote.voter_node, vote_verdict=vote.local_verdict, final_verdict=signed.final_verdict)
        state.rewarded_nodes.add(vote.voter_node)
    _persist_consensus_state(state)
    return signed


@dataclass
class _VoiceSessionState:
    session_id: str
    hostname: str
    transcriber: StreamingTranscriber
    utterances: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_event: float = field(default_factory=time.time)


class _SseHub:
    def __init__(self, *, max_queue: int = 32) -> None:
        self._max_queue = max(4, int(max_queue))
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = {"event": event, "data": data or {}, "timestamp": time.time()}
        stale: list[queue.Queue] = []
        with self._lock:
            for subscriber in list(self._subscribers):
                try:
                    subscriber.put_nowait(payload)
                except queue.Full:
                    stale.append(subscriber)
            for subscriber in stale:
                self._subscribers.discard(subscriber)


class _RateLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = max(1, int(limit))
        self._window = max(1.0, float(window_seconds))
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: Optional[float] = None) -> bool:
        moment = now or time.time()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and moment - events[0] > self._window:
                events.popleft()
            if len(events) >= self._limit:
                return False
            events.append(moment)
        return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_ADMIN_EVENTS = _SseHub()
_SCRIPT_INTERPRETER = SentientScriptInterpreter()
_VOICE_SESSIONS: dict[str, _VoiceSessionState] = {}
_VOICE_LOCK = threading.Lock()
_VOICE_IDLE_TIMEOUT = float(os.getenv("VOICE_SESSION_IDLE_S", "120"))
_REFLECTION_SYNC_LOG = get_log_path("reflection_sync.jsonl", "REFLECTION_SYNC_LOG")
_RECENT_REFLECTION_SYNC_IDS: deque[str] = deque(maxlen=200)
_VERIFIER_RATE_LIMIT = _RateLimiter(limit=60, window_seconds=60.0)
_MAX_VERIFIER_BUNDLE_BYTES = 5_000_000
_MAX_VERIFIER_STEPS = 1_000


if not hasattr(registry, "_relay_original_register_or_update"):
    registry._relay_original_register_or_update = registry.register_or_update  # type: ignore[attr-defined]
_registry_register_or_update = registry._relay_original_register_or_update  # type: ignore[attr-defined]
if not hasattr(registry, "_relay_original_record_voice_activity"):
    registry._relay_original_record_voice_activity = registry.record_voice_activity  # type: ignore[attr-defined]
_registry_record_voice_activity = registry._relay_original_record_voice_activity  # type: ignore[attr-defined]
if not hasattr(registry, "_relay_original_set_trust_level"):
    registry._relay_original_set_trust_level = registry.set_trust_level  # type: ignore[attr-defined]
_registry_set_trust_level = registry._relay_original_set_trust_level  # type: ignore[attr-defined]


def _local_node_id() -> str:
    node_id = registry.local_hostname
    if node_id:
        return node_id
    return socket.gethostname()


def _notify_admin(event: str, data: Optional[Dict[str, Any]] = None) -> None:
    if not _CONSOLE_ENABLED:
        return
    _ADMIN_EVENTS.publish(event, data or {})


def _mesh_refresh_from_registry() -> None:
    try:
        nodes = registry.active_nodes()
    except Exception:  # pragma: no cover - defensive
        return
    for record in nodes:
        node_id = str(record.get("hostname") or record.get("id") or "").strip()
        if not node_id:
            continue
        capabilities_raw = record.get("capabilities") or {}
        if isinstance(capabilities_raw, Mapping):
            capabilities = [
                key
                for key, value in capabilities_raw.items()
                if value not in (None, False, "")
            ]
        elif isinstance(capabilities_raw, (list, tuple)):
            capabilities = [str(item) for item in capabilities_raw]
        else:
            capabilities = []
        emotion_vector = record.get("emotion") or record.get("emotions") or {}
        dream_state = record.get("dream_state") or record.get("dream") or {}
        load = record.get("load") or record.get("jobs_inflight") or 0.0
        trust = record.get("trust_score") or 0.0
        AUTONOMY_HINT = {
            "roles": record.get("roles", []),
            "advisory": record.get("trust_level"),
        }
        _MESH.update_node(
            node_id,
            trust=float(trust),
            load=float(load),
            capabilities=capabilities,
            emotion=emotion_vector if isinstance(emotion_vector, Mapping) else {},
            dream_state=dream_state if isinstance(dream_state, Mapping) else {},
            attributes=AUTONOMY_HINT,
        )
    local_id = _local_node_id()
    if local_id:
        _MESH.update_node(
            local_id,
            capabilities=["local"],
            attributes={"roles": ["core"]},
        )


def _mesh_snapshot_payload(snapshot: Optional[MeshSnapshot] = None) -> Dict[str, object]:
    if snapshot is None:
        data = _MESH.status()
    else:
        data = snapshot.to_dict()
    payload = dict(data)
    payload["voices"] = _MESH.voices_status()
    payload["metrics"] = _MESH.metrics()
    payload["nodes"] = _MESH.nodes()
    try:
        dream_state = dream_loop.status()
        payload["metrics"]["remote_reflections"] = dream_state.get("remote_reflections", 0)
    except Exception:  # pragma: no cover - defensive
        pass
    return payload


def _broadcast_mesh_update(snapshot: Mapping[str, object] | MeshSnapshot) -> None:
    if isinstance(snapshot, MeshSnapshot):
        payload = _mesh_snapshot_payload(snapshot)
    else:
        payload = dict(snapshot)
    _notify_admin("mesh_update", payload)


governor.set_reflection_broadcast(lambda event, data: _notify_admin(event, dict(data)))


def _create_transcriber() -> StreamingTranscriber:
    if _STT_PIPELINE is not None:
        return StreamingTranscriber(vad_sensitivity=_STT_PIPELINE.vad_sensitivity)
    return StreamingTranscriber(vad_sensitivity=_VAD_SENSITIVITY)


def _ensure_voice_session(session_id: str, hostname: str) -> _VoiceSessionState:
    with _VOICE_LOCK:
        session = _VOICE_SESSIONS.get(session_id)
        if session is None:
            session = _VoiceSessionState(
                session_id=session_id,
                hostname=hostname,
                transcriber=_create_transcriber(),
            )
            _VOICE_SESSIONS[session_id] = session
        elif hostname and session.hostname != hostname:
            session.hostname = hostname
        return session


def _prune_voice_sessions(now: float) -> None:
    if not _VOICE_SESSIONS:
        return
    expired: list[_VoiceSessionState] = []
    with _VOICE_LOCK:
        for session in list(_VOICE_SESSIONS.values()):
            if now - session.last_event >= _VOICE_IDLE_TIMEOUT:
                expired.append(session)
    for session in expired:
        _complete_voice_session(session, reason="idle_timeout")


def _complete_voice_session(
    session: _VoiceSessionState,
    *,
    reason: str,
    flush: bool = True,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> str:
    if flush:
        for event in session.transcriber.flush():
            if event.text:
                session.utterances.append(event.text)
            if session.hostname:
                _registry_record_voice_activity(session.hostname, timestamp=event.timestamp)
                _notify_admin(
                    "voice-activity",
                    {"hostname": session.hostname, "timestamp": event.timestamp},
                )
                session.last_event = max(session.last_event, event.timestamp)
    summary = " ".join(session.utterances).strip()
    with _VOICE_LOCK:
        _VOICE_SESSIONS.pop(session.session_id, None)
    if summary:
        meta = {"session_id": session.session_id, "reason": reason, "utterances": len(session.utterances)}
        if extra_meta:
            meta.update(extra_meta)
        register_voice_session(summary, hostname=session.hostname, meta=meta)
        _notify_admin("voice-session", {"session_id": session.session_id})
    return summary


def _consume_transcription_events(
    session: _VoiceSessionState,
    hostname: str,
    events,
) -> list[Dict[str, Any]]:
    collected: list[Dict[str, Any]] = []
    for event in events:
        payload = {"text": event.text, "final": bool(event.final), "timestamp": event.timestamp}
        if event.text:
            session.last_event = max(session.last_event, event.timestamp)
            if event.final:
                session.utterances.append(event.text)
        if hostname:
            _registry_record_voice_activity(hostname, timestamp=event.timestamp)
            _notify_admin(
                "voice-activity",
                {"hostname": hostname, "timestamp": event.timestamp},
            )
        collected.append(payload)
    return collected


def _emit_node_update(record) -> None:
    if not record:
        return
    try:
        payload = {
            "hostname": record.hostname,
            "trust_level": getattr(record, "trust_level", None),
        }
    except AttributeError:
        payload = {}
    _notify_admin("nodes", payload)


def _register_or_update_with_event(*args, **kwargs):  # type: ignore[override]
    record = _registry_register_or_update(*args, **kwargs)
    if record:
        _emit_node_update(record)
    return record


def _set_trust_level_with_event(*args, **kwargs):  # type: ignore[override]
    record = _registry_set_trust_level(*args, **kwargs)
    if record:
        _emit_node_update(record)
    return record


def _record_voice_activity_with_event(*args, **kwargs):  # type: ignore[override]
    record = _registry_record_voice_activity(*args, **kwargs)
    if record:
        _notify_admin(
            "voice-activity",
            {"hostname": record.hostname, "timestamp": record.last_voice_activity},
        )
    return record


registry.register_or_update = _register_or_update_with_event  # type: ignore[assignment]
registry.set_trust_level = _set_trust_level_with_event  # type: ignore[assignment]
registry.record_voice_activity = _record_voice_activity_with_event  # type: ignore[assignment]


class _AdminStateWatcher(threading.Thread):
    def __init__(self, *, interval: float = 2.0) -> None:
        super().__init__(daemon=True)
        self._interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._last_snapshot: Optional[Dict[str, Any]] = None

    def stop(self) -> None:
        self._stop.set()

    def _snapshot(self) -> Dict[str, Any]:
        nodes_summary: list[Dict[str, Any]] = []
        for node in registry.active_nodes():
            caps = node.get("capabilities") or {}
            if isinstance(caps, dict):
                capability_keys = [
                    key
                    for key, value in caps.items()
                    if value not in (None, False, "", 0)
                ]
            else:
                capability_keys = []
            nodes_summary.append(
                {
                    "hostname": node.get("hostname"),
                    "trust_level": node.get("trust_level"),
                    "capabilities": sorted(set(capability_keys)),
                    "last_voice_activity": int(float(node.get("last_voice_activity") or 0)),
                }
            )
        nodes_summary.sort(key=lambda entry: (entry.get("hostname") or ""))
        dream_status = dream_loop.status()
        memory_summary = _memory_summary()
        return {
            "nodes": nodes_summary,
            "dream": {
                "active": bool(dream_status.get("active")),
                "last_cycle": dream_status.get("last_cycle"),
            },
            "memory": {
                "total": memory_summary.get("total"),
                "dream": memory_summary.get("categories", {}).get("dream"),
            },
        }

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                snapshot = self._snapshot()
            except Exception as exc:  # pragma: no cover - defensive
                logging.debug("[AdminEvents] snapshot failed: %s", exc, exc_info=True)
                continue
            if snapshot != self._last_snapshot:
                self._last_snapshot = snapshot
                _notify_admin("refresh", {"snapshot": snapshot})


_ADMIN_WATCHER: Optional[_AdminStateWatcher] = None
if _CONSOLE_ENABLED:
    _ADMIN_WATCHER = _AdminStateWatcher(interval=float(os.getenv("ADMIN_SSE_INTERVAL_S", "2")))
    _ADMIN_WATCHER.start()


def _build_remote_headers(*, include_secret: bool = True) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if include_secret:
        headers["X-Relay-Secret"] = RELAY_SECRET
    if NODE_TOKEN:
        headers[_NODE_HEADER] = NODE_TOKEN
    node_id = _local_node_id()
    if node_id:
        headers[_NODE_ID_HEADER] = node_id
    return headers


class _CsrfManager:
    def __init__(self, enabled: bool, ttl_seconds: int) -> None:
        self.enabled = enabled
        self._ttl = ttl_seconds
        self._tokens: Dict[str, float] = {}

    def issue(self) -> str:
        if not self.enabled:
            return ""
        token = secrets.token_urlsafe(32)
        self._tokens[token] = time.time() + self._ttl
        self._prune()
        return token

    def validate(self, token: Optional[str]) -> bool:
        if not self.enabled:
            return True
        if not token:
            return False
        self._prune()
        expiry = self._tokens.get(token)
        if not expiry or expiry < time.time():
            self._tokens.pop(token, None)
            return False
        return True

    def _prune(self) -> None:
        now = time.time()
        for token, expiry in list(self._tokens.items()):
            if expiry < now:
                self._tokens.pop(token, None)


_csrf_manager = _CsrfManager(_CSRF_ENABLED, _ADMIN_TTL)


def _proxy_remote_json(path: str, payload: Dict[str, Any], *, capability: Optional[str] = None) -> Optional[Dict[str, Any]]:
    node = NODE_ROUTER.next(capability, trusted_only=True)
    if not node:
        return None
    url = f"http://{node.ip}:{node.port}{path}"
    try:
        response = requests.post(url, json=payload, headers=_build_remote_headers(), timeout=_REMOTE_TIMEOUT)
    except requests.RequestException as exc:
        logging.warning("[Relay] Remote %s failed for %s (%s): %s", path, node.hostname, node.ip, exc)
        return None
    if response.status_code != 200:
        logging.warning(
            "[Relay] Remote %s returned %s for %s (%s)", path, response.status_code, node.hostname, node.ip
        )
        return None
    logging.info("[Relay] Routed %s to %s (%s)", path, node.hostname, node.ip)
    try:
        return response.json()
    except ValueError:
        logging.warning("[Relay] Remote %s produced non-JSON payload", path)
        return None


def _is_authorised_for_node_routes() -> bool:
    pairing_service.cleanup_sessions()
    if request.headers.get("X-Relay-Secret") == RELAY_SECRET:
        return True
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) == NODE_TOKEN:
        return True
    node_id = request.headers.get(_NODE_ID_HEADER)
    token = request.headers.get(_NODE_HEADER)
    if node_id and token and pairing_service.verify_node_token(node_id, token):
        return True
    session_token = request.cookies.get(pairing_service.session_cookie_name)
    if session_token and pairing_service.validate_session(session_token):
        return True
    header_session = request.headers.get("X-Session-Token")
    if header_session and pairing_service.validate_session(header_session):
        return True
    return False


def _remote_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def _admin_actor() -> str:
    actor = request.headers.get("X-Admin-Actor")
    if actor:
        return actor
    token = request.headers.get(_NODE_HEADER)
    if token:
        return f"token:{token[:12]}"
    return f"ip:{_remote_ip()}"


def _ip_allowed(ip_address: str) -> bool:
    if not _ADMIN_ALLOWLIST:
        return True
    try:
        addr = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return any(addr in network for network in _ADMIN_ALLOWLIST)


def _admin_authorised(*, require_csrf: bool = False) -> bool:
    if app.config.get("TESTING"):
        return True
    if not _CONSOLE_ENABLED:
        return False
    if not _ip_allowed(_remote_ip()):
        return False
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) != NODE_TOKEN:
        return False
    if require_csrf and not _csrf_manager.validate(request.headers.get("X-CSRF-Token")):
        return False
    return True


def _authorised_for_sse() -> bool:
    if not _CONSOLE_ENABLED:
        return False
    if not _ip_allowed(_remote_ip()):
        return False
    token = request.headers.get(_NODE_HEADER) or request.args.get("token")
    if NODE_TOKEN and token != NODE_TOKEN:
        return False
    session_token = request.cookies.get(pairing_service.session_cookie_name)
    if session_token and pairing_service.validate_session(session_token):
        return True
    header_session = request.headers.get("X-Session-Token")
    if header_session and pairing_service.validate_session(header_session):
        return True
    if NODE_TOKEN and token == NODE_TOKEN:
        return True
    return False


def _admin_response(payload: Dict[str, Any]) -> Response:
    body = dict(payload)
    token = _csrf_manager.issue()
    if not token and app.config.get("TESTING"):
        token = "test-csrf-token"
    if token:
        body.setdefault("csrf_token", token)
    response = jsonify(body)
    if not hasattr(response, "headers"):
        response = Response(response, status=200)
        if hasattr(response, "headers"):
            response.headers["Content-Type"] = "application/json"
    if token and hasattr(response, "headers"):
        response.headers["X-CSRF-Token"] = token
    return response


def _gpu_status() -> Dict[str, Any]:
    if _STT_CONFIG:
        return {"backend": _STT_CONFIG.get("backend"), "description": _STT_CONFIG.get("description")}
    return {"backend": "cpu", "description": "CPU"}


def _memory_summary() -> Dict[str, Any]:
    metrics = governor.metrics()
    metrics["secure_store"] = secure_store.is_enabled()
    return metrics


_EMOTION_PULSE_PRESETS = [
    ("joy", ("radiant", "#facc15")),
    ("love", ("warm", "#f472b6")),
    ("gratitude", ("golden", "#fbbf24")),
    ("content", ("calm", "#38bdf8")),
    ("compassion", ("soothe", "#34d399")),
    ("hope", ("sky", "#22d3ee")),
    ("enthusiasm", ("spark", "#f97316")),
    ("confidence", ("steady", "#0ea5e9")),
    ("sad", ("deep", "#6366f1")),
    ("grief", ("midnight", "#4f46e5")),
    ("loneliness", ("midnight", "#475569")),
    ("fear", ("violet", "#a855f7")),
    ("anxiety", ("ember", "#fb7185")),
    ("panic", ("flare", "#ef4444")),
    ("anger", ("crimson", "#ef4444")),
    ("frustration", ("ember", "#f97316")),
    ("rage", ("storm", "#dc2626")),
    ("ambivalence", ("mauve", "#c084fc")),
    ("confusion", ("nebula", "#818cf8")),
    ("dissonance", ("static", "#a5b4fc")),
    ("boredom", ("mute", "#94a3b8")),
    ("surprise", ("electric", "#22d3ee")),
]


def _emotion_pulse(label: str, intensity: float) -> Dict[str, object]:
    tone, color = ("neutral", "#94a3b8")
    name = label.lower()
    for keyword, preset in _EMOTION_PULSE_PRESETS:
        if keyword in name:
            tone, color = preset
            break
    level = "calm"
    if intensity >= 0.6:
        level = "surge"
    elif intensity >= 0.3:
        level = "focused"
    return {
        "color": color,
        "tone": tone,
        "level": level,
        "intensity": round(max(0.0, min(1.0, float(intensity))), 3),
    }


def _top_emotions(vector: Mapping[str, float], limit: int = 3) -> list[Dict[str, object]]:
    ranked: list[tuple[str, float]] = []
    for label, raw in vector.items():
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0.0:
            continue
        ranked.append((label, value))
    ranked.sort(key=lambda item: item[1], reverse=True)
    out: list[Dict[str, object]] = []
    for label, value in ranked[:limit]:
        out.append({"label": label, "value": round(value, 3), "percent": round(value * 100, 1)})
    return out


def _goal_progress_snapshot(goal: Mapping[str, object]) -> Dict[str, object]:
    raw_fraction = goal.get("progress")
    try:
        fraction = float(raw_fraction)
    except (TypeError, ValueError):
        fraction = 0.0
    status = str(goal.get("status") or "open").lower()
    if not (0.0 < fraction <= 1.0):
        status_map = {
            "completed": 1.0,
            "needs_review": 0.65,
            "in_progress": 0.55,
            "blocked": 0.35,
            "failed": 0.25,
            "stuck": 0.2,
            "open": 0.15,
        }
        fraction = status_map.get(status, 0.2 if status else 0.1)
    steps = goal.get("steps")
    if isinstance(steps, list) and steps:
        done = sum(1 for step in steps if isinstance(step, Mapping) and step.get("done"))
        fraction = max(fraction, done / len(steps))
    capped = max(0.0, min(1.0, fraction))
    return {
        "fraction": round(capped, 3),
        "percent": round(capped * 100, 1),
        "status": status,
    }


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m" + (f" {remaining}s" if remaining and minutes < 5 else "")
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h" + (f" {minutes}m" if minutes and hours < 12 else "")
    days, hours = divmod(hours, 24)
    return f"{days}d" + (f" {hours}h" if hours else "")


def _dream_panel_snapshot() -> Dict[str, Any]:
    loop = dream_loop.status()
    interval_minutes = loop.get("interval_minutes")
    try:
        interval_minutes = float(interval_minutes)
    except (TypeError, ValueError):
        try:
            interval_minutes = float(os.getenv("DREAM_INTERVAL_MIN", "30"))
        except ValueError:
            interval_minutes = 30.0
    last_cycle = loop.get("last_cycle")
    seconds_since: Optional[float] = None
    seconds_until: Optional[float] = None
    fraction = 0.0
    interval_seconds = interval_minutes * 60.0 if interval_minutes else None
    if last_cycle:
        try:
            ts = datetime.datetime.fromisoformat(str(last_cycle))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            seconds_since = max(0.0, (now - ts).total_seconds())
            if interval_seconds:
                fraction = min(seconds_since / interval_seconds, 1.0)
                seconds_until = max(0.0, interval_seconds - seconds_since)
        except Exception:
            LOGGER.debug("Failed to parse dream loop timestamp", exc_info=True)
    elif loop.get("active"):
        fraction = 0.25

    mood_vector = empty_emotion_vector()
    try:
        mood_state = get_global_state().state()
        for label, value in mood_state.items():
            try:
                mood_vector[label] = float(value)
            except (TypeError, ValueError):
                continue
    except Exception:
        LOGGER.debug("EPU global state unavailable", exc_info=True)
    dominant = dominant_emotion(mood_vector, neutral_label="Neutral")
    intensity = float(mood_vector.get(dominant, 0.0)) if dominant in mood_vector else 0.0
    top_emotions = _top_emotions(mood_vector)
    pulse = _emotion_pulse(dominant, intensity)

    goal = mm.next_goal()
    active_goal: Dict[str, Any] | None = None
    if goal:
        active_goal = {
            "id": goal.get("id"),
            "text": goal.get("text"),
            "status": goal.get("status"),
            "priority": goal.get("priority"),
            "deadline": goal.get("deadline"),
            "progress": _goal_progress_snapshot(goal),
        }
        schedule_at = goal.get("schedule_at")
        if schedule_at:
            active_goal["scheduled_at"] = schedule_at

    progress = {
        "fraction": round(max(0.0, min(1.0, fraction)), 3),
        "percent": round(max(0.0, min(1.0, fraction)) * 100, 1),
        "seconds_since_last_cycle": seconds_since,
        "seconds_until_next_cycle": seconds_until,
        "interval_minutes": interval_minutes,
    }
    progress["since_label"] = _format_duration(seconds_since)
    progress["until_label"] = _format_duration(seconds_until)

    return {
        "loop": {
            "active": bool(loop.get("active")),
            "configured": bool(loop.get("configured")),
            "last_cycle": last_cycle,
            "interval_minutes": interval_minutes,
            "progress": progress,
        },
        "mood": {
            "dominant": dominant,
            "intensity": round(intensity, 3),
            "vector": mood_vector,
            "top": top_emotions,
        },
        "pulse": pulse,
        "active_goal": active_goal,
    }




def _admin_status_payload() -> Dict[str, Any]:
    metrics = _memory_summary()
    status = dream_loop.status()
    pending_goals = metrics.get("categories", {}).get("goal", 0)
    _mesh_refresh_from_registry()
    mesh_snapshot = _mesh_snapshot_payload()
    autonomy_status = AUTONOMY.status()
    return {
        "role": _ROLE,
        "model": os.getenv("SENTIENTOS_MODEL", "unknown"),
        "backend": os.getenv("SENTIENTOS_BACKEND", "local"),
        "uptime_seconds": time.time() - _PROCESS_START,
        "dream_loop": status,
        "pending_goals": pending_goals,
        "mem_entries": metrics.get("total", 0),
        "webui_enabled": _WEBUI_ENABLED,
        "gpu": _gpu_status(),
        "watchdog": WATCHDOG.snapshot(),
        "voice": _STT_CONFIG or {},
        "safety_events_1h": count_recent_events(1),
        "verifier": _verifier_status(),
        "mesh": mesh_snapshot,
        "autonomy": autonomy_status,
    }


def _verifier_status() -> Dict[str, Any]:
    summary = _SENTIENT_VERIFIER.status()
    summary["counts"] = _verifier_counts_today()
    return summary


def _verifier_counts_today() -> Dict[str, int]:
    try:
        today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return _VERIFIER_STORE.verdict_counts(
            since=today.replace(tzinfo=datetime.timezone.utc).timestamp()
        )
    except Exception:  # pragma: no cover - defensive
        return {}


@app.route("/admin/scripts", methods=["GET", "POST"])
def admin_scripts() -> Response:
    if request.method == "GET":
        if not _admin_authorised():
            return Response("Forbidden", status=403)
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        history = list_script_history(limit=max(1, limit), history=_SCRIPT_INTERPRETER.history)
        payload: Dict[str, Any] = {"history": history}
        shadows: list[Dict[str, Any]] = []
        try:
            dream_status = dream_loop.status()
            insight = str(dream_status.get("last_insight") or "").strip()
            if insight:
                shadows.append(_SCRIPT_INTERPRETER.build_shadow(kind="dream", text=insight))
        except Exception:
            pass
        try:
            reflection = governor.metrics().get("last_reflection")
            if reflection:
                reflection_text = json.dumps(reflection, sort_keys=True)
                shadows.append(_SCRIPT_INTERPRETER.build_shadow(kind="reflection", text=reflection_text))
        except Exception:
            pass
        if shadows:
            payload["shadows"] = shadows
        return _admin_response(payload)

    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    script_payload = payload.get("script") or payload.get("plan")
    if not script_payload:
        return jsonify({"error": "script required"}), 400
    try:
        script = _SCRIPT_INTERPRETER.load_script(script_payload)
    except ScriptExecutionError as exc:
        return jsonify({"error": str(exc), "path": exc.path or ""}), 400
    if payload.get("sign"):
        _SCRIPT_INTERPRETER.signer.sign(script)
    if payload.get("mode") == "verify" or payload.get("verify_only"):
        verified = _SCRIPT_INTERPRETER.signer.verify(script)
        return _admin_response({"verified": bool(verified)})
    try:
        result = _SCRIPT_INTERPRETER.execute(
            script,
            verify_signature=bool(payload.get("verify_signature", True)),
        )
    except ScriptExecutionError as exc:
        return jsonify({"error": str(exc), "path": exc.path or ""}), 400
    response_payload = {
        "run_id": result.run_id,
        "fingerprint": result.fingerprint,
        "outputs": result.outputs,
    }
    return _admin_response(response_payload)


@app.route("/admin/scripts/<path:run_id>/logs", methods=["GET"])
def admin_script_logs(run_id: str) -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    shadow = load_safety_shadow(run_id, history=_SCRIPT_INTERPRETER.history)
    if shadow is None:
        return jsonify({"error": "not_found"}), 404
    return _admin_response(shadow)


def _verifier_submit_key() -> tuple[str, Optional[str]]:
    token = str(request.headers.get(_NODE_HEADER) or "").strip()
    if token:
        hashed = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        key = f"token:{hashed}"
    else:
        key = f"ip:{_remote_ip()}"
    node_id = request.headers.get(_NODE_ID_HEADER)
    if node_id:
        node_id = node_id.strip() or None
    return key, node_id


def _lookup_request_node(bundle: Mapping[str, Any]) -> Optional[NodeRecord]:
    node_id = request.headers.get(_NODE_ID_HEADER)
    if node_id:
        record = registry.get(node_id.strip())
        if record is not None:
            return record
    run_log = bundle.get("claimed_run") if isinstance(bundle, Mapping) else None
    if isinstance(run_log, Mapping):
        from_node = run_log.get("from_node")
        if isinstance(from_node, str) and from_node:
            record = registry.get(from_node)
            if record is not None:
                return record
    return None


def _bundle_is_oversized(bundle: Mapping[str, Any]) -> bool:
    try:
        encoded = json.dumps(bundle).encode("utf-8")
    except Exception:
        return False
    if len(encoded) > _MAX_VERIFIER_BUNDLE_BYTES:
        return True
    run_log = bundle.get("claimed_run")
    if isinstance(run_log, Mapping):
        steps = run_log.get("steps")
        if isinstance(steps, Sequence) and len(steps) > _MAX_VERIFIER_STEPS:
            return True
    return False


def _verifier_event_payload(report: "VerificationReport") -> Dict[str, Any]:
    verified_at = report.timestamps.get("verified") if isinstance(report.timestamps, Mapping) else None
    return {
        "job_id": report.job_id,
        "verdict": report.verdict,
        "script_hash": report.script_hash,
        "from_node": report.from_node,
        "score": report.score,
        "verifier_node": report.verifier_node,
        "timestamp": verified_at or time.time(),
    }


@app.route("/admin/verify/submit", methods=["POST"])
def admin_verify_submit() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json(silent=True) or {}
    bundle = payload.get("bundle")
    if bundle is None:
        script = payload.get("script") or payload.get("plan")
        if script is None:
            return jsonify({"error": "script required"}), 400
        run_log = payload.get("run_log")
        env = payload.get("env") or {}
        bundle = {"script": script, "claimed_run": run_log, "env": env}
    if not isinstance(bundle, dict):
        return jsonify({"error": "bundle must be an object"}), 400
    if _bundle_is_oversized(bundle):
        LOGGER.warning("[Verifier] bundle rejected due to size limit")
        log_event("verifier_bundle_oversized")
        return jsonify({"error": "bundle_too_large"}), 413
    rate_key, _ = _verifier_submit_key()
    if not _VERIFIER_RATE_LIMIT.allow(rate_key):
        LOGGER.warning("[Verifier] submission rate limited for %s", rate_key)
        log_event("verifier_rate_limited")
        response = jsonify({"error": "rate_limited"})
        response.status_code = 429
        return response
    record = _lookup_request_node(bundle)
    if record is not None and getattr(record, "is_suspended", False):
        LOGGER.warning("[Verifier] submission blocked for suspended node %s", record.hostname)
        log_event("verifier_suspended")
        return jsonify({"error": "node_suspended"}), 403
    try:
        report = _SENTIENT_VERIFIER.verify_bundle(bundle)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.exception("[Verifier] bundle verification failed", exc_info=exc)
        return jsonify({"error": "verification_failed"}), 500
    response_payload = {
        "job_id": report.job_id,
        "verdict": report.verdict,
        "score": report.score,
        "script_hash": report.script_hash,
        "from_node": report.from_node,
        "verifier_node": report.verifier_node,
        "timestamp": report.timestamps.get("verified") if isinstance(report.timestamps, Mapping) else None,
    }
    _notify_admin("verifier_report", response_payload)
    _notify_admin("verifier_update", _verifier_event_payload(report))
    return _admin_response(response_payload)


@app.route("/admin/verify/status/<job_id>", methods=["GET"])
def admin_verify_status(job_id: str) -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    summary = _VERIFIER_STORE.get_status(job_id)
    if summary is None:
        return jsonify({"error": "not_found"}), 404
    payload = summary.to_dict()
    payload["verifier"] = _SENTIENT_VERIFIER.status()
    return _admin_response(payload)


@app.route("/admin/verify/report/<job_id>", methods=["GET"])
def admin_verify_report(job_id: str) -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    report = _VERIFIER_STORE.get_report(job_id)
    if report is None:
        return jsonify({"error": "not_found"}), 404
    return _admin_response(report)


@app.route("/admin/verify/list", methods=["GET"])
def admin_verify_list() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    summaries = [summary.to_dict() for summary in _VERIFIER_STORE.list_reports(limit=max(1, limit))]
    return _admin_response({"reports": summaries})


@app.route("/admin/verify/replay/<job_id>", methods=["POST"])
def admin_verify_replay(job_id: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    bundle = _VERIFIER_STORE.get_bundle(job_id)
    if bundle is None:
        return jsonify({"error": "not_found"}), 404
    rate_key, _ = _verifier_submit_key()
    if not _VERIFIER_RATE_LIMIT.allow(rate_key):
        LOGGER.warning("[Verifier] replay rate limited for %s", rate_key)
        log_event("verifier_rate_limited")
        response = jsonify({"error": "rate_limited"})
        response.status_code = 429
        return response
    record = _lookup_request_node(bundle)
    if record is not None and getattr(record, "is_suspended", False):
        LOGGER.warning("[Verifier] replay blocked for suspended node %s", record.hostname)
        log_event("verifier_suspended")
        return jsonify({"error": "node_suspended"}), 403
    try:
        report = _SENTIENT_VERIFIER.replay_job(job_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.exception("[Verifier] replay failed", exc_info=exc)
        return jsonify({"error": "verification_failed"}), 500
    response_payload = {
        "job_id": report.job_id,
        "verdict": report.verdict,
        "score": report.score,
        "script_hash": report.script_hash,
        "from_node": report.from_node,
        "verifier_node": report.verifier_node,
        "timestamp": report.timestamps.get("verified") if isinstance(report.timestamps, Mapping) else None,
    }
    _notify_admin("verifier_report", response_payload)
    _notify_admin("verifier_update", _verifier_event_payload(report))
    return _admin_response(response_payload)


@app.route("/admin/verify/consensus/submit", methods=["POST"])
def admin_verify_consensus_submit() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id_required"}), 400
    try:
        quorum_k = int(payload.get("quorum_k") or 0)
        quorum_n = int(payload.get("quorum_n") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_quorum"}), 400
    if quorum_k <= 0 or quorum_n <= 0 or quorum_k > quorum_n:
        return jsonify({"error": "invalid_quorum"}), 400
    participants_obj = payload.get("participants")
    participants: List[str] | None = None
    if isinstance(participants_obj, Sequence) and not isinstance(participants_obj, (str, bytes, bytearray)):
        participants = [str(entry) for entry in participants_obj if entry]
    selected = _select_consensus_participants(quorum_n, participants)
    try:
        report = _SENTIENT_VERIFIER.replay_job(job_id)
    except ValueError:
        return jsonify({"error": "unknown_job"}), 404
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("[Consensus] failed to replay job %s", job_id, exc_info=exc)
        return jsonify({"error": "replay_failed"}), 500
    vote = _SENTIENT_VERIFIER.make_vote(report)
    with _CONSENSUS_LOCK:
        state = _get_or_create_consensus_state(job_id, quorum_k, quorum_n, selected)
        if state.status != "RUNNING":
            return jsonify({"error": "job_not_running"}), 409
        try:
            state.register_vote(vote)
        except ValueError:
            registry.record_misbehavior(vote.voter_node, "NON_DET")
            return jsonify({"error": "conflicting_vote"}), 409
        except RuntimeError:
            return jsonify({"error": "job_not_running"}), 409
        _VERIFIER_STORE.store_vote(vote)
        consensus = _maybe_finalise_consensus(state)
        if consensus is None:
            _persist_consensus_state(state)
        snapshot = state.snapshot()
    _broadcast_consensus_update(state)
    response_payload: Dict[str, Any] = {
        "vote": vote.to_dict(),
        "snapshot": snapshot,
    }
    if consensus is not None:
        response_payload["consensus"] = consensus.to_dict()
    return _admin_response(response_payload)


@app.route("/admin/verify/consensus/status", methods=["GET"])
def admin_verify_consensus_status() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id_required"}), 400
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(job_id)
        if state is not None:
            snapshot = state.snapshot()
            return _admin_response(snapshot)
    consensus_payload = _VERIFIER_STORE.get_consensus(job_id)
    if consensus_payload:
        votes_obj = consensus_payload.get("votes") if isinstance(consensus_payload, Mapping) else []
        votes_list: List[Dict[str, Any]] = []
        participants: Set[str] = set()
        if isinstance(votes_obj, Sequence):
            for vote in votes_obj:
                if isinstance(vote, Mapping):
                    votes_list.append(dict(vote))
                    voter = vote.get("voter_node")
                    if isinstance(voter, str):
                        participants.add(voter)
        payload = {
            "job_id": job_id,
            "quorum_k": consensus_payload.get("quorum_k"),
            "quorum_n": consensus_payload.get("quorum_n"),
            "received": len(votes_list),
            "needed": 0,
            "participants": sorted(participants),
            "provisional_verdict": consensus_payload.get("final_verdict"),
            "finalized": True,
            "final_verdict": consensus_payload.get("final_verdict"),
            "latest_votes": votes_list,
            "status": "FINALIZED",
            "retries_by_node": {},
            "errors_by_node": {},
            "retry_after": {},
            "resumed": False,
            "last_update": consensus_payload.get("finalized_at"),
            "started_at": consensus_payload.get("started_at"),
            "force_reason": consensus_payload.get("force_reason"),
        }
        return _admin_response(payload)
    votes = _VERIFIER_STORE.list_votes(job_id)
    if votes:
        participants = sorted({str(vote.get("voter_node")) for vote in votes if isinstance(vote, Mapping) and vote.get("voter_node")})
        payload = {
            "job_id": job_id,
            "received": len(votes),
            "needed": 0,
            "participants": participants,
            "provisional_verdict": "INCONCLUSIVE",
            "finalized": False,
            "latest_votes": votes,
            "status": "RUNNING",
            "retries_by_node": {},
            "errors_by_node": {},
            "retry_after": {},
            "resumed": False,
        }
        return _admin_response(payload)
    return jsonify({"error": "not_found"}), 404


@app.route("/admin/verify/consensus/cancel", methods=["POST"])
def admin_verify_consensus_cancel() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id_required"}), 400
    reason_raw = payload.get("reason")
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) else None
    actor = _admin_actor()
    with _CONSENSUS_LOCK:
        state = _ensure_consensus_state(job_id)
        if state is None:
            return jsonify({"error": "not_found"}), 404
        state.cancel(reason=reason)
        _persist_consensus_state(state)
        snapshot = state.snapshot()
    _broadcast_consensus_update(state)
    _shadow_event("verifier_consensus_canceled", job_id=job_id, actor=actor, reason=reason)
    return _admin_response({"status": "canceled", "snapshot": snapshot})


@app.route("/admin/verify/consensus/finalize", methods=["POST"])
def admin_verify_consensus_finalize() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id_required"}), 400
    reason_raw = payload.get("reason")
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) else None
    actor = _admin_actor()
    with _CONSENSUS_LOCK:
        state = _ensure_consensus_state(job_id)
        if state is None:
            return jsonify({"error": "not_found"}), 404
        if state.consensus is None or state.consensus.final_verdict == "INCONCLUSIVE":
            return jsonify({"error": "quorum_not_met"}), 409
        if len(state.votes) < state.quorum_k:
            return jsonify({"error": "quorum_not_met"}), 409
        state.force_reason = reason
        consensus = _maybe_finalise_consensus(state, actor=actor)
        if consensus is None:
            return jsonify({"error": "quorum_not_met"}), 409
        _persist_consensus_state(state)
        snapshot = state.snapshot()
    _broadcast_consensus_update(state)
    _shadow_event("verifier_consensus_forced", job_id=job_id, actor=actor, reason=reason)
    return _admin_response({"status": "finalized", "snapshot": snapshot, "consensus": consensus.to_dict()})


@app.route("/admin/verify/consensus/report", methods=["GET"])
def admin_verify_consensus_report() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id_required"}), 400
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(job_id)
        if state is not None and state.consensus is not None:
            payload = state.consensus.to_dict()
            payload["report_url"] = f"/admin/verify/report/{job_id}"
            return _admin_response(payload)
    consensus_payload = _VERIFIER_STORE.get_consensus(job_id)
    if consensus_payload:
        data = dict(consensus_payload)
        data["report_url"] = f"/admin/verify/report/{job_id}"
        return _admin_response(data)
    return jsonify({"error": "not_found"}), 404


@app.route("/mesh/verify/solicit", methods=["POST"])
def mesh_verify_solicit() -> Response:
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "")
    requester = str(payload.get("requester") or "")
    if not job_id or not requester:
        return jsonify({"error": "bad_request"}), 400
    if not _mesh_rate_allow(requester):
        return jsonify({"error": "rate_limited"}), 429
    record = registry.get(requester)
    if record is None or record.trust_level != "trusted" or record.is_suspended:
        return jsonify({"error": "unauthorised"}), 403
    if not _verify_mesh_signature(payload):
        registry.record_misbehavior(requester, "BAD_SIG")
        return jsonify({"error": "invalid_signature"}), 403
    bundle_obj: Optional[Mapping[str, Any]]
    if isinstance(payload.get("bundle_inline"), Mapping):
        bundle_obj = dict(payload.get("bundle_inline"))  # type: ignore[arg-type]
    else:
        ref = payload.get("script_bundle_ref")
        bundle_obj = _VERIFIER_STORE.get_bundle(str(ref)) if isinstance(ref, str) else None
    if not isinstance(bundle_obj, Mapping):
        return jsonify({"error": "bundle_required"}), 400
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(job_id)
        if state is not None:
            if state.status != "RUNNING":
                state.errors_by_node[requester] = "job_not_running"
                state.retries_by_node[requester] = _SOLICIT_RETRY_MAX
                state.retry_after[requester] = float("inf")
                state.last_update = time.time()
                _persist_consensus_state(state)
                registry.record_consensus_error(requester)
                return jsonify({"error": "job_not_running"}), 409
            if state.has_exhausted_retries(requester):
                state.errors_by_node[requester] = "retry_exhausted"
                state.retry_after[requester] = float("inf")
                state.retries_by_node[requester] = _SOLICIT_RETRY_MAX
                state.last_update = time.time()
                _persist_consensus_state(state)
                registry.record_consensus_error(requester)
                return jsonify({"error": "retry_exhausted"}), 409
            if not state.allows_retry(requester):
                retry_after = state.retry_after.get(requester)
                hint_ms = registry.verifier_backoff_hint_ms(requester)
                return jsonify({"error": "retry_later", "retry_after": retry_after, "backoff_hint_ms": hint_ms}), 429
        if len(_LOCAL_ACTIVE_SOLICITATIONS) >= _MAX_MESH_PARTICIPATION and job_id not in _LOCAL_ACTIVE_SOLICITATIONS:
            return jsonify({"error": "busy"}), 429
        _LOCAL_ACTIVE_SOLICITATIONS.add(job_id)
    try:
        report = _SENTIENT_VERIFIER.verify_bundle(
            dict(bundle_obj), job_id_override=job_id, persist_bundle=False
        )
    except ValueError as exc:
        with _CONSENSUS_LOCK:
            _LOCAL_ACTIVE_SOLICITATIONS.discard(job_id)
            state = _CONSENSUS_STATES.get(job_id)
            if state is not None:
                state.record_retry(requester, success=False, error=str(exc))
                _persist_consensus_state(state)
        registry.record_consensus_error(requester)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("[Consensus] solicit verification failed", exc_info=exc)
        with _CONSENSUS_LOCK:
            _LOCAL_ACTIVE_SOLICITATIONS.discard(job_id)
            state = _CONSENSUS_STATES.get(job_id)
            if state is not None:
                state.record_retry(requester, success=False, error="verification_failed")
                _persist_consensus_state(state)
        registry.record_consensus_error(requester)
        return jsonify({"error": "verification_failed"}), 500
    finally:
        with _CONSENSUS_LOCK:
            _LOCAL_ACTIVE_SOLICITATIONS.discard(job_id)
    script_hash = str(payload.get("script_hash") or "")
    if script_hash and script_hash != report.script_hash:
        registry.record_misbehavior(requester, "BAD_MERKLE")
        return jsonify({"error": "script_mismatch"}), 409
    vote = _SENTIENT_VERIFIER.make_vote(report)
    _VERIFIER_STORE.store_vote(vote)
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(job_id)
        if state is not None:
            try:
                state.register_vote(vote)
            except ValueError:
                registry.record_misbehavior(vote.voter_node, "NON_DET")
                state.record_retry(requester, success=False, error="non_deterministic")
                _persist_consensus_state(state)
                registry.record_consensus_error(requester)
            else:
                consensus = _maybe_finalise_consensus(state)
                state.record_retry(requester, success=True, error=None)
                _persist_consensus_state(state)
                registry.clear_consensus_error(requester)
    if state is not None:
        _broadcast_consensus_update(state)
    return _admin_response({"vote": vote.to_dict()})


@app.route("/mesh/verify/submit_vote", methods=["POST"])
def mesh_verify_submit_vote() -> Response:
    payload = request.get_json(silent=True) or {}
    vote_payload: Mapping[str, Any]
    if isinstance(payload.get("vote"), Mapping):
        vote_payload = payload["vote"]  # type: ignore[assignment]
    elif isinstance(payload, Mapping):
        vote_payload = payload
    else:
        return jsonify({"error": "invalid_vote"}), 400
    try:
        vote = _vote_from_payload(vote_payload)
    except Exception:
        return jsonify({"error": "invalid_vote"}), 400
    if not vote.job_id or not vote.voter_node:
        return jsonify({"error": "invalid_vote"}), 400
    record = registry.get(vote.voter_node)
    if record is None or record.is_suspended:
        return jsonify({"error": "unauthorised"}), 403
    if not verify_vote_signatures((vote,), registry):
        registry.record_misbehavior(vote.voter_node, "BAD_SIG")
        return jsonify({"error": "invalid_signature"}), 403
    with _CONSENSUS_LOCK:
        state = _CONSENSUS_STATES.get(vote.job_id)
        if state is None:
            return jsonify({"error": "unknown_job"}), 404
        if state.status != "RUNNING":
            return jsonify({"error": "job_not_running"}), 409
        report_payload = _VERIFIER_STORE.get_report(vote.job_id)
        if report_payload:
            expected_hash = report_payload.get("proof_hash") if isinstance(report_payload, Mapping) else None
            expected_merkle = merkle_root_for_report(report_payload) if isinstance(report_payload, Mapping) else None
            if expected_hash and vote.proof_hash and vote.proof_hash != expected_hash:
                registry.record_misbehavior(vote.voter_node, "BAD_MERKLE")
                return jsonify({"error": "proof_mismatch"}), 409
            if expected_merkle and vote.merkle_root and vote.merkle_root != expected_merkle:
                registry.record_misbehavior(vote.voter_node, "BAD_MERKLE")
                return jsonify({"error": "merkle_mismatch"}), 409
        try:
            state.register_vote(vote)
        except ValueError:
            registry.record_misbehavior(vote.voter_node, "NON_DET")
            return jsonify({"error": "conflicting_vote"}), 409
        except RuntimeError:
            return jsonify({"error": "job_not_running"}), 409
        _VERIFIER_STORE.store_vote(vote)
        consensus = _maybe_finalise_consensus(state)
        if consensus is None:
            _persist_consensus_state(state)
        snapshot = state.snapshot()
    _broadcast_consensus_update(state)
    response_payload: Dict[str, Any] = {"status": "accepted", "snapshot": snapshot}
    if consensus is not None:
        response_payload["consensus"] = consensus.to_dict()
    return _admin_response(response_payload)


@app.route("/admin/dream", methods=["GET"])
def admin_dream() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    payload = _dream_panel_snapshot()
    return _admin_response(payload)


def _guess_mimetype(name: str, default: str = "text/plain") -> str:
    if name.endswith(".js"):
        return "text/javascript"
    if name.endswith(".css"):
        return "text/css"
    if name.endswith(".html"):
        return "text/html"
    if name.endswith(".webmanifest"):
        return "application/manifest+json"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".png"):
        return "image/png"
    return default


def _serve_static(root: Path, asset: str, *, default_mimetype: str = "text/plain") -> Response:
    candidate = (root / asset).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return Response("Not Found", status=404)
    if not candidate.exists() or not candidate.is_file():
        return Response("Not Found", status=404)
    data = candidate.read_bytes()
    mimetype = _guess_mimetype(asset, default_mimetype)
    try:
        return Response(data, status=200, mimetype=mimetype)
    except TypeError:
        response = Response(data, status=200)
        if hasattr(response, "headers"):
            response.headers["Content-Type"] = mimetype
        return response


@app.route("/sse", methods=["GET"])
def admin_event_stream() -> Response:
    if not _authorised_for_sse():
        return Response("Forbidden", status=403)

    subscriber = _ADMIN_EVENTS.subscribe()

    def stream():
        try:
            yield "event: refresh\ndata: {}\n\n"
            while True:
                try:
                    message = subscriber.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                event = str(message.get("event") or "refresh").strip() or "refresh"
                data = message.get("data") or {}
                try:
                    payload = json.dumps(data)
                except (TypeError, ValueError):
                    payload = "{}"
                yield f"event: {event}\ndata: {payload}\n\n"
        finally:
            _ADMIN_EVENTS.unsubscribe(subscriber)

    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _sanitise_memories(entries: list[dict], *, decrypt: bool) -> list[dict]:
    cleaned: list[dict] = []
    for entry in entries:
        data = dict(entry)
        if not decrypt:
            data.pop("text", None)
        cleaned.append(data)
    return cleaned


def _incognito_enabled() -> bool:
    return os.getenv("MEM_INCOGNITO", "0") == "1"


def _proxy_upstream_json(path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _UPSTREAM_CORE:
        logging.debug("[Relay] Thin routing requested but UPSTREAM_CORE is not configured")
        return None
    base = _UPSTREAM_CORE
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"
    url = base.rstrip("/") + (path if path.startswith("/") else "/" + path)
    headers = _build_remote_headers(include_secret=False)
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=_STREAM_TIMEOUT)
    except requests.RequestException as exc:
        logging.warning("[Relay] Upstream %s failed: %s", url, exc)
        return None
    if response.status_code != 200:
        logging.warning("[Relay] Upstream %s returned %s", url, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        logging.warning("[Relay] Upstream %s produced non-JSON payload", url)
        return None


def _authorised_for_ui() -> bool:
    pairing_service.cleanup_sessions()
    if request.headers.get("X-Relay-Secret") == RELAY_SECRET:
        return True
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) == NODE_TOKEN:
        return True
    session_token = request.cookies.get(pairing_service.session_cookie_name)
    if session_token and pairing_service.validate_session(session_token):
        return True
    header_session = request.headers.get("X-Session-Token")
    if header_session and pairing_service.validate_session(header_session):
        return True
    return False




def _ensure_background_services() -> None:
    if os.getenv("SENTIENTOS_DISABLE_DISCOVERY") == "1":
        return
    try:
        discovery.start()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to start node discovery: %s", exc, exc_info=True)
    try:
        synchronizer.start()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to start distributed memory sync: %s", exc, exc_info=True)


_ensure_background_services()


@app.route("/", methods=["GET"])
def webui_root() -> Response:
    if not _WEBUI_ENABLED:
        return Response("Web UI disabled", status=404)
    index_path = _WEBUI_ROOT / "index.html"
    if not index_path.exists():
        return Response("Web UI unavailable", status=404)
    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError:
        return Response("Web UI unavailable", status=500)
    try:
        return Response(content, status=200, mimetype="text/html")
    except TypeError:  # Fallback for flask stub
        resp = Response(content, status=200)
        if hasattr(resp, "headers"):
            resp.headers["Content-Type"] = "text/html"
        return resp


@app.route("/console", methods=["GET"])
def console_root() -> Response:
    if not _CONSOLE_ENABLED:
        return Response("Console disabled", status=404)
    return _serve_static(_CONSOLE_ROOT, "index.html", default_mimetype="text/html")


@app.route("/console/<path:asset>", methods=["GET"])
def console_asset(asset: str) -> Response:
    if not _CONSOLE_ENABLED:
        return Response("Console disabled", status=404)
    return _serve_static(_CONSOLE_ROOT, asset)


@app.route("/webui/pwa/<path:asset>", methods=["GET"])
def pwa_asset(asset: str) -> Response:
    return _serve_static(_PWA_ROOT, asset)


@app.route("/webui/<path:asset>", methods=["GET"])
def webui_asset(asset: str) -> Response:
    if not _WEBUI_ENABLED:
        return Response("Web UI disabled", status=404)
    candidate = (_WEBUI_ROOT / asset).resolve()
    try:
        candidate.relative_to(_WEBUI_ROOT)
    except ValueError:
        return Response("Not Found", status=404)
    if not candidate.exists() or not candidate.is_file():
        return Response("Not Found", status=404)
    mimetype = "text/plain"
    if asset.endswith(".js"):
        mimetype = "text/javascript"
    elif asset.endswith(".css"):
        mimetype = "text/css"
    elif asset.endswith(".svg"):
        mimetype = "image/svg+xml"
    data = candidate.read_bytes()
    try:
        return Response(data, status=200, mimetype=mimetype)
    except TypeError:
        resp = Response(data, status=200)
        if hasattr(resp, "headers"):
            resp.headers["Content-Type"] = mimetype
        return resp


@app.route("/nodes", methods=["GET"])
def list_nodes() -> Response:
    if not _is_authorised_for_node_routes():
        return Response("Forbidden", status=403)
    return jsonify({"nodes": registry.active_nodes(), "capabilities": registry.capability_map()})


@app.route("/nodes/list", methods=["GET"])
def nodes_list_ui() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    return jsonify({"nodes": registry.active_nodes(), "capabilities": registry.capability_map()})


@app.route("/admin/status", methods=["GET"])
def admin_status() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(_admin_status_payload())


@app.route("/admin/mesh/status", methods=["GET"])
def admin_mesh_status() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    _mesh_refresh_from_registry()
    snapshot = _mesh_snapshot_payload()
    return _admin_response({"snapshot": snapshot})


@app.route("/admin/mesh/voices", methods=["GET"])
def admin_mesh_voices() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response({"voices": _MESH.voices_status()})


@app.route("/admin/mesh/sessions", methods=["GET"])
def admin_mesh_sessions() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    job_id = request.args.get("job_id")
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    sessions = _MESH.sessions(job_id, limit=limit)
    return _admin_response({"sessions": sessions})


@app.route("/admin/mesh/cycle", methods=["POST"])
def admin_mesh_cycle() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json(silent=True) or {}
    jobs_payload = payload.get("jobs") or []
    jobs: List[MeshJob] = []
    for entry in jobs_payload:
        if not isinstance(entry, Mapping):
            continue
        job_id = str(entry.get("job_id") or f"manual-{uuid.uuid4().hex[:8]}")
        script = entry.get("script") or {}
        prompt = str(entry.get("prompt") or "")
        priority = int(entry.get("priority") or 1)
        requirements = entry.get("requirements") or []
        metadata = entry.get("metadata") or {}
        jobs.append(
            MeshJob(
                job_id=job_id,
                script=script if isinstance(script, Mapping) else {},
                prompt=prompt,
                priority=priority,
                requirements=requirements,
                metadata=metadata if isinstance(metadata, Mapping) else {},
            )
        )
    _mesh_refresh_from_registry()
    snapshot = _MESH.cycle(jobs)
    payload = _mesh_snapshot_payload(snapshot)
    _broadcast_mesh_update(payload)
    return _admin_response({"snapshot": payload})


@app.route("/admin/autonomy/status", methods=["GET"])
def admin_autonomy_status() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(AUTONOMY.status())


@app.route("/admin/autonomy/start", methods=["POST"])
def admin_autonomy_start() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    AUTONOMY.start()
    return _admin_response(AUTONOMY.status())


@app.route("/admin/autonomy/stop", methods=["POST"])
def admin_autonomy_stop() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    AUTONOMY.stop()
    return _admin_response(AUTONOMY.status())


@app.route("/admin/autonomy/reflect", methods=["POST"])
def admin_autonomy_reflect() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    plans = AUTONOMY.reflective_cycle(force=True)
    _mesh_refresh_from_registry()
    snapshot = _mesh_snapshot_payload()
    _broadcast_mesh_update(snapshot)
    return _admin_response({"plans": plans, "snapshot": snapshot})


@app.route("/admin/health", methods=["GET"])
def admin_health() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    payload = {
        "watchdog": WATCHDOG.snapshot(),
        "voice": {"enabled": _VOICE_ENABLED, "config": _STT_CONFIG},
        "safety_events_1h": count_recent_events(1),
    }
    return _admin_response(payload)


@app.route("/admin/nodes", methods=["GET"])
def admin_nodes() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    nodes = registry.active_nodes()
    groups: Dict[str, list[Dict[str, Any]]] = {"trusted": [], "provisional": [], "blocked": []}
    for record in nodes:
        level = str(record.get("trust_level", "provisional"))
        groups.setdefault(level, []).append(record)
    payload = {
        "nodes": nodes,
        "groups": groups,
        "capabilities": registry.capability_map(),
    }
    return _admin_response(payload)


@app.route("/admin/memory/summary", methods=["GET"])
def admin_memory_summary() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(_memory_summary())


@app.route("/admin/memory/recall", methods=["POST"])
def admin_memory_recall() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    query = payload.get("query")
    try:
        k = max(1, int(payload.get("k", 5)))
    except (TypeError, ValueError):
        k = 5
    decrypt = bool(payload.get("decrypt"))
    memories = governor.recall(query, k=k)
    return jsonify({"memories": _sanitise_memories(memories, decrypt=decrypt)})


@app.route("/admin/nodes/<hostname>/trust", methods=["POST"])
def admin_nodes_trust(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    level = str(payload.get("level") or payload.get("trust_level") or "trusted").strip()
    record = registry.set_trust_level(hostname, level)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/nodes/<hostname>/block", methods=["POST"])
def admin_nodes_block(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    record = registry.set_trust_level(hostname, "blocked")
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/nodes/<hostname>/rekey", methods=["POST"])
def admin_nodes_rekey(hostname: str) -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    token = str(payload.get("token") or payload.get("node_token") or "").strip()
    if not token:
        return jsonify({"error": "token required"}), 400
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = registry.store_token(hostname, digest)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify({"stored": True, "hostname": hostname})


@app.route("/admin/rotate-keys", methods=["POST"])
def admin_rotate_keys() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    result = mem_admin.rotate_keys()
    return jsonify(result)


@app.route("/webrtc/create", methods=["POST"])
def webrtc_create() -> Response:
    if not _VOICE_ENABLED or _WEBRTC_MANAGER is None:
        return Response("Voice disabled", status=404)
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    offer = payload.get("offer")
    if not isinstance(offer, dict):
        return jsonify({"error": "offer required"}), 400
    try:
        session = _WEBRTC_MANAGER.create_session(offer, token=request.headers.get(_NODE_HEADER))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(session)


@app.route("/webrtc/ice", methods=["POST"])
def webrtc_add_ice() -> Response:
    if not _VOICE_ENABLED or _WEBRTC_MANAGER is None:
        return Response("Voice disabled", status=404)
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    session_id = str(payload.get("session_id") or "").strip()
    candidate = payload.get("candidate")
    if not session_id or not isinstance(candidate, dict):
        return jsonify({"error": "session_id and candidate required"}), 400
    try:
        updated = _WEBRTC_MANAGER.add_ice_candidate(session_id, candidate)
    except KeyError:
        return jsonify({"error": "unknown_session"}), 404
    return jsonify(updated)


@app.route("/voice/stream", methods=["POST"])
def voice_stream() -> Response:
    if not _VOICE_ENABLED or _STT_PIPELINE is None:
        return Response("Voice disabled", status=404)
    if not (_authorised_for_ui() or request.headers.get("X-Relay-Secret") == RELAY_SECRET):
        return Response("Forbidden", status=403)

    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or payload.get("session") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    provided_hostname = str(payload.get("hostname") or request.headers.get(_NODE_ID_HEADER) or "").strip()
    hostname = provided_hostname or _local_node_id()
    now = time.time()
    _prune_voice_sessions(now)
    session = _ensure_voice_session(session_id, hostname)
    hostname = session.hostname

    chunk = payload.get("chunk")
    if chunk is None:
        chunk = payload.get("data")
    encoding = str(payload.get("encoding") or "").lower()
    response_events: list[Dict[str, Any]] = []
    if chunk is not None:
        if isinstance(chunk, (bytes, bytearray)):
            submitted = bytes(chunk)
        elif isinstance(chunk, str):
            if encoding == "base64":
                try:
                    submitted = base64.b64decode(chunk)
                except Exception:
                    submitted = chunk
            else:
                submitted = chunk
        else:
            submitted = json.dumps(chunk)
        response_events.extend(_consume_transcription_events(session, hostname, session.transcriber.submit_audio(submitted)))

    if payload.get("flush"):
        response_events.extend(_consume_transcription_events(session, hostname, session.transcriber.flush()))

    summary_hint = str(payload.get("summary") or "").strip()
    if summary_hint:
        session.utterances.append(summary_hint)
        session.last_event = now

    result: Dict[str, Any] = {"session_id": session_id, "events": response_events, "finalized": False}
    if payload.get("complete") or payload.get("final") or payload.get("finalise"):
        extra_meta = {"client_summary": bool(summary_hint), "hostname": hostname}
        summary = _complete_voice_session(
            session,
            reason="client_finalise",
            flush=not bool(payload.get("flush")),
            extra_meta=extra_meta,
        )
        if summary:
            result["summary"] = summary
        elif summary_hint:
            register_voice_session(summary_hint, hostname=hostname, meta={"session_id": session_id, "reason": "client_summary"})
            result["summary"] = summary_hint
        result["finalized"] = True
    else:
        if provided_hostname and session.hostname != provided_hostname:
            session.hostname = provided_hostname

    return jsonify(result)


@app.route("/nodes/trust", methods=["POST"])
def nodes_trust() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    hostname = str(payload.get("hostname") or payload.get("node_id") or "").strip()
    level = str(payload.get("trust_level") or payload.get("level") or "trusted").strip()
    if not hostname:
        return jsonify({"error": "hostname required"}), 400
    record = registry.set_trust_level(hostname, level)
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/nodes/block", methods=["POST"])
def nodes_block() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    hostname = str(payload.get("hostname") or payload.get("node_id") or "").strip()
    if not hostname:
        return jsonify({"error": "hostname required"}), 400
    record = registry.set_trust_level(hostname, "blocked")
    if not record:
        return jsonify({"error": "node not found"}), 404
    return jsonify(record.serialise())


@app.route("/admin/webrtc/sessions", methods=["GET"])
def admin_webrtc_sessions() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    if _WEBRTC_MANAGER is None:
        return jsonify({"sessions": []})
    return _admin_response({"sessions": _WEBRTC_MANAGER.list_sessions()})


@app.route("/admin/watchdog", methods=["GET"])
def admin_watchdog_snapshot() -> Response:
    if not _admin_authorised():
        return Response("Forbidden", status=403)
    return _admin_response(WATCHDOG.snapshot())


@app.route("/admin/watchdog/register", methods=["POST"])
def admin_watchdog_register() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    name = str(payload.get("name") or "").strip()
    host = payload.get("host")
    port = payload.get("port")
    if not name or host is None or port is None:
        return jsonify({"error": "name, host, port required"}), 400

    def restart() -> None:
        logging.info("[Watchdog] Restart requested for %s", name)

    WATCHDOG.register_port(name, str(host), int(port), restart=restart)
    return jsonify({"registered": True, "name": name})


@app.route("/admin/watchdog/heartbeat", methods=["POST"])
def admin_watchdog_heartbeat() -> Response:
    if not _admin_authorised(require_csrf=True):
        return Response("Forbidden", status=403)
    payload = request.get_json() or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    WATCHDOG.report_heartbeat(name)
    return jsonify({"ack": True, "name": name})


@app.route("/pair/start", methods=["POST"])
def pair_start() -> Response:
    if not _authorised_for_ui():
        return Response("Forbidden", status=403)
    host = request.host.split(":")[0] if request.host else _local_node_id()
    data = pairing_service.start_pairing(host=host)
    return jsonify(data)


@app.route("/pair/confirm", methods=["POST"])
def pair_confirm() -> Response:
    payload = request.get_json() or {}
    try:
        result = pairing_service.confirm_pairing(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    response = jsonify(result)
    session_token = result.get("session_token")
    if session_token and _WEBUI_AUTH_MODE == "cookie":
        response.set_cookie(
            pairing_service.session_cookie_name,
            session_token,
            max_age=int(os.getenv("PAIRING_SESSION_TTL_S", str(24 * 3600))),
            secure=False,
            httponly=False,
            samesite="Lax",
        )
    return response


@app.route("/nodes/register", methods=["POST"])
def register_node() -> Response:
    if not _is_authorised_for_node_routes():
        return Response("Forbidden", status=403)
    data = request.get_json() or {}
    token = data.get("token") or request.headers.get(_NODE_HEADER)
    if NODE_TOKEN and token != NODE_TOKEN:
        return Response("Forbidden", status=403)
    hostname = str(data.get("hostname") or data.get("id") or "").strip()
    ip = str(data.get("ip") or request.remote_addr or "").strip()
    if not hostname or not ip:
        return jsonify({"error": "hostname and ip are required"}), 400
    try:
        port = int(data.get("port", 5000))
    except (TypeError, ValueError):
        port = 5000
    capabilities = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
    record = registry.register_or_update(hostname, ip, port=port, capabilities=capabilities, last_seen=time.time())
    return jsonify(record.serialise()), 201


@app.route("/memory/export", methods=["GET", "POST"])
def memory_export() -> Response:
    if request.method == "GET":
        if NODE_TOKEN and request.headers.get(_NODE_HEADER) != NODE_TOKEN:
            return Response("Forbidden", status=403)
        limit_arg = request.args.get("limit")
        limit = None
        if limit_arg:
            try:
                limit = max(1, int(limit_arg))
            except ValueError:
                limit = None
        fragments = list(mm.iter_fragments(limit=limit, reverse=False))
        payload = {"fragments": fragments}
        allow_compression = "zstd" in (request.headers.get("Accept-Encoding", "").lower())
        body, headers = encode_payload(payload, allow_compression=allow_compression)
        response = Response(body, status=200, mimetype="application/json")
        for key, value in headers.items():
            response.headers[key] = value
        return response

    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    options = request.get_json() or {}
    include_insights = bool(options.get("include_insights", True))
    include_dreams = bool(options.get("include_dreams", True))
    passphrase = options.get("passphrase")
    archive = mem_export.export_encrypted(
        None,
        include_insights=include_insights,
        include_dreams=include_dreams,
        passphrase=passphrase,
    )
    response = Response(archive, status=200, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = "attachment; filename=sentientos_memory.bin"
    return response


@app.route("/reflect/sync", methods=["POST"])
def reflect_sync() -> Response:
    if NODE_TOKEN and request.headers.get(_NODE_HEADER) != NODE_TOKEN:
        return Response("Forbidden", status=403)
    hostname = str(request.headers.get(_NODE_ID_HEADER) or "").strip()
    if not hostname:
        return jsonify({"error": "node_id_required"}), 400
    record = registry.get(hostname)
    if not record or record.trust_level != "trusted":
        return jsonify({"error": "node_not_trusted"}), 403
    envelope = request.get_json(silent=True)
    if not isinstance(envelope, dict):
        return jsonify({"error": "invalid_payload"}), 400
    try:
        summary = decrypt_reflection_payload(envelope)
    except ValueError as exc:
        LOGGER.debug("Reflection sync decrypt failed: %s", exc)
        return jsonify({"error": "decrypt_failed"}), 400
    summary_id = str(envelope.get("summary_id") or summary.get("reflection_id") or "").strip()
    if summary_id:
        if summary_id in _RECENT_REFLECTION_SYNC_IDS:
            return jsonify({"status": "duplicate"}), 200
        _RECENT_REFLECTION_SYNC_IDS.append(summary_id)
    summary = {k: v for k, v in summary.items() if v is not None}
    summary["received_from"] = hostname
    summary["received_at"] = datetime.datetime.utcnow().isoformat()
    importance = summary.get("importance")
    try:
        importance_value = float(importance) if importance is not None else 0.35
    except (TypeError, ValueError):
        importance_value = 0.35
    importance_value = max(0.1, min(1.0, importance_value))
    summary["importance"] = importance_value
    try:
        trust = getattr(record, "trust_score", 0.0)
        dream_loop.register_remote_reflection(hostname, summary, trust=trust)
    except AttributeError:
        pass
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("[Mesh] failed to register remote reflection", exc_info=True)
    try:
        _REFLECTION_SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_REFLECTION_SYNC_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
    except OSError:
        LOGGER.debug("Failed to persist reflection sync log", exc_info=True)
    try:
        mm.append_memory(
            json.dumps({"reflection_sync": summary}, ensure_ascii=False),
            tags=["reflection", "sync"],
            source="reflection_sync",
            summary=summary.get("headline") or summary.get("reason") or "Remote reflection",
            importance=importance_value,
        )
    except Exception:
        LOGGER.debug("Failed to record reflection sync memory", exc_info=True)
    _notify_admin("refresh", {"source": "reflection_sync", "from": hostname})
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat() -> Response:
    payload = request.get_json() or {}
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/chat", payload)
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if not _authorised_for_ui() and request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    capability = "llm"
    remote = _proxy_remote_json("/chat", payload, capability=capability)
    if remote is not None:
        return jsonify(remote)
    message = payload.get("message", "")
    model = payload.get("model", "default").strip().lower()
    emotions = payload.get("emotions") or empty_emotion_vector()
    chunks = chunk_message(message)
    reply = "\n".join(chunks)
    write_mem(
        f"[CHAT] Model: {model} | Message: {message}\n{reply}",
        tags=["chat", model],
        emotions=emotions,
    )
    return jsonify({"reply": reply, "model": model, "routed": "local", "chunks": chunks})


@app.route("/relay", methods=["POST"])
def relay():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    data = request.get_json() or {}
    remote = _proxy_remote_json("/relay", data, capability=data.get("capability"))
    if remote is not None:
        return jsonify(remote)

    message = data.get("message", "")
    model = data.get("model", "default").strip().lower()
    emotion_vector = data.get("emotions") or empty_emotion_vector()

    reply = f"Echo: {message} ({model})"
    write_mem(
        f"[RELAY] → Model: {model} | Message: {message}\n{reply}",
        tags=["relay", model],
        source="relay",
        emotions=emotion_vector,
    )
    return jsonify({"reply_chunks": chunk_message(reply)})


@app.route("/memory/import", methods=["POST"])
def memory_import() -> Response:
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    payload: bytes | None = None
    passphrase = request.form.get("passphrase") if request.form else None
    if "archive" in request.files:
        payload = request.files["archive"].read()
        if not passphrase:
            passphrase = request.form.get("passphrase") if request.form else None
    elif request.data:
        payload = request.data
    elif request.is_json:
        data = request.get_json() or {}
        archive_b64 = data.get("archive")
        if archive_b64:
            payload = base64.b64decode(archive_b64)
        passphrase = passphrase or data.get("passphrase")
    if payload is None:
        return jsonify({"error": "archive payload required"}), 400
    stats = mem_export.import_encrypted(payload, passphrase=passphrase)
    return jsonify(stats)


@app.route("/memory/stats", methods=["GET"])
def memory_stats() -> Response:
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return Response("Forbidden", status=403)
    if secure_store.is_enabled():
        categories = secure_store.category_counts()
        count = secure_store.fragment_count()
    else:
        categories = {}
        count = sum(1 for _ in mm.iter_fragments(limit=5000, reverse=False))
    return jsonify({"categories": categories, "count": count})


@app.route("/status", methods=["GET"])
def status() -> Response:
    loop_status: Dict[str, Any] = {}
    try:
        loop_status = dream_loop.status()
    except Exception:  # pragma: no cover - defensive
        loop_status = {"active": False}
    payload: Dict[str, Any] = {
        "incognito": _incognito_enabled(),
        "dream_loop_active": bool(loop_status.get("active")),
        "safety_events_1h": count_recent_events(1),
    }
    if secure_store.is_enabled():
        payload.update(
            {
                "memory_db_size_bytes": secure_store.db_size_bytes(),
                "mem_entries": secure_store.fragment_count(),
                "active_key_id": secure_store.get_backend().get_active_key_id(),
                "last_rotation_at": secure_store.get_meta("last_rotation_at"),
                "last_reflection_at": secure_store.get_meta("last_reflection_at"),
            }
        )
    else:
        payload.update(
            {
                "memory_db_size_bytes": 0,
                "mem_entries": sum(1 for _ in mm.iter_fragments(limit=1000, reverse=False)),
                "active_key_id": None,
                "last_rotation_at": None,
                "last_reflection_at": None,
            }
        )
    payload["dream_loop"] = loop_status
    payload["role"] = _ROLE or "core"
    payload["upstream_host"] = _UPSTREAM_CORE or None
    payload["capability_map"] = registry.capability_map()
    payload["webui_enabled"] = _WEBUI_ENABLED
    return jsonify(payload)


@app.route("/health/status", methods=["GET"])
def health_status() -> Response:
    payload = {
        "incognito": _incognito_enabled(),
        "secure_store": secure_store.is_enabled(),
        "watchdog": None,
        "console": {"enabled": _CONSOLE_ENABLED},
        "voice": {"enabled": _VOICE_ENABLED},
    }
    if _VOICE_ENABLED:
        payload["voice"]["stt"] = _STT_CONFIG
    payload["watchdog"] = WATCHDOG.snapshot()
    return jsonify(payload)


@app.route("/dreamloop/status", methods=["GET"])
def dreamloop_status() -> Response:
    payload: Dict[str, Any] = {}
    try:
        payload.update(dream_loop.status())
    except Exception:  # pragma: no cover - defensive
        payload["active"] = False
    payload["dream_loop_enabled"] = dream_loop.is_enabled()
    payload["watchdog"] = WATCHDOG.snapshot()
    payload["console"] = {"enabled": _CONSOLE_ENABLED}
    payload["voice"] = {"enabled": _VOICE_ENABLED, "config": _STT_CONFIG}
    return jsonify(payload)


@app.route("/act", methods=["POST"])
def act():
    if _ROLE == "thin":
        payload = request.get_json() or {}
        upstream = _proxy_upstream_json("/act", payload)
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    payload = request.get_json() or {}
    if not payload.get("async"):
        remote = _proxy_remote_json("/act", payload)
        if remote is not None:
            return jsonify(remote)

    payload = dict(payload)
    explanation = payload.pop("why", None)
    user = request.headers.get("X-User", "relay")
    call_id = write_mem(
        f"[ACT REQUEST] {json.dumps(payload)}",
        tags=["act", "request"],
        source=user,
    )
    if payload.pop("async", False):
        action_id = actuator.start_async(payload, explanation=explanation, user=user)
        return jsonify({"status": "queued", "action_id": action_id, "request_log_id": call_id})

    result = actuator.act(payload, explanation=explanation, user=user)
    result["request_log_id"] = call_id
    return jsonify(result)


@app.route("/act_status", methods=["POST"])
def act_status():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")
    return jsonify(actuator.get_status(aid))


@app.route("/act_stream", methods=["POST"])
def act_stream():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")

    def gen():
        last = None
        while True:
            status = actuator.get_status(aid)
            if status != last:
                yield f"data: {json.dumps(status)}\n\n"
                last = status
            if status.get("status") in {"finished", "failed", "unknown"}:
                break
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


@app.route("/goals/list", methods=["POST"])
def goals_list():
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/list", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    return jsonify(mm.get_goals(open_only=False))


@app.route("/goals/add", methods=["POST"])
def goals_add():
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/add", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    data = request.get_json() or {}
    intent = data.get("intent") or {}
    goal = mm.add_goal(
        data.get("text", ""),
        intent=intent,
        priority=int(data.get("priority", 1)),
        deadline=data.get("deadline"),
        schedule_at=data.get("schedule_at"),
    )
    return jsonify(goal)


@app.route("/goals/complete", methods=["POST"])
def goals_complete():
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/complete", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    gid = (request.get_json() or {}).get("id")
    goal = mm.get_goal(gid)
    if not goal:
        return "not found", 404
    goal["status"] = "completed"
    mm.save_goal(goal)
    return jsonify({"status": "ok"})


@app.route("/goals/delete", methods=["POST"])
def goals_delete():
    if _ROLE == "thin":
        upstream = _proxy_upstream_json("/goals/delete", request.get_json() or {})
        if upstream is not None:
            return jsonify(upstream)
        return jsonify({"error": "upstream_unavailable"}), 503
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    gid = (request.get_json() or {}).get("id")
    mm.delete_goal(gid)
    return jsonify({"status": "deleted"})


@app.route("/agent/run", methods=["POST"])
def agent_run():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    cycles = int((request.get_json() or {}).get("cycles", 1))
    import autonomous_reflector as ar
    ar.run_loop(iterations=cycles, interval=0.01)
    return jsonify({"status": "ran", "cycles": cycles})


def _read_last(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        return json.loads(line)
    except Exception:
        return {}


@app.route("/mood")
def mood() -> Response:
    data = _read_last(epu.MOOD_LOG)
    return jsonify(data.get("mood", {}))


@app.route("/current_emotion")
def current_emotion() -> Response:
    return mood()


@app.route("/eeg")
def eeg_state() -> Response:
    path = get_log_path("eeg_events.jsonl", "EEG_LOG")
    return jsonify(_read_last(path))


@app.route("/haptics")
def haptics_state() -> Response:
    path = get_log_path("haptics_events.jsonl", "HAPTIC_LOG")
    return jsonify(_read_last(path))


@app.route("/bio")
def bio_state() -> Response:
    path = get_log_path("bio_events.jsonl", "BIO_LOG")
    return jsonify(_read_last(path))


def register_voice_activity(hostname: str, timestamp: float | None = None) -> None:
    if not hostname:
        return
    record = _registry_record_voice_activity(hostname, timestamp=timestamp)
    if record is None:
        record = _registry_register_or_update(hostname, "127.0.0.1", last_voice_activity=timestamp or time.time())
    if record:
        _notify_admin(
            "voice-activity",
            {"hostname": record.hostname, "timestamp": record.last_voice_activity},
        )


def register_voice_session(
    summary: str,
    *,
    hostname: str | None = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    fragment = governor.remember_voice_session(summary, meta=meta)
    if not fragment:
        return
    logging.debug("[Voice] Stored session summary for %s", fragment.get("id"))
    if hostname:
        _registry_record_voice_activity(hostname, timestamp=time.time())
    _notify_admin("memory", {"category": "voice_session"})


def register_watchdog_check(name: str, check) -> None:
    WATCHDOG.register_check(name, check)


register_watchdog_check("relay", lambda: (True, None))
WATCHDOG.register_check("memory", lambda: (secure_store.is_enabled(), None))


if __name__ == "__main__":
    print("[Relay] Lumos blessing auto-approved (headless/auto mode).")
    print(f"[Relay] Starting Flask relay service on http://{_RELAY_HOST}:{_RELAY_PORT} …")
    print(f"[SentientOS] Relay bound to http://{_RELAY_HOST}:{_RELAY_PORT}")
    app.run(host=_RELAY_HOST, port=_RELAY_PORT)
