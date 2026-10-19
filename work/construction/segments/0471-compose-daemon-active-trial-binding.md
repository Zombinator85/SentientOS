# Sequence 471 — Compose daemon planning with active-trial binding

## Source increment

Starting from verified main `fd9f44f9079c75034f9f6a62bed4777f52d76f77`, this increment adds `RuntimeMaintenanceSurfaces.plan_production_self_reflection_transition_active_trial_binding(request_id)`. It obtains the canonical read-only verified transition plan, fails closed unless the plan is ready and contains the request-declared campaign trial, then passes that exact plan and identifier to `ProductionSelfReflectionCampaign.bind_verified_transition_plan_to_active_trial`.

The campaign owner reprojects the request plan and revalidates the active digest-verified campaign state and trial under its lock. The daemon API does not accept a caller-selected trial ID, process an operator request, select approval, advance progress, grant authority, or execute a stage. Tests assert the request-declared identifier is forwarded and that missing declaration prevents binding.

## Verification and merge

Exact candidate `bfb25ad31dcd24dec2ec2e775ed7bf68ac49b8df` passed CI #39310728482, including source validation, the integrated lifecycle, canonical planning/execution separation, transition-receipt checks, self-check, Mypy, pytest with coverage, documentation linkcheck, and Helm. Required Quality Gate #39310728321 passed strict audits with actual Administrator authority, exact acceptance binding, hosted privileged finalization, and the separate pre-publication metadata guard. Codex CI #39310728489, Docker #39310728513, Release #39310728348, Invariant Tests #39310728453, Gradient null regression #39310728329, and Lint Benchmark #39310728467 also passed.

PR #2446 merged by regular merge with expected head `bfb25ad31dcd24dec2ec2e775ed7bf68ac49b8df`. Main is `19f202bd0f44352599f0750f58133407256d610a`, tree `689b126c098ca7798626901739177e9003c21ca6`, with ordered parents `fd9f44f9079c75034f9f6a62bed4777f52d76f77` and `bfb25ad31dcd24dec2ec2e775ed7bf68ac49b8df`. Main was independently read back at that commit. No separate post-merge workflow runs were returned for merge commit `19f202bd0f44352599f0750f58133407256d610a`.

## Next dependency and limits

Next, trace the separate stage-approval artifact contract and determine whether the daemon can produce a read-only stage-admission plan from an explicitly supplied approval while preserving live owner admission as the sole execution boundary. Do not have the planner select or mint approvals.

Historical test provenance remains `INTEGRITY_BROKEN`; sequence-286 loss remains explicit. No production inference or campaign execution is enabled. Protected and stale workspaces were not modified.
