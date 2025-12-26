"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
# noqa: D100 - all tests share this setup module
from __future__ import annotations
import builtins
import importlib.util
import json
import sys
from pathlib import Path

import types

# Ensure the repository root is on sys.path before importing project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub privilege checks before importing modules that may call them on import
builtins.require_admin_banner = lambda *a, **k: None  # type: ignore[attr-defined]
builtins.require_covenant_alignment = lambda *a, **k: None  # type: ignore[attr-defined]

yaml_stub = types.ModuleType("yaml")
def _safe_yaml(text, *_, **__):
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


yaml_stub.safe_load = _safe_yaml
sys.modules.setdefault("yaml", yaml_stub)

pdfrw_stub = types.ModuleType("pdfrw")
pdfrw_stub.PdfDict = dict
pdfrw_stub.PdfReader = lambda *_a, **_k: None
pdfrw_stub.PdfWriter = type(
    "PdfWriterStub",
    (),
    {
        "addpage": lambda *_a, **_k: None,
        "write": lambda *_a, **_k: None,
    },
)
sys.modules.setdefault("pdfrw", pdfrw_stub)

from sentientos.privilege import require_admin_banner, require_covenant_alignment

require_admin_banner()
require_covenant_alignment()
# The admin banner checks can exit the process during module import if not
# stubbed ahead of time. Stub them here so test discovery doesn't trip the
# privilege checks.

import pytest

from tests.legacy_policy import LEGACY_SKIP_REASON, is_legacy_candidate, legacy_marker_enabled

from sentientos.codex_startup_guard import codex_startup_phase

from privilege_lint._env import HAS_NODE, HAS_GO, HAS_DMYPY, NODE, GO, DMYPY
from nacl.signing import SigningKey


sys.modules['requests'] = types.ModuleType('requests')
sys.modules['requests'].get = lambda *a, **k: None
sys.modules['requests'].post = lambda *a, **k: None
sys.modules['requests'].request = lambda *a, **k: None

for name in ['pyesprima', 'sarif_om']:
    if importlib.util.find_spec(name) is None:
        sys.modules[name] = types.ModuleType(name)


def pytest_configure(config):
    config.addinivalue_line('markers', 'requires_node: skip if node missing')
    config.addinivalue_line('markers', 'requires_go: skip if go missing')
    config.addinivalue_line('markers', 'requires_dmypy: skip if dmypy missing')
    config.addinivalue_line('markers', 'network: tests that mock HTTP calls')
    config.addinivalue_line('markers', 'legacy: quarantined tests run with -m legacy')


def pytest_addoption(parser):
    parser.addoption(
        '--run-network',
        action='store_true',
        default=False,
        help='run tests marked as network'
    )


@pytest.fixture(scope="session")
def codex_startup():
    with codex_startup_phase():
        yield


@pytest.fixture(autouse=True)
def configure_pulse_environment(tmp_path, monkeypatch):
    history_dir = tmp_path / "pulse_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    key_dir = tmp_path / "pulse_keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    monitoring_dir = tmp_path / "glow" / "monitoring"
    monitoring_dir.mkdir(parents=True, exist_ok=True)

    signing_key = SigningKey.generate()
    private_key = key_dir / "ed25519_private.key"
    public_key = key_dir / "ed25519_public.key"
    private_key.write_bytes(signing_key.encode())
    public_key.write_bytes(signing_key.verify_key.encode())

    monkeypatch.setenv("PULSE_HISTORY_ROOT", str(history_dir))
    monkeypatch.setenv("PULSE_SIGNING_KEY", str(private_key))
    monkeypatch.setenv("PULSE_VERIFY_KEY", str(public_key))
    monkeypatch.delenv("MONITORING_METRICS_PATH", raising=False)

    from sentientos import pulse_query as pulse_query_module

    monkeypatch.setattr(pulse_query_module, "_PULSE_HISTORY_ROOT", history_dir)
    monkeypatch.setattr(pulse_query_module, "_METRICS_PATH", monitoring_dir / "metrics.jsonl")
    monkeypatch.setattr(pulse_query_module, "_VERIFY_KEY", None)
    yield


def pytest_collection_modifyitems(config, items):
    allowed_modules = {
        "tests.test_network_daemon",
        "tests.test_pulse_persistence",
        "tests.test_pulse_priority",
        "tests.test_pulse_federation",
        "tests.test_criteria_dsl",
        "tests.test_daemon_manager",
        "tests.test_federated_restart",
        "tests.test_pulse_query",
        "tests.test_codex_veil",
        "tests.test_codex_iterations",
        "tests.test_codex_rewrites",
        "tests.test_codex_anomalies",
        "tests.test_codex_intent",
        "tests.test_codex_embodiment",
        "tests.test_codex_integration",
        "tests.test_manifest_reconciliation",
        "tests.test_verifier_consensus_resume",
        "tests.test_verifier_consensus_backoff",
        "tests.test_verifier_consensus_console_actions",
        "tests.test_expand_mode",
        "tests.test_architect_integration",
        "tests.test_architect_priorities",
        "tests.test_architect_federated_priorities",
        "tests.test_architect_steering",
        "tests.test_architect_conflict_resolution",
        "tests.test_architect_cycles",
        "tests.test_architect_trajectory",
        "tests.test_codex_plans",
        "tests.test_codex_strategy",
        "tests.test_codex_strategies",
        "tests.test_codex_orchestration",
        "tests.test_codex_meta_strategies",
        "tests.test_codex_governance",
        "tests.test_codex_narratives",
        "tests.test_codex_healer",
        "tests.test_change_narrator",
        "tests.test_boot_chronicler",
        "tests.test_codex_specs",
        "tests.test_codex_scaffolds",
        "tests.test_sentientscript_interpreter",
        "tests.test_codex_implementations",
        "tests.test_codex_refinements",
        "tests.test_codex_testcycles",
        "tests.test_codex_coverage",
        "tests.test_codex_amendments",
        "tests.test_codex_sandbox",
        "tests.test_autogenesis_loop",
        "tests.test_genesis_forge",
        "tests.test_local_model",
        "tests.test_oracle_cycle",
        "tests.test_codex_gap_seeker",
        "tests.test_external_gap_seeker",
        "tests.test_oracle_relay",
        "tests.test_research_timer",
        "tests.test_commit_watcher_ci",
        "tests.test_dashboard_event_stream",
        "tests.test_dashboard_api",
        "tests.test_proof_validity",
        "tests.test_experiment_adapters",
        "tests.test_hungry_eyes",
        "tests.test_motion_detector",
        "tests.test_mic_monitor",
        "tests.test_keys_roundtrip",
        "tests.test_rotation",
        "tests.test_incognito",
        "tests.test_export_import",
        "tests.test_camera_daemon",
        "tests.test_reporter",
        "tests.test_talkback_actuator",
        "tests.test_redaction",
        "tests.test_secrets_scan",
        "tests.test_embeddings_migration",
        "tests.test_perception_reasoner",
        "tests.test_autonomy_readiness",
        "tests.test_autonomy_supervisor",
        "tests.test_pairing_flow",
        "tests.test_rr_routing",
        "tests.test_thin_proxy",
        "tests.test_ui_served",
        "tests.test_pwa_manifest",
        "tests.test_admin_console_auth",
        "tests.test_webrtc_signaling",
        "tests.test_stt_tts_roundtrip",
        "tests.test_watchdog_recover",
        "tests.e2e.test_alert_rules",
        "tests.e2e.test_services",
        "tests.e2e.test_perf_targets",
        "tests.e2e.test_soak",
        "tests.test_sentient_verifier",
        "tests.test_sentient_verifier_sse",
        "tests.test_sentient_verifier_replay",
        "tests.test_experiment_consensus",
        "tests.test_verifier_consensus_core",
        "tests.test_verifier_consensus_mesh",
        "tests.test_verifier_consensus_console", 
        "tests.test_sentient_mesh_scheduler", 
        "tests.test_council_adapters", 
        "tests.test_sentient_autonomy", 
        "tests.test_restart_determinism", 
        "tests.test_console_mesh_ui", 
        "tests.test_experiment_chain",
        "tests.test_demo_gallery",
        "tests.test_console_dashboard",
        "tests.test_console_dashboard_federation_replay",
        "tests.test_runtime_shell",
        "tests.test_runtime_bootstrap",
        "tests.test_persona_loop",
        "tests.test_federation_passive_replay",
        "tests.test_federation_delta",
        "tests.test_federation_poller_replay_integration",
        "tests.test_world_events",
        "tests.test_world_sources",
        "tests.test_voice_asr",
        "tests.test_voice_tts",
        "tests.test_consciousness_scaffolding",
        "tests.consciousness.test_sentience_kernel",
        "tests.integrity.test_covenant_autoalign",
        "tests.test_glossary_lint",
    }
    legacy_enabled = legacy_marker_enabled(config.option.markexpr)
    for item in items:
        module_name = item.module.__name__
        path_str = str(getattr(item, "fspath", ""))
        if is_legacy_candidate(
            module_name=module_name,
            path_str=path_str,
            test_name=item.name,
            keywords=item.keywords,
            allowed_modules=allowed_modules,
        ):
            item.add_marker(pytest.mark.legacy)
            if not legacy_enabled:
                item.add_marker(pytest.mark.skip(reason=LEGACY_SKIP_REASON))
        if 'requires_node' in item.keywords and not HAS_NODE:
            item.add_marker(pytest.mark.skip(reason=f'node missing: {NODE.info}'))
        if 'requires_go' in item.keywords and not HAS_GO:
            item.add_marker(pytest.mark.skip(reason=f'go missing: {GO.info}'))
        if 'requires_dmypy' in item.keywords and not HAS_DMYPY:
            item.add_marker(pytest.mark.skip(reason=f'dmypy missing: {DMYPY.info}'))
        if 'network' in item.keywords and not config.getoption('--run-network'):
            item.add_marker(pytest.mark.skip(reason='network test skipped: add --run-network to run'))
