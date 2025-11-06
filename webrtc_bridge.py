"""Minimal signalling state used to test WebRTC route plumbing."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class _Session:
    session_id: str
    offer: Dict[str, object]
    answer: Dict[str, object]
    created_at: float
    expires_at: float
    ice_candidates: List[Dict[str, object]] = field(default_factory=list)
    token: Optional[str] = None

    def serialise(self) -> Dict[str, object]:
        return {
            "session_id": self.session_id,
            "answer": dict(self.answer),
            "expires_at": self.expires_at,
            "ice_candidates": [dict(candidate) for candidate in self.ice_candidates],
        }


class WebRTCSessionManager:
    """Keeps track of transient WebRTC sessions for signalling tests."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
        ice_servers: Optional[List[Dict[str, object]]] = None,
    ) -> None:
        self._ttl = max(60, int(ttl_seconds))
        self._sessions: Dict[str, _Session] = {}
        self._ice_servers = list(ice_servers or [])

    def _prune(self) -> None:
        now = time.time()
        expired = [sid for sid, session in self._sessions.items() if session.expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)

    def create_session(self, offer: Dict[str, object], *, token: Optional[str] = None) -> Dict[str, object]:
        if "sdp" not in offer:
            raise ValueError("offer missing sdp")
        session_id = secrets.token_urlsafe(18)
        now = time.time()
        answer = {
            "type": "answer",
            "sdp": offer.get("sdp", ""),
            "iceServers": self._ice_servers,
        }
        session = _Session(
            session_id=session_id,
            offer=dict(offer),
            answer=answer,
            created_at=now,
            expires_at=now + self._ttl,
            token=token,
        )
        self._sessions[session_id] = session
        self._prune()
        payload = session.serialise()
        payload["ice_servers"] = self._ice_servers
        return payload

    def add_ice_candidate(self, session_id: str, candidate: Dict[str, object]) -> Dict[str, object]:
        self._prune()
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError("unknown session")
        session.ice_candidates.append(dict(candidate))
        return session.serialise()

    def get_session(self, session_id: str) -> Optional[Dict[str, object]]:
        self._prune()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.serialise()

    def list_sessions(self) -> List[Dict[str, object]]:
        self._prune()
        return [session.serialise() for session in self._sessions.values()]


__all__ = ["WebRTCSessionManager"]
