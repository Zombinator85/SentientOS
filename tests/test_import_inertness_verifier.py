from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "verify_import_inertness.py"


def _run(
    tmp_path: Path,
    module_root: Path = ROOT,
    modules: tuple[str, ...] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    output = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable, str(VERIFIER), "--module-root", str(module_root), "--output", str(output),
            *(arg for module in (modules or ()) for arg in ("--module", module)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, json.loads(output.read_text(encoding="utf-8"))


def _api_fixture(tmp_path: Path, initializer: str, actuator: str = "") -> Path:
    root = tmp_path / "modules"
    package = root / "api"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(initializer, encoding="utf-8")
    (package / "actuator.py").write_text(actuator, encoding="utf-8")
    return root


def test_import_verifier_reports_all_required_modules(tmp_path):
    completed, result = _run(tmp_path)
    assert completed.returncode == 0
    assert result["status"] == "import_inertness_ready"
    assert [item["module"] for item in result["module_results"]] == [
        "sentientos", "scripts.lock", "api", "api.actuator",
        "integration_memory", "codex", "codex.integrity_daemon", "codex.strategy",
        "memory_manager", "curiosity_goal_helper", "curiosity_executor",
        "emotion_memory", "emotion_utils", "semantic_embeddings", "memory_governor", "node_registry",
        "capability_ledger", "cathedral_const", "sentient_autonomy",
        "sentientos.autonomy.curiosity_loop", "sentientos.autonomy.runtime",
        "sentientos.hosted_validation_evidence",
    ]


def test_startup_import_probes_ignore_ambient_markers_and_require_fresh_inertness(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_STARTUP_ROOT_PID", "ambient-root")
    monkeypatch.setenv("CODEX_STARTUP_FINALIZED", "ambient-finalized")
    completed, result = _run(
        tmp_path,
        modules=("sentientos.codex_startup_guard", "codex.integrity_daemon"),
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert result["status"] == "import_inertness_ready"
    assert all(item["environment_changes"] == {} for item in result["module_results"])


def test_import_verifier_detects_startup_marker_mutation_despite_ambient_state(
    tmp_path, monkeypatch
):
    root = _api_fixture(
        tmp_path,
        "import os\nos.environ.setdefault('CODEX_STARTUP_ROOT_PID', 'imported')\n",
    )
    monkeypatch.setenv("CODEX_STARTUP_ROOT_PID", "ambient-root")
    completed, result = _run(tmp_path, root, ("api",))

    assert completed.returncode != 0
    assert result["status"] == "runtime_effect_invoked"
    assert result["module_results"][0]["environment_changes"]["CODEX_STARTUP_ROOT_PID"] == {
        "after_present": True,
        "before_present": False,
    }


def test_import_verifier_accepts_explicit_import_inertness_inventory(tmp_path):
    modules = (
        "experiment_tracker",
        "privilege_lint_cli",
        "plugin_bus",
        "gui_stub",
        "emotion_pump",
        "emotions",
        "emotion_udp_bridge",
        "audit_immutability",
        "scripts.audit_immutability_verifier",
        "scripts.verify_audits",
        "architect_daemon",
        "reflection_dashboard",
        "scripts.ritual_header_repair",
        "scripts.fix_header_subset",
        "fix_header_subset",
        "integration_memory",
        "codex",
        "codex.integrity_daemon",
        "codex.strategy",
        "memory_manager",
        "curiosity_goal_helper",
        "curiosity_executor",
        "sentient_autonomy",
        "sentientos.autonomy.curiosity_loop",
        "sentientos.autonomy.runtime",
        "emotion_memory",
        "emotion_utils",
        "semantic_embeddings",
        "memory_governor",
        "node_registry",
        "capability_ledger",
        "cathedral_const",
    )
    output = tmp_path / "inventory.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--module-root",
            str(ROOT),
            "--output",
            str(output),
            *(arg for module in modules for arg in ("--module", module)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    result = json.loads(output.read_text(encoding="utf-8"))

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert result["status"] == "import_inertness_ready"
    assert [item["module"] for item in result["module_results"]] == list(modules)
    assert all(item["privilege_invoked"] == [] for item in result["module_results"])
    assert all(item["effects_invoked"] == [] for item in result["module_results"])
    assert all(item["environment_changes"] == {} for item in result["module_results"])


def test_import_verifier_rejects_package_privilege_invocation(tmp_path):
    root = _api_fixture(
        tmp_path,
        "from sentientos.privilege import require_admin_banner\nrequire_admin_banner()\n",
    )
    completed, result = _run(tmp_path, root, ("api", "api.actuator"))
    assert completed.returncode != 0
    assert result["status"] == "privilege_invoked"


def test_import_verifier_rejects_import_time_directory_creation(tmp_path):
    root = _api_fixture(
        tmp_path,
        "",
        "import os\nfrom pathlib import Path\nPath(os.environ['SENTIENTOS_LOG_DIR']).mkdir(parents=True)\n",
    )
    completed, result = _run(tmp_path, root, ("api", "api.actuator"))
    assert completed.returncode != 0
    assert result["status"] == "runtime_effect_invoked"


def test_import_verifier_rejects_external_plugin_execution(tmp_path):
    root = _api_fixture(
        tmp_path,
        "",
        "import os\nfrom pathlib import Path\nexec(next(Path(os.environ['ACT_PLUGINS_DIR']).glob('*.py')).read_text())\n",
    )
    completed, result = _run(tmp_path, root, ("api", "api.actuator"))
    assert completed.returncode != 0
    assert result["status"] == "plugin_executed"
