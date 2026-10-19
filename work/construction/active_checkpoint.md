# Active construction checkpoint

## Latest verified main

PR #2446 added a distinct daemon API to compose the read-only verified transition plan with the canonical campaign owner's active-trial binding. It takes the trial identifier only from the exact request's verified receipt projection, fails closed when the plan or declaration is absent, and delegates to the owner to revalidate the plan and current digest-verified campaign state. Planning does not process requests or execute a stage.

Exact candidate `bfb25ad31dcd24dec2ec2e775ed7bf68ac49b8df` passed CI, source validation, Mypy, pytest with coverage, docs linkcheck, Helm, Codex CI, Docker, release, invariants, gradient regression, lint, hosted Administrator strict audits, exact acceptance binding, privileged finalizer, and separate metadata guard. PR #2446 merged regularly as `19f202bd0f44352599f0750f58133407256d610a`, tree `689b126c098ca7798626901739177e9003c21ca6`. No separate post-merge workflow run for this merge SHA was returned.

## Open evidence boundaries

- Scheduled Federation Health run #39279382936 completed its privileged update on a pre-merge main head and uploaded execution-bound evidence; its publication job failed because repository policy prohibits Actions-token PR creation. The workflow already declares `contents:write` and `pull-requests:write`. No scheduled execution on current main has been observed.
- Nightly Self Check #39235681245 and Nightly Audit Integrity #39228761152 succeeded on older heads. The remaining automated publication repair needs an authorized least-privilege GitHub App integration or administrator-approved repository setting.
- Next developmental dependency: trace the separate stage-approval artifact contract and determine whether a read-only stage-admission plan can consume an explicitly supplied approval while leaving live owner admission as the execution boundary. The planner must not select or mint approvals.
- Historical test provenance remains `INTEGRITY_BROKEN`; sequence-286 loss remains explicit. Production A→B→A still requires commissioned identities, distinct serving approvals, operator preregistration, and live execution.
- Sequences 382–386 and stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.

Latest verified main: `19f202bd0f44352599f0750f58133407256d610a`, tree `689b126c098ca7798626901739177e9003c21ca6`
Latest construction segment: `work/construction/segments/0471-compose-daemon-active-trial-binding.md`
Latest segment SHA-256: 18c393d1f58fabe94231db4895b0529dc4ca8b3e69ee7c5935819d37fbf0655b
Sequence: 471 (daemon planning composes request-declared active-trial binding; no separate post-merge workflow or current-main scheduled Federation Health has been observed)
