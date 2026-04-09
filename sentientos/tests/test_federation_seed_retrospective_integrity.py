from __future__ import annotations

import json

from sentientos.federation_seed_retrospective_integrity import derive_bounded_federation_seed_retrospective_integrity_review


def _record(*, health_status: str, denied: int = 0, failed: int = 0, fragmented: int = 0, transition: str = "unchanged") -> dict[str, object]:
    return {
        "health_status": health_status,
        "transition_classification": transition,
        "outcome_counts": {
            "success": 3 - min(3, denied + failed + fragmented),
            "denied": denied,
            "failed_after_admission": failed,
            "fragmented_unresolved": fragmented,
        },
    }


def _review(history: list[dict[str, object]], *, stability: str = "stable") -> dict[str, object]:
    return derive_bounded_federation_seed_retrospective_integrity_review(
        history,
        seed_stability={"classification": stability},
    )


def test_classifies_clean_recent_history() -> None:
    review = _review([_record(health_status="healthy"), _record(health_status="healthy"), _record(health_status="healthy")])
    assert review["review_classification"] == "clean_recent_history", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_denial_heavy() -> None:
    review = _review(
        [
            _record(health_status="healthy", denied=3),
            _record(health_status="healthy", denied=2),
            _record(health_status="healthy", denied=3),
            _record(health_status="healthy"),
        ]
    )
    assert review["review_classification"] == "denial_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_failure_heavy() -> None:
    review = _review(
        [
            _record(health_status="degraded", failed=1),
            _record(health_status="degraded", failed=2),
            _record(health_status="degraded", failed=2),
            _record(health_status="healthy"),
        ]
    )
    assert review["review_classification"] == "failure_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_fragmentation_heavy() -> None:
    review = _review(
        [
            _record(health_status="fragmented", fragmented=2),
            _record(health_status="fragmented", fragmented=3),
            _record(health_status="fragmented", fragmented=2),
            _record(health_status="healthy"),
        ]
    )
    assert review["review_classification"] == "fragmentation_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_oscillatory_instability() -> None:
    review = _review(
        [
            _record(health_status="healthy", denied=1),
            _record(health_status="degraded", failed=1),
            _record(health_status="healthy", denied=1),
            _record(health_status="degraded", failed=1),
        ],
        stability="oscillating",
    )
    assert review["review_classification"] == "oscillatory_instability", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_mixed_stress_pattern() -> None:
    review = _review(
        [
            _record(health_status="healthy", denied=1),
            _record(health_status="degraded", failed=1),
            _record(health_status="fragmented", fragmented=1),
        ]
    )
    assert review["review_classification"] == "mixed_stress_pattern", json.dumps(review, indent=2, sort_keys=True)


def test_classifies_insufficient_history() -> None:
    review = _review([_record(health_status="healthy"), _record(health_status="healthy")])
    assert review["review_classification"] == "insufficient_history", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_is_explicitly_non_sovereign() -> None:
    review = _review([_record(health_status="healthy"), _record(health_status="healthy"), _record(health_status="healthy")])
    assert review["diagnostic_only"] is True
    assert review["non_authoritative"] is True
    assert review["decision_power"] == "none"
    assert review["retrospective_support_signal_only"] is True
    assert review["does_not_change_admission_or_readiness"] is True
