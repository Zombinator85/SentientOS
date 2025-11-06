from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import random
import secrets
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

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
        return payload


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

    # -- public API ---------------------------------------------------------

    def verify_bundle(self, bundle: Mapping[str, Any]) -> VerificationReport:
        if not isinstance(bundle, Mapping):
            raise ValueError("bundle must be a mapping")
        self._enforce_limits(bundle)
        script = bundle.get("script")
        claimed_run = bundle.get("claimed_run")
        env = bundle.get("env") or {}
        if not isinstance(env, Mapping):
            env = {}
        report = self.verify_script(script, claimed_run, env=env)
        try:
            self._store.save_bundle(report.job_id, dict(bundle))
        except Exception:  # pragma: no cover - storage failures should not fail verification
            pass
        return report

    def verify_script(
        self,
        script: Mapping[str, Any] | None,
        run_log: Mapping[str, Any] | None,
        *,
        env: Mapping[str, Any] | None = None,
    ) -> VerificationReport:
        script_payload = self._normalise_script(script)
        env_payload = dict(env or {})
        script_hash = self._script_hash(script_payload)
        job_id = self._generate_job_id()
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
        verdict = "REPLAY_ERROR"
        score = 0.0
        try:
            replay = self._replay_engine(script_payload, env_payload, claimed_steps=claimed_steps)
            replay_steps = replay["steps"]
            replay_final_state_hash = replay["final_state_hash"]
            replay_log_hash = replay["log_hash"]
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
        state_seed = "0" * 64
        for index, raw_step in enumerate(steps[:_MAX_STEPS]):
            if not isinstance(raw_step, Mapping):
                continue
            action = str(raw_step.get("action") or "noop")
            result = self._execute_step(action, raw_step, rng)
            timestamp = self._resolve_timestamp(start_time, clock_mode, index, claimed_steps)
            state_seed = self._state_hash(state_seed, result, index)
            replay_steps.append(
                StepResult(
                    index=index,
                    action=action,
                    result=result,
                    timestamp=timestamp,
                    state_hash=state_seed,
                )
            )
        serialised = [step.to_dict() for step in replay_steps]
        return {
            "steps": serialised,
            "final_state_hash": state_seed,
            "log_hash": self._log_hash(serialised),
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


def _utcnow_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()


__all__ = [
    "SentientVerifier",
    "VerificationReport",
    "StepResult",
    "StepDiff",
]
