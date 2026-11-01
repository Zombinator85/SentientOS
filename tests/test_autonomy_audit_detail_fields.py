from __future__ import annotations

from sentientos.autonomy.audit import AutonomyActionLogger


def test_action_logger_accepts_typed_detail_mapping(tmp_path) -> None:
    logger = AutonomyActionLogger(path=tmp_path / "actions.jsonl")

    logger.log(
        "browser",
        "open",
        "performed",
        detail_fields={"target": "https://example.test", "reason": "operator-requested"},
    )

    entry = logger.recent()[0]
    assert entry["target"] == "https://example.test"
    assert entry["reason"] == "operator-requested"
