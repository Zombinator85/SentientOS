#!/usr/bin/env python3
"""Static guardrails for context-hygiene prompt assembly boundaries.

This verifier reads source text and AST only. It intentionally does not import
prompt_assembler.py, context-hygiene helpers, memory/runtime modules, provider
SDKs, browser/tool controllers, or optional speech dependencies.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCAN_TARGETS: tuple[str, ...] = (
    "prompt_assembler.py",
    "sentientos/context_hygiene/prompt_materialization_audit.py",
    "sentientos/context_hygiene/prompt_assembler_compliance.py",
    "sentientos/context_hygiene/prompt_adapter_contract.py",
    "sentientos/context_hygiene/prompt_constraint_verifier.py",
    "sentientos/context_hygiene/prompt_dry_run_envelope.py",
    "sentientos/context_hygiene/prompt_handoff_manifest.py",
    "sentientos/context_hygiene/prompt_preflight.py",
    "sentientos/context_hygiene/context_packet.py",
    "sentientos/context_hygiene/safety_metadata.py",
    "sentientos/context_hygiene/source_kind_contracts.py",
    "sentientos/context_hygiene/selector.py",
)

FORBIDDEN_FIELD_PATTERNS: tuple[str, ...] = (
    "final_prompt",
    "final_prompt_text",
    "assembled_prompt",
    "prompt_text",
    "rendered_prompt",
    "materialized_prompt",
    "system_prompt",
    "developer_prompt",
    "llm_params",
    "llm_parameters",
    "model_params",
    "provider_params",
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "browser_handle",
    "mouse_handle",
    "keyboard_handle",
)

NEGATIVE_MARKER_PREFIXES: tuple[str, ...] = (
    "does_not_",
    "no_",
    "non_",
    "not_",
    "without_",
    "must_not_",
)

SHADOW_ALLOWLIST_NAMES: frozenset[str] = frozenset(
    {
        "preview_context_hygiene_adapter_payload_for_prompt_assembly",
        "build_context_hygiene_shadow_prompt_adapter_preview",
        "build_context_hygiene_shadow_prompt_blueprint",
        "build_shadow_prompt_blueprint_from_adapter_payload",
        "PromptAssemblerShadowAdapterPreview",
        "PromptAssemblerShadowBlueprint",
        "PromptMaterializationAuditReceipt",
        "audit_receipt_allows_shadow_materializer",
    }
)

PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS: frozenset[str] = frozenset(
    {
        "sentientos.context_hygiene.prompt_adapter_contract",
        "sentientos.context_hygiene.prompt_assembler_compliance",
    }
)
PROMPT_ASSEMBLER_FORBIDDEN_CONTEXT_HYGIENE_IMPORTS: tuple[str, ...] = (
    "sentientos.context_hygiene.selector",
    "sentientos.context_hygiene.prompt_preflight",
    "sentientos.context_hygiene.prompt_handoff_manifest",
    "sentientos.context_hygiene.prompt_dry_run_envelope",
    "sentientos.context_hygiene.prompt_constraint_verifier",
    "sentientos.context_hygiene.prompt_materialization_audit",
    "sentientos.context_hygiene.context_packet",
    "sentientos.context_hygiene.safety_metadata",
    "sentientos.context_hygiene.source_kind_contracts",
)

FORBIDDEN_IMPORT_PATTERNS: tuple[str, ...] = (
    "memory_manager",
    "openai",
    "requests",
    "httpx",
    "browser",
    "pyautogui",
    "mouse",
    "keyboard",
    "task_admission",
    "task_executor",
    "orchestrator",
    "orchestration",
    "router",
    "routing",
    "executor",
    "execution",
    "action_router",
    "action_executor",
    "action_dispatch",
    "retention",
    "feedback",
    "screen_awareness",
    "vision_tracker",
    "mic_bridge",
    "multimodal_tracker",
    "embodiment_runtime",
    "raw_screen",
    "raw_audio",
    "raw_vision",
    "raw_multimodal",
)

FORBIDDEN_CALL_NAMES: tuple[str, ...] = (
    "assemble_prompt",
    "create",
    "chat.completions.create",
    "responses.create",
    "complete",
    "completion",
    "retrieve_memory",
    "retrieve_memories",
    "search_memory",
    "query_memory",
    "write_memory",
    "save_memory",
    "append_memory",
    "commit_retention",
    "commit",
    "trigger_feedback",
    "execute_action",
    "dispatch_action",
    "route_task",
    "route_work",
    "admit_task",
    "admit_work",
    "execute_task",
    "execute_work",
    "orchestrate",
    "browser",
    "click",
    "typewrite",
    "press",
)

FORBIDDEN_PROVIDER_CALL_OWNERS: tuple[str, ...] = ("openai", "client", "provider", "llm", "model")
FORBIDDEN_CONTEXT_PAYLOAD_TYPES: tuple[str, ...] = (
    "ContextPacket",
    "PromptAssemblyAdapterPayload",
    "PromptAssemblerShadowBlueprint",
    "PromptMaterializationAuditReceipt",
)
MATERIALIZER_FUNCTION_PREFIXES: tuple[str, ...] = ("materialize", "render", "assemble")


class ContextHygienePromptBoundaryStatus(str, Enum):
    BOUNDARY_CLEAN = "boundary_clean"
    BOUNDARY_CLEAN_WITH_WARNINGS = "boundary_clean_with_warnings"
    BOUNDARY_FAILED = "boundary_failed"
    BOUNDARY_SCAN_ERROR = "boundary_scan_error"


@dataclass(frozen=True, order=True)
class ContextHygienePromptBoundaryFinding:
    path: str
    line: int
    column: int
    code: str
    detail: str
    severity: str = "blocker"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContextHygienePromptBoundaryReport:
    status: ContextHygienePromptBoundaryStatus
    scanned_paths: tuple[str, ...]
    findings: tuple[ContextHygienePromptBoundaryFinding, ...] = field(default_factory=tuple)
    warnings: tuple[ContextHygienePromptBoundaryFinding, ...] = field(default_factory=tuple)
    shadow_allowlist: tuple[str, ...] = field(default_factory=lambda: tuple(sorted(SHADOW_ALLOWLIST_NAMES)))

    @property
    def ok(self) -> bool:
        return self.status in {
            ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN,
            ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN_WITH_WARNINGS,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "scanned_paths": list(self.scanned_paths),
            "findings": [finding.to_dict() for finding in self.findings],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "shadow_allowlist": list(self.shadow_allowlist),
        }


def _display_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _module_name_from_import(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return tuple(module + (f".{alias.name}" if module else alias.name) for alias in node.names)
    return ()


def _name_is_negative_marker(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(NEGATIVE_MARKER_PREFIXES)
        or lowered.startswith(("forbidden_", "_forbidden_"))
        or "_forbidden_" in lowered
        or "_not_" in lowered
        or "does_not" in lowered
        or "must_not" in lowered
        or "without" in lowered
    )


def _identifier_contains_forbidden_field(name: str) -> str | None:
    lowered = name.lower()
    if name in SHADOW_ALLOWLIST_NAMES or _name_is_negative_marker(name):
        return None
    for pattern in FORBIDDEN_FIELD_PATTERNS:
        if pattern in lowered:
            return pattern
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return ""


def _target_names(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Name):
        yield node.id, node.lineno, node.col_offset
    elif isinstance(node, ast.Attribute):
        yield node.attr, node.lineno, node.col_offset
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            yield from _target_names(elt)


def _string_dict_keys(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Dict):
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                yield key.value, key.lineno, key.col_offset


def _annotation_mentions_context_payload(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return any(payload_type in ast.unparse(node) for payload_type in FORBIDDEN_CONTEXT_PAYLOAD_TYPES)


def _is_prompt_assembler(path: Path) -> bool:
    return path.name == "prompt_assembler.py"


def _is_context_hygiene_module(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return "sentientos" in parts and "context_hygiene" in parts


def _finding(path: Path, line: int, col: int, code: str, detail: str, repo_root: Path) -> ContextHygienePromptBoundaryFinding:
    return ContextHygienePromptBoundaryFinding(
        path=_display_path(path, repo_root),
        line=line,
        column=col,
        code=code,
        detail=detail,
    )


def scan_file_for_prompt_boundary_violations(path: str | Path, *, repo_root: str | Path = REPO_ROOT) -> tuple[ContextHygienePromptBoundaryFinding, ...]:
    """Scan one Python source file for prompt-boundary violations.

    The scan is purely textual/AST-based; the target module is never imported.
    """
    root = Path(repo_root)
    source_path = Path(path)
    if not source_path.is_absolute():
        source_path = root / source_path
    findings: list[ContextHygienePromptBoundaryFinding] = []
    try:
        text = source_path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source_path))
    except Exception as exc:  # pragma: no cover - exact parse errors vary by Python.
        return (_finding(source_path, 1, 0, "boundary_scan_error", f"could not parse source: {exc}", root),)

    prompt_assembler = _is_prompt_assembler(source_path)
    context_hygiene = _is_context_hygiene_module(source_path) or not prompt_assembler

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module_name in _module_name_from_import(node):
                lowered = module_name.lower()
                if prompt_assembler and module_name.startswith("sentientos.context_hygiene"):
                    base = module_name.rsplit(".", 1)[0]
                    if any(module_name.startswith(forbidden) for forbidden in PROMPT_ASSEMBLER_FORBIDDEN_CONTEXT_HYGIENE_IMPORTS):
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "prompt_assembler_context_hygiene_bypass_import", f"prompt_assembler.py must not directly import {module_name}; use the Phase 70/71 shadow-only boundary", root))
                    elif base not in PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS and module_name not in PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS:
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "prompt_assembler_unapproved_context_hygiene_import", f"prompt_assembler.py imports unapproved context hygiene surface {module_name}", root))
                elif context_hygiene:
                    for pattern in FORBIDDEN_IMPORT_PATTERNS:
                        if pattern in lowered:
                            findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_import", f"prompt-boundary code must not import runtime/provider surface {module_name}", root))
                            break
                    if lowered.startswith("prompt_assembler") or lowered.startswith("sentientos.prompt_assembler"):
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_prompt_assembler_import", f"context hygiene code must not import {module_name}", root))

        if context_hygiene and isinstance(node, ast.AnnAssign):
            for name, line, col in _target_names(node.target):
                forbidden = _identifier_contains_forbidden_field(name)
                if forbidden:
                    findings.append(_finding(source_path, line, col, "forbidden_materialization_field", f"identifier {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, (ast.Assign, ast.AugAssign, ast.NamedExpr)):
            targets: Sequence[ast.AST]
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AugAssign):
                targets = (node.target,)
            else:
                targets = (node.target,)
            for target in targets:
                for name, line, col in _target_names(target):
                    forbidden = _identifier_contains_forbidden_field(name)
                    if forbidden:
                        findings.append(_finding(source_path, line, col, "forbidden_materialization_assignment", f"assignment target {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, ast.Dict):
            for name, line, col in _string_dict_keys(node):
                forbidden = _identifier_contains_forbidden_field(name)
                if forbidden:
                    findings.append(_finding(source_path, line, col, "forbidden_materialization_mapping_key", f"mapping key {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered_name = node.name.lower()
            if any(lowered_name.startswith(prefix) for prefix in MATERIALIZER_FUNCTION_PREFIXES):
                annotations = [arg.annotation for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)] + [node.returns]
                if any(_annotation_mentions_context_payload(annotation) for annotation in annotations):
                    findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_context_payload_materializer", f"function {node.name!r} appears to materialize/render/assemble a context hygiene payload type", root))

        if context_hygiene and isinstance(node, ast.Call):
            call = _call_name(node.func)
            lowered_call = call.lower()
            if call == "assemble_prompt" or lowered_call.endswith(".assemble_prompt"):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_assemble_prompt_call", "context hygiene prompt-boundary code must not call assemble_prompt(...) directly", root))
            elif any(lowered_call == forbidden or lowered_call.endswith(f".{forbidden}") for forbidden in FORBIDDEN_CALL_NAMES):
                if lowered_call == "commit" and not any(owner in lowered_call for owner in ("retention", "memory")):
                    continue
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_call", f"forbidden runtime/provider call pattern {call!r}", root))
            elif any(owner in lowered_call for owner in FORBIDDEN_PROVIDER_CALL_OWNERS) and any(verb in lowered_call for verb in ("create", "complete", "invoke", "generate", "send")):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_provider_call", f"forbidden LLM/provider call pattern {call!r}", root))
            elif any(term in lowered_call for term in ("retrieve_memory", "write_memory", "save_memory", "search_memory", "commit_retention", "execute_action", "route_work", "admit_work")):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_call", f"forbidden context side-effect call pattern {call!r}", root))

    return tuple(sorted(findings))


def scan_prompt_assembler_shadow_boundary(path: str | Path = "prompt_assembler.py", *, repo_root: str | Path = REPO_ROOT) -> tuple[ContextHygienePromptBoundaryFinding, ...]:
    return scan_file_for_prompt_boundary_violations(path, repo_root=repo_root)


def _resolve_scan_targets(paths: Sequence[str | Path] | None, repo_root: Path) -> tuple[Path, ...]:
    selected = paths if paths else DEFAULT_SCAN_TARGETS
    return tuple((Path(p) if Path(p).is_absolute() else repo_root / Path(p)) for p in selected)


def scan_context_hygiene_prompt_boundaries(paths: Sequence[str | Path] | None = None, *, repo_root: str | Path = REPO_ROOT) -> ContextHygienePromptBoundaryReport:
    root = Path(repo_root)
    targets = _resolve_scan_targets(paths, root)
    findings: list[ContextHygienePromptBoundaryFinding] = []
    scanned: list[str] = []
    for target in targets:
        scanned.append(_display_path(target, root))
        findings.extend(scan_file_for_prompt_boundary_violations(target, repo_root=root))
    unique_findings = tuple(sorted({finding: None for finding in findings}.keys()))
    status = (
        ContextHygienePromptBoundaryStatus.BOUNDARY_FAILED
        if unique_findings
        else ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN
    )
    return ContextHygienePromptBoundaryReport(status=status, scanned_paths=tuple(scanned), findings=unique_findings)


def summarize_context_hygiene_prompt_boundary_scan(report: ContextHygienePromptBoundaryReport) -> str:
    lines = [
        f"Context hygiene prompt boundary scan: {report.status.value}",
        f"Scanned files: {len(report.scanned_paths)}",
        f"Findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(f"- {finding.path}:{finding.line}:{finding.column} [{finding.code}] {finding.detail}")
    if not report.findings:
        lines.append("No prompt materialization, forbidden runtime import/call, or context-hygiene bypass findings detected.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify context-hygiene prompt boundary static guardrails.")
    parser.add_argument("paths", nargs="*", help="Optional Python files to scan instead of the default Phase 75 target set.")
    parser.add_argument("--json", action="store_true", help="Emit deterministic JSON report.")
    args = parser.parse_args(argv)
    report = scan_context_hygiene_prompt_boundaries(args.paths or None)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(summarize_context_hygiene_prompt_boundary_scan(report))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests.
    raise SystemExit(main())
