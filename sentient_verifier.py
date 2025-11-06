from __future__ import annotations

import base64
import datetime as _dt
import ast
import base64
import operator
import hashlib
import json
import random
import secrets
import socket
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from nacl.signing import SigningKey, VerifyKey

from node_registry import NodeRegistry, registry as global_registry
from pairing_service import PairingService
from verifier_store import VerifierStore


_MAX_BUNDLE_BYTES = 5_000_000
_MAX_STEPS = 1_000


@dataclass
class StepResult:
    index: int
    action: str
    result: Mapping[str, Any]
    timestamp: float
    state_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "i": self.index,
            "action": self.action,
            "result": _as_jsonable(self.result),
            "ts": self.timestamp,
            "state_hash": self.state_hash,
        }


@dataclass
class StepDiff:
    step: int
    field: str
    expected: Any
    observed: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "field": self.field,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass
class ProofTrace:
    step: int
    pre: Optional[str] = None
    post: Optional[str] = None
    status: str = "SKIP"
    pre_status: Optional[str] = None
    post_status: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"step": self.step, "status": self.status}
        if self.pre is not None:
            payload["pre"] = self.pre
        if self.post is not None:
            payload["post"] = self.post
        if self.pre_status:
            payload["pre_status"] = self.pre_status
        if self.post_status:
            payload["post_status"] = self.post_status
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass
class VerificationReport:
    job_id: str
    script_hash: str
    from_node: Optional[str]
    verifier_node: str
    verdict: str
    score: float
    diffs: List[StepDiff] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamps: Dict[str, Any] = field(default_factory=dict)
    signer_fingerprint: Optional[str] = None
    signature: Optional[str] = None
    proofs: List[ProofTrace] = field(default_factory=list)
    proof_counts: Dict[str, int] = field(default_factory=dict)
    proof_hash: Optional[str] = None

    def to_dict(self, *, include_signature: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": self.job_id,
            "script_hash": self.script_hash,
            "from_node": self.from_node,
            "verifier_node": self.verifier_node,
            "verdict": self.verdict,
            "score": self.score,
            "diffs": [diff.to_dict() for diff in self.diffs],
            "evidence": _as_jsonable(self.evidence),
            "timestamps": dict(self.timestamps),
        }
        if self.signer_fingerprint:
            payload["signer_fingerprint"] = self.signer_fingerprint
        if include_signature and self.signature:
            payload["signature"] = self.signature
        if self.proofs:
            payload["proofs"] = [trace.to_dict() for trace in self.proofs]
        if self.proof_counts:
            payload["proof_counts"] = dict(self.proof_counts)
        if self.proof_hash:
            payload["proof_hash"] = self.proof_hash
        return payload


@dataclass(frozen=True)
class Vote:
    job_id: str
    script_hash: str
    local_verdict: str
    proof_hash: Optional[str]
    merkle_root: Optional[str]
    metrics: Mapping[str, Any]
    voter_node: str
    voter_sig: str
    ts: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "script_hash": self.script_hash,
            "local_verdict": self.local_verdict,
            "proof_hash": self.proof_hash,
            "merkle_root": self.merkle_root,
            "metrics": _as_jsonable(self.metrics),
            "voter_node": self.voter_node,
            "voter_sig": self.voter_sig,
            "ts": self.ts,
        }

    def digest(self) -> str:
        payload = {
            "job_id": self.job_id,
            "local_verdict": self.local_verdict,
            "merkle_root": self.merkle_root,
            "proof_hash": self.proof_hash,
            "script_hash": self.script_hash,
            "ts": self.ts,
            "voter_node": self.voter_node,
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConsensusVerdict:
    job_id: str
    script_hash: str
    quorum_k: int
    quorum_n: int
    votes: Sequence[Vote]
    final_verdict: str
    merkle_root: Optional[str]
    bundle_sig: Optional[str]
    finalized_at: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "script_hash": self.script_hash,
            "quorum_k": self.quorum_k,
            "quorum_n": self.quorum_n,
            "votes": [vote.to_dict() for vote in self.votes],
            "final_verdict": self.final_verdict,
            "merkle_root": self.merkle_root,
            "bundle_sig": self.bundle_sig,
            "finalized_at": self.finalized_at,
        }


class SentientVerifier:
    """Perform deterministic replay of Sentient Script executions."""

    def __init__(
        self,
        *,
        registry: Optional[NodeRegistry] = None,
        store: Optional[VerifierStore] = None,
    ) -> None:
        self._registry = registry or global_registry
        self._store = store or VerifierStore.default()
        self._pairing = PairingService()
        self._signing_key: SigningKey = self._pairing._signing_key  # pylint: disable=protected-access
        self._verify_key = self._signing_key.verify_key
        self._fingerprint = self._pairing.public_key_fingerprint
        self._pending = 0
        self._last_verdict: Optional[str] = None
        self._last_error: Optional[str] = None
        self._register_local_capabilities()

    # -- public API ---------------------------------------------------------

    def verify_bundle(
        self,
        bundle: Mapping[str, Any],
        *,
        job_id_override: Optional[str] = None,
        persist_bundle: bool = True,
    ) -> VerificationReport:
        if not isinstance(bundle, Mapping):
            raise ValueError("bundle must be a mapping")
        self._enforce_limits(bundle)
        script = bundle.get("script")
        claimed_run = bundle.get("claimed_run")
        env = bundle.get("env") or {}
        if not isinstance(env, Mapping):
            env = {}
        report = self.verify_script(script, claimed_run, env=env, job_id_override=job_id_override)
        if persist_bundle:
            try:
                self._store.save_bundle(report.job_id, dict(bundle))
            except Exception:  # pragma: no cover - storage failures should not fail verification
                pass
        return report

    def replay_job(self, job_id: str) -> VerificationReport:
        bundle = self._store.get_bundle(job_id)
        if bundle is None:
            raise ValueError("unknown_job")
        if not isinstance(bundle, Mapping):
            raise ValueError("invalid_bundle")
        return self.verify_bundle(dict(bundle), job_id_override=job_id, persist_bundle=False)

    def verify_script(
        self,
        script: Mapping[str, Any] | None,
        run_log: Mapping[str, Any] | None,
        *,
        env: Mapping[str, Any] | None = None,
        job_id_override: Optional[str] = None,
    ) -> VerificationReport:
        script_payload = self._normalise_script(script)
        env_payload = dict(env or {})
        script_hash = self._script_hash(script_payload)
        job_id = job_id_override or self._generate_job_id()
        submitted_at = _utcnow_iso()
        from_node = None
        claimed_steps: List[Dict[str, Any]] = []
        claimed_final_state_hash: Optional[str] = None
        claimed_log_hash: Optional[str] = None
        signature_valid = True

        if run_log and isinstance(run_log, Mapping):
            from_node = self._optional_string(run_log.get("from_node"))
            claimed_steps = self._extract_steps(run_log)
            claimed_final_state_hash = self._optional_string(run_log.get("final_state_hash"))
            claimed_log_hash = self._log_hash(claimed_steps) if claimed_steps else None
            signature_valid = self._verify_claimed_signature(script_hash, run_log)

        diffs: List[StepDiff] = []
        evidence: Dict[str, Any] = {}
        proof_traces: List[ProofTrace] = []
        proof_counts: Dict[str, int] = {"pass": 0, "fail": 0, "error": 0}
        proof_hash: Optional[str] = None
        verdict = "REPLAY_ERROR"
        score = 0.0
        try:
            replay = self._replay_engine(script_payload, env_payload, claimed_steps=claimed_steps)
            replay_steps = replay["steps"]
            replay_final_state_hash = replay["final_state_hash"]
            replay_log_hash = replay["log_hash"]
            proof_traces = replay.get("proofs", [])
            proof_counts = replay.get("proof_counts", proof_counts)
            proof_hash = replay.get("proof_hash")
            if claimed_steps:
                diffs = self._diff(claimed_steps, replay_steps)
            verdict = self._verdict(signature_valid, diffs, error=None)
            score = self._score_for_verdict(verdict)
            evidence = {
                "replay_final_state_hash": replay_final_state_hash,
                "claimed_final_state_hash": claimed_final_state_hash,
                "replay_log_hash": replay_log_hash,
                "claimed_log_hash": claimed_log_hash,
            }
        except Exception as exc:  # pragma: no cover - defensive guard
            verdict = self._verdict(signature_valid, [], error=str(exc))
            score = self._score_for_verdict(verdict)
            evidence = {
                "replay_final_state_hash": None,
                "claimed_final_state_hash": claimed_final_state_hash,
                "replay_log_hash": None,
                "claimed_log_hash": claimed_log_hash,
            }
            self._last_error = str(exc)
        else:
            self._last_error = None

        timestamps = {
            "submitted": submitted_at,
            "verified": _utcnow_iso(),
        }
        report = VerificationReport(
            job_id=job_id,
            script_hash=script_hash,
            from_node=from_node,
            verifier_node=self._local_hostname(),
            verdict=verdict,
            score=score,
            diffs=diffs,
            evidence=evidence,
            timestamps=timestamps,
            proofs=proof_traces,
            proof_counts=proof_counts,
            proof_hash=proof_hash,
        )
        self.sign_report(report)
        self._store.save_report(report.to_dict())
        if from_node:
            self._apply_trust_outcome(from_node, verdict)
        self._last_verdict = verdict
        return report

    def sign_report(self, report: VerificationReport) -> VerificationReport:
        payload = report.to_dict(include_signature=False)
        payload.pop("signature", None)
        message = _canonical_json(payload).encode("utf-8")
        signature = self._signing_key.sign(message).signature
        report.signature = base64.b64encode(signature).decode("ascii")
        report.signer_fingerprint = self._fingerprint
        return report

    def make_vote(self, report: VerificationReport) -> Vote:
        merkle_root = merkle_root_for_report(report)
        payload = {
            "job_id": report.job_id,
            "script_hash": report.script_hash,
            "proof_hash": report.proof_hash,
            "merkle_root": merkle_root,
        }
        message = _canonical_json(payload).encode("utf-8")
        signature = self._signing_key.sign(message).signature
        voter_sig = base64.b64encode(signature).decode("ascii")
        metrics: Dict[str, Any] = {
            "score": report.score,
            "proof_counts": dict(report.proof_counts),
            "diffs": len(report.diffs),
        }
        vote = Vote(
            job_id=report.job_id,
            script_hash=report.script_hash,
            local_verdict=report.verdict,
            proof_hash=report.proof_hash,
            merkle_root=merkle_root,
            metrics=metrics,
            voter_node=self._local_hostname(),
            voter_sig=voter_sig,
            ts=time.time(),
        )
        return vote

    def sign_consensus(self, consensus: ConsensusVerdict, *, timestamp: Optional[float] = None) -> ConsensusVerdict:
        payload = _consensus_signature_payload(consensus)
        message = _canonical_json(payload).encode("utf-8")
        signature = self._signing_key.sign(message).signature
        bundle_sig = base64.b64encode(signature).decode("ascii")
        finalised = timestamp if timestamp is not None else time.time()
        return ConsensusVerdict(
            job_id=consensus.job_id,
            script_hash=consensus.script_hash,
            quorum_k=consensus.quorum_k,
            quorum_n=consensus.quorum_n,
            votes=tuple(consensus.votes),
            final_verdict=consensus.final_verdict,
            merkle_root=consensus.merkle_root,
            bundle_sig=bundle_sig,
            finalized_at=finalised,
        )

    def verify_signature(self, report: Mapping[str, Any]) -> bool:
        signature = report.get("signature")
        if not isinstance(signature, str) or not signature:
            return False
        payload = dict(report)
        payload.pop("signature", None)
        try:
            message = _canonical_json(payload).encode("utf-8")
            self._verify_key.verify(message, base64.b64decode(signature))
        except Exception:  # pragma: no cover - defensive
            return False
        return True

    def status(self) -> Dict[str, Any]:
        return {
            "pending": self._pending,
            "last_verdict": self._last_verdict,
            "last_error": self._last_error,
        }

    # -- helpers -------------------------------------------------------------

    def _apply_trust_outcome(self, hostname: str, verdict: str) -> None:
        try:
            self._registry.apply_verification_outcome(hostname, verdict)
        except AttributeError:
            pass

    def _register_local_capabilities(self) -> None:
        try:
            hostname = self._local_hostname()
            record = self._registry.get(hostname)
            capabilities: Dict[str, Any] = {"verifier_capable": True}
            trust_level = "trusted"
            ip = "127.0.0.1"
            port = 5000
            if record is not None:
                capabilities.update(record.capabilities)
                trust_level = record.trust_level
                ip = record.ip
                port = record.port
            capabilities["verifier_pubkey"] = base64.b64encode(self._verify_key.encode()).decode("ascii")
            self._registry.register_or_update(
                hostname,
                ip,
                port=port,
                capabilities=capabilities,
                trust_level=trust_level,
                pubkey_fingerprint=self._fingerprint,
                roles=getattr(record, "roles", None),
            )
            self._registry.set_local_identity(hostname)
        except Exception:
            # Registry updates should not prevent verifier startup.
            pass

    def _generate_job_id(self) -> str:
        return f"vfy_{secrets.token_hex(6)}"

    def _local_hostname(self) -> str:
        host = self._registry.local_hostname
        if host:
            return host
        return socket.gethostname()

    @staticmethod
    def _normalise_script(script: Mapping[str, Any] | None) -> Dict[str, Any]:
        if isinstance(script, Mapping):
            return dict(script)
        if script is None:
            return {}
        raise ValueError("script must be a mapping")

    def _extract_steps(self, run_log: Mapping[str, Any]) -> List[Dict[str, Any]]:
        steps_obj = run_log.get("steps")
        if not isinstance(steps_obj, Sequence):
            return []
        steps: List[Dict[str, Any]] = []
        for raw in list(steps_obj)[:_MAX_STEPS]:
            if isinstance(raw, Mapping):
                steps.append({
                    "i": int(raw.get("i") or len(steps)),
                    "action": str(raw.get("action") or ""),
                    "result": _as_jsonable(raw.get("result") or {}),
                    "ts": float(raw.get("ts") or 0.0),
                    "state_hash": str(raw.get("state_hash") or ""),
                })
        return steps

    def _verify_claimed_signature(self, script_hash: str, run_log: Mapping[str, Any]) -> bool:
        signature = run_log.get("signature")
        fingerprint = self._optional_string(run_log.get("signer_fingerprint"))
        if not isinstance(signature, str) or not signature:
            return False
        verify_key = self._lookup_verify_key(run_log, fingerprint)
        if verify_key is None:
            return False
        payload = dict(run_log)
        payload.pop("signature", None)
        payload["script_hash"] = script_hash
        message = _canonical_json(payload).encode("utf-8")
        try:
            verify_key.verify(message, base64.b64decode(signature))
        except Exception:  # pragma: no cover - invalid signature
            return False
        return True

    def _lookup_verify_key(self, run_log: Mapping[str, Any], fingerprint: Optional[str]) -> Optional[VerifyKey]:
        hostname = self._optional_string(run_log.get("from_node"))
        candidates: List[Any] = []
        if hostname:
            record = self._registry.get(hostname)
            if record is not None:
                candidates.append(record)
        if fingerprint:
            for record in self._registry.records():
                if record.pubkey_fingerprint == fingerprint:
                    candidates.append(record)
        for record in candidates:
            pubkey = record.capabilities.get("sentientscript_pubkey")
            if not isinstance(pubkey, str) or not pubkey:
                continue
            try:
                return VerifyKey(base64.b64decode(pubkey))
            except Exception:
                continue
        return None

    def _replay_engine(
        self,
        script: Mapping[str, Any],
        env: Mapping[str, Any],
        *,
        claimed_steps: Sequence[Mapping[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        steps = script.get("steps")
        if not isinstance(steps, Sequence):
            steps = []
        rng = random.Random(int(env.get("seed") or 0))
        start_time = float(env.get("start_time") or time.time())
        clock_mode = str(env.get("clock_mode") or "fixed").lower()
        replay_steps: List[StepResult] = []
        state = self._initial_state(env)
        previous_result: Optional[Mapping[str, Any]] = None
        proof_traces: List[ProofTrace] = []
        proof_counts = {"pass": 0, "fail": 0, "error": 0}
        state_seed = "0" * 64
        for index, raw_step in enumerate(steps[:_MAX_STEPS]):
            if not isinstance(raw_step, Mapping):
                continue
            action = str(raw_step.get("action") or "noop")
            state_before = deepcopy(state)
            step_traces = self._prepare_step_proofs(index, raw_step)
            if step_traces:
                context_before = self._proof_context(
                    state_before,
                    env,
                    result=None,
                    step=index,
                    previous=previous_result,
                )
                for trace in step_traces:
                    status, error = self._evaluate_proof_expression(trace.pre, context_before)
                    trace.pre_status = status
                    if error:
                        trace.error = error
            result = self._execute_step(action, raw_step, rng)
            timestamp = self._resolve_timestamp(start_time, clock_mode, index, claimed_steps)
            state_seed = self._state_hash(state_seed, result, index)
            state = self._update_state(state, result)
            if step_traces:
                context_after = self._proof_context(
                    state,
                    env,
                    result=result,
                    step=index,
                    previous=previous_result,
                )
                for trace in step_traces:
                    status, error = self._evaluate_proof_expression(trace.post, context_after)
                    trace.post_status = status
                    if error and not trace.error:
                        trace.error = error
                    self._finalise_trace_status(trace)
                    if trace.status == "PASS":
                        proof_counts["pass"] += 1
                    elif trace.status == "FAIL":
                        proof_counts["fail"] += 1
                    elif trace.status == "ERROR":
                        proof_counts["error"] += 1
                    proof_traces.append(trace)
            replay_steps.append(
                StepResult(
                    index=index,
                    action=action,
                    result=result,
                    timestamp=timestamp,
                    state_hash=state_seed,
                )
            )
            previous_result = result
        serialised = [step.to_dict() for step in replay_steps]
        proof_hash = self._proof_hash(proof_traces)
        return {
            "steps": serialised,
            "final_state_hash": state_seed,
            "log_hash": self._log_hash(serialised),
            "proofs": proof_traces,
            "proof_counts": proof_counts,
            "proof_hash": proof_hash,
        }

    def _execute_step(
        self,
        action: str,
        parameters: Mapping[str, Any],
        rng: random.Random,
    ) -> Dict[str, Any]:
        if action == "const":
            return {"value": parameters.get("value")}
        if action == "add":
            operands = self._numbers_from(parameters.get("operands"))
            return {"value": sum(operands)}
        if action == "multiply":
            operands = self._numbers_from(parameters.get("operands"))
            product = 1.0
            for operand in operands:
                product *= operand
            return {"value": product}
        if action == "random_int":
            minimum, maximum = self._int_bounds(parameters)
            return {"value": rng.randint(minimum, maximum)}
        if action == "random_float":
            minimum, maximum = self._float_bounds(parameters)
            return {"value": minimum + (maximum - minimum) * rng.random()}
        if action == "echo":
            payload = {key: value for key, value in parameters.items() if key != "action"}
            return payload or {"value": None}
        return {key: value for key, value in parameters.items() if key != "action"}

    def _initial_state(self, env: Mapping[str, Any]) -> Dict[str, Any]:
        state_obj = env.get("state")
        if isinstance(state_obj, Mapping):
            state = deepcopy(_as_jsonable(state_obj))
            if not isinstance(state, dict):
                state = dict(state)
        else:
            state = {}
        memory = state.get("memory")
        if isinstance(memory, Mapping):
            state["memory"] = dict(memory)
        else:
            state["memory"] = {}
        return state

    def _prepare_step_proofs(self, index: int, step: Mapping[str, Any]) -> List[ProofTrace]:
        proofs_obj = step.get("proofs")
        candidates: List[Mapping[str, Any]] = []
        if isinstance(proofs_obj, Mapping):
            candidates.append(proofs_obj)
        elif isinstance(proofs_obj, Sequence):
            for entry in proofs_obj:
                if isinstance(entry, Mapping):
                    candidates.append(entry)
        else:
            single = step.get("proof")
            if isinstance(single, Mapping):
                candidates.append(single)
        traces: List[ProofTrace] = []
        for candidate in candidates:
            pre = self._coerce_expression(candidate.get("pre") or candidate.get("precondition"))
            post = self._coerce_expression(candidate.get("post") or candidate.get("postcondition"))
            if pre is None and post is None:
                continue
            traces.append(ProofTrace(step=index, pre=pre, post=post))
        return traces

    @staticmethod
    def _coerce_expression(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _proof_context(
        self,
        state: Mapping[str, Any],
        env: Mapping[str, Any],
        *,
        result: Optional[Mapping[str, Any]],
        step: int,
        previous: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        memory = state.get("memory") if isinstance(state.get("memory"), Mapping) else {}
        return {
            "state": state,
            "memory": memory,
            "env": env,
            "result": result,
            "step": step,
            "previous_result": previous,
        }

    def _evaluate_proof_expression(
        self, expression: Optional[str], context: Mapping[str, Any]
    ) -> tuple[str, Optional[str]]:
        if not expression:
            return "SKIP", None
        try:
            outcome = bool(_safe_eval(expression, context))
        except Exception as exc:  # pragma: no cover - defensive
            return "ERROR", str(exc)
        return ("PASS" if outcome else "FAIL"), None

    @staticmethod
    def _finalise_trace_status(trace: ProofTrace) -> ProofTrace:
        statuses = [trace.pre_status, trace.post_status]
        if any(status == "ERROR" for status in statuses):
            trace.status = "ERROR"
        elif any(status == "FAIL" for status in statuses):
            trace.status = "FAIL"
        elif any(status == "PASS" for status in statuses):
            trace.status = "PASS"
        else:
            trace.status = "SKIP"
        return trace

    def _proof_hash(self, traces: Sequence[ProofTrace]) -> Optional[str]:
        if not traces:
            return None
        payload = [trace.to_dict() for trace in traces]
        return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _update_state(self, state: Dict[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        for key, value in result.items():
            if isinstance(value, Mapping):
                if key == "memory":
                    memory = state.setdefault("memory", {})
                    if isinstance(memory, dict):
                        memory.update(self._coerce_mapping(value))
                    else:
                        state["memory"] = self._coerce_mapping(value)
                else:
                    existing = state.get(key)
                    if isinstance(existing, dict):
                        existing.update(self._coerce_mapping(value))
                    else:
                        state[key] = self._coerce_mapping(value)
            else:
                state[key] = value
        return state

    @staticmethod
    def _coerce_mapping(value: Mapping[str, Any]) -> Dict[str, Any]:
        return {str(key): _as_jsonable(val) for key, val in value.items()}

    @staticmethod
    def _numbers_from(value: Any) -> List[float]:
        numbers: List[float] = []
        if isinstance(value, Sequence):
            for item in value:
                try:
                    numbers.append(float(item))
                except (TypeError, ValueError):
                    numbers.append(0.0)
        return numbers

    @staticmethod
    def _int_bounds(parameters: Mapping[str, Any]) -> tuple[int, int]:
        minimum = int(parameters.get("min") or parameters.get("minimum") or 0)
        maximum = int(parameters.get("max") or parameters.get("maximum") or minimum)
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    @staticmethod
    def _float_bounds(parameters: Mapping[str, Any]) -> tuple[float, float]:
        minimum = float(parameters.get("min") or parameters.get("minimum") or 0.0)
        maximum = float(parameters.get("max") or parameters.get("maximum") or 1.0)
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    def _resolve_timestamp(
        self,
        start_time: float,
        clock_mode: str,
        index: int,
        claimed_steps: Sequence[Mapping[str, Any]] | None,
    ) -> float:
        if clock_mode == "recorded" and claimed_steps and index < len(claimed_steps):
            try:
                return float(claimed_steps[index].get("ts") or start_time + index)
            except (TypeError, ValueError):
                return start_time + index
        return start_time + index

    def _state_hash(self, seed: str, result: Mapping[str, Any], index: int) -> str:
        payload = {
            "prev": seed,
            "index": index,
            "result": _as_jsonable(result),
        }
        return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _log_hash(self, steps: Sequence[Mapping[str, Any]]) -> str:
        return "sha256:" + hashlib.sha256(_canonical_json(list(steps)).encode("utf-8")).hexdigest()

    def _diff(
        self,
        expected: Sequence[Mapping[str, Any]],
        observed: Sequence[Mapping[str, Any]],
    ) -> List[StepDiff]:
        diffs: List[StepDiff] = []
        length = max(len(expected), len(observed))
        for index in range(length):
            if index >= len(expected):
                diffs.append(StepDiff(step=index, field="step", expected=None, observed=observed[index]))
                continue
            if index >= len(observed):
                diffs.append(StepDiff(step=index, field="step", expected=expected[index], observed=None))
                continue
            diffs.extend(self._compare_step(index, expected[index], observed[index]))
        return diffs

    def _compare_step(
        self,
        index: int,
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> List[StepDiff]:
        diffs: List[StepDiff] = []
        keys = set(expected.keys()) | set(observed.keys())
        for key in sorted(keys):
            exp_value = expected.get(key)
            obs_value = observed.get(key)
            if isinstance(exp_value, Mapping) and isinstance(obs_value, Mapping):
                diffs.extend(
                    self._compare_nested(index, f"{key}.", exp_value, obs_value)
                )
                continue
            if self._values_close(exp_value, obs_value):
                continue
            diffs.append(StepDiff(step=index, field=key, expected=exp_value, observed=obs_value))
        return diffs

    def _compare_nested(
        self,
        index: int,
        prefix: str,
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> List[StepDiff]:
        diffs: List[StepDiff] = []
        keys = set(expected.keys()) | set(observed.keys())
        for key in sorted(keys):
            field = f"{prefix}{key}"
            exp_value = expected.get(key)
            obs_value = observed.get(key)
            if isinstance(exp_value, Mapping) and isinstance(obs_value, Mapping):
                diffs.extend(self._compare_nested(index, f"{field}.", exp_value, obs_value))
                continue
            if self._values_close(exp_value, obs_value):
                continue
            diffs.append(StepDiff(step=index, field=field, expected=exp_value, observed=obs_value))
        return diffs

    @staticmethod
    def _values_close(lhs: Any, rhs: Any) -> bool:
        if lhs == rhs:
            return True
        try:
            return abs(float(lhs) - float(rhs)) < 1e-9
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _score_for_verdict(verdict: str) -> float:
        mapping = {
            "VERIFIED_OK": 1.0,
            "DIVERGED": 0.3,
            "SIGNATURE_MISMATCH": 0.0,
            "REPLAY_ERROR": 0.0,
        }
        return mapping.get(verdict, 0.0)

    def _verdict(self, signature_valid: bool, diffs: Iterable[StepDiff], *, error: Optional[str]) -> str:
        if not signature_valid:
            return "SIGNATURE_MISMATCH"
        if error:
            return "REPLAY_ERROR"
        if list(diffs):
            return "DIVERGED"
        return "VERIFIED_OK"

    def _script_hash(self, script: Mapping[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(_canonical_json(script).encode("utf-8")).hexdigest()

    @staticmethod
    def _optional_string(value: object) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

    def _enforce_limits(self, bundle: Mapping[str, Any]) -> None:
        try:
            encoded = json.dumps(bundle).encode("utf-8")
        except Exception as exc:  # pragma: no cover - serialization failure
            raise ValueError("bundle must be JSON serialisable") from exc
        if len(encoded) > _MAX_BUNDLE_BYTES:
            raise ValueError("bundle exceeds size limit")
        claimed_run = bundle.get("claimed_run")
        if isinstance(claimed_run, Mapping):
            steps = claimed_run.get("steps")
            if isinstance(steps, Sequence) and len(steps) > _MAX_STEPS:
                raise ValueError("claimed run exceeds step limit")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _as_jsonable(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _as_jsonable(value) for key, value in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [_as_jsonable(item) for item in payload]
    return payload


def merkle_root_for_report(report: VerificationReport | Mapping[str, Any]) -> Optional[str]:
    proofs: Sequence[Any]
    if isinstance(report, VerificationReport):
        proofs = report.proofs
    elif isinstance(report, Mapping):
        proofs_obj = report.get("proofs")
        if isinstance(proofs_obj, Sequence):
            proofs = list(proofs_obj)
        else:
            proofs = []
    else:
        proofs = []
    leaves: List[bytes] = []
    for raw in proofs:
        if isinstance(raw, ProofTrace):
            step = int(raw.step)
            status = str(raw.status)
            digest = raw.post or ""
        elif isinstance(raw, Mapping):
            step = int(raw.get("step") or 0)
            status = str(raw.get("status") or "SKIP")
            digest = raw.get("post_state_digest")
            if digest is None:
                digest = raw.get("post")
            if digest is None:
                digest = ""
        else:
            continue
        if digest is None:
            digest = ""
        payload = f"{step}|{status}|{digest}".encode("utf-8")
        leaves.append(hashlib.sha256(payload).digest())
    if not leaves:
        return None
    nodes = leaves
    while len(nodes) > 1:
        next_level: List[bytes] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
            digest = hashlib.sha256(left + right).digest()
            next_level.append(digest)
        nodes = next_level
    return nodes[0].hex()


def merge_votes(votes: Sequence[Vote], quorum_k: int, quorum_n: int) -> ConsensusVerdict:
    if quorum_k <= 0 or quorum_n <= 0:
        raise ValueError("quorum thresholds must be positive")
    if not votes:
        raise ValueError("votes required to merge")
    unique: Dict[str, Vote] = {}
    for vote in sorted(votes, key=lambda item: (item.voter_node, item.ts)):
        previous = unique.get(vote.voter_node)
        if previous is None:
            unique[vote.voter_node] = vote
            continue
        if previous.digest() != vote.digest():
            raise ValueError(f"conflicting vote for node {vote.voter_node}")
    deduped = list(unique.values())
    job_ids = {vote.job_id for vote in deduped}
    script_hashes = {vote.script_hash for vote in deduped}
    if len(job_ids) != 1 or len(script_hashes) != 1:
        raise ValueError("votes reference multiple jobs or scripts")
    tally: Dict[str, List[Vote]] = {}
    for vote in deduped:
        tally.setdefault(vote.local_verdict, []).append(vote)
    verdict_priority = ["VERIFIED_OK", "DIVERGED", "MISMATCH", "INCONCLUSIVE"]
    winning_verdict = "INCONCLUSIVE"
    winning_votes: List[Vote] = []
    max_count = 0
    for verdict in verdict_priority:
        candidates = tally.get(verdict, [])
        if len(candidates) < quorum_k:
            continue
        digest_concat = "".join(sorted(vote.digest() for vote in candidates))
        count = len(candidates)
        priority = verdict_priority.index(verdict)
        replace = False
        if count > max_count:
            replace = True
        elif count == max_count and priority < verdict_priority.index(winning_verdict):
            replace = True
        elif count == max_count and verdict == winning_verdict:
            replace = digest_concat < "".join(sorted(vote.digest() for vote in winning_votes))
        if replace:
            max_count = count
            winning_verdict = verdict
            winning_votes = sorted(candidates, key=_vote_sort_key)
    majority_merkle: Optional[str] = None
    if winning_verdict != "INCONCLUSIVE" and winning_votes:
        roots = {vote.merkle_root for vote in winning_votes if vote.merkle_root}
        if len(roots) == 1:
            majority_merkle = next(iter(roots))
    ordered_votes = tuple(sorted(deduped, key=_vote_sort_key))
    return ConsensusVerdict(
        job_id=job_ids.pop(),
        script_hash=script_hashes.pop(),
        quorum_k=quorum_k,
        quorum_n=quorum_n,
        votes=ordered_votes,
        final_verdict=winning_verdict,
        merkle_root=majority_merkle,
        bundle_sig=None,
        finalized_at=None,
    )


def verify_vote_signatures(votes: Sequence[Vote], registry: NodeRegistry) -> bool:
    for vote in votes:
        try:
            verify_key = _load_verify_key_for_node(registry, vote.voter_node)
        except ValueError:
            return False
        if verify_key is None:
            return False
        try:
            signature = base64.b64decode(vote.voter_sig)
        except Exception:
            return False
        message = _canonical_json(_vote_signature_payload(vote)).encode("utf-8")
        try:
            verify_key.verify(message, signature)
        except Exception:
            return False
    return True


def verify_consensus_signatures(consensus: ConsensusVerdict, registry: NodeRegistry) -> bool:
    if not verify_vote_signatures(consensus.votes, registry):
        return False
    if not consensus.bundle_sig:
        return True
    hostname = registry.local_hostname
    if not hostname:
        return False
    verify_key = _load_verify_key_for_node(registry, hostname)
    if verify_key is None:
        return False
    try:
        signature = base64.b64decode(consensus.bundle_sig)
    except Exception:
        return False
    message = _canonical_json(_consensus_signature_payload(consensus)).encode("utf-8")
    try:
        verify_key.verify(message, signature)
    except Exception:
        return False
    return True


def _load_verify_key_for_node(registry: NodeRegistry, hostname: str) -> Optional[VerifyKey]:
    record = registry.get(hostname)
    if record is None:
        return None
    pubkey = record.capabilities.get("verifier_pubkey")
    if not isinstance(pubkey, str) or not pubkey:
        return None
    try:
        return VerifyKey(base64.b64decode(pubkey))
    except Exception as exc:  # pragma: no cover - invalid key material
        raise ValueError("invalid verifier key") from exc


def _vote_signature_payload(vote: Vote) -> Mapping[str, Any]:
    return {
        "job_id": vote.job_id,
        "script_hash": vote.script_hash,
        "proof_hash": vote.proof_hash,
        "merkle_root": vote.merkle_root,
    }


def _vote_sort_key(vote: Vote) -> Tuple[str, float, str]:
    return (
        vote.voter_node,
        float(vote.ts),
        vote.digest(),
    )


def _consensus_signature_payload(consensus: ConsensusVerdict) -> Mapping[str, Any]:
    digests = [vote.digest() for vote in sorted(consensus.votes, key=_vote_sort_key)]
    return {
        "job_id": consensus.job_id,
        "script_hash": consensus.script_hash,
        "quorum_k": consensus.quorum_k,
        "quorum_n": consensus.quorum_n,
        "final_verdict": consensus.final_verdict,
        "merkle_root": consensus.merkle_root,
        "votes": digests,
    }


_ALLOWED_BIN_OPS: Dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPS: Dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_ALLOWED_COMPARISONS: Dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.In: lambda lhs, rhs: lhs in rhs,
    ast.NotIn: lambda lhs, rhs: lhs not in rhs,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}
_ALLOWED_CALLS: Dict[str, Any] = {
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "all": all,
    "any": any,
    "round": round,
}


def _safe_eval(expression: str, context: Mapping[str, Any]) -> Any:
    tree = ast.parse(expression, mode="eval")

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in {"True", "False", "None"}:
                return {"True": True, "False": False, "None": None}[node.id]
            if node.id in context:
                return context[node.id]
            raise ValueError(f"unknown name: {node.id}")
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(_eval(value) for value in node.values)
            if isinstance(node.op, ast.Or):
                return any(_eval(value) for value in node.values)
            raise ValueError("unsupported boolean operator")
        if isinstance(node, ast.UnaryOp):
            func = _ALLOWED_UNARY_OPS.get(type(node.op))
            if func is None:
                raise ValueError("unsupported unary operator")
            return func(_eval(node.operand))
        if isinstance(node, ast.BinOp):
            func = _ALLOWED_BIN_OPS.get(type(node.op))
            if func is None:
                raise ValueError("unsupported binary operator")
            return func(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                func = _ALLOWED_COMPARISONS.get(type(op))
                if func is None:
                    raise ValueError("unsupported comparison")
                right = _eval(comparator)
                if not func(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Subscript):
            base = _eval(node.value)
            index_node = node.slice
            if isinstance(index_node, ast.Slice):
                lower = _eval(index_node.lower) if index_node.lower else None
                upper = _eval(index_node.upper) if index_node.upper else None
                step = _eval(index_node.step) if index_node.step else None
                return base[slice(lower, upper, step)]
            if hasattr(ast, "Index") and isinstance(index_node, ast.Index):  # pragma: no cover - py<3.9
                index_node = index_node.value
            index = _eval(index_node)
            return base[index]
        if isinstance(node, ast.Dict):
            return {_eval(key): _eval(value) for key, value in zip(node.keys, node.values)}
        if isinstance(node, ast.List):
            return [_eval(element) for element in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_eval(element) for element in node.elts)
        if isinstance(node, ast.Set):
            return {_eval(element) for element in node.elts}
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_CALLS:
                func = _ALLOWED_CALLS[node.func.id]
                args = [_eval(arg) for arg in node.args]
                kwargs = {kw.arg: _eval(kw.value) for kw in node.keywords if kw.arg}
                if any(kw.arg is None for kw in node.keywords):
                    raise ValueError("keyword argument must be named")
                return func(*args, **kwargs)
            raise ValueError("disallowed function call")
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    return _eval(tree)


def _utcnow_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()


__all__ = [
    "SentientVerifier",
    "VerificationReport",
    "StepResult",
    "StepDiff",
    "ProofTrace",
]
