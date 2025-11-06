"""Base classes for Sentient Mesh council voice adapters."""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Dict, Mapping, MutableMapping, Optional

__all__ = [
    "MeshVoice",
    "VoiceExchange",
    "VoiceRateLimitError",
]


@dataclass(frozen=True)
class VoiceExchange:
    """Structured record of a council exchange."""

    voice: str
    role: str
    content: str
    signature: str
    advisory: bool
    timestamp: float
    metadata: Mapping[str, object]

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "voice": self.voice,
            "role": self.role,
            "content": self.content,
            "signature": self.signature,
            "advisory": self.advisory,
            "timestamp": round(self.timestamp, 6),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class VoiceRateLimitError(RuntimeError):
    """Raised when a voice would exceed its allotted call rate."""


class _WindowRateLimiter:
    def __init__(self, *, base_limit: int = 4, window_seconds: float = 60.0) -> None:
        self._base_limit = max(1, int(base_limit))
        self._window = max(1.0, float(window_seconds))
        self._events: Dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, quota: float, *, now: Optional[float] = None) -> bool:
        moment = float(now or time.time())
        quota = max(0.25, float(quota))
        limit = max(1, math.ceil(self._base_limit * quota))
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and moment - events[0] > self._window:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(moment)
        return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class MeshVoice(ABC):
    """Abstract adapter for a council voice."""

    def __init__(
        self,
        name: str,
        *,
        advisory: bool,
        env_prefix: str,
        base_limit: int = 4,
        requires_key: bool = False,
    ) -> None:
        self.name = name
        self.advisory = advisory
        self._env_prefix = env_prefix.upper()
        self._requires_key = requires_key
        self._api_key = os.getenv(f"{self._env_prefix}_API_KEY")
        self._limiter = _WindowRateLimiter(base_limit=base_limit)
        self._last_signature: Optional[str] = None

    # -- metadata ---------------------------------------------------------
    @property
    def available(self) -> bool:
        if not self._requires_key:
            return True
        return bool(self._api_key)

    @property
    def config(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "advisory": self.advisory,
            "requires_key": self._requires_key,
            "available": self.available,
        }
        if self._api_key:
            payload["token_fingerprint"] = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()[:8]
        return payload

    # -- canonical serialisation -----------------------------------------
    @staticmethod
    def canonical(data: Mapping[str, object]) -> str:
        return json.dumps(dict(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def signature(self, content: Mapping[str, object] | str) -> str:
        if isinstance(content, Mapping):
            payload = self.canonical(content)
        else:
            payload = str(content)
        digest = hashlib.sha256(f"{self.name}:{payload}".encode("utf-8")).hexdigest()
        self._last_signature = digest
        return digest

    # -- rate limiting ----------------------------------------------------
    def _check_budget(self, *, trust: float, now: Optional[float] = None) -> None:
        key = f"{self.name}:{self.__class__.__name__}"
        allowed = self._limiter.allow(key, quota=max(0.25, trust), now=now)
        if not allowed:
            raise VoiceRateLimitError(f"{self.name} rate limit exceeded")

    # -- deterministic completions ---------------------------------------
    def _persona(self) -> str:
        return self.name

    def _deterministic_text(self, *, mode: str, prompt: str, trust: float) -> str:
        scaffold = {
            "voice": self.name,
            "mode": mode,
            "persona": self._persona(),
            "prompt": prompt,
            "trust": round(float(trust), 3),
        }
        digest = hashlib.sha256(self.canonical(scaffold).encode("utf-8")).hexdigest()
        token = digest[:12]
        return f"[{self.name}:{mode}] {self._persona()} reflection {token}"

    def ask(self, prompt: str, *, trust: float = 1.0) -> VoiceExchange:
        self._check_budget(trust=trust)
        reply = self._deterministic_text(mode="ask", prompt=prompt, trust=trust)
        metadata = {"prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]}
        signature = self.signature({"prompt": prompt, "reply": reply, "mode": "ask"})
        return VoiceExchange(
            voice=self.name,
            role="ask",
            content=reply,
            signature=signature,
            advisory=self.advisory,
            timestamp=time.time(),
            metadata=metadata,
        )

    def critique(self, statement: str, *, trust: float = 1.0) -> VoiceExchange:
        self._check_budget(trust=trust)
        reply = self._deterministic_text(mode="critique", prompt=statement, trust=trust)
        metadata = {"statement_hash": hashlib.sha256(statement.encode("utf-8")).hexdigest()[:8]}
        signature = self.signature({"statement": statement, "reply": reply, "mode": "critique"})
        return VoiceExchange(
            voice=self.name,
            role="critique",
            content=reply,
            signature=signature,
            advisory=self.advisory,
            timestamp=time.time(),
            metadata=metadata,
        )

    def vote(self, transcript: Mapping[str, object], *, trust: float = 1.0) -> VoiceExchange:
        self._check_budget(trust=trust)
        serial = self.canonical(transcript)
        digest = hashlib.sha256(serial.encode("utf-8")).digest()
        pivot = digest[0]
        decision = "approve" if pivot % 3 == 0 else ("revise" if pivot % 3 == 1 else "defer")
        confidence = round(0.45 + (pivot / 255.0) * 0.5, 3)
        payload: MutableMapping[str, object] = {
            "decision": decision,
            "confidence": confidence,
            "advisory": self.advisory,
            "transcript_hash": hashlib.sha256(serial.encode("utf-8")).hexdigest()[:10],
        }
        signature = self.signature({"vote": payload, "voice": self.name})
        payload["signature"] = signature
        return VoiceExchange(
            voice=self.name,
            role="vote",
            content=self.canonical(payload),
            signature=signature,
            advisory=self.advisory,
            timestamp=time.time(),
            metadata=payload,
        )

    @abstractmethod
    def identity(self) -> str:
        """Return the stable identity for the adapter."""


class _CloudVoiceMixin:
    def identity(self) -> str:  # pragma: no cover - simple mapping
        return f"{self.__class__.__name__}:{self.name}"

    def _persona(self) -> str:
        provider = self.__class__.__name__.replace("Voice", "")
        return f"{provider} councilor"
