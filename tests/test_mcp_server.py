from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from advisory_connector import ADVISORY_PHASE
from fastapi.testclient import TestClient

from sentientos.mcp.audit import MCPAuditLogger
from sentientos.mcp.server import create_app


class StubProbe:
    def __init__(self, phase: str) -> None:
        self.phase = phase

    def current_phase(self) -> str:  # pragma: no cover - trivial
        return self.phase


def _payload(**overrides: Any) -> Dict[str, Any]:
    base = {
        "goal": "map out a safe plan",
        "context_slice": ["module_a.py", "secrets.txt"],
        "constraints": {"must": ["log only"], "must_not": ["mutate"]},
        "forbidden_domains": ["payments"],
        "desired_artifacts": ["plan", "tests"],
        "phase": ADVISORY_PHASE,
        "redaction_profile": ["secret"],
    }
    base.update(overrides)
    return base


def test_handshake_reports_tools_and_phase(tmp_path: Path) -> None:
    probe = StubProbe(ADVISORY_PHASE)
    app = create_app(audit_logger=MCPAuditLogger(tmp_path / "audit.jsonl"), phase_probe=probe)
    client = TestClient(app)

    response = client.get("/mcp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["server"] == "sentientos-mcp-advisory"
    assert payload["phase"] == ADVISORY_PHASE
    assert payload["endpoints"]["advisory"] == "/mcp/advisory"
    assert payload["tools"]


def test_phase_enforcement_blocks_requests(tmp_path: Path) -> None:
    probe = StubProbe("OPERATIONS")
    app = create_app(audit_logger=MCPAuditLogger(tmp_path / "audit.jsonl"), phase_probe=probe)
    client = TestClient(app)

    response = client.post("/mcp/advisory", json=_payload())

    assert response.status_code == 403
    assert "ADVISORY_WINDOW" in response.json()["detail"]


def test_schema_validation_and_authority_language_rejection(tmp_path: Path) -> None:
    probe = StubProbe(ADVISORY_PHASE)
    app = create_app(audit_logger=MCPAuditLogger(tmp_path / "audit.jsonl"), phase_probe=probe)
    client = TestClient(app)

    bad_payload = _payload(goal="You must obey")
    response = client.post("/mcp/advisory", json=bad_payload)

    assert response.status_code == 400
    assert "prescriptive" in response.json()["detail"]

    missing_goal = _payload(goal="")
    response = client.post("/mcp/advisory", json=missing_goal)
    assert response.status_code in (400, 422)


def test_audit_log_records_hashes_and_redactions(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit_logger = MCPAuditLogger(audit_path)
    probe = StubProbe(ADVISORY_PHASE)
    app = create_app(audit_logger=audit_logger, phase_probe=probe)
    client = TestClient(app)

    response = client.post("/mcp/advisory", json=_payload())
    assert response.status_code == 200

    records = audit_logger.records()
    assert len(records) == 1
    entry = records[0]
    assert entry["request_hash"]
    assert entry["response_hash"]
    assert "secret" in entry["redactions"]
    assert entry["decision"] == "accepted"

    on_disk = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(on_disk) == 1


def test_deterministic_responses(tmp_path: Path) -> None:
    probe = StubProbe(ADVISORY_PHASE)
    app = create_app(audit_logger=MCPAuditLogger(tmp_path / "audit.jsonl"), phase_probe=probe)
    client = TestClient(app)

    first = client.post("/mcp/advisory", json=_payload()).json()
    second = client.post("/mcp/advisory", json=_payload()).json()

    assert first == second
    assert first["executable"] is False
