import importlib

import pytest

import pairing_service as pairing_module
from node_registry import NodeRegistry


@pytest.mark.usefixtures("clean_pairing")
class TestPairingFlow:
    def test_start_confirm_promotes_trust(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PAIRING_REQUIRE_PIN", "0")
        local_registry = NodeRegistry(tmp_path / "nodes.json")
        monkeypatch.setattr(pairing_module, "registry", local_registry, raising=False)
        service = pairing_module.PairingService(storage_dir=tmp_path / "pairing")

        start_payload = service.start_pairing(host="core-host")
        assert "pair_code" in start_payload
        assert len(start_payload["pair_code"]) == 6

        confirm_payload = {
            "node_id": "thin-1",
            "pair_code": start_payload["pair_code"],
            "ip": "10.0.0.2",
            "api_port": 5010,
            "roles": ["thin"],
            "capabilities": {"llm": False, "stt": True},
        }
        confirmation = service.confirm_pairing(confirm_payload)
        assert confirmation["status"] == "paired"
        assert confirmation["node_id"] == "thin-1"
        assert "node_token" in confirmation
        assert "session_token" in confirmation

        # Token verification should promote the node to trusted.
        assert service.verify_node_token("thin-1", confirmation["node_token"]) is True
        record = local_registry.get("thin-1")
        assert record is not None
        assert record.trust_level == "trusted"
        assert record.token_hash
        # Session token resolves to the paired node.
        assert service.validate_session(confirmation["session_token"]) == "thin-1"


@pytest.fixture
def clean_pairing(monkeypatch):
    # Ensure each test reloads the module with default environment.
    monkeypatch.delenv("PAIRING_REQUIRE_PIN", raising=False)
    importlib.reload(pairing_module)
    yield
    importlib.reload(pairing_module)
