from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.federation_health_execution_receipt import build_execution_receipt


def test_execution_receipt_binds_schedule_to_exact_main_report(tmp_path: Path) -> None:
    report = tmp_path / "FEDERATION_HEALTH.md"
    report.write_text("# Federation Health\n\n- Status: quiet\n", encoding="utf-8")

    receipt = build_execution_receipt(
        run_id="39223000001",
        run_attempt="2",
        event_name="schedule",
        ref="refs/heads/main",
        head_sha="a" * 40,
        report_path=report,
    )

    assert receipt == {
        "schema_version": "sentientos.federation_health_execution:v1",
        "workflow": "Federation Health Update",
        "workflow_run_id": 39223000001,
        "workflow_run_attempt": 2,
        "event_name": "schedule",
        "ref": "refs/heads/main",
        "head_sha": "a" * 40,
        "administrator_preflight": "passed",
        "health_generator": "completed_successfully",
        "report_path": "docs/FEDERATION_HEALTH.md",
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    assert "peer" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("run_id", "0", "workflow_run_id_invalid"),
        ("run_attempt", "0", "workflow_run_attempt_invalid"),
        ("event_name", "pull_request", "workflow_event_not_allowed"),
        ("ref", "refs/heads/feature", "workflow_ref_not_main"),
        ("head_sha", "not-a-commit", "workflow_head_sha_invalid"),
    ],
)
def test_execution_receipt_rejects_unbound_execution_metadata(
    tmp_path: Path, field: str, value: str, error: str
) -> None:
    report = tmp_path / "FEDERATION_HEALTH.md"
    report.write_text("# Federation Health\n", encoding="utf-8")
    run_id = "39223000001"
    run_attempt = "1"
    event_name = "schedule"
    ref = "refs/heads/main"
    head_sha = "b" * 40
    if field == "run_id":
        run_id = value
    elif field == "run_attempt":
        run_attempt = value
    elif field == "event_name":
        event_name = value
    elif field == "ref":
        ref = value
    else:
        head_sha = value

    with pytest.raises(ValueError, match=error):
        build_execution_receipt(
            run_id=run_id,
            run_attempt=run_attempt,
            event_name=event_name,
            ref=ref,
            head_sha=head_sha,
            report_path=report,
        )


def test_federation_health_workflow_binds_receipt_after_admin_gate() -> None:
    workflow = Path(".github/workflows/federation-health.yml").read_text(
        encoding="utf-8"
    )
    health = workflow.split("\n  publish:", 1)[0]
    admin = health.index('test "$(sudo -n id -u)" = "0"')
    generator = health.index("python federation_health_badge.py")
    receipt = health.index("scripts/federation_health_execution_receipt.py")
    upload = health.index("actions/upload-artifact@v4")
    assert admin < generator < receipt < upload
    assert "docs/FEDERATION_HEALTH_EXECUTION.json" in health

    publisher = workflow.split("\n  publish:", 1)[1]
    assert "needs: [health, fixture]" in workflow
    assert "docs/FEDERATION_HEALTH_EXECUTION.json" in publisher
    assert "contents: write" in publisher
    assert "pull-requests: write" in publisher
    assert "actions: write" not in workflow
    # The disposable fixture still creates only its explicit Markdown sentinel.
    fixture = workflow.split("\n  fixture:", 1)[1].split("\n  publish:", 1)[0]
    assert "FEDERATION_HEALTH_EXECUTION.json" not in fixture
