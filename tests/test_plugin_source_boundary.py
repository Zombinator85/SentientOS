from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import plugin_framework as pf
from scripts.verify_plugin_source_boundary import verify


def test_explicit_builtin_initialization_is_idempotent() -> None:
    pf.PLUGINS.clear()
    pf.PLUGINS_INFO.clear()
    pf.initialize_plugins()
    first = pf.PLUGINS["wave_hand"]
    pf.initialize_plugins()
    assert pf.PLUGINS == {"wave_hand": first}
    assert pf.plugin_status() == {"wave_hand": True}


def test_internal_registration_survives_builtin_reload() -> None:
    class Internal(pf.BasePlugin):
        allowed_postures = ["normal"]
        requires_epoch = False
        capabilities = []

    plugin = Internal()
    pf.register_plugin("internal_test", plugin)
    pf.PLUGINS_INFO["internal_test"] = "internal"
    pf.reload_plugins()
    assert pf.PLUGINS["internal_test"] is plugin


def test_proposal_activation_has_zero_effect(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "proposal-marker"
    source = tmp_path / "offered.py"
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('owned')\n", encoding="utf-8")
    before = dict(pf.PLUGINS)
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("source read")))
    pf.propose_plugin("offered", str(source))
    assert pf.approve_proposal("offered") is False
    assert pf.list_proposals()["offered"]["status"] == "external_activation_unsupported"
    assert dict(pf.PLUGINS) == before
    assert not marker.exists()
    assert not (tmp_path / "offered.py.py").exists()


def test_configured_external_directory_has_zero_process_real_execution(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    marker = tmp_path / "marker"
    payloads = {
        "top_level.py": f"from pathlib import Path\nPath({str(marker)!r}).write_text('owned')\n",
        "malformed.py": "def broken(:\n",
        "register.py": "def register(callback): callback('external', object())\n",
        "declared.py": "class LooksValid:\n allowed_postures=['normal']\n requires_epoch=True\n capabilities=[]\n",
        "raises.py": "raise RuntimeError('imported')\n",
        "unrelated.py": "VALUE = 1\n",
    }
    for name, source in payloads.items():
        (hostile / name).write_text(source, encoding="utf-8")
    script = """
import json, plugin_framework as pf, plugins_cli, sys
pf.initialize_plugins(); pf.list_plugins(); pf.plugin_status(); pf.reload_plugins()
for command in ('list', 'status', 'reload'):
    sys.argv = ['plugins_cli.py', command]
    plugins_cli.main()
print('RESULT=' + json.dumps(sorted(pf.list_plugins())))
"""
    env = dict(os.environ, GP_PLUGINS_DIR=str(hostile), SENTIENTOS_HEADLESS="1")
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], env=env,
                            text=True, capture_output=True, check=True)
    assert "RESULT=[\"wave_hand\"]" in result.stdout
    assert not marker.exists()


def test_static_verifier_passes() -> None:
    assert verify()["status"] == "plugin_source_boundary_ready"
