"""Pairing and trust management for SentientOS nodes.

This module provides a small service that handles secure pairing between
devices on the local network. The pairing flow exposes short lived pairing
codes and optional PIN confirmation. When a peer is confirmed a per-node JWT
token is issued and persisted in :mod:`node_registry` with a provisional trust
level. The first successful token validation promotes the node to *trusted*.

The implementation intentionally keeps dependencies light so it can operate in
resource constrained environments (e.g. thin clients or e-readers). Ed25519
keys are backed by the bundled :mod:`nacl.signing` shim which provides a
deterministic signing key suitable for computing public key fingerprints.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from nacl import signing

from node_registry import registry
from sentientos.storage import get_data_root

load_dotenv()

_PAIRING_DIR_NAME = "pairing"
_PRIVATE_KEY_FILE = "ed25519.key"
_PUBLIC_KEY_FILE = "ed25519.pub"
_DEFAULT_CODE_ROTATE_S = 60.0
_DEFAULT_CODE_TTL_S = int(os.getenv("PAIRING_CODE_TTL_S", "300"))
_SESSION_COOKIE_NAME = "sentientos_session"


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sha256(data: str) -> str:
    digest = hashlib.sha256()
    digest.update(data.encode("utf-8"))
    return digest.hexdigest()


def _random_code(length: int = 6) -> str:
    return "".join(str(os.urandom(1)[0] % 10) for _ in range(length))


def _random_pin(length: int = 4) -> str:
    return "".join(str((os.urandom(1)[0] % 10)) for _ in range(length))


def _default_pairing_secret() -> str:
    return os.getenv("PAIRING_TOKEN_SECRET") or os.getenv("RELAY_SECRET", "pairing-secret")


def _now() -> float:
    return time.time()


@dataclass
class _CodeState:
    value: str
    issued_at: float
    pin: str


class PairingService:
    """Manage node pairing, trust and token issuance."""

    def __init__(
        self,
        *,
        storage_dir: Optional[Path] = None,
        code_rotate_seconds: float = _DEFAULT_CODE_ROTATE_S,
        code_ttl_seconds: int = _DEFAULT_CODE_TTL_S,
        session_ttl_seconds: int = int(os.getenv("PAIRING_SESSION_TTL_S", str(24 * 3600))),
    ) -> None:
        self._storage_dir = Path(storage_dir) if storage_dir else get_data_root() / _PAIRING_DIR_NAME
        if os.getenv("PAIRING_RESET") == "1" and self._storage_dir.exists():
            for child in self._storage_dir.glob("*"):
                try:
                    child.unlink()
                except OSError:
                    pass
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._code_rotate = code_rotate_seconds
        self._code_ttl = code_ttl_seconds
        self._session_ttl = session_ttl_seconds
        self._require_pin = os.getenv("PAIRING_REQUIRE_PIN", "0") == "1"
        self._token_secret = _default_pairing_secret()
        self._token_algorithm = os.getenv("PAIRING_TOKEN_ALG", "HS256").upper()
        self._signing_key = self._load_or_create_key()
        self._verify_key = self._signing_key.verify_key
        self._public_fingerprint = hashlib.sha256(self._verify_key.encode()).hexdigest()
        self._code_state: Optional[_CodeState] = None
        self._sessions: Dict[str, tuple[str, float]] = {}

    @property
    def public_key_fingerprint(self) -> str:
        return self._public_fingerprint

    @property
    def session_cookie_name(self) -> str:
        return _SESSION_COOKIE_NAME

    def _load_or_create_key(self) -> signing.SigningKey:
        private_path = self._storage_dir / _PRIVATE_KEY_FILE
        if private_path.exists():
            try:
                raw = private_path.read_bytes()
                return signing.SigningKey(raw)
            except Exception:
                pass
        signing_key = signing.SigningKey.generate()
        private_path.write_bytes(signing_key.encode())
        public_path = self._storage_dir / _PUBLIC_KEY_FILE
        public_path.write_bytes(signing_key.verify_key.encode())
        return signing_key

    def _ensure_code(self) -> _CodeState:
        with self._lock:
            now = _now()
            if self._code_state is None:
                self._code_state = _CodeState(value=_random_code(), issued_at=now, pin=_random_pin())
            elif now - self._code_state.issued_at >= self._code_rotate:
                self._code_state = _CodeState(value=_random_code(), issued_at=now, pin=_random_pin())
            return self._code_state

    def start_pairing(self, host: Optional[str] = None) -> Dict[str, object]:
        state = self._ensure_code()
        remaining = max(0.0, state.issued_at + self._code_ttl - _now())
        host = host or socket.gethostname()
        qr_payload = f"sentientos://pair?host={host}&code={state.value}"
        qr_svg = (
            "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 200 60\">"
            f"<rect width='200' height='60' fill='#0b0d11'/>"
            f"<text x='10' y='35' fill='#f3f4f6' font-size='14'>{qr_payload}</text>"
            "</svg>"
        )
        payload: Dict[str, object] = {
            "pair_code": state.value,
            "qr_svg": qr_svg,
            "expires_in": remaining,
        }
        if self._require_pin:
            payload["pin"] = state.pin
        return payload

    def _build_jwt(self, payload: Dict[str, object]) -> str:
        if self._token_algorithm != "HS256":
            raise ValueError(f"Unsupported pairing token algorithm: {self._token_algorithm}")
        header = {"alg": self._token_algorithm, "typ": "JWT"}
        body = json.dumps(header, separators=(",", ":")).encode("utf-8")
        header_part = _base64url(body)
        payload_part = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        message = f"{header_part}.{payload_part}".encode("utf-8")
        signature = hmac.new(self._token_secret.encode("utf-8"), message, hashlib.sha256).digest()
        token = f"{header_part}.{payload_part}.{_base64url(signature)}"
        return token

    def _decode_jwt(self, token: str) -> Dict[str, object]:
        try:
            header_raw, payload_raw, signature_raw = token.split(".")
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("invalid token") from exc
        if self._token_algorithm != "HS256":
            raise ValueError("Unsupported token algorithm")
        message = f"{header_raw}.{payload_raw}".encode("utf-8")
        expected = hmac.new(self._token_secret.encode("utf-8"), message, hashlib.sha256).digest()
        if _base64url(expected) != signature_raw:
            raise ValueError("invalid signature")
        payload = json.loads(_base64url_decode(payload_raw).decode("utf-8"))
        return payload

    def _issue_token(self, node_id: str) -> str:
        ttl_hours = float(os.getenv("NODE_TOKEN_TTL_H", "720"))
        expires_at = int(_now() + ttl_hours * 3600)
        payload = {"sub": node_id, "exp": expires_at, "scope": "node"}
        return self._build_jwt(payload)

    def _store_session(self, node_id: str) -> str:
        token = uuid.uuid4().hex
        expires = _now() + self._session_ttl
        with self._lock:
            self._sessions[token] = (node_id, expires)
        return token

    def _validate_code(self, code: str, pin: Optional[str]) -> None:
        with self._lock:
            state = self._ensure_code()
            if not code or code != state.value:
                raise ValueError("invalid_pair_code")
            if _now() - state.issued_at > self._code_ttl:
                raise ValueError("pair_code_expired")
            if self._require_pin and (pin or "").strip() != state.pin:
                raise ValueError("pin_required")

    def confirm_pairing(self, payload: Dict[str, object]) -> Dict[str, object]:
        code = str(payload.get("pair_code") or payload.get("code") or "").strip()
        pin = payload.get("pin")
        pin_value = str(pin) if pin is not None else None
        node_id = str(payload.get("node_id") or payload.get("hostname") or "").strip()
        if not node_id:
            raise ValueError("node_id_required")
        ip = str(payload.get("ip") or payload.get("address") or "127.0.0.1" )
        api_port = int(payload.get("api_port") or payload.get("port") or 5000)
        roles = payload.get("roles") if isinstance(payload.get("roles"), (list, tuple)) else []
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
        pubkey_fingerprint = payload.get("public_key_fpr") or payload.get("pubkey_fingerprint")
        upstream_host = payload.get("upstream_host") if isinstance(payload.get("upstream_host"), str) else None
        self._validate_code(code, pin_value)
        token = self._issue_token(node_id)
        token_hash = _sha256(token)
        registry.register_or_update(
            node_id,
            ip,
            port=api_port,
            capabilities=capabilities,
            roles=[str(r) for r in roles],
            token_hash=token_hash,
            pubkey_fingerprint=str(pubkey_fingerprint) if pubkey_fingerprint else None,
            trust_level="provisional",
            upstream_host=upstream_host,
            last_seen=_now(),
        )
        registry.store_token(node_id, token_hash)
        session_token = self._store_session(node_id)
        with self._lock:
            # Invalidate current code after a successful pairing to force rotation.
            self._code_state = None
        return {
            "status": "paired",
            "node_id": node_id,
            "node_token": token,
            "session_token": session_token,
        }

    def verify_node_token(self, node_id: str, token: str) -> bool:
        try:
            payload = self._decode_jwt(token)
        except ValueError:
            return False
        if payload.get("sub") != node_id:
            return False
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and exp < _now():
            return False
        record = registry.get(node_id)
        if not record or not record.token_hash:
            return False
        if record.token_hash != _sha256(token):
            return False
        if record.trust_level != "trusted":
            registry.set_trust_level(node_id, "trusted")
        return True

    def validate_session(self, token: str) -> Optional[str]:
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            node_id, expires = session
            if expires < _now():
                self._sessions.pop(token, None)
                return None
            return node_id

    def cleanup_sessions(self) -> None:
        with self._lock:
            expired = [key for key, (_, exp) in self._sessions.items() if exp < _now()]
            for key in expired:
                self._sessions.pop(key, None)


pairing_service = PairingService()

__all__ = [
    "PairingService",
    "pairing_service",
]
