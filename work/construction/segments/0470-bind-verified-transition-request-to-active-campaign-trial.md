# Sequence 470 — Bind the verified transition request to the active campaign trial

## Source increment

Sequence 470 began from verified main `360ac720b194412518188bd5526f430a3b70185d`. PR #2443 added canonical campaign binding, but review after merge found that its first implementation paired a caller-supplied request identifier with the live active trial without proving the exact transition request declared that trial. The returned label overstated what the receipt established.

PR #2444 corrected that integration while preserving PR #2443's merge history. The resident transition operator now projects the optional `campaign_trial_id` from the exact request's stage evidence into verified receipt schema v2, under the request digest. The campaign observer exposes the declared identifier while keeping the receipt's own binding status explicitly `not_established_by_transition_receipt`. The canonical campaign owner accepts a binding only when the declared identifier matches both the requested trial and current digest-verified active campaign state. Stage approval remains separate and live transition-owner revalidation remains required.

The projection and binding are observational. They do not select approval, grant authority, process a packet from the planning API, advance campaign state, or authorize execution.

## Verification and merge

The first PR #2444 candidate, `b90654455270be9364d0fe980fb470f2ff776099`, failed source validation because the test projection fixture still emitted the v1 schema and omitted the declared trial identifier. The fixture and receipt assertions were corrected in the follow-up commit, producing exact candidate `d15cbf2444e85f108f5723e1a61259746f753b3c`.

On that exact candidate, CI run #39308509382 passed source validation, integrated lifecycle, canonical planning/execution separation, transition receipt projection, receipt-to-campaign planning without execution, self-check, Mypy, pytest with coverage, documentation linkcheck, and Helm. Required Quality Gate #39308511865 passed strict audits with actual Administrator authority, exact acceptance binding, hosted privileged finalization, and the separate pre-publication metadata guard. Codex CI #39308509453, Docker #39308509440, Release #39308509070, Invariant Tests #39308509160, Gradient null regression #39308509297, and Lint Benchmark #39308509326 also passed. An earlier candidate run #39308509157 failed during hosted pre-commit-state reconstruction and did not pass finalization; it is not counted as a successful check on the corrected candidate.

PR #2444 merged by regular merge with expected head `d15cbf2444e85f108f5723e1a61259746f753b3c`. Main is `9988e3a0c0fbf35b14f8f5b95ea84752d889e155`, tree `4c367f215a39532925135d4abfa8a90911b3638a`, with ordered parents `b457641498e4eaaa04660c047fb4f42ff4b7ee2a` and `d15cbf2444e85f108f5723e1a61259746f753b3c`. Main was independently read back at that commit. No separate post-merge workflow runs were returned for merge commit `9988e3a0c0fbf35b14f8f5b95ea84752d889e155`.

## Next dependency and limits

Next, connect the daemon's explicit read-only transition planner to the canonical campaign owner's request-declared active-trial binding, preserving per-stage approval separation, exact receipt and live-journal validation, and terminal interruption handling. Keep planning separate from packet processing and execution.

Historical test provenance remains `INTEGRITY_BROKEN`; sequence-286 loss remains explicit. No production inference or campaign execution is enabled. Protected and stale workspaces were not modified.
