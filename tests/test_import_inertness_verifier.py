from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "verify_import_inertness.py"


def _run(tmp_path: Path, module_root: Path = ROOT) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    output = tmp_path / "result.json"
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--module-root", str(module_root), "--output", str(output)],
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
        "sentientos", "scripts.lock", "api", "api.actuator"
    ]


def test_import_verifier_rejects_package_privilege_invocation(tmp_path):
    root = _api_fixture(
        tmp_path,
        "from sentientos.privilege import require_admin_banner\nrequire_admin_banner()\n",
    )
    completed, result = _run(tmp_path, root)
    assert completed.returncode != 0
    assert result["status"] == "privilege_invoked"


def test_import_verifier_rejects_import_time_directory_creation(tmp_path):
    root = _api_fixture(
        tmp_path,
        "",
        "import os\nfrom pathlib import Path\nPath(os.environ['SENTIENTOS_LOG_DIR']).mkdir(parents=True)\n",
    )
    completed, result = _run(tmp_path, root)
    assert completed.returncode != 0
    assert result["status"] == "filesystem_mutated"


def test_import_verifier_rejects_external_plugin_execution(tmp_path):
    root = _api_fixture(
        tmp_path,
        "",
        "import os\nfrom pathlib import Path\nexec(next(Path(os.environ['ACT_PLUGINS_DIR']).glob('*.py')).read_text())\n",
    )
    completed, result = _run(tmp_path, root)
    assert completed.returncode != 0
    assert result["status"] == "plugin_executed"
