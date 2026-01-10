from __future__ import annotations

from pathlib import Path
import types

import pytest

from sentientos.consciousness.attention_arbitrator import AttentionArbitratorDaemon
from sentientos.consciousness.sentience_kernel import SentienceKernel
from sentientos.consciousness.simulation_engine import SimulationEngine
from sentientos.boot_ceremony import BootAnnouncer, CeremonialScript, EventEmitter
from sentientos.cathedral.amendment import Amendment
from sentientos.cathedral.apply import AmendmentApplicator
from sentientos.integrity import covenant_autoalign
from sentientos.privilege import require_covenant_alignment
from tests import conftest as tests_conftest
from tests.federation_skip_policy import FEDERATION_SKIP_INTENTS
from tests.integrity import test_repo_invariant_tripwire

pytestmark = pytest.mark.no_legacy_skip


def test_autoalign_functions_cover_all_stages():
    checks = {
        "boot": covenant_autoalign.autoalign_on_boot,
        "cycle": covenant_autoalign.autoalign_before_cycle,
        "amendment": covenant_autoalign.autoalign_after_amendment,
    }
    for stage, fn in checks.items():
        result = fn()
        assert result["stage"] == stage
        assert result["guardrails_active"] is True
        assert result["daemons_constrained"] is True


def test_boot_sequence_triggers_autoalign(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(covenant_autoalign, "autoalign_on_boot", lambda: calls.append("boot"))
    script = CeremonialScript(BootAnnouncer(EventEmitter()))
    monkeypatch.setattr(script, "_mount_vows", lambda: None)
    monkeypatch.setattr(script, "_bind_integrity", lambda: None)
    monkeypatch.setattr(script, "_wake_healer", lambda: None)
    monkeypatch.setattr(script, "_prime_forge", lambda: None)

    script.perform()

    assert calls == ["boot"]


def test_consciousness_cycle_invokes_autoalign(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(covenant_autoalign, "autoalign_before_cycle", lambda: calls.append("cycle"))

    monkeypatch.setattr(
        "sentientos.consciousness.sentience_kernel.load_self_state",
        lambda path=None: {"novelty_score": 0.0, "last_focus": None},
    )
    monkeypatch.setattr(
        "sentientos.consciousness.sentience_kernel.update_self_state", lambda payload, path=None: payload
    )
    monkeypatch.setattr("sentientos.consciousness.sentience_kernel.pulse_bus.publish", lambda payload: payload)

    kernel = SentienceKernel(self_path=str(tmp_path / "self.json"))
    kernel.run_cycle()

    monkeypatch.setattr(
        "sentientos.consciousness.simulation_engine.load_self_state", lambda path=None: {"identity": "system"}
    )
    monkeypatch.setattr("sentientos.consciousness.simulation_engine.apply_pulse_defaults", lambda payload: payload)

    class _Result:
        summary = "ok"
        transcript = []
        confidence = 1.0

    monkeypatch.setattr(
        "sentientos.consciousness.simulation_engine.SimulationEngine.run", lambda self, **__: _Result()
    )
    monkeypatch.setattr(
        "sentientos.consciousness.simulation_engine.SimulationEngine._write_private_log",
        lambda *a, **k: None,
    )

    engine = SimulationEngine(self_path=Path(tmp_path / "sim.json"))
    engine.run_cycle()

    monkeypatch.setattr("sentientos.consciousness.attention_arbitrator.load_self_state", lambda: {})
    AttentionArbitratorDaemon().run_cycle()

    assert calls == ["cycle", "cycle", "cycle"]


def test_amendment_pipeline_autoalign(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(covenant_autoalign, "autoalign_after_amendment", lambda: calls.append("amend"))

    applicator = AmendmentApplicator(runtime_config={})
    amendment = Amendment(
        id="demo",
        created_at="2024-01-01T00:00:00Z",
        proposer="system",
        summary="refresh",
        changes={"config": {"runtime": {"root": str(tmp_path)}}},
    )

    result = applicator.apply(amendment)

    assert calls.count("amend") >= 2
    assert result.status in {"applied", "noop", "partial", "error"}


def test_alignment_alias_replaces_blessing():
    # Legacy entry points now delegate to covenant autoalignment.
    assert require_covenant_alignment() is None


def test_repo_invariant_tripwire_runs_in_default_suite():
    test_repo_invariant_tripwire.test_codex_public_surface_contract_tripwire()
    test_repo_invariant_tripwire.test_federation_public_surface_contract()
    test_repo_invariant_tripwire.test_executor_exports_no_federation_symbols()
    test_repo_invariant_tripwire.test_top_level_module_tripwires()
    test_repo_invariant_tripwire.test_minimal_public_symbol_tripwires()
    test_repo_invariant_tripwire.test_forbidden_imports_executor_to_federation()
    test_repo_invariant_tripwire.test_forbidden_imports_codex_startup_to_federation()
    test_repo_invariant_tripwire.test_forbidden_imports_federation_to_executor()


def test_default_suite_policy_keeps_federation_quarantined(monkeypatch):
    monkeypatch.delenv("SENTIENTOS_FEDERATION_ENABLED", raising=False)

    class DummyConfig:
        def __init__(self):
            self.option = types.SimpleNamespace(markexpr=None)

        def getoption(self, _name):
            return False

    class DummyItem:
        def __init__(self, module_name, path_str):
            self.module = types.SimpleNamespace(__name__=module_name)
            self.fspath = Path(path_str)
            self.name = "test_dummy"
            self.keywords = {}
            self.markers = []

        def add_marker(self, marker):
            self.markers.append(marker)

    config = DummyConfig()
    tripwire_item = DummyItem(
        "tests.integrity.test_repo_invariant_tripwire",
        "tests/integrity/test_repo_invariant_tripwire.py",
    )
    tripwire_item.keywords["always_on_integrity"] = True
    federation_module = next(iter(FEDERATION_SKIP_INTENTS))
    federation_item = DummyItem(federation_module, "tests/test_federation_transport.py")

    tests_conftest.pytest_collection_modifyitems(config, [tripwire_item, federation_item])

    tripwire_marker_names = {marker.name for marker in tripwire_item.markers}
    federation_marker_names = {marker.name for marker in federation_item.markers}

    assert "skip" not in tripwire_marker_names
    assert "skip" in federation_marker_names
    assert "federation_skip" in federation_marker_names
