import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.truth import ContradictionRegistry, EpistemicLedger, EpistemicOrientation, JudgmentSuspender


def test_contradiction_registry_keeps_links_without_resolution():
    ledger = EpistemicLedger()
    registry = ContradictionRegistry(ledger)

    registry.register_claim(
        "claim-sky-blue",
        topic="sky-state",
        value="blue",
        confidence=0.9,
        source_class="external_witness",
    )
    registry.register_claim(
        "claim-sky-green",
        topic="sky-state",
        value="green",
        confidence=0.92,
        source_class="external_witness",
    )

    topic_links = registry.contradictions_for_topic("sky-state")
    assert topic_links
    assert topic_links[0].status == "coexisting contradiction"

    contradiction_entries = [entry for entry in ledger.entries if entry.entry_type == "contradiction"]
    assert len(contradiction_entries) == len(topic_links)


def test_observation_cannot_become_belief_until_stable():
    orientation = EpistemicOrientation()
    ledger = orientation.ledger

    fragment = orientation.log_observation(
        "obs-frag-1",
        "temperature spike",
        source_class="external_witness",
        confidence=0.7,
        volatility=0.3,
        fragment=True,
    )

    with pytest.raises(ValueError):
        orientation.form_belief_from_observation(fragment)

    stable_observation = orientation.log_observation(
        "obs-stable-1",
        "temperature stabilized",
        source_class="external_witness",
        confidence=0.88,
        volatility=0.1,
        since_day=0,
        fragment=False,
    )
    ledger.advance_day(3)
    belief = orientation.form_belief_from_observation(stable_observation)

    assert belief.entry_type == "belief"
    assert belief.source_class == "internal_synthesis"


def test_suspension_survives_multiple_days():
    ledger = EpistemicLedger()
    suspender = JudgmentSuspender(ledger)

    record = suspender.suspend("claim-drift", reason="lack_of_data", note="waiting for logs")
    ledger.advance_day(5)

    assert suspender.is_suspended("claim-drift")
    assert suspender.days_withheld("claim-drift") == 5
    suspension_entries = [entry for entry in ledger.entries if entry.entry_type == "suspension"]
    assert any(entry.metadata.get("reason") == record.reason for entry in suspension_entries)


def test_confidence_decay_and_volatility_scoring():
    ledger = EpistemicLedger()

    decayed = ledger.apply_confidence_decay(0.9, days_elapsed=4, decay_rate=0.1)
    assert decayed < 0.9

    volatility = ledger.estimate_volatility([0.2, 0.8, 0.5, 0.4])
    assert 0 < volatility <= 1

    band = ledger.compute_confidence_band(0.6, volatility)
    assert band[0] <= 0.6 <= band[1]
