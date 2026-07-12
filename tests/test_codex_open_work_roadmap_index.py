from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

ROADMAP = Path("docs/development/codex_open_work_roadmap_index.md")


def _roadmap_text() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def test_recent_consent_bootstrap_and_repository_custody_consumed_work_is_indexed() -> None:
    text = _roadmap_text()

    required_markers = [
        "PR #1914",
        "PR #1915",
        "PR #1916",
        "PR #1917",
        "PR #1918",
        "PR #1919",
        "PR #1920",
        "PR #1921",
        "PR #1922",
        "Presentation boundary contract",
        "Presentation verifier initial landing",
        "Presentation verifier output-contract hardening",
        "Bootstrap invocation argument contract",
    ]

    for marker in required_markers:
        assert marker in text


def test_bootstrap_invocation_contract_note_is_preserved() -> None:
    text = _roadmap_text()

    assert "codex_bootstrap_invocation_contract.md" in text
    assert "supported bootstrap flags" in text
    assert "--existing-module" in text
    assert "--existing-cli" in text
    assert "argument parsing exits nonzero" in text


def test_sandboxed_adapter_stop_rule_is_preserved() -> None:
    text = _roadmap_text()

    blocked_phrases = [
        "sandboxed_live_memory_commit_adapter_envelope` is terminal",
        "No post-envelope implementation is authorized",
        "Do not create a sandboxed readiness gate, readiness packet, readiness envelope",
        "repeated sandboxed gate/packet/envelope/readiness ladder",
        "complete topology decision",
    ]

    for phrase in blocked_phrases:
        assert phrase in text


def test_candidate_tracks_require_separate_selection_and_are_non_authority() -> None:
    text = _roadmap_text()

    assert "Current-roadmap freshness verifier" in text
    assert "Consent-ladder index/readability consolidation" in text
    assert "Next-selection packet template" in text
    assert "does not select or implement any candidate" in text
    assert "does not authorize implementation" in text
    assert "Each candidate requires separate operator selection" in text
    assert text.count("| Current-roadmap freshness verifier |") == 0
    assert text.count("| Consent-ladder index/readability consolidation |") == 1
    assert text.count("| Next-selection packet template |") == 1


def test_roadmap_contains_no_forbidden_authority_grants() -> None:
    text = _roadmap_text().lower()

    forbidden_grants = [
        "this roadmap authorizes runtime",
        "this roadmap authorizes live-memory mutation",
        "this roadmap authorizes provider invocation",
        "this roadmap authorizes network calls",
        "this roadmap authorizes prompt export",
        "this roadmap authorizes host action",
        "this roadmap authorizes ledger writes",
        "this roadmap authorizes glow archives",
        "this roadmap authorizes daemon action",
        "this roadmap authorizes scheduler behavior",
        "this roadmap authorizes model training",
        "this roadmap authorizes federation authority",
        "this roadmap grants runtime",
        "this roadmap grants live-memory mutation",
        "this roadmap grants provider invocation",
        "this roadmap grants network calls",
        "this roadmap grants prompt export",
        "this roadmap grants host action",
        "this roadmap grants ledger writes",
        "this roadmap grants glow archives",
        "this roadmap grants daemon action",
        "this roadmap grants scheduler behavior",
        "this roadmap grants model training",
        "this roadmap grants federation authority",
    ]

    for phrase in forbidden_grants:
        assert phrase not in text

    required_denials = [
        "must not authorize runtime",
        "must not authorize storage writes",
        "must not execute actions",
        "must not grant consent truth",
        "do not create a sandboxed readiness gate",
        "metadata and review evidence only",
        "handoff readiness remains non-authority",
        "must not authorize autonomous repository mutation",
        "external codex/operator landing controls remain required",
    ]

    for phrase in required_denials:
        assert phrase in text
