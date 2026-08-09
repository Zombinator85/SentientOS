import pytest
import json
from pathlib import Path

from scripts.bootstrap_codex_task import main


def test_script_outputs_and_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    plan = tmp_path / "plan.json"
    scaffold = tmp_path / "scaffold.json"
    prompt = tmp_path / "prompt.txt"
    verifier = tmp_path / "verifier.json"
    code = main([
        "--task-name", "Codex Task Bootstrapper",
        "--task-goal", "metadata-only bootstrap",
        "--subsystem-kind", "developer_workflow_metadata",
        "--commit-title", "[codex:developer] add codex task bootstrapper",
        "--summary-output", str(summary),
        "--plan-output", str(plan),
        "--scaffold-output", str(scaffold),
        "--prompt-output", str(prompt),
        "--verifier-output", str(verifier),
        "--summary",
    ])
    assert code == 0
    assert summary.exists() and plan.exists() and scaffold.exists() and prompt.exists() and verifier.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"


def test_script_blocked_prompt_output_is_hard_stop(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    summary = tmp_path / "summary.json"
    code = main([
        "--task-name", "Network Provider Bootstrap",
        "--task-goal", "add provider network call",
        "--subsystem-kind", "developer_workflow_metadata",
        "--prompt-output", str(prompt),
        "--summary-output", str(summary),
    ])
    assert code == 1
    text = prompt.read_text(encoding="utf-8")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert "BLOCKED_DO_NOT_IMPLEMENT" in text
    assert "Only then make_pr" not in text
    assert "make_pr" not in text
    assert payload["artifact_classification"] == "diagnostic"


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(
    ("goal", "blocked"),
    [
        ("without provider inference", False),
        ("provider inference is forbidden", False),
        ("do not call OpenAI", False),
        ("do not call GitHub APIs", False),
        ("subprocess execution must remain disabled", False),
        ("shell execution is prohibited", False),
        ("do not invoke the action wing", False),
        ("use provider inference", True),
        ("call OpenAI for inference", True),
        ("use GitHub API to publish", True),
        ("spawn a subprocess", True),
        ("execute shell commands from the library", True),
        ("invoke the action wing", True),
    ],
)
def test_bootstrap_classifies_authority_surface_semantics(tmp_path: Path, goal: str, blocked: bool) -> None:
    summary = tmp_path / "summary.json"
    prompt = tmp_path / "prompt.txt"
    code = main([
        "--task-name", "Authority classification repair",
        "--task-goal", goal,
        "--subsystem-kind", "developer_workflow_metadata",
        "--summary-output", str(summary),
        "--prompt-output", str(prompt),
    ])
    payload = json.loads(summary.read_text(encoding="utf-8"))
    if blocked:
        assert code == 1
        assert payload["status"] == "blocked"
        assert "forbidden_authority_surface_requested" in payload["blocker_codes"]
    else:
        assert code == 0
        assert payload["status"] in {"ready", "ready_with_warnings"}
        assert "forbidden_authority_surface_requested" not in payload["blocker_codes"]


@pytest.mark.no_legacy_skip
def test_script_plan_output_includes_metadata_fixture_root(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    code = main([
        "--task-name", "Memory Commit Execution Gate",
        "--task-goal", "metadata-only execution gate",
        "--preset-id", "metadata_verification",
        "--subsystem-kind", "metadata_verification",
        "--capability-id", "memory_commit_execution_gate",
        "--commit-title", "[codex:memory] add memory commit execution gate",
        "--plan-output", str(plan),
    ])
    assert code == 0
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["fixture_root"] == "tests/fixtures/memory_commit_execution_gate/"

SUPPORTED_BOOTSTRAP_FLAGS = {
    "--task-name",
    "--task-goal",
    "--preset-id",
    "--subsystem-kind",
    "--commit-scope",
    "--output-dir",
    "--summary-output",
    "--plan-output",
    "--scaffold-output",
    "--prompt-output",
    "--verifier-output",
    "--summary",
    "--emit-prompt",
    "--new-module",
    "--new-cli",
    "--test-path",
    "--doc-path",
    "--capability-id",
    "--proof-bundle-artifact-kind",
    "--commit-title",
}


def _documented_bootstrap_flags(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    flags = set()
    for token in text.replace("`", " ").split():
        if token.startswith("--"):
            flags.add(token.rstrip(",.;:)"))
    return flags


def _documented_example_flags(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    flags: set[str] = set()
    in_bash = False
    for line in text.splitlines():
        if line.strip() == "```bash":
            in_bash = True
            continue
        if in_bash and line.strip() == "```":
            in_bash = False
            continue
        if not in_bash:
            continue
        for token in line.split():
            if token.startswith("--"):
                flags.add(token.rstrip(",.;:)"))
    return flags


@pytest.mark.no_legacy_skip
def test_invocation_contract_documents_supported_flags_exactly() -> None:
    flags = _documented_bootstrap_flags(Path("docs/development/codex_bootstrap_invocation_contract.md"))
    documented_supported = flags - {"--existing-module", "--existing-cli"}
    assert SUPPORTED_BOOTSTRAP_FLAGS == documented_supported


@pytest.mark.no_legacy_skip
def test_invocation_contract_doc_examples_only_use_supported_flags() -> None:
    flags = _documented_example_flags(Path("docs/development/codex_bootstrap_invocation_contract.md"))
    assert "--existing-module" not in flags
    assert "--existing-cli" not in flags
    assert flags <= SUPPORTED_BOOTSTRAP_FLAGS


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("flag", ["--existing-module", "--existing-cli"])
def test_unsupported_existing_path_flags_exit_nonzero(flag: str) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([
            "--task-name", "Unsupported flag repair",
            "--task-goal", "prove unsupported flags stop bootstrap invocation",
            flag, "sentientos/codex_task_bootstrapper.py",
        ])
    assert excinfo.value.code != 0


@pytest.mark.no_legacy_skip
def test_repair_task_pattern_documented_without_existing_flags() -> None:
    text = Path("docs/development/codex_bootstrap_invocation_contract.md").read_text(encoding="utf-8")
    assert "use `--new-module` and `--new-cli` only when intentionally naming" in text
    assert "even if that path already exists" in text
    assert "omit `--new-module` and `--new-cli`" in text
    assert "Do not invent `--existing-module`, `--existing-cli`" in text
