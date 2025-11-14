from datetime import datetime, timezone

from sentientos.cathedral import Amendment, amendment_digest


def _make_amendment(**overrides):
    base = dict(
        id="amend-001",
        created_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        proposer="codex",
        summary="Adjust demo timings",
        changes={
            "experiments": {"update": "demo_simple_success"},
            "metadata": {"ticket": "GOV-101"},
        },
        reason="Ensure demo aligns with latest rehearsal schedule.",
    )
    base.update(overrides)
    return Amendment(**base)


def test_amendment_digest_stable():
    amendment = _make_amendment()
    digest1 = amendment_digest(amendment)
    digest2 = amendment_digest(amendment)
    assert digest1 == digest2


def test_amendment_serialization_round_trip():
    amendment = _make_amendment()
    serialized = amendment.to_dict()
    restored = Amendment.from_dict(serialized)
    assert restored == amendment
    assert amendment_digest(restored) == amendment_digest(amendment)


def test_amendment_hashable():
    amendment = _make_amendment()
    another = _make_amendment(id="amend-002")
    seen = {amendment, another}
    assert len(seen) == 2
