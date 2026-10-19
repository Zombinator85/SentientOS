# Sequence 428 — Report audit issues accurately in the verifier summary

**Construction status: source candidate pending hosted verification.** This bounded source change follows the verified sequence 427 merge and the actual Nightly Audit Integrity output recorded in sequence 427.

The nightly audit log surfaced an optional `support_log.jsonl` previous-hash mismatch, then printed “No mismatches” because the verifier used only repair counters to decide whether to emit that sentence. This was misleading: no repair action had occurred, but an issue existed. The check also needs to avoid a blanket “No mismatches” statement if the independently computed audit-chain status is not healthy.

Sequence 428 changes the summary condition to require zero file/path issues, zero fix/quarantine/unrecoverable counts, and an `ok` audit-chain result. The strict privileged-audit classification, return codes, repair behavior, audit inputs, and log contents are unchanged. A focused regression test covers an issue, repair activity, unhealthy chain status, and the clean case.

Local verification: Python compilation passed for the changed module and test; direct assertions of the pure summary predicate passed for all four states; `git diff --check` passed. Ruff is unavailable in this sandbox. Canonical pytest was not run locally; exact-candidate hosted CI verification is pending.

Source base: verified main `457b0555f8e63d1951104c8db651e12500a8aa77`, tree `7be03edf9023dd97286e1b2e6fd3c59028883803`, the regular merge of PR #2395 preserving sequence 427's candidate tree. Sequence 428 does not alter any audit record, baseline, strict gate, privilege, workflow authority, or production behavior. Scheduled Federation Health and the two next nightly executions on this newest main have not yet occurred at this evidence cut; their results remain pending rather than presumed. All previous construction evidence remains append-only.
