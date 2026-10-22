from __future__ import annotations

from dataclasses import asdict, replace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewDecision,
    PromptOperatorReviewStatus,
    build_prompt_operator_review_receipt,
    compute_prompt_operator_review_digest,
    extract_required_operator_review_warning_codes,
    operator_review_satisfies_policy_decision,
    validate_prompt_operator_review_receipt,
)


def _policy() -> dict[str, object]:
    return {
        "decision_id": "policy:test:operator-review",
        "policy_status": PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        "requires_operator_review": True,
        "denied": False,
        "requested_ring": PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        "effective_ring": PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        "policy_digest": "digest:policy",
        "receipt_id": "audit:test",
        "receipt_digest": "digest:audit",
        "packet_id": "packet:test",
        "packet_scope": "turn",
        "warning_count": 1,
        "caveat_count": 0,
        "reasons": ({"code": "operator_review_required", "severity": "review"},),
    }


def _accepted(policy: dict[str, object], **times: object):
    return build_prompt_operator_review_receipt(
        policy,
        reviewer_ref="operator:test",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,
            PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS),
        accepted_warning_codes=extract_required_operator_review_warning_codes(policy),
        **times,
    )


@pytest.mark.parametrize("field", ("reviewed_at", "evaluated_at", "expires_at"))
@pytest.mark.parametrize("value", (
    "2026-01-01T00:00:00",
    "2026-01-01T00:00:00-00:00",
    123,
))
def test_ambiguous_review_time_never_satisfies_policy(field: str, value: object) -> None:
    policy = _policy()
    times: dict[str, object] = {
        "reviewed_at": "2026-01-01T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "evaluated_at": "2026-01-01T00:00:00Z",
    }
    times[field] = value
    receipt = _accepted(policy, **times)
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_INVALID
    assert any(item.code == "review_time_invalid" for item in receipt.findings)
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_extreme_review_times_fail_closed_when_utc_normalization_overflows() -> None:
    policy = _policy()
    values = ("0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59")
    for field in ("reviewed_at", "evaluated_at", "expires_at"):
        for value in values:
            receipt = _accepted(policy, **{field: value})
            assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_INVALID
            assert any(item.code == "review_time_invalid" for item in receipt.findings)
            assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_ttl_requires_review_and_evaluation_times() -> None:
    policy = _policy()
    receipt = _accepted(policy, ttl_seconds=3600)
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_INVALID
    assert any(item.code == "review_time_invalid" for item in receipt.findings)
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_recomputed_digest_does_not_make_ambiguous_expiry_valid() -> None:
    policy = _policy()
    valid = _accepted(policy)
    forged = replace(
        valid,
        expiration=replace(valid.expiration, expires_at="2030-01-01T00:00:00-00:00"),
        expired=False,
        findings=(),
        review_digest="",
    )
    forged = replace(forged, review_digest=compute_prompt_operator_review_digest(forged))
    assert any(item.code == "review_time_invalid" for item in validate_prompt_operator_review_receipt(forged))
    assert not operator_review_satisfies_policy_decision(policy, forged)


@pytest.mark.parametrize("ttl", ("3600", True, -1))
def test_recomputed_digest_does_not_make_malformed_ttl_valid(ttl: object) -> None:
    policy = _policy()
    valid = _accepted(policy)
    forged = asdict(valid)
    forged["expiration"]["ttl_seconds"] = ttl
    forged["review_digest"] = ""
    forged["review_digest"] = compute_prompt_operator_review_digest(forged)
    assert any(item.code == "review_time_invalid" for item in validate_prompt_operator_review_receipt(forged))
    assert not operator_review_satisfies_policy_decision(policy, forged)


def test_explicit_known_offsets_and_no_expiry_remain_usable() -> None:
    policy = _policy()
    without_expiry = _accepted(policy)
    with_expiry = _accepted(
        policy,
        reviewed_at="2026-01-01T00:00:00+00:00",
        expires_at="2030-01-01T00:00:00Z",
        evaluated_at="2026-01-01T00:00:00+00:00",
    )
    assert without_expiry.review_status == PromptOperatorReviewStatus.REVIEW_ACCEPTED
    assert operator_review_satisfies_policy_decision(policy, without_expiry)
    assert with_expiry.review_status == PromptOperatorReviewStatus.REVIEW_ACCEPTED
    assert operator_review_satisfies_policy_decision(policy, with_expiry)
