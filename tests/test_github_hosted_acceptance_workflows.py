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
    assert "pip install -e" in validate
    assert "verify_import_inertness.py" in validate and "python -m build" in validate
    assert "publish_release.py --noop" not in validate
    assert "softprops" not in validate and "secrets." not in validate
def test_required_quality_gate_runs_and_verifies_real_tests():
    text=(ROOT/".github/workflows/required-quality-gate.yml").read_text()
    assert "python -m scripts.run_tests" in text and "verify_task_acceptance.py" in text
    assert "validation_complete" in text and "--require-validation-complete" in text
def test_required_quality_gate_runs_on_construction_candidate_pushes() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    push = workflow.split("  push:", 1)[1].split("  merge_group:", 1)[0]
    assert "- main" in push
    assert "- 'codex/construct-sentientos*'" in push
    assert "sudo -n id -u" in workflow
    assert '--expected-sha "$GITHUB_SHA"' in workflow


def test_federation_health_update_uses_hosted_administrator_and_narrow_commit_scope() -> None:
    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    triggers = workflow.split("jobs:", 1)[0]
    assert "schedule:" in triggers and "workflow_dispatch:" in triggers
    assert "pull_request:" not in triggers and "push:" not in triggers
    assert "permissions:\n  contents: write" in workflow
    assert "test \"$(sudo -n id -u)\" = \"0\"" in workflow
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in workflow
    assert "python federation_health_badge.py" in workflow
    badge = (ROOT / "federation_health_badge.py").read_text()
    assert "require_admin_banner()" in badge
    assert "require_lumos_approval()" in badge
    assert "add: 'docs/FEDERATION_HEALTH.md'" in workflow


def test_nightly_self_check_uses_minimal_read_only_authority_and_admin_for_audits() -> None:
    workflow = (ROOT / ".github/workflows/nightly-self-check.yml").read_text()
    assert "permissions:\n  contents: read" in workflow
    audit = workflow.split("- name: Verify audits", 1)[1].split("- name:", 1)[0]
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in audit
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in audit
    assert "contents: write" not in workflow


def test_nightly_audit_repair_uses_safe_plan_apply_and_pr_scoped_write_access() -> None:
    workflow = (ROOT / ".github/workflows/audit-nightly.yml").read_text()
    assert "permissions:\n  contents: write\n  pull-requests: write" in workflow
    assert "issues: write" not in workflow and "actions: write" not in workflow
    initial = workflow.split("- name: Verify audits before repair", 1)[1].split("- name:", 1)[0]
    repair = workflow.split("- name: Plan and apply safe audit repairs", 1)[1].split("- name:", 1)[0]
    after = workflow.split("- name: Verify audits after repair", 1)[1].split("- name:", 1)[0]
    stage = workflow.split("- name: Stage append-only repair evidence", 1)[1].split("- name:", 1)[0]
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in initial
    assert "sudo -n env" in initial and "continue-on-error: true" in initial
    assert "python -m scripts.plan_audit_repairs logs/ --output \"$plan\"" in repair
    assert "python -m scripts.apply_audit_repairs --plan \"$plan\" --output \"$result\" --apply" in repair
    assert repair.count("sudo -n env") == 2
    assert "GITHUB_RUN_ID" in repair and "if: steps.initial.outputs.status != '0'" in repair
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in after
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in after
    assert "repair_receipts.jsonl" in stage and "quarantine_index.jsonl" in stage
    assert "git diff --cached --quiet -- logs/" in stage
    assert "id: publish" in workflow
    assert "steps.publish.outcome == 'success'" in workflow
    assert "--auto-repair" not in workflow
    assert "github.rest.repos.get(context.repo)" in workflow
    assert "base: repository.default_branch" in workflow
    assert "if: always() && steps.initial.outputs.status != '0'" in workflow


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
    assert selection.count("tests/") == 23
    assert "len(nodes)==23" in workflow
    assert "test_required_quality_gate_runs_pr_finalizer_with_hosted_administrator" in selection


def test_required_quality_gate_proves_pytest_bootstrap_before_exact_nodes() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.index("verify_import_inertness.py") < text.index("verify_pytest_bootstrap.py") < text.index("Execute required call phases")
    selection = text.split("python -m scripts.run_tests -q", 1)[1].split(
        "- name: Bind and verify exact acceptance", 1
    )[0]
    assert selection.count("tests/test_") == 23


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
    # CI installs the lock without invoking the privilege-gated repair script;
    # equivalent static checks and the full test suite run in later steps.
    self_check = ci.split("  self-check:", 1)[1].split("  docs:", 1)[0]
    assert "python -m pip install --only-binary=:all: -r requirements-codex.txt" in self_check
    assert "python -m scripts.lock check" in self_check
    assert "scripts/ci_self_check.py" not in self_check
    # Artifact retention must query one bounded, name-filtered page rather than
    # traversing every historical artifact in the repository.
    assert "permissions:\n      actions: write\n      contents: read" in self_check
    demo_cleanup = self_check.split("      - name: Remove old demo artifacts", 1)[1]
    assert "--method GET" in demo_cleanup
    assert "-f name=demo" in demo_cleanup
    assert "-F per_page=100" in demo_cleanup
    assert "--paginate" not in demo_cleanup


def test_docs_ci_installs_its_declared_docs_extra_without_skipping_gate() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    docs = ci.split("  docs:", 1)[1].split("  helm-k8s-test:", 1)[0]
    assert 'python -m pip install -e ".[docs]"' in docs
    assert "make docs" in docs
    assert "continue-on-error" not in docs


def test_github_mypy_jobs_use_the_repository_baseline_ratchet() -> None:
    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/lint.yml",
        ".github/workflows/nightly-self-check.yml",
    ):
        workflow = (ROOT / path).read_text()
        assert "python scripts/check_mypy_baseline.py" in workflow
        assert "run: mypy --strict" not in workflow


def test_pre_commit_uses_canonical_read_only_checks() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text()
    assert "entry: python -m scripts.check_audit_chain" in config
    assert "entry: python -m scripts.run_tests" in config
    assert "entry: python scripts/check_mypy_baseline.py" in config
    assert "pre-commit/mirrors-mypy" not in config


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
    assert "Verify exact resource-to-cognition acceptance nodes" in source_job
    assert "Verify canonical planning and execution separation" in source_job
    assert source_job.index("Run integrated resource-to-cognition lifecycle") < source_job.index(
        "Verify exact resource-to-cognition acceptance nodes") < source_job.index(
        "Verify canonical planning and execution separation")
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
        "tests/test_local_model_chat_recovery.py::test_restart_preserves_resource_provisioning_identity",
        "tests/test_resident_epistemic_development.py::test_restart_between_evidence_and_state_deduplicates_and_continues",
        "tests/test_resident_developmental_writeback.py::test_successful_selected_evidence_candidate_admitted_append_receipt_retrieval_and_restart",
        "tests/test_resident_developmental_cognition.py::test_restart_tick_n_plus_one_retrieves_prior_history_for_cognition",
        "tests/test_resident_developmental_cognition.py::test_real_invoker_retains_distinct_lessons_and_later_tick_reads_them",
        "tests/test_developmental_model_replacement_experiment.py::test_serving_receipt_references_survive_controlled_run_recovery",
        "sentientos/tests/test_work_plan_evidence_bounds.py::test_large_epistemic_evidence_round_trips_exactly_through_immutable_sidecar",
        "sentientos/tests/test_work_plan_evidence_bounds.py::test_large_epistemic_evidence_sidecar_tampering_fails_closed",
        "sentientos/tests/test_epistemic_planning.py::test_supported_model_bound_position_requires_exact_identity_and_reaches_plan_evidence",
    ):
        assert node in source_job


def test_quarantined_world_state_bridge_runs_as_separate_exact_acceptance() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_job = workflow.split("  source-validation:", 1)[1].split("\n  self-check:", 1)[0]
    assert "Run explicit World-State and resource-join controls" in source_job
    assert "python -m scripts.run_tests -- -m legacy -q" in source_job
    assert "world_state_contracts_provenance.json" in source_job
    assert "world_state_contracts_acceptance_result.json" in source_job
    assert "python -m scripts.verify_task_acceptance" in source_job
    for node in (
        "tests/test_world_state_board.py::test_world_state_snapshot_boundaries_and_authority_false",
        "tests/test_world_state_sources.py::test_manifest_bounds_path_safety_and_dedup",
        "tests/test_resource_invocation_process_generation_integration.py::test_parent_child_resource_invocation_generation_reaches_world_state",
    ):
        assert node in source_job

    
def test_privilege_lint_workflows_use_read_only_mode() -> None:
    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/lint.yml",
        ".github/workflows/nightly-self-check.yml",
    ):
        workflow = (ROOT / path).read_text()
        assert "python -m privilege_lint_cli --read-only --quiet ." in workflow
        assert "run: python privilege_lint.py" not in workflow


def test_required_quality_gate_runs_pr_finalizer_with_hosted_administrator() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    freeze = workflow.split(
        "- name: Freeze exact hosted acceptance for PR landing finalization", 1
    )[1].split("- name: Complete hosted privileged PR landing finalization", 1)[0]
    assert "if: github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos')" in freeze
    assert "cp glow/test_runs/test_run_provenance.json" in freeze
    assert 'manifest["test_provenance_path"]' in freeze
    assert 'str(root/"provenance.json")' in freeze
    assert "python scripts/verify_task_acceptance.py" in freeze
    assert "$GITHUB_SHA" not in freeze

    cleanup = workflow.split(
        "- name: Restore generated test-run residue after evidence capture", 1
    )[1].split("- name: Complete hosted privileged PR landing finalization", 1)[0]
    assert '["git","restore","--",tracked]' in cleanup
    assert 'source[:12] not in target.name' in cleanup
    assert 'code != "??"' in cleanup
    assert "refusing to remove tracked provenance" in cleanup

    finalizer = workflow.split(
        "- name: Complete hosted privileged PR landing finalization", 1
    )[1].split("- name: Upload hosted privileged PR landing finalizer evidence", 1)[0]
    assert "if: github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos')" in finalizer
    assert 'test "$(sudo -n id -u)" = "0"' in finalizer
    assert '"HOME=$HOME"' in finalizer
    assert '"PYTHONPATH=$GITHUB_WORKSPACE"' in finalizer
    assert "scripts/codex_finalize_landing.py finalize" in finalizer
    assert "--phase pr-metadata" in finalizer
    assert "--validation-profile solo" in finalizer
    assert '--task-acceptance-manifest "$RUNNER_TEMP/sentientos-landing-acceptance/manifest.json"' in finalizer
    assert "--allow-generated-artifact-cleanup" in finalizer
    assert 'SENTIENTOS_TEST_RUN_DIR="$RUNNER_TEMP/sentientos-landing-test-runs"' in finalizer
    assert 'PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in finalizer
    assert 'COMMIT_REF="${PR_HEAD_SHA:-HEAD}"' in finalizer
    assert 'git log -1 --format=%s "$COMMIT_REF"' in finalizer
    assert 'test "$PR_TITLE" = "$COMMIT_TITLE"' in finalizer

    upload = workflow.split(
        "- name: Upload hosted privileged PR landing finalizer evidence", 1
    )[1]
    assert "if: always() && (github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos'))" in upload
    assert "codex-finalizer-pr-metadata.json" in upload
    assert "acceptance-result.json" in upload
    assert "if-no-files-found: error" in upload
    permissions = workflow.split("permissions:", 1)[1].split("jobs:", 1)[0]
    assert "contents: read" in permissions
    assert workflow.index("Upload quality-gate evidence") < workflow.index(
        "Freeze exact hosted acceptance"
    ) < workflow.index("Restore generated test-run residue") < workflow.index(
        "Complete hosted privileged PR landing finalization"
    )
