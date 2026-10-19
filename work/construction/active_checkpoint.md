# Active construction checkpoint

## Latest verified main

PR #2443 introduced canonical binding between a verified transition plan and active campaign trial state. Post-merge review found that the initial implementation paired caller request and trial identifiers without proving the exact request declared the trial. PR #2444 corrected the claim and binding: the resident transition receipt now carries an optional request-digest-bound `campaign_trial_id` in schema v2, and canonical campaign binding requires that declared value to match the requested trial and live digest-verified active campaign state.

PR #2444 merged regularly as `9988e3a0c0fbf35b14f8f5b95ea84752d889e155`, tree `4c367f215a39532925135d4abfa8a90911b3638a`. Exact candidate `d15cbf2444e85f108f5723e1a61259746f753b3c` passed CI, source validation, Mypy, pytest with coverage, docs linkcheck, Helm, Codex CI, Docker, release, invariants, gradient regression, lint, hosted Administrator strict audits, exact acceptance binding, privileged finalizer, and the separate metadata guard. Earlier candidate failures are preserved in sequence 470 evidence and were corrected before the merge. No separate post-merge workflow run for `9988e3a0c0fbf35b14f8f5b95ea84752d889e155` was returned during verification.

## Open evidence boundaries

- Scheduled Federation Health run #39279382936 completed its privileged update on a pre-merge main head and uploaded execution-bound evidence; its publication job failed because repository policy prohibits Actions-token PR creation. The workflow already declares `contents:write` and `pull-requests:write`. No scheduled execution on current main has been observed.
- Nightly Self Check #39235681245 and Nightly Audit Integrity #39228761152 succeeded on older heads. The remaining automated publication repair needs an authorized least-privilege GitHub App integration or administrator-approved repository setting.
- Next developmental dependency: connect the daemon's explicit read-only transition planner to canonical request-declared active-trial binding while preserving separate approvals, exact receipt and live-journal verification, and terminal interruption handling. No campaign executor is enabled.
- Historical test provenance remains `INTEGRITY_BROKEN`; sequence-286 loss remains explicit. Production A→B→A still requires commissioned identities, distinct serving approvals, operator preregistration, and live execution.
- Sequences 382–386 and stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.

Latest verified main: `9988e3a0c0fbf35b14f8f5b95ea84752d889e155`, tree `4c367f215a39532925135d4abfa8a90911b3638a`
Latest construction segment: `work/construction/segments/0470-bind-verified-transition-request-to-active-campaign-trial.md`
Latest segment SHA-256: ff0a96aad33ec7c9952125fe148aaf3c80903d9f0475d9eec1f595ef01b9f18e
Sequence: 470 (request-declared trial identity is digest-bound; no separate post-merge workflow run or current-main scheduled Federation Health has been observed)
