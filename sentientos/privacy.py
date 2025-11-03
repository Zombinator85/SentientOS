"""Runtime privacy helpers for log redaction and PII hashing."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .config import PrivacyConfig, PrivacyRedactionConfig
from .storage import ensure_mounts, get_data_root

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-_.=:+/]+", re.IGNORECASE)
_HEX_LONG_RE = re.compile(r"\b[0-9a-fA-F]{64,}\b")
_BASE64_LONG_RE = re.compile(r"\b[A-Za-z0-9+/]{64,}={0,2}\b")


def _compile_patterns(config: PrivacyRedactionConfig) -> list[re.Pattern[str]]:
    patterns = [_EMAIL_RE, _BEARER_RE, _HEX_LONG_RE, _BASE64_LONG_RE]
    for raw in config.additional_patterns:
        try:
            patterns.append(re.compile(raw))
        except re.error:
            continue
    return patterns


@dataclass(frozen=True)
class RedactionResult:
    text: str
    redacted_tokens: Sequence[str]


class LogRedactor:
    """Apply regex-based masking to sensitive strings."""

    def __init__(self, config: PrivacyRedactionConfig) -> None:
        self._config = config
        self._patterns = _compile_patterns(config)
        self._whitelist = [re.compile(expr) for expr in config.whitelist]

    def _is_whitelisted(self, token: str) -> bool:
        return any(pattern.search(token) for pattern in self._whitelist)

    def redact(self, text: str) -> RedactionResult:
        if not self._config.enable:
            return RedactionResult(text=text, redacted_tokens=[])
        redacted_tokens: list[str] = []
        redacted = text
        for pattern in self._patterns:
            matches = list(pattern.finditer(redacted))
            for match in matches:
                token = match.group(0)
                if not token or self._is_whitelisted(token):
                    continue
                redacted_tokens.append(token)
                redacted = redacted.replace(token, "[REDACTED]")
        return RedactionResult(text=redacted, redacted_tokens=tuple(redacted_tokens))


class PrivacyManager:
    """Coordinate runtime privacy features (redaction + hashing)."""

    def __init__(self, config: PrivacyConfig) -> None:
        self._config = config
        self._redactor = LogRedactor(config.redactions)
        self._hash_enabled = bool(config.hash_pii)
        ensure_mounts()
        self._vault_path = get_data_root() / "vow" / "keys" / "pii_vault.jsonl"
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._salt_file = (
            Path(config.hash_salt_file).expanduser()
            if config.hash_salt_file is not None
            else self._vault_path.parent / "salt.key"
        )
        self._lock = threading.RLock()
        self._salt = self._load_or_create_salt()

    @property
    def redactor(self) -> LogRedactor:
        return self._redactor

    def _load_or_create_salt(self) -> bytes:
        if self._salt_file.exists():
            data = self._salt_file.read_bytes()
            if data:
                return data
        value = secrets.token_bytes(32)
        self._salt_file.write_bytes(value)
        return value

    def redact_log(self, message: str) -> RedactionResult:
        return self._redactor.redact(message)

    def _hash_token(self, token: str) -> str:
        digest = hashlib.sha256(self._salt + token.encode("utf-8")).hexdigest()
        return f"pii::{digest[:16]}"

    def _write_vault_entry(self, token: str, replacement: str) -> None:
        payload = {"token": token, "replacement": replacement}
        with self._lock:
            with self._vault_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")

    def hash_text(self, text: str) -> str:
        if not self._hash_enabled:
            return text
        tokens = []
        for pattern in _compile_patterns(self._config.redactions):
            tokens.extend(match.group(0) for match in pattern.finditer(text))
        unique_tokens = {token for token in tokens if token}
        hashed = text
        for token in sorted(unique_tokens, key=len, reverse=True):
            replacement = self._hash_token(token)
            hashed = hashed.replace(token, replacement)
            self._write_vault_entry(token, replacement)
        return hashed

    def hash_capsule(self, capsule: Mapping[str, object]) -> dict[str, object]:
        if not self._hash_enabled:
            return dict(capsule)
        mutated = dict(capsule)
        text = str(mutated.get("text", ""))
        mutated["text"] = self.hash_text(text)
        return mutated


__all__ = ["LogRedactor", "PrivacyManager", "RedactionResult"]

