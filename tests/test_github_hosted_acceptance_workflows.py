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
    requirements = (ROOT / "requirements-codex.txt").read_text()
    assert "cryptography>=42,<43" in requirements


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
    assert '"deployment/relay"' in test
    assert '"http://localhost:3928/"' in test


def test_doctrine_bundle_uses_importable_modules_and_requires_artifact_presence() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    sections = ci.split("- name: Emit doctrine contract bundle")
    assert len(sections) == 3
    for section in sections[1:]:
        bundle = section.split("- name: Upload doctrine contract bundle", 1)[0]
        assert "python -m scripts.emit_contract_status" in bundle
        assert "python -m scripts.emit_stability_doctrine" in bundle
        assert "python -m scripts.emit_ci_baseline" in bundle
        assert "python -m scripts.emit_contract_manifest" in bundle
        assert "python scripts/emit_contract_status.py" not in bundle
        assert "python scripts/emit_stability_doctrine.py" not in bundle
        assert "python scripts/emit_contract_manifest.py" not in bundle
        assert "protected_forge_ci=passed" in bundle
        assert "::warning::protected Forge CI" in bundle
        assert "make forge-ci || true" not in bundle

    uploads = ci.split("- name: Upload doctrine contract bundle")
    assert len(uploads) == 3
    for upload in uploads[1:]:
        assert "glow/contracts/contract_status.json" in upload
        assert "glow/contracts/contract_manifest.json" in upload.split("- name:", 1)[0]
        assert "if-no-files-found: error" in upload.split("- name:", 1)[0]


def test_smoke_job_conditions_use_supported_explicit_opt_in_contexts() -> None:
    remote = (ROOT / ".github/workflows/remote-smoke-ci.yml").read_text()
    remote_job = remote.split("  remote-smoke:", 1)[1].split("    steps:", 1)[0]
    assert "if: ${{ vars.SENTIENTOS_CI_RUN_REMOTE_SMOKE == '1' }}" in remote_job
    assert "secrets." not in remote_job and "env." not in remote_job
    assert "Require explicitly configured remote smoke credentials" in remote
    preflight = remote.split("Require explicitly configured remote smoke credentials", 1)[1].split("- uses:", 1)[0]
    assert "${{ secrets.REMOTE_SMOKE_HOST_1 }}" in preflight
    assert "required secret ${name} is missing" in preflight
    assert "exit 1" in preflight

    forge = (ROOT / ".github/workflows/forge-smoke.yml").read_text()
    forge_job = forge.split("  forge-smoke:", 1)[1].split("    steps:", 1)[0]
    assert "if: ${{ vars.SENTIENTOS_CI_RUN_FORGE_SMOKE == '1' }}" in forge_job
    assert "secrets." not in forge_job and "env." not in forge_job


def test_source_validation_verifies_exact_provenance_acceptance_nodes() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_job = workflow.split("  source-validation:", 1)[1].split("\n  self-check:", 1)[0]
    assert "Verify exact provenance-integrity acceptance nodes" in source_job
    assert "python -m scripts.verify_task_acceptance" in source_job
    assert '"repository_sha": os.environ["GITHUB_SHA"]' in source_job
    assert "glow/test_runs/source_validation_acceptance.json" in source_job
    assert "glow/test_runs/source_validation_acceptance_result.json" in source_job
    for node in (
        "tests/test_pytest_collection_reporter.py::test_reporter_records_setup_skip_without_claiming_a_call",
        "tests/test_pytest_collection_reporter.py::test_reporter_records_setup_xfail_as_xfailed_not_skipped",
        "tests/test_run_tests_failure_digest.py::test_successful_run_removes_prior_failure_digest",
        "tests/test_run_tests_bootstrap_airlock.py::test_minimal_airlock_pytest_constraint_matches_project_declaration",
        "tests/test_task_acceptance_verifier.py::test_setup_phase_skip_cannot_satisfy_a_required_call_node",
    ):
        assert node in source_job
