from __future__ import annotations

import json
from pathlib import Path

from sentientos.audit_chain_gate import AuditChainVerification
from sentientos.audit_strict_status import StrictAuditInputs, classify_strict_audit_state, write_strict_audit_artifacts


def _inputs(tmp_path: Path) -> StrictAuditInputs:
    baseline = tmp_path / "logs/privileged_audit.jsonl"
    runtime = tmp_path / "pulse/audit/privileged_audit.runtime.jsonl"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text("{}\n", encoding="utf-8")
    runtime.write_text("{}\n", encoding="utf-8")
    return StrictAuditInputs(
        baseline_path=str(baseline),
        runtime_path=str(runtime),
        baseline_status="ok",
        runtime_status="ok",
        baseline_errors=[],
        runtime_errors=[],
        runtime_error_kind="unknown",
        runtime_error_examples=[],
        suggested_fix="run: make audit-repair",
        environment_issues=[],
    )


def _chain(*, status: str, recovery_state: dict[str, object] | None = None) -> AuditChainVerification:
    return AuditChainVerification(
        status=status,
        created_at="2026-01-01T00:00:00Z",
        break_count=0 if status == "ok" else 1,
        checked_files=2,
        recovery_state=recovery_state,
    )


def test_classify_healthy_strict(tmp_path: Path) -> None:
    bucket, reasons, readiness = classify_strict_audit_state(
        inputs=_inputs(tmp_path),
        audit_chain=_chain(status="ok", recovery_state={"history_state": "intact_trusted"}),
    )
    assert bucket == "healthy_strict"
    assert readiness == "acceptable"
    assert reasons


def test_classify_healthy_reanchored(tmp_path: Path) -> None:
    bucket, _reasons, readiness = classify_strict_audit_state(
        inputs=_inputs(tmp_path),
        audit_chain=_chain(
            status="reanchored",
            recovery_state={
                "history_state": "reanchored_continuation",
                "checkpoint_id": "reanchor:abcd",
                "continuation_descends_from_anchor": True,
            },
        ),
    )
    assert bucket == "healthy_reanchored"
    assert readiness == "acceptable"


def test_classify_preserved_nonblocking(tmp_path: Path) -> None:
    bucket, _reasons, readiness = classify_strict_audit_state(
        inputs=_inputs(tmp_path),
        audit_chain=_chain(
            status="broken",
            recovery_state={
                "history_state": "broken_preserved",
                "checkpoint_id": "reanchor:abcd",
                "continuation_descends_from_anchor": False,
            },
        ),
    )
    assert bucket == "broken_preserved_nonblocking"
    assert readiness == "acceptable"


def test_classify_blocking_without_checkpoint(tmp_path: Path) -> None:
    bucket, _reasons, readiness = classify_strict_audit_state(
        inputs=_inputs(tmp_path),
        audit_chain=_chain(status="broken", recovery_state={"history_state": "broken_preserved", "checkpoint_id": None}),
    )
    assert bucket == "blocking_chain_break"
    assert readiness == "blocking"


def test_artifacts_emit_deterministic_digest(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    chain = _chain(status="ok", recovery_state={"history_state": "intact_trusted"})
    first = write_strict_audit_artifacts(tmp_path, inputs=inputs, audit_chain=chain, verify_result={"status": "passed", "exit_code": 0})
    second = write_strict_audit_artifacts(tmp_path, inputs=inputs, audit_chain=chain, verify_result={"status": "passed", "exit_code": 0})
    assert first["bucket"] == "healthy_strict"
    assert second["bucket"] == "healthy_strict"

    digest_one = json.loads((tmp_path / "glow/contracts/final_strict_audit_digest.json").read_text(encoding="utf-8"))
    digest_two = json.loads((tmp_path / "glow/contracts/final_strict_audit_digest.json").read_text(encoding="utf-8"))
    assert digest_one["strict_audit_digest"] == digest_two["strict_audit_digest"]
