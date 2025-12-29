from __future__ import annotations

from typing import Mapping

import pytest

from sentientos import constitution


def _validate_invariants(assertions: Mapping[str, bool]) -> None:
    invariant_ids = {inv.identifier for inv in constitution.INVARIANTS}
    missing = invariant_ids.difference(assertions)
    unexpected = set(assertions).difference(invariant_ids)
    failed = sorted(key for key, value in assertions.items() if not value)

    if missing or unexpected or failed:
        details = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if unexpected:
            details.append(f"unexpected={sorted(unexpected)}")
        if failed:
            failed_details = [
                f"{key}: {constitution.INVARIANTS_BY_ID[key].statement}" for key in failed
            ]
            details.append(f"failed={failed_details}")
        raise AssertionError("Invariant violation: " + "; ".join(details))


def test_constitution_invariants_are_declared_and_asserted() -> None:
    domains = {
        constitution.DOMAIN_AUTHORITY,
        constitution.DOMAIN_RECOVERY,
        constitution.DOMAIN_MEMORY,
        constitution.DOMAIN_NARRATIVE,
        constitution.DOMAIN_EMBODIMENT,
    }
    for invariant in constitution.INVARIANTS:
        assert invariant.identifier
        assert invariant.statement
        assert invariant.domain in domains
        assert constitution.INVARIANTS_BY_ID[invariant.identifier] == invariant

    _validate_invariants(constitution.CURRENT_SYSTEM_ASSERTIONS)


@pytest.mark.parametrize(
    ("domain", "invariant_id"),
    [
        (constitution.DOMAIN_AUTHORITY, "AUTH-CONSENT-REQUIRED-EMBODIMENT-EGRESS"),
        (constitution.DOMAIN_RECOVERY, "REC-NEVER-RECOVER-IMMUTABLE"),
        (constitution.DOMAIN_MEMORY, "MEM-NO-SILENT-DELETION"),
        (constitution.DOMAIN_NARRATIVE, "NARRATIVE-RENDERING-NO-EVENTS"),
        (constitution.DOMAIN_EMBODIMENT, "EMB-NO-REAL-WORLD-IO-WITHOUT-ADAPTER"),
    ],
)
def test_forbidden_change_tripwires(domain: str, invariant_id: str) -> None:
    assert invariant_id in constitution.INVARIANTS_BY_DOMAIN[domain]
    statement = constitution.INVARIANTS_BY_ID[invariant_id].statement
    assertions = dict(constitution.CURRENT_SYSTEM_ASSERTIONS)
    assertions[invariant_id] = False

    with pytest.raises(AssertionError) as excinfo:
        _validate_invariants(assertions)

    message = str(excinfo.value)
    assert invariant_id in message
    assert statement in message
