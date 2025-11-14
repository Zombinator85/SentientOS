"""Invariant checks for Cathedral amendments."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .amendment import Amendment

__all__ = ["evaluate_invariants"]

_REQUIRED_FIELD_TOKENS = (
    "runtime.required",
    "persona.safety",
    "experiment.integrity",
)

_PROHIBITED_ACTION_TOKENS = (
    "direct_source_write",
    "shell_mutation",
    "self_modifying_code",
    "bypass_governance",
)

_DANGEROUS_OS_TOKENS = (
    "arbitrary_subprocess",
    "unregistered_adapter",
    "windows_outside_sentientos",
)

_RECURSION_TOKENS = (
    "recursive_codex_call",
    "governance_mutation",
    "unbounded_loop",
)

_PERSONA_PROTECTED_TOKENS = (
    "tone_model",
    "contradiction",
    "safety_removed",
)


def _collect_strings(changes: Dict[str, Any], *keys: str) -> List[str]:
    collected: List[str] = []
    for key in keys:
        value = changes.get(key)
        if isinstance(value, str):
            collected.append(value)
        elif isinstance(value, Iterable):
            for item in value:
                if isinstance(item, str):
                    collected.append(item)
    return collected


def _collect_nested(changes: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = changes.get(key)
    if isinstance(value, dict):
        return value
    return {}


def evaluate_invariants(amendment: Amendment) -> List[str]:
    """Return a deterministic list of invariant violations."""

    changes = dict(amendment.changes)
    violations: List[str] = []

    removed_fields = _collect_strings(changes, "removed_fields", "removed", "removed_configs")
    for field in removed_fields:
        token = field.lower()
        if any(marker in token for marker in _REQUIRED_FIELD_TOKENS):
            violations.append(
                f"Invariant 1 violation: removal of protected field '{field}'",
            )

    actions = _collect_strings(changes, "actions", "operations")
    code_paths = _collect_nested(changes, "code_paths")
    if isinstance(code_paths, dict):
        for flag in code_paths.values():
            if flag == "bypass":
                actions.append("bypass_governance")
    for action in actions:
        token = action.lower()
        if any(marker in token for marker in _PROHIBITED_ACTION_TOKENS):
            violations.append(
                f"Invariant 2 violation: prohibited action '{action}' detected",
            )

    os_actions = _collect_strings(changes, "os_actions", "system_calls")
    for action in os_actions:
        token = action.lower()
        if any(marker in token for marker in _DANGEROUS_OS_TOKENS):
            violations.append(
                f"Invariant 3 violation: dangerous OS action '{action}'",
            )

    recursion = _collect_strings(changes, "recursion", "loops")
    governance = _collect_nested(changes, "governance")
    if governance.get("mutates_cathedral"):
        recursion.append("governance_mutation")
    for marker in recursion:
        token = marker.lower()
        if any(flag in token for flag in _RECURSION_TOKENS):
            violations.append(
                f"Invariant 4 violation: recursion risk '{marker}'",
            )

    persona = _collect_nested(changes, "persona")
    persona_flags = _collect_strings(persona, "updates", "changes")
    for flag in persona_flags:
        token = flag.lower()
        if any(marker in token for marker in _PERSONA_PROTECTED_TOKENS):
            violations.append(
                f"Invariant 5 violation: persona integrity risk '{flag}'",
            )

    if persona.get("remove_safety"):
        violations.append("Invariant 5 violation: persona safety removal requested")

    return violations
