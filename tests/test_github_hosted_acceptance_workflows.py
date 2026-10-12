from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).parents[1]

def test_devcontainer_uses_private_virtualenv():
    text=(ROOT/".devcontainer/Dockerfile").read_text()
    assert "VIRTUAL_ENV=/opt/venv" in text and "PATH=/opt/venv/bin:$PATH" in text
    assert "python3 -m venv /opt/venv" in text and "python -m pip install --upgrade" in text
    assert "python3 -m pip install --upgrade" not in text
def test_disabled_accelerator_performs_no_setup():
    text=(ROOT/".github/workflows/ci.yaml").read_text()
    assert "enabled: false" not in text and "accelerator: cuda" not in text
    assert "accelerator: cpu" in text and "Build devcontainer image" in text and "Run CI script" in text
def test_release_pr_validation_installs_project_without_publishing():
    text=(ROOT/".github/workflows/release.yml").read_text()
    validate=text.split("  publish:",1)[0]
    assert "pip install -e" in validate and "import sentientos" in validate and "--noop" in validate
    assert "softprops" not in validate and "secrets." not in validate
def test_required_quality_gate_runs_and_verifies_real_tests():
    text=(ROOT/".github/workflows/required-quality-gate.yml").read_text()
    assert "python -m scripts.run_tests" in text and "verify_task_acceptance.py" in text
    assert "validation_complete" in text and "--require-validation-complete" in text
def test_required_quality_gate_name_is_unique():
    matches=[]
    for path in (ROOT/".github/workflows").glob("*.y*ml"):
        if "Required / Quality Gate" in path.read_text(): matches.append(path)
    assert matches == [ROOT/".github/workflows/required-quality-gate.yml"]
def test_required_quality_gate_uses_minimal_dependency_bootstrap() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    assert "--only-binary=:all: -r requirements-codex.txt" in workflow
    assert "--no-deps -e ." in workflow
    assert "python -m pip check" in workflow
    assert '.[dev,test]' not in workflow


def test_required_quality_gate_runs_diagnostic_import_smoke() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    smoke = "python scripts/verify_import_inertness.py --output glow/test_runs/quality_gate_import_smoke.json"
    assert workflow.index("python -m pip check") < workflow.index(smoke)
    assert workflow.index(smoke) < workflow.index("python -m scripts.run_tests")
    assert "python -c \"import sentientos" not in workflow
    assert "continue-on-error" not in workflow and "|| true" not in workflow


def test_required_quality_gate_uploads_import_smoke_evidence() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    upload = workflow.split("- name: Upload quality-gate evidence", 1)[1]
    assert "if: always()" in upload
    assert "glow/test_runs/quality_gate_import_smoke.json" in upload


def test_required_quality_gate_runs_exact_nodes_after_import_smoke() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    selection = workflow.split("python -m scripts.run_tests -q", 1)[1].split(
        "- name: Bind and verify exact acceptance", 1
    )[0]
    assert selection.count("tests/") == 19
    assert "len(nodes)==19" in workflow
def test_required_quality_gate_proves_pytest_bootstrap_before_exact_nodes() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.index("verify_import_inertness.py") < text.index("verify_pytest_bootstrap.py") < text.index("Execute required call phases")
    assert text.count("tests/test_") == 19


def test_required_quality_gate_uploads_pytest_bootstrap_evidence() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.count("quality_gate_pytest_bootstrap.json") == 2


def test_invariant_and_helm_jobs_install_the_canonical_test_airlock() -> None:
    invariant = (ROOT / ".github/workflows/invariant-tests.yml").read_text()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "python -m pip install --no-deps -e ." in invariant
    assert "python -m pip install --only-binary=:all: -r requirements-codex.txt" in invariant
    helm = ci.split("  helm-k8s-test:", 1)[1]
    assert "python -m pip install --no-deps -e ." in helm
    assert "python -m pip install --only-binary=:all: -r requirements-codex.txt" in helm
    assert "pip install -e .[dev]" not in helm


def test_ci_adds_separate_unprivileged_canonical_lifecycle_validation() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    source = ci.split("  source-validation:", 1)[1].split("  self-check:", 1)[0]
    assert "python -m scripts.run_tests -q" in source
    assert "tests/test_local_model_chat_recovery.py" in source
    assert "tests/test_resident_developmental_cognition.py" in source
    assert "tests/test_local_model_catalog_deployment_capability_admission.py" in source
    assert "tests/test_import_inertness_verifier.py" in source
    assert "tests/integrity/test_import_purity.py" in source
    assert "--noconftest" not in source
    assert "continue-on-error" not in source
    assert "|| true" not in source
    assert ".ci-runtime/governor" in source
    assert "runner.temp" not in ci
    # The existing privileged self-check remains present with its approval gate.
    self_check = ci.split("  self-check:", 1)[1].split("  docs:", 1)[0]
    assert "python -m scripts.lock install" in self_check
    assert "LUMOS_AUTO_APPROVE" in self_check


def test_docs_ci_installs_its_declared_docs_extra_without_skipping_gate() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    docs = ci.split("  docs:", 1)[1].split("  helm-k8s-test:", 1)[0]
    assert 'python -m pip install -e ".[docs]"' in docs
    assert "make docs" in docs
    assert "continue-on-error" not in docs


def test_helm_smoke_keeps_service_monitor_optional_without_dropping_opt_in() -> None:
    values = (ROOT / "helm/values.yaml").read_text()
    template = (ROOT / "helm/templates/serviceMonitor.yaml").read_text()
    test = (ROOT / "tests/integration/helm_k8s_test.py").read_text()
    assert "serviceMonitor:" in values and "enabled: false" in values
    assert "if .Values.serviceMonitor.enabled" in template
    assert "--set\", \"serviceMonitor.enabled=true" in test
    assert "ServiceMonitor\" not in default_render.stdout" in test
