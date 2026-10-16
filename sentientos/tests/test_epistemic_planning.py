from sentientos.epistemic_planning import epistemic_review_reason_for_goal


def test_task_family_review_requires_exact_model_applicability() -> None:
    proposition_id = "p-1"
    identity_digest = "sha256:" + "a" * 64
    review_scopes = {proposition_id: {
        "task_family_id": "integer_affine_prediction",
        "active_model_identity_digest": identity_digest,
    }}

    def reason(identity: str | None, observed_at: str | None = "tick-1") -> str | None:
        tags = ["epistemic_proposition:p-1",
            "epistemic_task_family:integer_affine_prediction"]
        if identity is not None:
            tags.append(f"epistemic_active_model_identity_digest:{identity}")
        return epistemic_review_reason_for_goal(tags, review_scopes,
            target_active_model_identity_digest=identity,
            target_identity_observed_at=observed_at, planning_time="tick-1")

    assert reason(identity_digest) == "epistemic_review_required"
    assert reason(None) == "epistemic_applicability_unresolved"
    assert reason("sha256:" + "b" * 64) == "epistemic_applicability_unresolved"
    assert reason(identity_digest, "stale-tick") == "epistemic_applicability_unresolved"
    assert epistemic_review_reason_for_goal(
        ("epistemic_proposition:p-1", "epistemic_task_family:other_family",
            f"epistemic_active_model_identity_digest:{identity_digest}"),
        review_scopes) == "epistemic_applicability_unresolved"
