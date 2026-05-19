from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CANONICAL_AUTHORITY_CLAIM_FAMILIES: tuple[str, ...] = (
    "execution_authority",
    "verification_replay",
    "lifecycle_real_closure",
    "agent_execution",
    "scheduler",
    "live_tracker",
    "network",
    "provider",
    "prompt_export",
    "subprocess_or_shell",
    "pr_branch_issue_mutation",
    "workspace_execution",
)

AUTHORITY_CLAIM_ALIASES: dict[str, tuple[str, ...]] = {
    "execution_authority": (
        "execution_permitted",
        "execution_performed",
        "target_write_performed",
        "rollback_performed",
    ),
    "verification_replay": ("verification_replay_performed",),
    "lifecycle_real_closure": ("real_lifecycle_closure_performed",),
    "agent_execution": (
        "agent_execution_requested",
        "agent_execution_permitted",
        "agent_execution_performed",
    ),
    "scheduler": (
        "scheduler_requested",
        "scheduler_performed",
        "scheduler_authority_claimed",
        "scheduler_invoked",
        "scheduler_permitted",
    ),
    "live_tracker": (
        "live_tracker_requested",
        "live_tracker_performed",
        "live_tracker_authority_claimed",
        "live_tracker_mutation_claimed",
        "live_tracker_invoked",
    ),
    "network": (
        "network_requested",
        "network_performed",
        "network_authority_claimed",
        "network_permitted",
        "network_invoked",
    ),
    "provider": (
        "provider_requested",
        "provider_invocation_performed",
        "provider_authority_claimed",
        "provider_invocation_claimed",
        "provider_invoked",
    ),
    "prompt_export": (
        "prompt_export_requested",
        "prompt_export_performed",
        "prompt_export_authority_claimed",
        "prompt_assembly_performed",
    ),
    "subprocess_or_shell": (
        "subprocess_used",
        "shell_used",
        "subprocess_or_shell_performed",
        "subprocess_authority_claimed",
        "subprocess_invoked",
        "shell_authority_claimed",
        "shell_invoked",
    ),
    "pr_branch_issue_mutation": (
        "pr_creation_requested",
        "branch_creation_requested",
        "issue_mutation_requested",
        "pr_mutation_claimed",
        "pr_creation_claimed",
        "branch_mutation_claimed",
        "branch_creation_claimed",
        "issue_mutation_claimed",
        "issue_comment_mutation_claimed",
    ),
    "workspace_execution": (
        "workspace_execution_performed",
        "target_write_performed",
    ),
}

ALIASES_TO_FAMILY: dict[str, str] = {
    alias: family for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES for alias in AUTHORITY_CLAIM_ALIASES[family]
}

AUTHORITY_CONTRADICTION_CODES: dict[str, str] = {
    "execution_authority": "dry_run_claims_real_execution_authority",
    "verification_replay": "dry_run_claims_verification_replay_authority",
    "lifecycle_real_closure": "dry_run_claims_real_lifecycle_closure_authority",
    "agent_execution": "dry_run_claims_agent_execution_authority",
    "scheduler": "dry_run_claims_scheduler_authority",
    "live_tracker": "dry_run_claims_live_tracker_authority",
    "network": "dry_run_claims_network_authority",
    "provider": "dry_run_claims_provider_authority",
    "prompt_export": "dry_run_claims_prompt_export_authority",
    "subprocess_or_shell": "dry_run_claims_subprocess_or_shell_authority",
    "pr_branch_issue_mutation": "dry_run_claims_pr_branch_issue_mutation_authority",
    "workspace_execution": "dry_run_claims_workspace_execution_authority",
}

_TRUTHY_STRINGS = frozenset({"true", "yes"})
_FALSEY_STRINGS = frozenset({"false", "no", ""})


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUTHY_STRINGS:
            return True
        if lowered in _FALSEY_STRINGS:
            return False
    return False


def normalize_authority_claims(mapping: Mapping[str, Any] | None) -> dict[str, bool]:
    claims = {family: False for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES}
    if not isinstance(mapping, Mapping):
        return claims
    for key, value in mapping.items():
        family = ALIASES_TO_FAMILY.get(str(key))
        if family and _coerce_bool(value):
            claims[family] = True
    return claims


def authority_claims_from_nested_evidence(*evidence: Any) -> dict[str, bool]:
    claims = {family: False for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            local = normalize_authority_claims(node)
            for family, claimed in local.items():
                if claimed:
                    claims[family] = True
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    for item in evidence:
        walk(item)
    return claims


def authority_contradiction_codes(claims: Mapping[str, bool]) -> tuple[str, ...]:
    return tuple(
        AUTHORITY_CONTRADICTION_CODES[family]
        for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES
        if bool(claims.get(family, False))
    )


def authority_claim_summary(claims: Mapping[str, bool]) -> tuple[str, ...]:
    return tuple(family for family in CANONICAL_AUTHORITY_CLAIM_FAMILIES if bool(claims.get(family, False)))


__all__ = [
    "ALIASES_TO_FAMILY",
    "AUTHORITY_CLAIM_ALIASES",
    "AUTHORITY_CONTRADICTION_CODES",
    "CANONICAL_AUTHORITY_CLAIM_FAMILIES",
    "authority_claim_summary",
    "authority_claims_from_nested_evidence",
    "authority_contradiction_codes",
    "normalize_authority_claims",
]
