import json
from pathlib import Path

from scripts import run_operator_confirmed_execution as cli


def test_script_blocks_without_confirm(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    proposal = tmp_path / "proposal.json"
    review.write_text(json.dumps({"status": "execution_review_ready", "packet": {"work_item_id": "w1", "transaction_plan_ready": True}}), encoding="utf-8")
    proposal.write_text(json.dumps({"work_item_id": "w1", "proposed_targets": []}), encoding="utf-8")
    rc = cli.main(["--execution-review", str(review), "--proposal", str(proposal), "--workspace-root", str(tmp_path)])
    assert rc != 0
