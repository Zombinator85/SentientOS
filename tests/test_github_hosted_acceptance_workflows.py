from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).parents[1]

def test_source_validation_runs_verified_transition_receipt_regressions():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert "- name: Verify transition-stage receipt projection" in source_validation
    nodes = (
        "test_verified_stage_receipt_requires_completed_semantically_verified_journal_binding",
        "test_verified_stage_receipt_accepts_journal_recovered_completion",
        "test_verified_stage_receipt_rejects_rejected_or_missing_custody",
        "test_stage_approval_correlation_must_match_signed_request",
        "test_stage_approval_operation_must_match_signed_request",
        "test_subordinate_approval_summary_must_match_signed_artifact",
        "test_subordinate_approval_summary_is_required",
    )
    for node in nodes:
        assert node in source_validation
    assert "test_transition_stage_plan_rejects_tampering_and_stale_owner" in source_validation
    assert (
        "cp glow/test_runs/test_run_provenance.json \\\n"
        "            glow/test_runs/transition_receipt_provenance.json"
    ) in source_validation
    assert "transition_receipt_acceptance.json" in source_validation
    assert "transition_receipt_acceptance_result.json" in source_validation
    assert "source_validation_provenance.json" in source_validation


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
    assert "types: [opened, synchronize, reopened, edited]" in text
    assert "python -m scripts.run_tests" in text and "verify_task_acceptance.py" in text
    assert "validation_complete" in text and "--require-validation-complete" in text
def test_required_quality_gate_runs_on_construction_candidate_pushes() -> None:
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    push = workflow.split("  push:", 1)[1].split("  merge_group:", 1)[0]
    assert "- main" in push
    assert "- 'codex/construct-sentientos*'" in push
    assert "sudo -n id -u" in workflow
    source_sha = "${{ github.event.pull_request.head.sha || github.sha }}"
    assert f"ref: {source_sha}" in workflow
    assert f"QUALITY_GATE_SOURCE_SHA: {source_sha}" in workflow
    assert '--expected-sha "$QUALITY_GATE_SOURCE_SHA"' in workflow


def test_federation_health_update_uses_hosted_administrator_and_narrow_commit_scope() -> None:
    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    triggers = workflow.split("jobs:", 1)[0]
    assert "schedule:" in triggers and "workflow_dispatch:" in triggers
    assert "pull_request:" not in triggers
    push = triggers.split("  push:", 1)[1]
    assert (
        "branches:\n      - main\n"
        "      - automation/federation-health-publication-fixture"
    ) in push
    assert (
        'paths:\n      - ".github/workflows/federation-health.yml"\n'
        '      - "federation_health_badge.py"\n'
        '      - "work/federation_health_publication_fixture_request.txt"'
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
    assert "inputs.publication_fixture == true || (github.event_name == 'push'" in workflow
    assert "github.ref == 'refs/heads/automation/federation-health-publication-fixture'" in workflow
    assert 'fixture_request_commit_must_change_only_sentinel' in workflow
    assert 'fixture_request_parent_must_be_current_main' in workflow
    assert 'ref: main' in publisher
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
    assert 'DELETE_TRIGGER_BRANCH:' in publisher
    assert 'trigger_branch_deleted' in publisher
    # The one-shot sentinel must be absent from main so its addition is an
    # observable, exact-path push on the disposable fixture branch.
    assert not (ROOT / "work/federation_health_publication_fixture_request.txt").exists()

def test_federation_health_schedule_avoids_top_of_hour_load_spike() -> None:
    import yaml

    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    parsed = yaml.safe_load(workflow)
    triggers = parsed.get("on", parsed.get(True))
    cron = triggers["schedule"][0]["cron"]
    minute = cron.split()[0]
    assert minute not in {"0", "*"}


def test_scheduled_workflows_do_not_collide_by_minute_and_hour() -> None:
    import yaml

    workflow_paths = sorted((ROOT / ".github/workflows").glob("*.yml")) + sorted(
        (ROOT / ".github/workflows").glob("*.yaml")
    )
    occupied: dict[tuple[int, int], str] = {}

    def expand(field: str, maximum: int) -> set[int]:
        values: set[int] = set()
        for item in field.split(","):
            base, separator, step_text = item.partition("/")
            step = int(step_text) if separator else 1
            assert step > 0
            if base == "*":
                lower, upper = 0, maximum
            elif "-" in base:
                lower_text, upper_text = base.split("-", maxsplit=1)
                lower, upper = int(lower_text), int(upper_text)
            else:
                lower = upper = int(base)
            assert 0 <= lower <= upper <= maximum
            values.update(range(lower, upper + 1, step))
        return values

    for path in workflow_paths:
        parsed = yaml.safe_load(path.read_text())
        triggers = parsed.get("on", parsed.get(True, {}))
        for entry in triggers.get("schedule", []):
            fields = entry["cron"].split()
            assert len(fields) == 5, path
            minutes = expand(fields[0], 59)
            hours = expand(fields[1], 23)
            for hour in hours:
                for minute in minutes:
                    slot = (hour, minute)
                    previous = occupied.get(slot)
                    assert previous is None, (
                        f"scheduled workflows collide at {hour:02}:{minute:02}: "
                        f"{previous} and {path}"
                    )
                    occupied[slot] = str(path.relative_to(ROOT))


def test_nightly_self_check_uses_minimal_read_only_authority_and_admin_for_audits() -> None:
    workflow = (ROOT / ".github/workflows/nightly-self-check.yml").read_text()
    assert "permissions:\n  contents: read" in workflow
    import yaml

    parsed = yaml.safe_load(workflow)
    assert parsed["jobs"]["self-check"]["if"] == "${{ github.ref == 'refs/heads/main' }}"
    administrator = workflow.split(
        "- name: Verify hosted Administrator availability", 1
    )[1].split("- name:", 1)[0]
    assert 'test "$(sudo -n id -u)" = "0"' in administrator
    audit = workflow.split("- name: Verify audits", 1)[1].split("- name:", 1)[0]
    assert workflow.index("Verify hosted Administrator availability") < workflow.index("Verify audits")
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
    administrator = audit.split(
        "- name: Verify hosted Administrator availability", 1
    )[1].split("- name:", 1)[0]
    repair = repair_job.split("- name: Plan and apply safe audit repairs", 1)[1].split("- name:", 1)[0]
    repair_administrator = repair_job.split(
        "- name: Verify hosted Administrator availability", 1
    )[1].split("- name:", 1)[0]
    after = repair_job.split("- name: Verify audits after repair", 1)[1].split("- name:", 1)[0]
    stage = repair_job.split("- name: Stage append-only repair evidence", 1)[1].split("- name:", 1)[0]
    assert "permissions:\n      contents: read" in audit
    assert "outputs:\n      status: ${{ steps.initial.outputs.status }}" in audit
    assert "permissions:\n      contents: write\n      pull-requests: write" in repair_job
    import yaml
    parsed = yaml.safe_load(workflow)
    assert parsed["jobs"]["audit"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["repair"]["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert parsed["jobs"]["audit"]["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert parsed["jobs"]["repair"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && needs.audit.result == 'success' "
        "&& needs.audit.outputs.status != '0' }}"
    )
    assert "if: needs.audit.outputs.status != '0'" not in repair_job
    assert "python -m scripts.verify_audits logs/ --strict --no-input" in initial
    assert 'test "$(sudo -n id -u)" = "0"' in administrator
    assert "sudo -n env" in initial
    assert 'test "$(sudo -n id -u)" = "0"' in repair_administrator
    assert repair_job.index("Verify hosted Administrator availability") < repair_job.index(
        "Plan and apply safe audit repairs"
    )
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
    assert selection.count("tests/") == 30
    node_lines = [line for line in selection.splitlines() if "tests/" in line]
    assert all(line.rstrip().endswith("\\") for line in node_lines[:-1])
    assert "len(nodes)==30" in workflow
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
    assert selection.count("tests/test_") == 30


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
    assert ci.count("${{ runner.temp }}/sentientos-test-artifacts/*") == 2
    assert ci.count('RUNNER_TEMP/sentientos-test-artifacts') == 2
    assert "runner.temp" not in ci.replace(
        "${{ runner.temp }}/sentientos-test-artifacts/*", ""
    )
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


def test_ci_source_validation_verifies_append_only_construction_custody() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    source = ci.split("  source-validation:", 1)[1].split("  self-check:", 1)[0]
    assert "Verify append-only construction custody" in source
    assert "python scripts/verify_construction_continuation_custody.py --repo-root . --summary" in source
    assert source.index("Verify append-only construction custody") < source.index("Install canonical test airlock")


def test_ci_uploads_only_test_artifacts_bound_by_current_provenance() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "glow/test_runs/pytest_junitxml*.xml" not in ci
    assert "scripts/stage_current_test_artifacts.py" in ci
    assert "tests/test_stage_current_test_artifacts.py" in ci
    for job_name, upload_name in (
        ("source-validation", "Upload canonical test evidence"),
        ("self-check", "Upload test failure digest artifacts"),
    ):
        job = ci.split(f"  {job_name}:", 1)[1]
        if job_name == "source-validation":
            job = job.split("  self-check:", 1)[0]
        else:
            job = job.split("  docs:", 1)[0]
        stage = job.index("Stage current test-run artifacts")
        upload = job.index(upload_name)
        marker = job.index("Mark current test-run provenance cutoff")
        assert stage < upload
        assert marker < job.index("Install canonical test airlock")
        assert '--output-dir "$RUNNER_TEMP/sentientos-test-artifacts"' in job
        assert '--expected-repository-sha "$GITHUB_SHA"' in job
        assert '--started-after "$RUNNER_TEMP/sentientos-test-run-started"' in job
        assert "${{ runner.temp }}/sentientos-test-artifacts/*" in job[upload:]


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
    assert (
        "if: ${{ github.ref == 'refs/heads/main' && vars.SENTIENTOS_CI_RUN_REMOTE_SMOKE == '1' }}"
        in remote_job
    )
    assert "secrets." not in remote_job and "env." not in remote_job
    assert "Require explicitly configured remote smoke credentials" in remote
    preflight = remote.split("Require explicitly configured remote smoke credentials", 1)[1].split("- uses:", 1)[0]
    assert "${{ secrets.REMOTE_SMOKE_HOST_1 }}" in preflight
    assert "required secret ${name} is missing" in preflight
    assert "exit 1" in preflight

    forge = (ROOT / ".github/workflows/forge-smoke.yml").read_text()
    forge_job = forge.split("  forge-smoke:", 1)[1].split("    steps:", 1)[0]
    assert (
        "if: ${{ github.ref == 'refs/heads/main' && vars.SENTIENTOS_CI_RUN_FORGE_SMOKE == '1' }}"
        in forge_job
    )
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
    bootstrap = workflow.split(
        "- name: Bootstrap minimal documentation tooling with hosted Administrator authority", 1
    )[1].split("- name:", 1)[0]
    assert 'test "$(sudo -n id -u)" = "0"' in bootstrap
    assert "scripts/build_docs.py --bootstrap-docs" in bootstrap
    assert "SENTIENTOS_HEADLESS=1 LUMOS_AUTO_APPROVE=1" in bootstrap
    assert workflow.index("Run strict audits with actual Administrator authority") < workflow.index(
        "Bootstrap minimal documentation tooling"
    )
    assert workflow.index("Bootstrap minimal documentation tooling") < workflow.index(
        "Reconstruct and verify exact hosted pre-commit state"
    )

    freeze = workflow.split(
        "- name: Freeze exact hosted acceptance for PR landing finalization", 1
    )[1].split("- name: Restore generated test-run residue after evidence capture", 1)[0]
    assert "if: github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos')" in freeze
    assert "cp glow/test_runs/test_run_provenance.json" in freeze
    assert 'manifest["test_provenance_path"]' in freeze
    assert 'str(root/"provenance.json")' in freeze
    assert "python scripts/verify_task_acceptance.py" in freeze
    assert "$GITHUB_SHA" not in freeze

    cleanup = workflow.split(
        "- name: Restore generated test-run residue after evidence capture", 1
    )[1].split("- name: Reconstruct and verify exact hosted pre-commit state", 1)[0]
    assert '["git","restore","--",tracked]' in cleanup
    assert 'source[:12] not in target.name' in cleanup
    assert 'code != "??"' in cleanup
    assert "refusing to remove tracked provenance" in cleanup

    precommit = workflow.split(
        "- name: Reconstruct and verify exact hosted pre-commit state", 1
    )[1].split("- name: Complete hosted privileged PR landing finalization", 1)[0]
    assert "trap precommit_failure ERR" in precommit
    assert "phase=%s line=%s exit=%s" in precommit
    for phase in (
        "workspace_reconstruction",
        "package_install",
        "precommit_acceptance",
        "privileged_finalizer",
        "finalizer_result_validation",
    ):
        assert f"PRECOMMIT_PHASE={phase}" in precommit
    assert 'GIT_LFS_SKIP_SMUDGE=1 git worktree add --detach "$PRECOMMIT_WORKSPACE" "$PRECOMMIT_PARENT"' in precommit
    assert 'git diff --binary "$PRECOMMIT_PARENT" "$COMMIT_REF"' in precommit
    assert "selected_node_ids" in precommit
    assert 'env["PYTHONPATH"] = workspace' in precommit
    assert 'len(nodes) != 30' in precommit
    assert 'provenance.get("git_sha") != expected_head' in precommit
    assert "--phase pre-commit" in precommit
    assert "finalizer_exit_code=$?" in precommit
    assert "cat \"$RUNNER_TEMP/codex-finalizer-pre-commit.json\"" in precommit
    assert "set +e" in precommit and "set -e" in precommit
    assert '"reasons": reasons' in precommit
    assert "--validation-profile solo" in precommit
    assert '--workspace-root "$PRECOMMIT_WORKSPACE"' in precommit
    assert "--allow-current-tracked-changes" in precommit
    assert "--allow-current-task-files" in precommit
    assert 'status != "ready_to_commit"' in precommit
    assert 'SENTIENTOS_TEST_RUN_DIR="$PRECOMMIT_FINALIZER_TEST_RUN_DIR"' in precommit
    assert 'test "$PRECOMMIT_WORKSPACE" = "$RUNNER_TEMP/sentientos-precommit-workspace"' in precommit
    assert 'sudo -n git -c safe.directory="$GITHUB_WORKSPACE" -C "$GITHUB_WORKSPACE"' in precommit
    assert 'worktree remove --force "$PRECOMMIT_WORKSPACE"' in precommit

    finalizer = workflow.split(
        "- name: Complete hosted privileged PR landing finalization", 1
    )[1].split("- name: Verify pre-publication PR metadata guard", 1)[0]
    assert "if: github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos')" in finalizer
    assert 'test "$(sudo -n id -u)" = "0"' in finalizer
    assert '"HOME=$HOME"' in finalizer
    assert '"PYTHONPATH=$METADATA_WORKSPACE"' in finalizer
    assert "scripts/codex_finalize_landing.py finalize" in finalizer
    assert "--phase pr-metadata" in finalizer
    assert "--validation-profile solo" in finalizer
    assert '--pre-commit-finalizer-json "$RUNNER_TEMP/codex-finalizer-pre-commit.json"' in finalizer
    assert '--task-acceptance-manifest "$ACCEPTANCE_MANIFEST"' in finalizer
    assert "--allow-generated-artifact-cleanup" in finalizer
    assert 'SENTIENTOS_TEST_RUN_DIR="$RUNNER_TEMP/sentientos-landing-test-runs"' in finalizer
    assert 'PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in finalizer
    assert 'COMMIT_REF="${PR_HEAD_SHA:-HEAD}"' in finalizer
    assert 'git log -1 --format=%s "$COMMIT_REF"' in finalizer
    assert 'test "$PR_TITLE" = "$COMMIT_TITLE"' in finalizer
    assert 'GIT_LFS_SKIP_SMUDGE=1 git worktree add --detach "$METADATA_WORKSPACE" "$COMMIT_REF"' in finalizer
    assert 'provenance.get("git_sha") != expected_head' in finalizer
    assert 'candidate acceptance must contain the exact 30 required nodes' in finalizer
    candidate_verify = finalizer.index(
        'PYTHONPATH="$METADATA_WORKSPACE" python "$METADATA_WORKSPACE/scripts/verify_task_acceptance.py"'
    )
    assert finalizer.rfind('cd "$METADATA_WORKSPACE"', 0, candidate_verify) >= 0
    assert 'SENTIENTOS_METADATA_WORKSPACE=$METADATA_WORKSPACE' in finalizer

    guard = workflow.split(
        "- name: Verify pre-publication PR metadata guard", 1
    )[1].split("- name: Upload hosted privileged PR landing finalizer evidence", 1)[0]
    assert "scripts/codex_pr_metadata_guard.py verify" in guard
    assert "guard_exit=$?" in guard
    assert '"reasons": payload.get("reasons")' in guard
    assert "pre-publication metadata guard blocked (exit" in guard
    assert '--pre-commit-finalizer-json "$RUNNER_TEMP/codex-finalizer-pre-commit.json"' in guard
    assert '--pr-metadata-finalizer-json "$RUNNER_TEMP/codex-finalizer-pr-metadata.json"' in guard
    assert '--matrix-json-path "$RUNNER_TEMP/solo-matrix-not-requested.json"' in guard
    assert '--workspace-root "$METADATA_WORKSPACE"' in guard
    assert 'cd "$METADATA_WORKSPACE"' in guard
    assert 'payload.get("status") != "pr_metadata_guard_ready"' in guard

    candidate_cleanup = workflow.split(
        "- name: Remove exact PR candidate workspace", 1
    )[1].split("- name:", 1)[0]
    assert "Remove exact PR candidate workspace" in workflow
    assert 'test "$(sudo -n id -u)" = "0"' in candidate_cleanup
    assert 'sudo -n git -c safe.directory="$GITHUB_WORKSPACE" -C "$GITHUB_WORKSPACE"' in candidate_cleanup
    assert 'worktree remove --force "$CANDIDATE_WORKSPACE"' in candidate_cleanup
    assert "Upload exact PR candidate acceptance evidence" in workflow

    upload = workflow.split(
        "- name: Upload hosted privileged PR landing finalizer evidence", 1
    )[1]
    assert "if: always() && (github.event_name == 'pull_request' || startsWith(github.ref, 'refs/heads/codex/construct-sentientos'))" in upload
    assert "codex-finalizer-pr-metadata.json" in upload
    assert "codex-finalizer-pre-commit.json" in upload
    assert "codex-pr-metadata-guard.json" in upload
    assert "acceptance-result.json" in upload
    assert "if-no-files-found: error" in upload
    permissions = workflow.split("permissions:", 1)[1].split("jobs:", 1)[0]
    assert "contents: read" in permissions
    assert workflow.index("Upload quality-gate evidence") < workflow.index(
        "Freeze exact hosted acceptance"
    ) < workflow.index("Restore generated test-run residue") < workflow.index(
        "Reconstruct and verify exact hosted pre-commit state"
    ) < workflow.index(
        "Complete hosted privileged PR landing finalization"
    ) < workflow.index(
        "Verify pre-publication PR metadata guard"
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
        expected_paths = {
            ".github/workflows/audit-nightly.yml": {
                ".github/workflows/audit-nightly.yml",
                "audit_chain.py",
                "audit_immutability.py",
                "config/master_files.json",
                "logs/**",
                "scripts/apply_audit_repairs.py",
                "scripts/cli_common.py",
                "scripts/plan_audit_repairs.py",
                "scripts/provenance_hash_chain.py",
                "scripts/tooling_status.py",
                "scripts/verify_audits.py",
                "sentientos/audit_chain_gate.py",
                "sentientos/audit_recovery.py",
                "sentientos/audit_sink.py",
                "sentientos/audit_strict_status.py",
                "sentientos/privilege.py",
                "sentientos/recovery_tasks.py",
            },
            ".github/workflows/nightly-self-check.yml": {
                ".github/workflows/nightly-self-check.yml",
                "audit_chain.py",
                "audit_immutability.py",
                "glow/contracts/canonical_typing_baseline.json",
                "mypy.ini",
                "privilege_lint_cli.py",
                "pyproject.toml",
                "requirements-codex.txt",
                "scripts/analyze_test_provenance.py",
                "scripts/check_mypy_baseline.py",
                "scripts/cli_common.py",
                "scripts/mypy_baseline_common.py",
                "scripts/provenance_hash_chain.py",
                "scripts/pytest_airlock_guard.py",
                "scripts/run_tests.py",
                "scripts/verify_audits.py",
                "sentientos/audit_chain_gate.py",
                "sentientos/audit_recovery.py",
                "sentientos/audit_sink.py",
                "sentientos/audit_strict_status.py",
                "sentientos/privilege.py",
                "sentientos/runtime_governor.py",
                "tests/**",
            },
        }[path]
        assert actual_paths == expected_paths


def test_workflow_dispatch_jobs_are_main_bound() -> None:
    import yaml

    audit = yaml.safe_load((ROOT / ".github/workflows/audit-nightly.yml").read_text())
    capture = yaml.safe_load((ROOT / ".github/workflows/capture-audit-baseline.yml").read_text())
    forge = yaml.safe_load((ROOT / ".github/workflows/forge-smoke.yml").read_text())
    self_check = yaml.safe_load((ROOT / ".github/workflows/nightly-self-check.yml").read_text())
    remote_smoke = yaml.safe_load((ROOT / ".github/workflows/remote-smoke-ci.yml").read_text())
    federation = yaml.safe_load((ROOT / ".github/workflows/federation-health.yml").read_text())
    main_guard = "${{ github.ref == 'refs/heads/main' }}"
    assert capture["permissions"] == {"contents": "read"}
    assert capture["jobs"]["capture"]["if"] == main_guard
    assert capture["jobs"]["capture"]["permissions"] == {"contents": "read"}
    assert capture["jobs"]["capture"]["steps"][0]["with"]["persist-credentials"] is False
    assert capture["jobs"]["commit"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && inputs.commit_baseline == 'true' }}"
    )
    assert capture["jobs"]["commit"]["permissions"] == {"contents": "write"}
    assert capture["jobs"]["commit"]["needs"] == "capture"
    assert capture["jobs"]["commit"]["steps"][0]["with"]["ref"] == "${{ github.sha }}"
    assert "git push origin HEAD:main" in capture["jobs"]["commit"]["steps"][-1]["run"]
    assert forge["permissions"] == {"contents": "read"}
    assert forge["jobs"]["forge-smoke"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && vars.SENTIENTOS_CI_RUN_FORGE_SMOKE == '1' }}"
    )
    assert remote_smoke["permissions"] == {"contents": "read"}
    assert remote_smoke["jobs"]["remote-smoke"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && vars.SENTIENTOS_CI_RUN_REMOTE_SMOKE == '1' }}"
    )
    assert audit["jobs"]["audit"]["if"] == main_guard
    assert audit["jobs"]["repair"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && needs.audit.result == 'success' "
        "&& needs.audit.outputs.status != '0' }}"
    )
    assert self_check["jobs"]["self-check"]["if"] == main_guard
    assert federation["jobs"]["health"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && inputs.publication_fixture != true }}"
    )
    fixture_guard = federation["jobs"]["fixture"]["if"]
    assert "inputs.publication_fixture == true && github.ref == 'refs/heads/main'" in fixture_guard
    assert "github.event_name == 'push'" in fixture_guard
    assert "refs/heads/automation/federation-health-publication-fixture" in fixture_guard
    publish_guard = federation["jobs"]["publish"]["if"]
    assert "needs.health.result == 'success' && github.ref == 'refs/heads/main'" in publish_guard
    assert "needs.fixture.result == 'success'" in publish_guard
    assert "refs/heads/automation/federation-health-publication-fixture" in publish_guard


def test_dev_extra_includes_runtime_dependency_used_by_privilege_lint() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    dev = pyproject.split("dev = [", 1)[1].split("]", 1)[0]
    assert '"PyYAML>=6,<7"' in dev


def test_federation_health_fixture_keeps_generator_read_only_and_cleans_up():
    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    import yaml

    parsed = yaml.safe_load(workflow)
    assert parsed["jobs"]["health"]["if"] == "${{ github.ref == 'refs/heads/main' && inputs.publication_fixture != true }}"
    assert "inputs.publication_fixture == true && github.ref == 'refs/heads/main'" in parsed["jobs"]["fixture"]["if"]
    publish_if = parsed["jobs"]["publish"]["if"]
    assert "needs.health.result == 'success' && github.ref == 'refs/heads/main'" in publish_if
    assert "needs.fixture.result == 'success'" in publish_if
    assert "refs/heads/automation/federation-health-publication-fixture" in publish_if
    assert parsed["jobs"]["fixture"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["health"]["permissions"] == {"contents": "read"}
    assert parsed["jobs"]["publish"]["permissions"] == {
        "contents": "write", "pull-requests": "write"
    }
    assert "actions: write" not in workflow
    assert "TEST FIXTURE — NOT TELEMETRY" in workflow
    assert "publication_scope_verified" in workflow
    assert '"trigger_branch_deleted": trigger_branch_deleted' in workflow
    assert "and trigger_branch_deleted" in workflow
    assert "cleanup_errors" in workflow
    assert "fixture_publication_cleanup_or_scope_unverified" in workflow
    cleanup = workflow.split(
        "- name: Close any fixture PR and remove its branch without merging", 1
    )[1].split("- name: Upload changed-output publication proof", 1)[0]
    assert 'ref = f"repos/{repository}/git/ref/heads/{branch}"' in cleanup
    assert 'delete_ref = f"repos/{repository}/git/refs/heads/{branch}"' in cleanup
    assert '["gh", "api", "--method", "DELETE", delete_ref]' in cleanup
    assert '"repos/{repository}/git/refs/heads/"' in cleanup
    assert '["gh", "api", "--method", "DELETE", trigger_ref]' not in cleanup
    assert '"--method", "DELETE", trigger_delete_ref' in cleanup
    assert "CalledProcessError as exc" in cleanup
    assert "delete-branch: false" in workflow
    assert workflow.count("name: federation-health-publication-fixture-${{ github.run_id }}") == 1
    proof_upload = workflow.split("- name: Upload changed-output publication proof", 1)[1]
    assert "always() && (inputs.publication_fixture == true || (github.event_name == 'push'" in proof_upload
    assert "&& 'always-true' || 'false' }}" in workflow


def test_federation_health_fixture_cleanup_deletes_refs_and_fails_closed(tmp_path):
    import json
    import os
    import subprocess
    import sys
    import textwrap

    workflow = (ROOT / ".github/workflows/federation-health.yml").read_text()
    cleanup_step = workflow.split(
        "- name: Close any fixture PR and remove its branch without merging", 1
    )[1].split("- name: Upload changed-output publication proof", 1)[0]
    marker = "          python - <<'PY'\n"
    script = textwrap.dedent(cleanup_step.split(marker, 1)[1].split("\n          PY", 1)[0])
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args=sys.argv[1:]\n"
        "method=args[args.index('--method')+1] if '--method' in args else 'GET'\n"
        "endpoint=next(x for x in args if x.startswith('repos/'))\n"
        "state_path=pathlib.Path(os.environ['FAKE_GH_STATE'])\n"
        "state=json.loads(state_path.read_text())\n"
        "state['requests'].append([method, endpoint])\n"
        "state_path.write_text(json.dumps(state))\n"
        "if endpoint.endswith('/pulls/42'):\n"
        "  if method == 'PATCH': state['pr_state']='closed'; state_path.write_text(json.dumps(state))\n"
        "  print(json.dumps({'number':42,'state':state['pr_state'],'merged':False,'merged_at':None,'head':{'ref':state['fixture_branch'],'repo':{'full_name':state['repository']}}}))\n"
        "elif '/git/refs/heads/' in endpoint and method == 'DELETE':\n"
        "  if os.environ.get('FAKE_GH_FAIL_DELETE') == '1': print('Resource not accessible by integration',file=sys.stderr); sys.exit(1)\n"
        "  branch=endpoint.split('/git/refs/heads/',1)[1]; state['refs'][branch]=False; state_path.write_text(json.dumps(state)); print('{}')\n"
        "elif '/git/ref/heads/' in endpoint and method == 'GET':\n"
        "  branch=endpoint.split('/git/ref/heads/',1)[1]\n"
        "  if not state['refs'].get(branch,False): print('HTTP 404: Reference does not exist',file=sys.stderr); sys.exit(1)\n"
        "  print(json.dumps({'ref':endpoint}))\n"
        "else: print('unexpected mocked GitHub request: '+method+' '+endpoint,file=sys.stderr); sys.exit(2)\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    repository = "Zombinator85/SentientOS"
    fixture_branch = "automation/federation-health-fixture-123"
    trigger_branch = "automation/federation-health-publication-fixture"

    def invoke_cleanup(*, fail_delete: bool) -> tuple[subprocess.CompletedProcess[str], dict]:
        run_dir = tmp_path / ("failed" if fail_delete else "passed")
        run_dir.mkdir()
        state_path = run_dir / "github.json"
        state_path.write_text(json.dumps({
            "repository": repository,
            "fixture_branch": fixture_branch,
            "pr_state": "open",
            "refs": {fixture_branch: True, trigger_branch: True},
            "requests": [],
        }), encoding="utf-8")
        proof = {
            "schema_version": "sentientos.federation_health_fixture_publication:v1",
            "workflow_run_id": "123",
            "repository": repository,
            "pull_request_number": 42,
            "pull_request_url": "https://github.com/Zombinator85/SentientOS/pull/42",
            "pull_request_head_sha": "a" * 40,
            "pull_request_base_sha": "b" * 40,
            "test_fixture_only": True,
            "publication_scope_verified": True,
            "cleanup": {"closed": False, "merged": False, "branch_deleted": False},
            "verified": False,
        }
        (run_dir / "federation-health-fixture-publication.json").write_text(
            json.dumps(proof), encoding="utf-8"
        )
        env = os.environ.copy()
        env.update({
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "FAKE_GH_STATE": str(state_path),
            "GH_REPOSITORY": repository,
            "PR_NUMBER": "42",
            "FIXTURE_BRANCH": fixture_branch,
            "DELETE_TRIGGER_BRANCH": "true",
            "GITHUB_RUN_ID": "123",
            "RUNNER_TEMP": str(run_dir),
            "GITHUB_OUTPUT": str(run_dir / "output.txt"),
        })
        if fail_delete:
            env["FAKE_GH_FAIL_DELETE"] = "1"
        else:
            env.pop("FAKE_GH_FAIL_DELETE", None)
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, env=env,
            capture_output=True, text=True, check=False,
        )
        return result, json.loads(
            (run_dir / "federation-health-fixture-publication.json").read_text()
        )

    passed, proof = invoke_cleanup(fail_delete=False)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert proof["verified"] is True
    assert proof["cleanup"] == {
        "closed": True,
        "merged": False,
        "branch_deleted": True,
        "trigger_branch_deleted": True,
    }
    state = json.loads(
        (tmp_path / "passed" / "github.json").read_text(encoding="utf-8")
    )
    deletes = [request for request in state["requests"] if request[0] == "DELETE"]
    assert deletes == [
        ["DELETE", f"repos/{repository}/git/refs/heads/{fixture_branch}"],
        ["DELETE", f"repos/{repository}/git/refs/heads/{trigger_branch}"],
    ]
    failed, failed_proof = invoke_cleanup(fail_delete=True)
    assert failed.returncode != 0
    assert failed_proof["verified"] is False
    assert any(
        "Resource not accessible by integration" in item
        for item in failed_proof["cleanup_errors"]
    )



def test_post_merge_feedback_uses_only_pull_request_comment_authority() -> None:
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/post_merge_feedback.yml").read_text())
    trigger = workflow.get("on", workflow.get(True, {}))
    assert trigger == {"pull_request_target": {"types": ["closed"]}}
    assert "permissions" not in workflow
    assert workflow["jobs"]["invite"]["permissions"] == {"pull-requests": "write"}
    assert workflow["jobs"]["invite"]["if"] == "github.event.pull_request.merged == true"
    steps = workflow["jobs"]["invite"]["steps"]
    assert len(steps) == 1
    assert steps[0]["uses"] == "actions/github-script@v7"


def test_source_validation_runs_transition_receipt_campaign_planning_regression():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert "- name: Verify transition receipt informs campaign planning without execution" in source_validation
    node = (
        "tests/test_production_self_reflection_campaign.py::"
        "test_verified_transition_receipt_plans_next_stage_without_execution"
    )
    assert node in source_validation
    assert "transition_stage_planning_provenance.json" in source_validation
    assert "transition_stage_planning_acceptance.json" in source_validation
    assert "transition_stage_planning_acceptance_result.json" in source_validation


def test_source_validation_runs_active_trial_transition_receipt_binding_regression():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert (
        "- name: Verify active-trial transition stage receipt binding without execution"
        in source_validation
    )
    for node in (
        "test_campaign_binds_verified_stage_receipt_to_active_trial_without_execution",
        "test_campaign_binds_final_verified_stage_receipt_to_active_trial_without_execution",
        "test_campaign_stage_receipt_binding_rejects_changed_live_owner",
    ):
        assert node in source_validation
    assert "active_trial_stage_receipt_provenance.json" in source_validation
    assert "active_trial_stage_receipt_acceptance.json" in source_validation
    assert "active_trial_stage_receipt_acceptance_result.json" in source_validation


def test_source_validation_requires_verified_transition_receipts_for_new_outcomes():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert (
        "- name: Verify transition stage receipts are required for new trial outcomes"
        in source_validation
    )
    for node in (
        "test_run_one_records_verified_transition_stage_provenance_in_immutable_outcome",
        "test_new_protocol_requires_live_transition_owner_before_trial_start",
        "test_v2_protocol_rejects_disabled_transition_receipt_policy",
        "test_historical_protocol_without_owner_policy_keeps_v1_receipt_compatibility",
    ):
        assert node in source_validation
    assert "verified_trial_outcome_provenance.json" in source_validation
    assert "verified_trial_outcome_acceptance.json" in source_validation
    assert "verified_trial_outcome_acceptance_result.json" in source_validation


def test_source_validation_indexes_verified_trial_provenance_in_reports():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert (
        "- name: Verify completed campaign reports retain verified trial provenance"
        in source_validation
    )
    assert (
        "tests/test_production_self_reflection_campaign.py::"
        "test_v2_campaign_report_indexes_verified_trial_provenance"
        in source_validation
    )
    assert (
        "tests/test_github_hosted_acceptance_workflows.py::"
        "test_source_validation_indexes_verified_trial_provenance_in_reports"
        in source_validation
    )
    for artifact in (
        "trial_report_provenance.json",
        "trial_report_provenance_acceptance.json",
        "trial_report_provenance_acceptance_result.json",
    ):
        assert artifact in source_validation


def test_source_validation_indexes_read_only_campaign_report_verification():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert (
        "- name: Verify persisted campaign reports without mutation"
        in source_validation
    )
    assert (
        "tests/test_production_self_reflection_campaign.py::"
        "test_campaign_report_verification_is_read_only"
        in source_validation
    )
    assert (
        "tests/test_production_self_reflection_campaign.py::"
        "test_v2_campaign_report_indexes_verified_trial_provenance"
        in source_validation
    )
    assert (
        "tests/test_github_hosted_acceptance_workflows.py::"
        "test_source_validation_indexes_read_only_campaign_report_verification"
        in source_validation
    )
    for artifact in (
        "campaign_report_verification.json",
        "campaign_report_verification_acceptance.json",
        "campaign_report_verification_acceptance_result.json",
    ):
        assert artifact in source_validation


def test_source_validation_indexes_daemon_campaign_report_verification():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    source_validation = workflow.split("\n  self-check:", 1)[0]
    assert "- name: Verify daemon campaign report inspection is read-only" in source_validation
    for node in (
        "tests/test_sentientosd_resident_cognitive_transition_composition.py::"
        "test_daemon_campaign_report_inspection_is_read_only_and_owner_independent",
        "tests/test_sentientosd_resident_cognitive_transition_composition.py::"
        "test_daemon_campaign_report_inspection_fails_closed_without_configured_root",
        "tests/test_sentientosd_resident_cognitive_transition_composition.py::"
        "test_transition_feedback_includes_verified_campaign_report_projection",
        "tests/test_github_hosted_acceptance_workflows.py::"
        "test_source_validation_indexes_daemon_campaign_report_verification",
    ):
        assert node in source_validation
    for artifact in (
        "daemon_campaign_report_inspection.json",
        "daemon_campaign_report_inspection_acceptance.json",
        "daemon_campaign_report_inspection_acceptance_result.json",
    ):
        assert artifact in source_validation
