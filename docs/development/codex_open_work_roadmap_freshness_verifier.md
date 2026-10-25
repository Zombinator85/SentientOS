# Codex Open-Work Roadmap Freshness Verifier

`sentientos/codex_open_work_roadmap_freshness_verifier.py` is a deterministic developer-workflow metadata verifier for [`codex_open_work_roadmap_index.md`](codex_open_work_roadmap_index.md) and the consumed-history archive it declares. It checks archived history for consumed-work markers and stable controls, while checking current next-work options only in the active compact index. The report binds the exact bytes of both inputs.

Verifier success is only roadmap freshness evidence. It is not implementation selection, runtime authority, consent, policy truth, prompt assembly, prompt export, provider invocation, network authority, live-memory mutation, host action, ledger authority, glow authority, daemon authority, scheduler authority, model-training authority, federation authority, commit authority, PR authority, or readiness authority.

## What it checks

The verifier reads a Markdown roadmap and emits a stable JSON report with these result groups:

- `consumed_work_results`: verifies required consumed PR markers from PR #1898 through PR #1922. PR #1918 is no longer optional or informational; PR #1918 through PR #1922 must all be recorded as consumed roadmap/freshness-verifier/repository-mutation custody history.
- `blocked_surface_results`: verifies the sandboxed live-memory commit adapter envelope remains terminal, post-envelope implementation remains blocked, sandboxed readiness gate/packet/envelope and repeated ladders remain blocked, future continuation requires a complete topology decision, and metadata/review evidence is not live authority.
- `bootstrap_contract_results`: verifies the roadmap links or names `codex_bootstrap_invocation_contract.md`, supported/documented bootstrap flags, unsupported `--existing-module` and `--existing-cli`, and the requirement to stop/retry bootstrap when argument parsing exits nonzero.
- `candidate_track_results`: verifies the active index preserves its canonical available-next-work options, selection rules, and root authority boundaries. Historical candidate tables in the archive are not interpreted as current options.
- `repository_mutation_custody_results`: verifies the roadmap records the freshness verifier as already implemented/consumed, repository-mutation custody through PR #1922 as consumed, autonomous repository mutation as blocked, handoff readiness as non-authority, and external Codex/operator landing controls as required.
- `forbidden_authority_results`: fails on positive authorization language near forbidden surfaces, including autonomous repository staging, committing, branch mutation, pushing, PR creation, runtime proposal adoption, evidence-to-authority escalation, and repository authority, while allowing denial phrases such as `must not`, `does not`, `do not`, `not authorized`, `blocked`, `forbidden`, `without authority`, or `requires separate authorization`.

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
- `2`: the active roadmap or its declared sibling archive is missing, unreadable, empty, or ambiguously referenced, or JSON/Markdown output cannot be written.

## Output formats

The JSON report includes `verifier_id`, `metadata_only`, `verifier_only`, source path, a SHA-256 digest of a canonical manifest containing both input file digests, the two input records in `source_inputs`, `verification_status`, the full `verification_checks` list, grouped result lists, a `violation_summary`, and the non-authority posture.

The Markdown report contains deterministic sections for source summary, verification status, verification checks, consumed work results, blocked surface results, bootstrap contract results, candidate track results, forbidden authority results, violation summary, and non-authority posture. Table cells escape pipes and newlines for stable review rendering.

## Relationship to the roadmap candidate list

This verifier was implemented by the consumed `Current-roadmap freshness verifier` candidate as metadata-only review/test tooling. The active index is the source for current next-work options; its archive preserves consumed history without making archived options current again. A passing verifier does not select work or authorize implementation. Future work still requires the roadmap's separate selection rules, fresh bounded prompt text, successful bootstrap, matrix/finalizer/supervisor/PR metadata guard controls, and clean-tree landing rules.

## Updating consumed-work markers

When a roadmap-refresh PR adds consumed history, update the archive and the verifier's expected consumed-work marker list in `sentientos/codex_open_work_roadmap_freshness_verifier.py` with focused tests in `tests/test_codex_open_work_roadmap_freshness_verifier.py`. Keep current options in the active index and preserve the non-authority posture: freshness evidence does not become consent, policy truth, runtime readiness, commit authority, PR authority, or implementation authority.
