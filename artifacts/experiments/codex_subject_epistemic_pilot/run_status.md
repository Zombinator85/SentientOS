# Codex-subject epistemic pilot run status

Protocol `codex_epistemic_proposition_correction_pilot_20261031_01` was
preregistered before any model responses. It contains 12 prompts: four
PersistentEpistemicStateOwner proposition histories, each tested in original,
corrected, and corrected-state pressure-only conditions. The held-out answer
key is stored separately and was not passed to Codex CLI.

Three complete attempts were recorded without overwriting earlier reports.
Every slot is `failed_inference`; no CLI session id and no candidate response
were captured. Attempt 1 exited 2 because the CLI rejected an unsupported option
(`--ask-for-approval`, absent from the installed `codex exec --help`); this was
removed. Attempts 2 and 3 exited 1 with empty stdout and no session ids. Their
raw stderr was not retained by the initial runner revision; exact stderr
hashes remain in the reports. The ChatGPT login check passed, and attempt 3
included the managed proxy and CA environment. The root cause of those two
failures therefore remains unresolved.

All three scoring reports are `insufficient` across all 12 slots. These are
transport/CLI execution failures, not model answers or cognitive outcomes.
No successful model observation is claimed. The model slug was pinned as
`gpt-6-astra`, reasoning effort `high`, and Codex CLI version
`codex-cli 0.159.0-alpha.3`; this CLI does not expose a provider build id.

The reports preserve the failed attempt digests and preregistration binding.

## Writable Codex home diagnostic

A fourth diagnostic run used a private mode-0700 workspace directory as
`CODEX_HOME`, with `auth.json` symlinked to the existing read-only login file;
the credential was not copied. This removed the read-only-home startup error
and the CLI initialized its local state, but the run did not return from its
first invocation. The wrapper produced no structured observation report,
stdout, stderr, session id, or captured response. It remained active beyond the
runner's 180-second per-call timeout and was interrupted after more than six
minutes. The private runtime directory and its generated state files are
preserved separately in `/workspace` for provenance; they are not treated as
model responses. The state does not establish whether the prompt reached the
model, so this attempt is indeterminate and contributes no scored observation.

The held-out answer key was not supplied to the Codex CLI in any attempt.
Three complete attempt reports score `insufficient`; the interrupted fourth
attempt has no score report. No cognitive outcome is claimed.

## Landing-validation history

A prior explicitly exhaustive 135-lane validation attempt ended `matrix_failed`
with five required lane failures. `governed_local_model_invocation_tests` was
interrupted after reproducing the environment hang. The independently
reproduced failures were
`test_reconciliation_rejects_reserved_directory_mode_change_before_delete`
in `host_local_diagnostic_lifecycle_closure_tests` and
`test_admission_ledger_refuses_symlinked_parent_custody` in
`resident_developmental_cognition_tests`. `strict_audits` and
`audit_immutability` both reported that Administrator access is required.
Targeted mypy, the mypy baseline, documentation build, prompt-boundary checks,
and the codex landing gate test lane passed. These failed results remain
preserved in the external validation evidence custody bundle; they are not
reclassified as passing by the subsequent solo profile.

The custody archive is
`/tmp/sentientos-evidence-custody/codex-subject-pilot-20261030.tar.gz`;
SHA-256:
`205baab88a5915b27ba83df63cf94a11fc79c6811290fb6bb8b73966d8bddbaf`.
Its detached custody-manifest SHA-256 is
`27f8e640acb154d7f25beb73d44ca4a854968c28d20615f5ea3e0a0c11b0d20f`.
The bundle contains generated validation provenance, both versions of the run
index, the three complete failed pilot reports and their scores, and the
failed exhaustive matrix/finalizer evidence. It excludes the protocol,
answer key, preregistration, and Codex runtime state.

## Recovery-runner implementation validation

The recoverability change checkpoints each slot atomically. On resume, an
already captured slot is retained; a slot that was in flight at interruption
is recorded as `interrupted_unknown` and is never called again. Remaining slots
can proceed, while scoring still requires a complete twelve-slot report.

The new recovery test initially failed because its fake-CLI interruption hook
assumed a different argv position. That failure and its run provenance are
preserved in external custody. The hook was corrected; all 14 focused tests
then passed in two complete runs, including the runner's interrupted-checkpoint
resume test. One solo-finalizer attempt separately caught a mypy narrowing issue
in checkpoint validation; the issue was fixed and targeted mypy now passes.

The accepted 14-node test provenance is copied under `validation/` and is
bound by this task's acceptance manifest. Its chain includes the preceding
failed test run, which is preserved rather than discarded. External custody
for the generated test-run files and finalizer diagnostics is
`/tmp/sentientos-evidence-custody/solo-finalizer-validation-20261030.tar.gz`;
SHA-256:
`f8e0e390a96085385f4ae95ffcdf4f5e0f3fe1c4cbc18b72f058759972bc5c90`.
The detached manifest SHA-256 is
`60a5fd55e16cdf02da22bbb2d9d1803d3df5c3d0dadb81f6e0dc00458384327e`.

The task acceptance manifest now references the sealed validation copy at
`validation/test_run_provenance.json` rather than the mutable global Glow run
index. That copy binds repository SHA `4bb252953d8b92f16d238d2eeee696360ce376a2`
and records 14 selected nodes, 14 passed, and zero failed. The validator
returned `task_acceptance_ready`. Its provenance digest is
`sha256:2bf34b0f6349c28ba94c4bbe4ed2474699a2d3be3cc4af9a2008ea83dc184314`.
The three preceding run records and their hash-chain links are retained beside
it; the first run's one failure remains visible and is not overwritten.

The separately preserved solo-finalizer diagnostics are in
`/tmp/sentientos-evidence-custody/solo-finalizer-validation-20261030.tar.gz`
(SHA-256 `f8e0e390a96085385f4ae95ffcdf4f5e0f3fe1c4cbc18b72f058759972bc5c90`).
This includes the first recovery-test failure, both successful 14-node test
runs, and solo-finalizer reports showing the caught typing issue and later
path-binding diagnostics. It excludes the answer key and Codex runtime state.
