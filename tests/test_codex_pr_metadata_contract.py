import pytest

from sentientos.codex_pr_metadata_contract import CodexPRValidationRollup, build_pr_body_from_rollup, verify_pr_metadata

pytestmark = pytest.mark.no_legacy_skip


def _full_body() -> str:
    return """
## Full command matrix results
ok
## Matrix runner --summary result
ok
## Matrix runner --output result/path
artifacts/matrix/latest.json
## Targeted mypy result
ok
## Baseline result
ok
## Docs build result
ok
## Prompt-boundary result
ok
## Strict audit result
ok
## Immutability verifier result
ok
## Unresolved risks
none
"""


def test_1740_nonconforming_title_fails_verification() -> None:
    res = verify_pr_metadata(pr_title="bad title", pr_body=_full_body())
    assert res.status == "codex_pr_metadata_contract_incomplete"
    assert res.title_ok is False


def test_1740_body_with_only_local_tests_fails_verification() -> None:
    res = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body="local tests only")
    assert res.status == "codex_pr_metadata_contract_incomplete"
    assert res.local_only_validation_claim_detected is True


def test_1740_body_with_full_validation_rollup_passes() -> None:
    res = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_full_body())
    assert res.status == "codex_pr_metadata_contract_ready"


def test_1740_exact_intended_commit_title_passes() -> None:
    title = "[codex:developer] add verifier"
    res = verify_pr_metadata(pr_title=title, pr_body=_full_body(), intended_commit_title=title)
    assert res.status == "codex_pr_metadata_contract_ready"


def test_1740_mismatched_intended_commit_title_fails() -> None:
    res = verify_pr_metadata(
        pr_title="[codex:developer] add verifier",
        pr_body=_full_body(),
        intended_commit_title="[codex:developer] other",
    )
    assert res.status == "codex_pr_metadata_contract_incomplete"
    assert res.intended_commit_title_ok is False


def test_builder_includes_all_required_sections() -> None:
    body = build_pr_body_from_rollup(
        CodexPRValidationRollup(
            full_command_matrix_results="a",
            matrix_runner_summary_result="b",
            matrix_runner_output_result_path="c",
            targeted_mypy_result="d",
            baseline_result="e",
            docs_build_result="f",
            prompt_boundary_result="g",
            strict_audit_result="h",
            immutability_verifier_result="i",
            unresolved_risks="j",
        )
    )
    for marker in (
        "Full command matrix results",
        "Matrix runner --summary result",
        "Matrix runner --output result/path",
        "Targeted mypy result",
        "Baseline result",
        "Docs build result",
        "Prompt-boundary result",
        "Strict audit result",
        "Immutability verifier result",
        "Unresolved risks",
    ):
        assert marker in body


def _solo_body() -> str:
    return """
## Validation evidence
Validation profile: solo
Exhaustive matrix disposition: not_requested_for_solo_profile
Targeted mypy result: passed
Baseline result: passed
Docs build result: passed
Prompt-boundary result: passed
Strict audit result: passed
Immutability verifier result: passed
Unresolved risks: none
"""


def test_solo_profile_metadata_verification_uses_explicit_profile() -> None:
    result = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_solo_body(), validation_profile="solo")
    assert result.status == "codex_pr_metadata_contract_ready"


def test_solo_profile_omission_and_success_contradiction_fail() -> None:
    missing = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_solo_body().replace("not_requested_for_solo_profile", "not recorded"), validation_profile="solo")
    contradictory = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_solo_body() + "\nMatrix passed.\n", validation_profile="solo")
    assert missing.status == "codex_pr_metadata_contract_incomplete"
    assert contradictory.status == "codex_pr_metadata_contract_incomplete"


def test_profile_is_not_inferred_from_body_prose() -> None:
    result = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_solo_body(), validation_profile="exhaustive")
    assert result.status == "codex_pr_metadata_contract_incomplete"


def test_exhaustive_markers_remain_required() -> None:
    result = verify_pr_metadata(pr_title="[codex:developer] ok", pr_body=_solo_body(), validation_profile="exhaustive")
    assert "full command matrix results" in result.missing_body_markers
