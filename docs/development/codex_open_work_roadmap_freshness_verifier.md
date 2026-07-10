# Codex Open-Work Roadmap Freshness Verifier

`sentientos/codex_open_work_roadmap_freshness_verifier.py` is a deterministic developer-workflow metadata verifier for [`codex_open_work_roadmap_index.md`](codex_open_work_roadmap_index.md). It checks that the current roadmap still preserves consumed-work history, blocked-surface doctrine, bootstrap invocation contract wording, candidate non-authority wording, and the absence of positive authority-grant drift.

Verifier success is only roadmap freshness evidence. It is not implementation selection, runtime authority, consent, policy truth, prompt assembly, prompt export, provider invocation, network authority, live-memory mutation, host action, ledger authority, glow authority, daemon authority, scheduler authority, model-training authority, federation authority, commit authority, PR authority, or readiness authority.

## What it checks

The verifier reads a Markdown roadmap and emits a stable JSON report with these result groups:

- `consumed_work_results`: verifies required consumed PR markers from PR #1898 through PR #1917 and emits an informational PR #1918 observation when present or absent.
- `blocked_surface_results`: verifies the sandboxed live-memory commit adapter envelope remains terminal, post-envelope implementation remains blocked, sandboxed readiness gate/packet/envelope and repeated ladders remain blocked, future continuation requires a complete topology decision, and metadata/review evidence is not live authority.
- `bootstrap_contract_results`: verifies the roadmap links or names `codex_bootstrap_invocation_contract.md`, supported/documented bootstrap flags, unsupported `--existing-module` and `--existing-cli`, and the requirement to stop/retry bootstrap when argument parsing exits nonzero.
- `candidate_track_results`: verifies the current candidate set remains exactly `Current-roadmap freshness verifier`, `Consent-ladder index/readability consolidation`, and `Next-selection packet template` unless a future roadmap refresh intentionally changes the set under a new consumed-work or selection posture. Candidate wording must remain documentation/review/test-only, require separate operator selection, not authorize implementation, and not grant runtime/live-memory/provider/network/prompt-export/host/ledger/glow/daemon/scheduler/model/federation authority.
- `forbidden_authority_results`: fails on positive authorization language near forbidden surfaces while allowing denial phrases such as `must not`, `does not`, `do not`, `not authorized`, `blocked`, `forbidden`, `without authority`, or `requires separate authorization`.

## CLI usage

```bash
python scripts/verify_codex_open_work_roadmap_freshness.py --summary
```

Options:

- `--roadmap-path PATH`: roadmap Markdown to verify. Defaults to `docs/development/codex_open_work_roadmap_index.md`.
- `--output PATH`: write deterministic JSON.
- `--markdown-output PATH`: write deterministic Markdown.
- `--summary`: print a compact JSON summary to stdout.

## Exit statuses

- `0`: verification ran successfully and found no violations.
- `1`: verification ran successfully and found one or more violations.
- `2`: the roadmap path is missing or unreadable, the roadmap is empty, or JSON/Markdown output cannot be written.

## Output formats

The JSON report includes `verifier_id`, `metadata_only`, `verifier_only`, source path, SHA-256 source digest, byte size, `verification_status`, the full `verification_checks` list, grouped result lists, a `violation_summary`, and the non-authority posture.

The Markdown report contains deterministic sections for source summary, verification status, verification checks, consumed work results, blocked surface results, bootstrap contract results, candidate track results, forbidden authority results, violation summary, and non-authority posture. Table cells escape pipes and newlines for stable review rendering.

## Relationship to the roadmap candidate list

This verifier implements the `Current-roadmap freshness verifier` candidate as metadata-only review/test tooling. It does not select or implement the remaining candidate tracks, and a passing verifier does not authorize future implementation. Future work still requires separate operator selection, fresh bounded prompt text, successful bootstrap, matrix/finalizer/supervisor/PR metadata guard controls, and clean-tree landing rules.

## Updating consumed-work markers

When a new roadmap-refresh PR intentionally changes the current history, update the verifier's expected consumed-work marker list in `sentientos/codex_open_work_roadmap_freshness_verifier.py` and the focused tests in `tests/test_codex_open_work_roadmap_freshness_verifier.py` during that same bounded documentation/review/test task. The update should record why the new PR marker is part of consumed history and must preserve the non-authority posture: freshness evidence does not become consent, policy truth, runtime readiness, commit authority, PR authority, or implementation authority.
