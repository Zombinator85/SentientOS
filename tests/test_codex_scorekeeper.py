import json
from pathlib import Path

from sentientos.codex.scorekeeper import CodexScorekeeper


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_codex_scorekeeper_generates_scorecard_and_review(tmp_path: Path) -> None:
    keeper = CodexScorekeeper(tmp_path, success_threshold=0.6, rejection_threshold=0.25)

    keeper.record_patch("core", success=True)
    keeper.record_patch("core", success=False, reverted=True)
    keeper.record_patch("ui", success=False)

    keeper.record_proposal("safety", outcome="rejected")
    keeper.record_proposal("safety", outcome="accepted")
    keeper.record_proposal("performance", outcome="accepted")

    report = keeper.compile()

    scorecard_entries = _read_jsonl(keeper.scorecard_path)
    assert scorecard_entries
    core_metrics = scorecard_entries[0]["patches"]["core"]
    assert core_metrics["success_rate"] < 1
    assert report["degradation_signals"]

    review_entries = _read_jsonl(keeper.review_path)
    assert review_entries[0]["trigger"] == "performance_degradation"
