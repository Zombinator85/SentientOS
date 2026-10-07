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
    assert "continue-on-error: true" in workflow and "|| true" not in workflow
    assert "Require every hosted validation stage to pass" in workflow


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
    assert selection.count("tests/") == 21
    assert "len(nodes)==21" in workflow
def test_required_quality_gate_proves_pytest_bootstrap_before_exact_nodes() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.index("verify_import_inertness.py") < text.index("verify_pytest_bootstrap.py") < text.index("Execute required call phases")
    assert text.count("tests/test_") == 21


def test_required_quality_gate_uploads_pytest_bootstrap_evidence() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.count("quality_gate_pytest_bootstrap.json") == 2


def test_invariant_workflow_installs_the_canonical_minimal_test_harness() -> None:
    workflow = (ROOT / ".github/workflows/invariant-tests.yml").read_text(encoding="utf-8")
    assert "python -m pip install -r requirements-codex.txt" in workflow
    assert "python -m pip install --no-deps -e ." in workflow
    assert "python -m pip check" in workflow
    assert ".[dev]" not in workflow


def test_docs_deploy_uses_pages_actions_compatible_with_artifact_v4() -> None:
    workflow = (ROOT / ".github/workflows/docs-deploy.yml").read_text(encoding="utf-8")
    assert "actions/upload-pages-artifact@v3" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "actions/upload-pages-artifact@v2" not in workflow
    assert "actions/deploy-pages@v2" not in workflow
    assert 'sudo env "PATH=$PATH" python scripts/build_docs.py --check-deps' in workflow
    assert 'sudo env "PATH=$PATH" python scripts/build_docs.py' in workflow


def test_prompt_assembler_invariant_runs_only_in_administrator_hosted_context() -> None:
    workflow = (ROOT / ".github/workflows/invariant-tests.yml").read_text(encoding="utf-8")
    assert "tests/test_prompt_assembler.py" not in workflow.split("name: Run invariant tests", 1)[1].split("- name:", 1)[0]
    assert 'sudo env "PATH=$PATH" "SENTIENTOS_HEADLESS=$SENTIENTOS_HEADLESS" python -m scripts.run_tests -q tests/test_prompt_assembler.py' in workflow


def test_required_hosted_gate_emits_exact_sha_privileged_stage_evidence() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert "Run privileged hosted landing checks" in workflow
    assert "sudo -n true" in workflow
    assert "sudo env \"PATH=$PATH\" python verify_audits.py --strict" in workflow
    assert "sudo env \"PATH=$PATH\" python scripts/audit_immutability_verifier.py" in workflow
    assert "sudo env \"PATH=$PATH\" python scripts/build_docs.py --check-deps" in workflow
    assert "sudo env \"PATH=$PATH\" python scripts/build_docs.py" in workflow
    for field in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_REF", "HOSTED_HEAD_SHA", "head_tree", "broad_validation", "docs_check_deps", "docs_build", "conclusion", "stages"):
        assert field in workflow
    assert "'codex/hosted-validation/**'" in workflow
    assert "workflow_dispatch:" in workflow
    assert "Require every hosted validation stage to pass" in workflow
    assert "glow/test_runs/hosted_privileged_validation.json" in workflow
