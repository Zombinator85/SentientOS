from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List
import json
import time

from advisory_connector import AdvisoryRequest, AdvisoryResponse

from .gate import hash_dataclass


class MCPAuditLogger:
    """Immutable JSONL-backed audit logger for MCP advisory interactions."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("audit_log/mcp_advisory_server.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[Dict[str, Any]] = []

    def log(
        self,
        *,
        request: AdvisoryRequest,
        response: AdvisoryResponse | None,
        redactions: tuple[str, ...],
        decision: str,
        reason: str,
        tone_report: Dict[str, Any] | None,
    ) -> None:
        record = {
            "timestamp": time.time(),
            "request_hash": hash_dataclass(request),
            "response_hash": hash_dataclass(response) if response else None,
            "redactions": list(redactions),
            "decision": decision,
            "reason": reason,
            "tone": tone_report,
            "request": asdict(request),
        }
        self._records.append(json.loads(json.dumps(record)))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def records(self) -> List[Dict[str, Any]]:
        return [json.loads(json.dumps(record)) for record in self._records]
