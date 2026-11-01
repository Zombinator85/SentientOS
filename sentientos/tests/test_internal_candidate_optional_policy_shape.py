import pytest

from sentientos.context_hygiene.prompt_internal_candidate import (
    validate_internal_prompt_candidate_input,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyRing,
)

pytestmark = pytest.mark.no_legacy_skip


def test_missing_policy_and_audit_receipts_are_reported() -> None:
    candidate_input = {
        "internal_only": True,
        "operator_visible_only": True,
        "no_llm": True,
        "requested_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "feature_flag_state": {"internal_no_llm_candidate": True},
        "policy_decision": None,
        "audit_receipt": None,
        "operator_review_receipt": None,
        "adapter_payload": None,
        "blueprint": None,
        "candidate_refs": (),
        "candidate_sections": (),
    }

    findings = validate_internal_prompt_candidate_input(candidate_input)

    codes = {finding.code for finding in findings}
    assert "missing_policy_decision" in codes
    assert "missing_audit_receipt" in codes
