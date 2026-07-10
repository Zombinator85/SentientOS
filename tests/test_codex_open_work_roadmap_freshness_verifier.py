from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_open_work_roadmap_freshness_verifier import (
    FAILED,
    NON_AUTHORITY_POSTURE,
    VERIFIED,
    dumps_report,
    render_markdown,
    verify_roadmap_text,
)


def valid_roadmap(include_1918: bool = False) -> str:
    prs = "\n".join(f"- PR #{number} consumed metadata only." for number in range(1898, 1918))
    optional = "\n- PR #1918 refreshed roadmap history." if include_1918 else ""
    return f"""# Roadmap

## Current sealed or paused areas

- `sandboxed_live_memory_commit_adapter_envelope` is terminal for the sandboxed adapter branch.
- No post-envelope implementation is authorized from that terminal envelope.
- Do not create a sandboxed readiness gate, readiness packet, readiness envelope, or repeated sandboxed gate/packet/envelope/readiness ladder.
- Future continuation requires a separate complete topology decision.
- Metadata and review evidence is not live authority.

## Recent consumed storage/operator consent and bootstrap-contract work

{prs}{optional}

## Process-hardening notes

- Bootstrap invocation drift is sealed by [`codex_bootstrap_invocation_contract.md`](codex_bootstrap_invocation_contract.md): future prompts must use only supported bootstrap flags / documented bootstrap flags, must not use unsupported `--existing-module` / `--existing-cli`, and must stop/retry bootstrap when argument parsing exits nonzero.

## Candidate next work tracks

This section lists documentation/review/test-only options for a future operator to select. It does not select or implement any candidate, does not authorize implementation, and does not grant runtime, live-memory mutation, provider invocation, network call, prompt export, host action, ledger write, glow archive, daemon action, scheduler behavior, model training, or federation authority. Each candidate requires separate operator selection.

| Candidate option | Scope if separately selected | Non-authority boundary |
| --- | --- | --- |
| Current-roadmap freshness verifier | Add or update docs/tests that check consumed-work entries and blocked-surface language stay current. | Review/test-only. Must not create runtime gates. |
| Consent-ladder index/readability consolidation | Consolidate links among existing consent/storage contracts, verifiers, and dossiers without adding a new rung. | Documentation/readability-only. |
| Next-selection packet template | Draft a template for choosing among safe docs/test-only work items without implying implementation authority. | Planning-only. Must require separate operator selection. |

## Blocked task classes

Do not select post-envelope sandboxed adapter continuation. Runtime authority is forbidden.
"""


def test_valid_current_roadmap_verifies() -> None:
    report = verify_roadmap_text(valid_roadmap(), "roadmap.md")
    assert report["verification_status"] == VERIFIED
    assert report["metadata_only"] is True
    assert report["verifier_only"] is True


def test_source_digest_and_byte_size_are_deterministic() -> None:
    text = valid_roadmap()
    report = verify_roadmap_text(text, "roadmap.md")
    assert report["source_digest"] == hashlib.sha256(text.encode()).hexdigest()
    assert report["source_byte_size"] == len(text.encode())
    assert verify_roadmap_text(text, "roadmap.md")["source_digest"] == report["source_digest"]


def test_output_json_is_deterministic() -> None:
    report = verify_roadmap_text(valid_roadmap(), "roadmap.md")
    assert dumps_report(report) == dumps_report(report)


def test_markdown_output_is_deterministic_and_escapes_pipes_newlines() -> None:
    report = verify_roadmap_text(valid_roadmap(), "roadmap.md")
    report["verification_checks"][0]["details"] = "alpha | beta\nnext"
    rendered = render_markdown(report)
    assert rendered == render_markdown(report)
    assert "alpha \\| beta<br>next" in rendered


def test_consumed_pr_markers_are_checked() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("PR #1904", "PR missing"), "roadmap.md")
    assert report["verification_status"] == FAILED
    assert "consumed_work.pr_1904" in report["violation_summary"]["violation_check_ids"]


def test_pr_1918_is_optional_info_if_not_recorded_as_consumed() -> None:
    report = verify_roadmap_text(valid_roadmap(include_1918=False), "roadmap.md")
    check = next(c for c in report["consumed_work_results"] if c["check_id"] == "consumed_work.pr_1918_optional")
    assert check["passed"] is True
    assert check["severity"] == "info"
    assert "does not mention" in check["details"]


def test_sandboxed_adapter_stop_language_is_required() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("terminal", "ongoing"), "roadmap.md")
    assert report["verification_status"] == FAILED
    assert "blocked_surface.terminal_envelope" in report["violation_summary"]["violation_check_ids"]


def test_bootstrap_invocation_contract_language_is_required() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("codex_bootstrap_invocation_contract.md", "other.md"), "roadmap.md")
    assert report["verification_status"] == FAILED
    assert "bootstrap_contract.link" in report["violation_summary"]["violation_check_ids"]


def test_unsupported_existing_module_and_cli_wording_is_required() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("--existing-module", "--old-module").replace("--existing-cli", "--old-cli"), "roadmap.md")
    assert "bootstrap_contract.unsupported_existing_module" in report["violation_summary"]["violation_check_ids"]
    assert "bootstrap_contract.unsupported_existing_cli" in report["violation_summary"]["violation_check_ids"]


def test_candidate_tracks_are_checked() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("| Next-selection packet template |", "| Other candidate |"), "roadmap.md")
    assert report["verification_status"] == FAILED
    assert "candidate_track.exact_candidate_set" in report["violation_summary"]["violation_check_ids"]


def test_candidates_must_require_separate_operator_selection() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("Each candidate requires separate operator selection.", "Each candidate can proceed."), "roadmap.md")
    assert "candidate_track.separate_operator_selection" in report["violation_summary"]["violation_check_ids"]


def test_candidates_must_be_non_authority() -> None:
    report = verify_roadmap_text(valid_roadmap().replace("does not authorize implementation", "can implement"), "roadmap.md")
    assert "candidate_track.no_implementation_authority" in report["violation_summary"]["violation_check_ids"]


def test_forbidden_authority_positive_wording_fails() -> None:
    report = verify_roadmap_text(valid_roadmap() + "\nThis roadmap authorizes runtime authority as current work.\n", "roadmap.md")
    assert report["verification_status"] == FAILED
    assert "forbidden_authority.runtime_authority" in report["violation_summary"]["violation_check_ids"]


def test_denial_forbidden_wording_does_not_falsely_fail() -> None:
    report = verify_roadmap_text(valid_roadmap() + "\nThis roadmap must not authorize runtime authority and provider invocation; both are forbidden.\n", "roadmap.md")
    assert report["verification_status"] == VERIFIED


def test_verifier_success_does_not_imply_implementation_selection() -> None:
    report = verify_roadmap_text(valid_roadmap(), "roadmap.md")
    posture = report["non_authority_posture"]
    assert report["verification_status"] == VERIFIED
    assert "not implementation selection" in posture


def test_verifier_success_does_not_imply_runtime_readiness_pr_commit_authority() -> None:
    posture = verify_roadmap_text(valid_roadmap(), "roadmap.md")["non_authority_posture"]
    for phrase in ("runtime authority", "readiness authority", "PR authority", "commit authority"):
        assert phrase in posture
    assert posture == NON_AUTHORITY_POSTURE
