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
    assert "pull_request:" not in triggers
    push = triggers.split("  push:", 1)[1]
    assert "branches:\n      - main" in push
    assert (
        'paths:\n      - ".github/workflows/federation-health.yml"\n'
        '      - "federation_health_badge.py"'
    ) in push
    import yaml

    parsed = yaml.safe_load(workflow)
    assert parsed["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["health"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["publish"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert "actions: write" not in workflow
    health = workflow.split("\n  publish:", 1)[0].split("\n  health:", 1)[1]
    publisher = workflow.split("\n  publish:", 1)[1]
    assert "peter-evans/create-pull-request@v7" not in health
    assert "actions/upload-artifact@v4" in health
    assert "if-no-files-found: error" in health
    assert "actions/download-artifact@v4" in publisher
    assert "needs: [health, fixture]" in publisher
    assert "test \"$(sudo -n id -u)\" = \"0\"" in health
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in health
    assert "python federation_health_badge.py" in health
    badge = (ROOT / "federation_health_badge.py").read_text()
    assert "require_admin_banner()" in badge
    assert "require_lumos_approval()" in badge
    assert "EndBug/add-and-commit@v9" not in workflow
    assert "peter-evans/create-pull-request@v7" in publisher
    assert "automation/federation-health" in publisher
    assert "format('automation/federation-health-fixture-{0}', github.run_id)" in publisher
    assert "add-paths: |\n            docs/FEDERATION_HEALTH.md" in publisher

def test_nightly_self_check_uses_minimal_read_only_authority_and_admin_for_audits() -> None:
    workflow = (ROOT / ".github/workflows/nightly-self-check.yml").read_text()
    assert "permissions:\n  contents: read" in workflow
    audit = workflow.split("- name: Verify audits", 1)[1].split("- name:", 1)[0]
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in audit
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in audit
    assert "contents: write" not in workflow



def test_governor_and_federation_test_roots_are_set_before_project_imports() -> None:
    conftest = (ROOT / "tests/conftest.py").read_text()
    setup = conftest.split("def _module_available", 1)[0]
    assert "tempfile.mkdtemp(prefix=\"sentientos-test-governor-\")" in setup
    assert "tempfile.mkdtemp(prefix=\"sentientos-test-federation-\")" in setup
    import_boundary = setup.index(
        "from scripts.editable_install import editable_install_from_repo_root"
    )
    assert setup.index('os.environ[_GOVERNOR_ROOT_ENV] = str(_TEST_GOVERNOR_ROOT)') < import_boundary
    assert setup.index('os.environ[_FEDERATION_ROOT_ENV] = str(_TEST_FEDERATION_ROOT)') < import_boundary
    fixture = conftest.split("def isolate_governor_runtime", 1)[1].split(
        "@pytest.fixture", 1
    )[0]
    assert "shutil.rmtree(_TEST_GOVERNOR_ROOT, ignore_errors=True)" in fixture
    assert "shutil.rmtree(_TEST_FEDERATION_ROOT, ignore_errors=True)" in fixture
    assert 'os.environ.pop(_GOVERNOR_ROOT_ENV, None)' in fixture
    assert 'os.environ.pop(_FEDERATION_ROOT_ENV, None)' in fixture
    pulse_fixture = conftest.split("def configure_pulse_environment", 1)[1].split(
        "@pytest.fixture", 1
    )[0]
    assert pulse_fixture.index(
        'monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(federation_runtime_dir))'
    ) < pulse_fixture.index("federated_governance_module.reset_controller()")


def test_nightly_self_check_installs_canonical_test_dependencies() -> None:
    workflow = (ROOT / ".github/workflows/nightly-self-check.yml").read_text()
    assert "pip install -e .[dev]" in workflow
    assert "run: |\n          python -m pip install --only-binary=:all: -r requirements-codex.txt" in workflow
    import yaml

    parsed = yaml.safe_load(workflow)
    assert "jobs" in parsed

def test_nightly_audit_repair_uses_safe_plan_apply_and_repair_only_write_access() -> None:
    workflow = (ROOT / ".github/workflows/audit-nightly.yml").read_text()
    assert "permissions:\n  contents: read" in workflow
    assert "issues: write" not in workflow and "actions: write" not in workflow
    audit = workflow.split("  audit:", 1)[1].split("\n  repair:", 1)[0]
    repair_job = workflow.split("  repair:", 1)[1]
    initial = audit.split("- name: Verify audits before repair", 1)[1].split("- name:", 1)[0]
    repair = repair_job.split("- name: Plan and apply safe audit repairs", 1)[1].split("- name:", 1)[0]
    after = repair_job.split("- name: Verify audits after repair", 1)[1].split("- name:", 1)[0]
    stage = repair_job.split("- name: Stage append-only repair evidence", 1)[1].split("- name:", 1)[0]
    assert "permissions:\n      contents: read" in audit
    assert "outputs:\n      status: ${{ steps.initial.outputs.status }}" in audit
    assert "permissions:\n      contents: write\n      pull-requests: write" in repair_job
    import yaml
    parsed = yaml.safe_load(workflow)
    assert parsed["jobs"]["audit"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["repair"]["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert "if: needs.audit.outputs.status != '0'" in repair_job
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in initial
    assert "sudo -n env" in initial
    assert "python -m scripts.plan_audit_repairs logs/ --output \"$plan\"" in repair
    assert "python -m scripts.apply_audit_repairs --plan \"$plan\" --output \"$result\" --apply" in repair
    assert repair.count("sudo -n env") == 2
    assert "GITHUB_RUN_ID" in repair
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in after
    assert 'sudo -n env "PATH=$PATH" "PYTHONPATH=$GITHUB_WORKSPACE"' in after
    assert "repair_receipts.jsonl" in stage and "quarantine_index.jsonl" in stage
    assert "git diff --cached --quiet -- logs/" in stage
    assert "id: publish" in repair_job
    assert "steps.publish.outcome == 'success'" in repair_job
    assert "--auto-repair" not in workflow
    assert "github.rest.repos.get(context.repo)" in repair_job
    assert "base: repository.default_branch" in repair_job
    assert "if: always() && (steps.final.outputs.status != '0'" in repair_job


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
    assert selection.count("tests/") == 29
    node_lines = [line for line in selection.splitlines() if "tests/" in line]
    assert all(line.rstrip().endswith("\\") for line in node_lines[:-1])
    assert "len(nodes)==29" in workflow
    assert "test_required_quality_gate_runs_pr_finalizer_with_hosted_administrator" in selection
    assert "tests/test_maintenance_resident_parent_supervision.py::test_restarted_parent_recovers_when_pid_is_reused_by_a_new_process_generation" in selection
    assert "tests/test_maintenance_resident_parent_supervision.py::test_restarted_parent_fails_closed_when_prior_process_generation_is_still_live" in selection
    assert "tests/test_maintenance_resident_parent_supervision.py::test_linux_process_start_ticks_reads_live_procfs_generation" in selection
    assert "tests/test_developmental_model_replacement_experiment.py::test_world_state_projection_preserves_declared_software_generation_without_claiming_observation" in selection
    assert "tests/test_sentientosd_resident_cognitive_transition_composition.py::test_production_transition_requires_verified_frozen_model_generation_lineage" in selection


def test_required_quality_gate_proves_pytest_bootstrap_before_exact_nodes() -> None:
    text = Path(".github/workflows/required-quality-gate.yml").read_text(encoding="utf-8")
    assert text.index("verify_import_inertness.py") < text.index("verify_pytest_bootstrap.py") < text.index("Execute required call phases")
    selection = text.split("python -m scripts.run_tests -q", 1)[1].split(
        "- name: Bind and verify exact acceptance", 1
    )[0]
    assert selection.count("tests/test_") == 29


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


def test_nightly_workflows_have_path_scoped_main_push_triggers() -> None:
    workflows = {
        ".github/workflows/nightly-self-check.yml",
        ".github/workflows/audit-nightly.yml",
    }
    for path in workflows:
        workflow = (ROOT / path).read_text()
        triggers = workflow.split("jobs:", 1)[0]
        assert "schedule:" in triggers and "workflow_dispatch:" in triggers
        push = triggers.split("  push:", 1)[1].split("  schedule:", 1)[0]
        assert "branches:\n      - main" in push
        path_lines = push.split("    paths:\n", 1)[1].splitlines()
        actual_paths = {
            line.strip()[2:].strip().strip('"')
            for line in path_lines
            if line.strip().startswith("- ")
        }
        expected_paths = {path}
        if path == ".github/workflows/nightly-self-check.yml":
            expected_paths.update({"pyproject.toml", "tests/conftest.py", "tests/test_runtime_governor.py"})
        assert actual_paths == expected_paths


def test_dev_extra_includes_runtime_dependency_used_by_privilege_lint() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    dev = pyproject.split("dev = [", 1)[1].split("]", 1)[0]
    assert '"PyYAML>=6,<7"' in dev


def test_federation_health_fixture_keeps_generator_read_only_and_cleans_up():
    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    import yaml

    parsed = yaml.safe_load(workflow)
    assert parsed["jobs"]["fixture"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["health"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["publish"]["permissions"] == {
        "contents": "write", "pull-requests": "write"
    }
    assert "actions: write" not in workflow
    assert "TEST FIXTURE — NOT TELEMETRY" in workflow
    assert "publication_scope_verified" in workflow
    assert 'proof["cleanup"] = {"closed": closed, "merged": merged, "branch_deleted": branch_deleted}' in workflow
    assert "cleanup_errors" in workflow
    assert "fixture_publication_cleanup_or_scope_unverified" in workflow
    assert "delete-branch: false" in workflow
    assert workflow.count("name: federation-health-publication-fixture-${{ github.run_id }}") == 1
    assert "draft: ${{ inputs.publication_fixture && 'always-true' || 'false' }}" in workflow



def test_post_merge_feedback_uses_only_issue_comment_authority() -> None:
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/post_merge_feedback.yml").read_text())
    trigger = workflow.get("on", workflow.get(True, {}))
    assert trigger == {"pull_request_target": {"types": ["closed"]}}
    assert "permissions" not in workflow
    assert workflow["jobs"]["invite"]["permissions"] == {"issues": "write"}
    assert workflow["jobs"]["invite"]["if"] == "github.event.pull_request.merged == true"
    steps = workflow["jobs"]["invite"]["steps"]
    assert len(steps) == 1
    assert steps[0]["uses"] == "actions/github-script@v7"
