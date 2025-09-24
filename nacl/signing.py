from __future__ import annotations

import hashlib
import os

from .exceptions import BadSignatureError


def _derive_signature(message: bytes, key: bytes) -> bytes:
    digest = hashlib.sha256()
    digest.update(message)
    digest.update(key)
    return digest.digest()


class SignedMessage:
    """Lightweight stand-in for :class:`nacl.signing.SignedMessage`."""

    def __init__(self, message: bytes, signature: bytes) -> None:
        self.message = message
        self.signature = signature

    def __bytes__(self) -> bytes:  # pragma: no cover - compatibility helper
        return self.message + self.signature


class VerifyKey:
    def __init__(self, key: bytes) -> None:
        self._key = bytes(key)

    def verify(self, message: bytes, signature: bytes) -> bytes:
        if not isinstance(signature, (bytes, bytearray)):
            raise BadSignatureError("signature must be bytes")
        expected = _derive_signature(bytes(message), self._key)
        if bytes(signature) != expected:
            raise BadSignatureError("invalid signature")
        return bytes(message)

    def encode(self) -> bytes:
        return self._key


class SigningKey:
    def __init__(self, seed: bytes | bytearray | None = None) -> None:
        if seed is None:
            seed = os.urandom(32)
        self._seed = bytes(seed)

    @classmethod
    def generate(cls) -> "SigningKey":
        return cls(os.urandom(32))

    def sign(self, message: bytes | bytearray) -> SignedMessage:
        payload = bytes(message)
        signature = _derive_signature(payload, self._seed)
        return SignedMessage(payload, signature)

    def encode(self) -> bytes:
        return self._seed

    @property
    def verify_key(self) -> VerifyKey:
        return VerifyKey(self._seed)
