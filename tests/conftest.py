"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
# noqa: D100 - all tests share this setup module
from __future__ import annotations
import json
import sys
from pathlib import Path
import builtins

# Ensure the repository root is on sys.path before importing project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub privilege checks before importing modules that may call them on import
builtins.require_admin_banner = lambda *a, **k: None  # type: ignore[attr-defined]
builtins.require_lumos_approval = lambda *a, **k: None  # type: ignore[attr-defined]

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
# The admin banner checks can exit the process during module import if not
# stubbed ahead of time. Stub them here so test discovery doesn't trip the
# privilege checks.

import importlib
import pytest
import types

try:
    importlib.import_module('yaml')
except Exception:
    yaml_stub = types.ModuleType('yaml')

    def _safe_load(text: str | None, *_, **__) -> object:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    yaml_stub.safe_load = _safe_load  # type: ignore[attr-defined]
    sys.modules['yaml'] = yaml_stub

from privilege_lint._env import HAS_NODE, HAS_GO, HAS_DMYPY, NODE, GO, DMYPY
from nacl.signing import SigningKey


sys.modules['requests'] = types.ModuleType('requests')
sys.modules['requests'].get = lambda *a, **k: None
sys.modules['requests'].post = lambda *a, **k: None
sys.modules['requests'].request = lambda *a, **k: None

for name in ['pyesprima', 'sarif_om']:
    try:
        importlib.import_module(name)
    except Exception:
        sys.modules[name] = types.ModuleType(name)


def pytest_configure(config):
    config.addinivalue_line('markers', 'requires_node: skip if node missing')
    config.addinivalue_line('markers', 'requires_go: skip if go missing')
    config.addinivalue_line('markers', 'requires_dmypy: skip if dmypy missing')
    config.addinivalue_line('markers', 'network: tests that mock HTTP calls')


def pytest_addoption(parser):
    parser.addoption(
        '--run-network',
        action='store_true',
        default=False,
        help='run tests marked as network'
    )


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
    }
    for item in items:
        if (
            item.name != "test_placeholder"
            and not item.name.startswith("test_emotion_pump")
            and item.module.__name__ not in allowed_modules
        ):
            item.add_marker(pytest.mark.skip(reason="legacy test disabled"))
        if 'requires_node' in item.keywords and not HAS_NODE:
            item.add_marker(pytest.mark.skip(reason=f'node missing: {NODE.info}'))
        if 'requires_go' in item.keywords and not HAS_GO:
            item.add_marker(pytest.mark.skip(reason=f'go missing: {GO.info}'))
        if 'requires_dmypy' in item.keywords and not HAS_DMYPY:
            item.add_marker(pytest.mark.skip(reason=f'dmypy missing: {DMYPY.info}'))
        if 'network' in item.keywords and not config.getoption('--run-network'):
            item.add_marker(pytest.mark.skip(reason='network test skipped: add --run-network to run'))
