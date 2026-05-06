from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_context_hygiene_prompt_boundaries as guardrails


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fixture(tmp_path: Path, source: str, name: str = "fixture.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _scan_source(tmp_path: Path, source: str, name: str = "fixture.py"):
    return guardrails.scan_file_for_prompt_boundary_violations(_write_fixture(tmp_path, source, name), repo_root=tmp_path)


def _codes(findings) -> set[str]:
    return {finding.code for finding in findings}


def test_default_scan_passes_on_current_repo() -> None:
    report = guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert report.ok, guardrails.summarize_context_hygiene_prompt_boundary_scan(report)
    assert not report.findings


def test_default_scan_reports_clean_or_clean_with_warnings() -> None:
    report = guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert report.status in {
        guardrails.ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN,
        guardrails.ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN_WITH_WARNINGS,
    }


@pytest.mark.parametrize("name", ["final_prompt_text", "assembled_prompt"])
def test_forbidden_prompt_materialization_assignments_are_detected(tmp_path: Path, name: str) -> None:
    findings = _scan_source(tmp_path, f"{name} = 'not allowed'\n")
    assert "forbidden_materialization_assignment" in _codes(findings)


def test_forbidden_prompt_text_field_is_detected(tmp_path: Path) -> None:
    findings = _scan_source(tmp_path, "from dataclasses import dataclass\n@dataclass\nclass Bad:\n    prompt_text: str = ''\n")
    assert "forbidden_materialization_field" in _codes(findings)


@pytest.mark.parametrize("marker", ["does_not_contain_final_prompt_text", "does_not_materialize_prompt_text"])
def test_negative_prompt_text_markers_are_allowed(tmp_path: Path, marker: str) -> None:
    findings = _scan_source(tmp_path, f"{marker} = True\n")
    assert not findings


def test_raw_payload_field_is_detected(tmp_path: Path) -> None:
    findings = _scan_source(tmp_path, "raw_payload = {'x': 'y'}\n")
    assert "forbidden_materialization_assignment" in _codes(findings)


@pytest.mark.parametrize("handle", ["execution_handle", "action_handle", "retention_handle", "retrieval_handle"])
def test_forbidden_runtime_handle_fields_are_detected(tmp_path: Path, handle: str) -> None:
    findings = _scan_source(tmp_path, f"{handle} = object()\n")
    assert "forbidden_materialization_assignment" in _codes(findings)


def test_forbidden_memory_manager_import_is_detected(tmp_path: Path) -> None:
    findings = _scan_source(tmp_path, "import memory_manager\n")
    assert "forbidden_runtime_import" in _codes(findings)


@pytest.mark.parametrize("module", ["openai", "requests", "httpx"])
def test_forbidden_provider_or_network_import_is_detected(tmp_path: Path, module: str) -> None:
    findings = _scan_source(tmp_path, f"import {module}\n")
    assert "forbidden_runtime_import" in _codes(findings)


@pytest.mark.parametrize("module", ["action_router", "retention_commit", "task_admission", "task_executor", "work_routing"])
def test_forbidden_action_retention_routing_import_is_detected(tmp_path: Path, module: str) -> None:
    findings = _scan_source(tmp_path, f"import {module}\n")
    assert "forbidden_runtime_import" in _codes(findings)


def test_forbidden_assemble_prompt_call_is_detected(tmp_path: Path) -> None:
    findings = _scan_source(tmp_path, "def f():\n    return assemble_prompt({})\n")
    assert "forbidden_assemble_prompt_call" in _codes(findings)


@pytest.mark.parametrize("call", ["openai.chat.completions.create", "client.responses.create", "llm.generate"])
def test_forbidden_llm_provider_call_pattern_is_detected(tmp_path: Path, call: str) -> None:
    findings = _scan_source(tmp_path, f"def f():\n    return {call}('x')\n")
    assert _codes(findings) & {"forbidden_provider_call", "forbidden_runtime_call"}


@pytest.mark.parametrize("call", ["retrieve_memory", "write_memory", "search_memory"])
def test_forbidden_memory_retrieval_or_write_call_pattern_is_detected(tmp_path: Path, call: str) -> None:
    findings = _scan_source(tmp_path, f"def f():\n    return {call}('x')\n")
    assert "forbidden_runtime_call" in _codes(findings)


@pytest.mark.parametrize("call", ["commit_retention", "execute_action", "route_work", "admit_work", "orchestrate"])
def test_forbidden_retention_action_routing_call_pattern_is_detected(tmp_path: Path, call: str) -> None:
    findings = _scan_source(tmp_path, f"def f():\n    return {call}('x')\n")
    assert "forbidden_runtime_call" in _codes(findings)


@pytest.mark.parametrize(
    "allowed_name",
    [
        "preview_context_hygiene_adapter_payload_for_prompt_assembly",
        "build_context_hygiene_shadow_prompt_adapter_preview",
    ],
)
def test_phase72_shadow_preview_helper_names_are_not_flagged_by_name(tmp_path: Path, allowed_name: str) -> None:
    findings = _scan_source(tmp_path, f"def {allowed_name}():\n    return None\n")
    assert not findings


@pytest.mark.parametrize(
    "allowed_name",
    ["build_context_hygiene_shadow_prompt_blueprint", "build_shadow_prompt_blueprint_from_adapter_payload", "PromptAssemblerShadowBlueprint"],
)
def test_phase73_shadow_blueprint_helper_names_are_not_flagged_by_name(tmp_path: Path, allowed_name: str) -> None:
    source = f"class {allowed_name}:\n    pass\n" if allowed_name.startswith("Prompt") else f"def {allowed_name}():\n    return None\n"
    findings = _scan_source(tmp_path, source)
    assert not findings


@pytest.mark.parametrize("allowed_name", ["PromptMaterializationAuditReceipt", "audit_receipt_allows_shadow_materializer"])
def test_phase74_audit_receipt_names_are_not_flagged_by_name(tmp_path: Path, allowed_name: str) -> None:
    source = f"class {allowed_name}:\n    pass\n" if allowed_name.startswith("Prompt") else f"def {allowed_name}():\n    return True\n"
    findings = _scan_source(tmp_path, source)
    assert not findings


def test_prompt_assembler_scan_allows_intentional_phase72_73_shadow_hook_imports() -> None:
    findings = guardrails.scan_prompt_assembler_shadow_boundary(REPO_ROOT / "prompt_assembler.py", repo_root=REPO_ROOT)
    assert not findings


def test_prompt_assembler_scan_flags_direct_context_hygiene_bypass_imports(tmp_path: Path) -> None:
    path = _write_fixture(tmp_path, "from sentientos.context_hygiene.selector import select_context_candidates\n", "prompt_assembler.py")
    findings = guardrails.scan_prompt_assembler_shadow_boundary(path, repo_root=tmp_path)
    assert "prompt_assembler_context_hygiene_bypass_import" in _codes(findings)


def test_script_cli_returns_zero_on_current_repo() -> None:
    result = subprocess.run([sys.executable, "scripts/verify_context_hygiene_prompt_boundaries.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "boundary_clean" in result.stdout


def test_script_cli_returns_nonzero_on_temporary_forbidden_materialization(tmp_path: Path) -> None:
    bad = _write_fixture(tmp_path, "final_prompt_text = 'blocked'\n")
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts/verify_context_hygiene_prompt_boundaries.py"), str(bad)], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "forbidden_materialization_assignment" in result.stdout


def test_report_serialization_and_summary_are_deterministic() -> None:
    first = guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    second = guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)
    assert guardrails.summarize_context_hygiene_prompt_boundary_scan(first) == guardrails.summarize_context_hygiene_prompt_boundary_scan(second)


def test_scan_does_not_import_prompt_assembler() -> None:
    sys.modules.pop("prompt_assembler", None)
    guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert "prompt_assembler" not in sys.modules


@pytest.mark.parametrize("module", ["memory_manager", "openai", "requests", "httpx", "pyttsx3"])
def test_scan_does_not_import_memory_runtime_provider_or_speech_modules(module: str) -> None:
    sys.modules.pop(module, None)
    guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert module not in sys.modules


def test_guardrail_script_is_import_pure() -> None:
    code = "import importlib, logging; before=len(logging.getLogger().handlers); importlib.import_module('scripts.verify_context_hygiene_prompt_boundaries'); after=len(logging.getLogger().handlers); assert before == after == 0"
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_phase74_audit_receipt_test_file_remains_present() -> None:
    assert (REPO_ROOT / "tests/test_phase74_prompt_materialization_audit_receipt.py").exists()


def test_architecture_boundary_test_file_remains_present() -> None:
    assert (REPO_ROOT / "tests/architecture/test_architecture_boundaries.py").exists()
