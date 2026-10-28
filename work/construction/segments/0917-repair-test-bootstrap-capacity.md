# Sequence 917: repair test bootstrap dependency and temp storage handling

The runner now bootstraps canonical minimal harness dependencies even when an editable install exists but an import is missing. Before pip runs, it checks temp free space: below 512 MiB it uses ignored repository-local `.codex-tmp`; if both locations are low it stops before invoking pip with an explicit storage error. Administrator checks, privilege requirements, and the minimal-only install boundary remain intact.

On verified main `7846e3006a8d3045239129a3ea6a7f923e4ce645` / `41047eea22b7422b47bdfb16bfa8aae51475be99`, the focused regression selection passed 20 tests with 3 existing skips and no failures. Exact task acceptance returned `task_acceptance_ready`; `make docs` generated 617 pages. Continuation custody verified all 916 predecessor sequences. Targeted mypy reports the existing `Path | None` unlink error only.

Test provenance run `92d3ad30255f4a29b1ec2e272518d0bf` is SHA-256 `5de059ff59a389336d7fc1190207d6d638226ea31553fd0afd4e6ba094cb2d5a` and is preserved at `work/construction/evidence/0917-test-run-provenance.json`. Exact acceptance output is preserved at `work/construction/evidence/0917-task-acceptance-result.json`. Sequence evidence: `work/construction/evidence/0917-repair-test-bootstrap-capacity.json`.
