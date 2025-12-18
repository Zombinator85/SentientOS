from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.council.governance_council import GovernanceCouncil
from sentientos.reflex.reflex_petitioner import ReflexPetitioner

pytestmark = pytest.mark.no_legacy_skip


def _fixed_now() -> datetime:
    return datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_reflex_petitioner_generates_petition_and_reinstates(tmp_path: Path) -> None:
    blacklist_path = tmp_path / "reflex_blacklist.json"
    trials_path = tmp_path / "reflex_trials.jsonl"
    petition_log = tmp_path / "reinstatement_petition.jsonl"
    ledger_path = tmp_path / "vote_ledger.jsonl"
    verdicts_path = tmp_path / "verdicts.jsonl"

    suppressed_at = _fixed_now() - timedelta(days=2)
    blacklist_path.write_text(
        json.dumps({
            "reflex-alpha": {
                "suppressed_at": suppressed_at.isoformat(),
                "reasons": ["persistent_failures"],
            }
        }),
        encoding="utf-8",
    )

    good_trial = {
        "rule_id": "reflex-alpha",
        "timestamp": (suppressed_at + timedelta(hours=2)).isoformat(),
        "status": "ok",
    }
    trials_path.write_text("\n".join([json.dumps(good_trial) for _ in range(4)]), encoding="utf-8")

    agents = [("Approver", lambda vote: "approve"), ("Guardian", lambda vote: "approve")]
    council = GovernanceCouncil(
        ledger_path=ledger_path,
        verdicts_path=verdicts_path,
        agent_behaviors=agents,
        quorum_required=2,
    )

    petitioner = ReflexPetitioner(
        blacklist_path=blacklist_path,
        trials_path=trials_path,
        petitions_path=petition_log,
        ttl_seconds=60,
        min_valid_trials=3,
        council=council,
        now_fn=_fixed_now,
    )

    result = petitioner.process_petitions()

    assert result["petitions_triggered"] == 1
    assert result["reinstated"] == ["reflex-alpha"]
    assert json.loads(blacklist_path.read_text(encoding="utf-8")) == {}
    petitions = petition_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(petitions) == 1
    logged = json.loads(petitions[0])
    assert logged["council_status"] == "approved"
