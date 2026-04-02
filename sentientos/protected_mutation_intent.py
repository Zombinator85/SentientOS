from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

INTENT_SCHEMA_VERSION = 1

_CODEXHEALER_DOMAIN = "codexhealer_repair_regenesis_linkage"

_ACTION_DOMAIN_MAP: dict[str, tuple[str, ...]] = {
    "lineage_integrate": ("genesisforge_lineage_proposal_adoption",),
    "proposal_adopt": ("genesisforge_lineage_proposal_adoption",),
    "generate_immutable_manifest": ("immutable_manifest_identity_writes",),
    "quarantine_clear": ("quarantine_clear_privileged_operator_action",),
}


@dataclass(frozen=True)
class ProtectedIntentEvaluation:
    status: str
    declared: bool
    declared_domains: tuple[str, ...]
    expected_domains: tuple[str, ...]
    expect_forward_enforcement: bool
    authority_match: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "declared": self.declared,
            "declared_domains": list(self.declared_domains),
            "expected_domains": list(self.expected_domains),
            "expect_forward_enforcement": self.expect_forward_enforcement,
            "authority_match": self.authority_match,
        }


def declare_protected_mutation_intent(
    *,
    domains: tuple[str, ...],
    authority_classes: tuple[str, ...],
    invocation_path: str,
    expect_forward_enforcement: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": INTENT_SCHEMA_VERSION,
        "declared": True,
        "domains": sorted(set(item for item in domains if item)),
        "authority_classes": sorted(set(item for item in authority_classes if item)),
        "expect_forward_enforcement": bool(expect_forward_enforcement),
        "invocation_path": invocation_path,
    }


def _normalize_declared_intent(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, Mapping) or not bool(raw.get("declared", False)):
        return None
    domains = sorted({str(item).strip() for item in (raw.get("domains") or []) if str(item).strip()})
    authority = sorted({str(item).strip() for item in (raw.get("authority_classes") or []) if str(item).strip()})
    return {
        "schema_version": int(raw.get("schema_version") or INTENT_SCHEMA_VERSION),
        "declared": True,
        "domains": domains,
        "authority_classes": authority,
        "expect_forward_enforcement": bool(raw.get("expect_forward_enforcement", True)),
        "invocation_path": str(raw.get("invocation_path") or ""),
    }


def expected_domains_for_decision(*, action_kind: str, actor: str, authority_class: str) -> tuple[str, ...]:
    domains = set(_ACTION_DOMAIN_MAP.get(action_kind, ()))
    if actor == "codex_healer" and authority_class == "repair":
        domains.add(_CODEXHEALER_DOMAIN)
    return tuple(sorted(domains))


def evaluate_declared_intent_for_decision(decision_row: Mapping[str, Any]) -> ProtectedIntentEvaluation:
    action_kind = str(decision_row.get("action_kind") or "")
    actor = str(decision_row.get("actor") or decision_row.get("execution_owner") or "")
    authority_class = str(decision_row.get("authority_class") or "")
    expected_domains = expected_domains_for_decision(action_kind=action_kind, actor=actor, authority_class=authority_class)
    declared_intent = _normalize_declared_intent(decision_row.get("protected_mutation_intent"))

    if not expected_domains:
        if declared_intent is not None:
            return ProtectedIntentEvaluation(
                status="declared_but_not_applicable",
                declared=True,
                declared_domains=tuple(declared_intent["domains"]),  # type: ignore[arg-type]
                expected_domains=(),
                expect_forward_enforcement=bool(declared_intent.get("expect_forward_enforcement", True)),
                authority_match=authority_class in set(declared_intent.get("authority_classes") or []),
            )
        return ProtectedIntentEvaluation(
            status="not_applicable",
            declared=False,
            declared_domains=(),
            expected_domains=(),
            expect_forward_enforcement=False,
            authority_match=True,
        )

    if declared_intent is None:
        return ProtectedIntentEvaluation(
            status="undeclared_but_protected_action",
            declared=False,
            declared_domains=(),
            expected_domains=expected_domains,
            expect_forward_enforcement=True,
            authority_match=False,
        )

    declared_domains = set(declared_intent.get("domains") or [])
    authority_set = {str(item) for item in declared_intent.get("authority_classes") or []}
    authority_match = authority_class in authority_set
    domain_match = bool(declared_domains.intersection(expected_domains))
    status = "declared_and_consistent" if domain_match and authority_match else "declared_but_mismatched"
    return ProtectedIntentEvaluation(
        status=status,
        declared=True,
        declared_domains=tuple(sorted(declared_domains)),
        expected_domains=expected_domains,
        expect_forward_enforcement=bool(declared_intent.get("expect_forward_enforcement", True)),
        authority_match=authority_match,
    )
