"""Deterministic trust-epoch tracking for pulse signing keys."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

_STATE_ENV = "PULSE_TRUST_EPOCH_STATE"
_ROOT_ENV = "PULSE_TRUST_EPOCH_ROOT"
_VERIFY_KEY_ENV = "PULSE_VERIFY_KEY"
_SIGNING_KEY_ENV = "PULSE_SIGNING_KEY"

_DEFAULT_ROOT = Path("/glow/pulse_trust")
_DEFAULT_STATE = _DEFAULT_ROOT / "epoch_state.json"

_MAX_COUNTER_KEYS = 64


@dataclass(frozen=True)
class EpochVerificationResult:
    signature_valid: bool
    trusted: bool
    classification: str
    epoch_id: str
    active_epoch_id: str
    key_id: str | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "signature_valid": self.signature_valid,
            "trusted": self.trusted,
            "classification": self.classification,
            "epoch_id": self.epoch_id,
            "active_epoch_id": self.active_epoch_id,
            "key_id": self.key_id,
            "reason": self.reason,
        }


class PulseTrustEpochManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._verify_cache: dict[str, VerifyKey] = {}

    def reset(self) -> None:
        with self._lock:
            self._verify_cache = {}

    def state_path(self) -> Path:
        return Path(os.getenv(_STATE_ENV, str(_DEFAULT_STATE)))

    def root_dir(self) -> Path:
        override = os.getenv(_ROOT_ENV)
        if override:
            return Path(override)
        return self.state_path().parent

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_jsonl(self, name: str, payload: Mapping[str, object]) -> None:
        path = self.root_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")

    def _write_state(self, state: Mapping[str, object]) -> None:
        path = self.state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _key_id_for_path(self, path: str) -> str | None:
        try:
            key = self._verify_key(path)
        except Exception:
            return None
        encoded = bytes(key.encode())
        digest = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
        return f"ed25519:{digest[:32]}"

    def _bootstrap_state(self) -> dict[str, object]:
        verify_path = str(Path(os.getenv(_VERIFY_KEY_ENV, "/vow/keys/ed25519_public.key")))
        signing_path = str(Path(os.getenv(_SIGNING_KEY_ENV, "/vow/keys/ed25519_private.key")))
        epoch_id = "epoch-0001"
        state = {
            "schema_version": 1,
            "active_epoch_id": epoch_id,
            "compromise_response_mode": False,
            "epochs": {
                epoch_id: {
                    "status": "active",
                    "verify_key_path": verify_path,
                    "signing_key_path": signing_path,
                    "activated_at": self._utc_now(),
                    "revoked": False,
                    "closed": False,
                    "transition_from": None,
                    "key_id": self._key_id_for_path(verify_path),
                }
            },
            "revoked_epochs": [],
            "transition_counter": 0,
            "decision_counters": {},
        }
        self._write_state(state)
        self._append_jsonl(
            "transitions.jsonl",
            {
                "event": "bootstrap_epoch",
                "epoch_id": epoch_id,
                "verify_key_path": verify_path,
                "signing_key_path": signing_path,
                "timestamp": state["epochs"][epoch_id]["activated_at"],
            },
        )
        return state

    def load_state(self) -> dict[str, object]:
        with self._lock:
            path = self.state_path()
            if not path.exists():
                return self._bootstrap_state()
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                return self._bootstrap_state()
            return state

    def active_epoch(self) -> dict[str, object]:
        state = self.load_state()
        epochs = state.get("epochs", {})
        active_id = str(state.get("active_epoch_id", "epoch-0001"))
        epoch = epochs.get(active_id)
        if not isinstance(epoch, dict):
            return self._bootstrap_state()["epochs"]["epoch-0001"]
        return epoch

    def active_epoch_id(self) -> str:
        return str(self.load_state().get("active_epoch_id", "epoch-0001"))

    def annotate_local_event(self, event: dict[str, object]) -> dict[str, object]:
        annotated = dict(event)
        epoch = self.active_epoch()
        annotated.setdefault("pulse_epoch_id", self.active_epoch_id())
        key_id = epoch.get("key_id")
        if isinstance(key_id, str) and key_id:
            annotated.setdefault("pulse_key_id", key_id)
        return annotated

    def _verify_key(self, path_value: str) -> VerifyKey:
        cached = self._verify_cache.get(path_value)
        if cached is not None:
            return cached
        key = VerifyKey(Path(path_value).read_bytes())
        self._verify_cache[path_value] = key
        return key

    def _bounded_increment(self, state: dict[str, object], key: str) -> None:
        counters_raw = state.setdefault("decision_counters", {})
        if not isinstance(counters_raw, dict):
            counters_raw = {}
            state["decision_counters"] = counters_raw
        counters = {str(k): int(v) for k, v in counters_raw.items() if isinstance(v, int)}
        counters[key] = counters.get(key, 0) + 1
        if len(counters) > _MAX_COUNTER_KEYS:
            ordered = sorted(counters.items(), key=lambda item: (-item[1], item[0]))[:_MAX_COUNTER_KEYS]
            counters = dict(ordered)
        state["decision_counters"] = counters

    @staticmethod
    def _parse_ts(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        text = value
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _retired_replay_allowance_seconds(self) -> int:
        value = os.getenv("SENTIENTOS_PULSE_RETIRED_REPLAY_SECONDS", "0").strip()
        try:
            return max(0, int(value))
        except ValueError:
            return 0

    def _retired_epoch_allowed(self, epoch_cfg: Mapping[str, object]) -> bool:
        allowance = self._retired_replay_allowance_seconds()
        if allowance <= 0:
            return False
        closed_at = self._parse_ts(epoch_cfg.get("closed_at"))
        if closed_at is None:
            return False
        return datetime.now(timezone.utc) <= closed_at + timedelta(seconds=allowance)

    def verify_event_signature(
        self,
        event: Mapping[str, object],
        *,
        serialized_payload: bytes,
        signature: str,
        actor: str,
        peer_name: str | None = None,
    ) -> EpochVerificationResult:
        state = self.load_state()
        active_epoch_id = str(state.get("active_epoch_id", "epoch-0001"))
        epochs = state.get("epochs", {})
        revoked = set(str(item) for item in state.get("revoked_epochs", []) if isinstance(item, str))
        epoch_id = str(event.get("pulse_epoch_id") or "legacy")

        candidate_epoch_ids: list[str] = [epoch_id]
        if epoch_id == "legacy":
            candidate_epoch_ids = sorted(str(key) for key in epochs.keys())

        valid_epoch: str | None = None
        valid_key_id: str | None = None
        signature_valid = False
        for candidate in candidate_epoch_ids:
            epoch_cfg = epochs.get(candidate)
            if not isinstance(epoch_cfg, dict):
                continue
            verify_path = epoch_cfg.get("verify_key_path")
            if not isinstance(verify_path, str) or not verify_path:
                continue
            try:
                verify_key = self._verify_key(verify_path)
                verify_key.verify(serialized_payload, base64.b64decode(signature))
                valid_epoch = candidate
                valid_key_id = epoch_cfg.get("key_id") if isinstance(epoch_cfg.get("key_id"), str) else None
                signature_valid = True
                break
            except (BadSignatureError, FileNotFoundError, ValueError, binascii.Error):
                continue

        if not signature_valid or valid_epoch is None:
            result = EpochVerificationResult(
                signature_valid=False,
                trusted=False,
                classification="invalid_signature",
                epoch_id=epoch_id,
                active_epoch_id=active_epoch_id,
                key_id=None,
                reason="signature_verification_failed",
            )
            self._record_decision(result, actor=actor, peer_name=peer_name)
            return result

        epoch_cfg = epochs.get(valid_epoch) if isinstance(epochs, dict) else None
        status = "unknown"
        if isinstance(epoch_cfg, dict):
            status = str(epoch_cfg.get("status") or "unknown")
        if valid_epoch in revoked or status == "revoked":
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=False,
                classification="revoked_epoch",
                epoch_id=valid_epoch,
                active_epoch_id=active_epoch_id,
                key_id=valid_key_id,
                reason="epoch_revoked",
            )
        elif valid_epoch == active_epoch_id:
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=True,
                classification="current_trusted_epoch",
                epoch_id=valid_epoch,
                active_epoch_id=active_epoch_id,
                key_id=valid_key_id,
                reason="active_epoch",
            )
        elif isinstance(epoch_cfg, dict) and self._retired_epoch_allowed(epoch_cfg):
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=True,
                classification="retired_epoch_replay_allowed",
                epoch_id=valid_epoch,
                active_epoch_id=active_epoch_id,
                key_id=valid_key_id,
                reason="retired_epoch_within_replay_window",
            )
        else:
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=False,
                classification="retired_epoch",
                epoch_id=valid_epoch,
                active_epoch_id=active_epoch_id,
                key_id=valid_key_id,
                reason="retired_epoch_outside_replay_window",
            )
        self._record_decision(result, actor=actor, peer_name=peer_name)
        return result

    def classify_epoch(
        self,
        event: Mapping[str, object],
        *,
        actor: str,
        peer_name: str | None = None,
    ) -> EpochVerificationResult:
        state = self.load_state()
        active_epoch_id = str(state.get("active_epoch_id", "epoch-0001"))
        epochs = state.get("epochs", {})
        revoked = set(str(item) for item in state.get("revoked_epochs", []) if isinstance(item, str))
        epoch_id = str(event.get("pulse_epoch_id") or "legacy")
        key_id = event.get("pulse_key_id")
        normalized_key_id = key_id if isinstance(key_id, str) and key_id else None
        if epoch_id == "legacy":
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=False,
                classification="unknown_epoch",
                epoch_id=epoch_id,
                active_epoch_id=active_epoch_id,
                key_id=normalized_key_id,
                reason="legacy_epoch_not_counted_for_federation",
            )
        elif epoch_id in revoked:
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=False,
                classification="revoked_epoch",
                epoch_id=epoch_id,
                active_epoch_id=active_epoch_id,
                key_id=normalized_key_id,
                reason="epoch_revoked",
            )
        elif isinstance(epochs, dict) and epoch_id not in epochs:
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=False,
                classification="unknown_epoch",
                epoch_id=epoch_id,
                active_epoch_id=active_epoch_id,
                key_id=normalized_key_id,
                reason="epoch_unknown",
            )
        elif epoch_id == active_epoch_id:
            result = EpochVerificationResult(
                signature_valid=True,
                trusted=True,
                classification="current_trusted_epoch",
                epoch_id=epoch_id,
                active_epoch_id=active_epoch_id,
                key_id=normalized_key_id,
                reason="active_epoch",
            )
        else:
            epoch_cfg = epochs.get(epoch_id) if isinstance(epochs, dict) else None
            if isinstance(epoch_cfg, dict) and self._retired_epoch_allowed(epoch_cfg):
                result = EpochVerificationResult(
                    signature_valid=True,
                    trusted=True,
                    classification="retired_epoch_replay_allowed",
                    epoch_id=epoch_id,
                    active_epoch_id=active_epoch_id,
                    key_id=normalized_key_id,
                    reason="retired_epoch_within_replay_window",
                )
            else:
                result = EpochVerificationResult(
                    signature_valid=True,
                    trusted=False,
                    classification="retired_epoch",
                    epoch_id=epoch_id,
                    active_epoch_id=active_epoch_id,
                    key_id=normalized_key_id,
                    reason="retired_epoch_outside_replay_window",
                )
        self._record_decision(result, actor=actor, peer_name=peer_name)
        return result

    def _record_decision(self, result: EpochVerificationResult, *, actor: str, peer_name: str | None) -> None:
        state = self.load_state()
        self._bounded_increment(state, result.classification)
        self._write_state(state)
        self._append_jsonl(
            "verification_decisions.jsonl",
            {
                "event": "pulse_epoch_verification",
                "actor": actor,
                "peer_name": peer_name,
                "classification": result.classification,
                "trusted": result.trusted,
                "signature_valid": result.signature_valid,
                "epoch_id": result.epoch_id,
                "active_epoch_id": result.active_epoch_id,
                "key_id": result.key_id,
                "reason": result.reason,
                "timestamp": self._utc_now(),
            },
        )

    def transition_epoch(
        self,
        *,
        new_epoch_id: str,
        verify_key_path: str,
        signing_key_path: str,
        actor: str,
        reason: str,
        compromise_response_mode: bool = False,
    ) -> dict[str, object]:
        state = self.load_state()
        epochs = state.setdefault("epochs", {})
        if not isinstance(epochs, dict):
            raise ValueError("invalid epoch state")
        active = str(state.get("active_epoch_id", "epoch-0001"))
        current = epochs.get(active)
        now = self._utc_now()
        if isinstance(current, dict):
            current["status"] = "closed"
            current["closed"] = True
            current["closed_at"] = now
        epochs[new_epoch_id] = {
            "status": "active",
            "verify_key_path": verify_key_path,
            "signing_key_path": signing_key_path,
            "activated_at": now,
            "revoked": False,
            "closed": False,
            "transition_from": active,
            "key_id": self._key_id_for_path(verify_key_path),
        }
        state["active_epoch_id"] = new_epoch_id
        state["transition_counter"] = int(state.get("transition_counter", 0)) + 1
        state["compromise_response_mode"] = bool(compromise_response_mode)
        self._write_state(state)
        self._append_jsonl(
            "transitions.jsonl",
            {
                "event": "epoch_transition",
                "from_epoch": active,
                "to_epoch": new_epoch_id,
                "verify_key_path": verify_key_path,
                "signing_key_path": signing_key_path,
                "actor": actor,
                "reason": reason,
                "compromise_response_mode": bool(compromise_response_mode),
                "timestamp": now,
            },
        )
        self._append_jsonl(
            "runtime_mode.jsonl",
            {
                "event": "compromise_mode_changed",
                "compromise_response_mode": bool(compromise_response_mode),
                "actor": actor,
                "reason": reason,
                "timestamp": now,
            },
        )
        return state

    def revoke_epoch(self, *, epoch_id: str, actor: str, reason: str) -> dict[str, object]:
        state = self.load_state()
        epochs = state.setdefault("epochs", {})
        if not isinstance(epochs, dict):
            raise ValueError("invalid epoch state")
        epoch = epochs.get(epoch_id)
        if not isinstance(epoch, dict):
            raise ValueError(f"unknown epoch: {epoch_id}")
        now = self._utc_now()
        epoch["status"] = "revoked"
        epoch["revoked"] = True
        epoch["revoked_at"] = now
        revoked = set(str(item) for item in state.get("revoked_epochs", []) if isinstance(item, str))
        revoked.add(epoch_id)
        state["revoked_epochs"] = sorted(revoked)
        state["compromise_response_mode"] = True
        self._write_state(state)
        self._append_jsonl(
            "revocations.jsonl",
            {
                "event": "epoch_revocation",
                "epoch_id": epoch_id,
                "actor": actor,
                "reason": reason,
                "timestamp": now,
            },
        )
        return state

    def clear_compromise_mode(self, *, actor: str, reason: str) -> dict[str, object]:
        state = self.load_state()
        state["compromise_response_mode"] = False
        self._write_state(state)
        self._append_jsonl(
            "runtime_mode.jsonl",
            {
                "event": "compromise_mode_changed",
                "compromise_response_mode": False,
                "actor": actor,
                "reason": reason,
                "timestamp": self._utc_now(),
            },
        )
        return state


_MANAGER = PulseTrustEpochManager()


def get_manager() -> PulseTrustEpochManager:
    return _MANAGER


def reset_manager() -> None:
    _MANAGER.reset()
