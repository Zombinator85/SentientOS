"""Tests for the GenesisForge autonomous capability expansion pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon
from sentientos.codex_healer import RecoveryLedger
from sentientos.genesis_forge import (
    AdoptionRite,
    CovenantVow,
    DaemonManifest,
    ForgeEngine,
    GenesisForge,
    NeedSeer,
    SpecBinder,
    TelemetryStream,
    TrialRun,
)


@pytest.fixture(autouse=True)
def _codex_startup(codex_startup: None) -> None:
    yield


def _review_board(_: object, __: object) -> bool:
    return True


def test_needseer_detects_unhandled_stream(tmp_path: Path) -> None:
    telemetries = [
        TelemetryStream(
            name="vision_bus",
            capability="vision_input",
            description="Camera frames from sanctuary sensors",
            handled_by=frozenset(),
            sample_payload={"frames": 1},
        )
    ]
    vows = [
        CovenantVow(
            capability="vision_input",
            description="Every camera input must be witnessed",
        )
    ]
    seer = NeedSeer(daemons=[DaemonManifest("audio_daemon", frozenset({"audio_input"}))])
    needs = seer.scan(telemetries, vows)
    assert [need.capability for need in needs] == ["vision_input"]

    engine = ForgeEngine(existing_daemons=[DaemonManifest("audio_daemon", frozenset({"audio_input"}))])
    proposal = engine.draft(needs[0])
    assert proposal.proposed_spec["lineage"]["provenance"] == "GenesisForge"
    assert proposal.blueprint.testing_requirements == [
        "acknowledge_capability",
        "emit_success_status",
        "record_provenance_GenesisForge",
    ]


def test_trialrun_detects_malformed_handler() -> None:
    need = NeedSeer().scan(
        [TelemetryStream("vision", "vision_input", "camera", frozenset(), {"frames": 3})],
        [CovenantVow("vision_input", "camera vow")],
    )[0]
    engine = ForgeEngine()
    proposal = engine.draft(need)

    # Replace handler with malformed implementation.
    def bad_handler(_: object) -> dict[str, object]:
        return {"status": "error"}

    proposal.blueprint.handler = bad_handler
    report = TrialRun().execute(proposal.blueprint)
    assert not report.passed
    assert "capability" in report.failures[0]


def test_lineage_records_provenance(tmp_path: Path) -> None:
    telemetry = [
        TelemetryStream(
            name="vision_stream",
            capability="vision_input",
            description="Camera frames",
            handled_by=frozenset(),
            sample_payload={"frames": 5},
        )
    ]
    vows = [CovenantVow("vision_input", "Cameras must be witnessed")]

    lineage_root = tmp_path / "lineage"
    covenant_root = tmp_path / "covenant"
    live_mount = tmp_path / "live"
    codex_index = tmp_path / "codex.json"
    ledger_path = tmp_path / "ledger.jsonl"

    seer = NeedSeer()
    engine = ForgeEngine()
    integrity = IntegrityDaemon(tmp_path)
    trial = TrialRun()
    binder = SpecBinder(lineage_root=lineage_root, covenant_root=covenant_root)
    adoption = AdoptionRite(
        live_mount=live_mount,
        codex_index=codex_index,
        review_board=_review_board,
    )
    ledger = RecoveryLedger(ledger_path)
    forge = GenesisForge(
        need_seer=seer,
        forge_engine=engine,
        integrity_daemon=integrity,
        trial_run=trial,
        spec_binder=binder,
        adoption_rite=adoption,
        ledger=ledger,
    )

    outcomes = forge.expand(telemetry, vows)
    assert outcomes and outcomes[0].status == "adopted"

    lineage_entries = [json.loads(line) for line in (lineage_root / "lineage.jsonl").read_text().splitlines()]
    assert lineage_entries[0]["provenance"] == "GenesisForge"

    ledger_lines = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert any(entry["status"] == "GenesisForge event" for entry in ledger_lines)

    codex_payload = json.loads(codex_index.read_text())
    assert codex_payload[0]["provenance"] == "GenesisForge"


def test_prevents_overwriting_existing_daemon(tmp_path: Path) -> None:
    telemetry = [
        TelemetryStream(
            name="vision_stream",
            capability="vision_input",
            description="Camera frames",
            handled_by=frozenset(),
        )
    ]
    vows = [CovenantVow("vision_input", "camera vow")]

    lineage_root = tmp_path / "lineage"
    covenant_root = tmp_path / "covenant"
    live_mount = tmp_path / "live"
    codex_index = tmp_path / "codex.json"
    ledger_path = tmp_path / "ledger.jsonl"

    binder = SpecBinder(lineage_root=lineage_root, covenant_root=covenant_root)
    # Pre-create a daemon file to force an overwrite attempt.
    existing = covenant_root / "daemons" / "VisionInputGenesisDaemon.json"
    existing.write_text("{}", encoding="utf-8")

    forge = GenesisForge(
        need_seer=NeedSeer(),
        forge_engine=ForgeEngine(),
        integrity_daemon=IntegrityDaemon(tmp_path),
        trial_run=TrialRun(),
        spec_binder=binder,
        adoption_rite=AdoptionRite(
            live_mount=live_mount,
            codex_index=codex_index,
            review_board=_review_board,
        ),
        ledger=RecoveryLedger(ledger_path),
    )

    outcomes = forge.expand(telemetry, vows)
    assert outcomes[0].status == "failed"
    assert isinstance(outcomes[0].details["error"], str)
    # Original file remains untouched.
    assert existing.read_text(encoding="utf-8") == "{}"
