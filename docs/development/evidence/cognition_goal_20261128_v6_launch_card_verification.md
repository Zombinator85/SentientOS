# Cognition campaign v6 launch-card verification

Captured: 2026-11-28 05:14 UTC
Campaign: `rootless-history-campaign-20261127000100000027`
Plan digest: `e515d86db444ed271712fde6c305f4815b0029a3c943ba5726907dd00894550c`

The repeatable CPU-only verifier is
`tools/verify_rootless_cognition_cycle_launch_card.py`. It checks the private
card mode and digest, campaign plan and implementation pins, model identity
recipe, private initial-history bundle binding, cycle IDs/seeds/environment,
cycle-27 preflight and independent reconstruction verification, source commit
ancestry, custody receipt binding, and absence of cycle output roots. It samples
GPU telemetry and reports launch gates but never loads a model.

The private report is retained in the experiment workspace, not this repository:
`sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle-launch-card-verification.json`
SHA-256: `7669679bee34b1bfd827aa3a215651bfed81734a80e943a801fd2ae305f689e4`
File mode: `0600`.

At capture, card integrity and pinned-source checks verified. GPU telemetry
reported 39% utilization and 1,717/12,288 MiB allocated, exceeding the 25%
launch ceiling. Both cycles therefore remain ineligible; operator confirmation
was absent and both cycle roots were absent. Cycle 28 also lacks its sequential
preflight and remains blocked on cycle 27 completion and chain verification.
No model was loaded, no inference ran, and no learning or authority is claimed.
The plan's independent preregistration-timing attestation remains false.

Reproduce with the workspace paths for `--card`, `--receipt`, and (optionally)
a new write-once private `--output` path. The verifier rejects an existing
output path to prevent silent report replacement.

## Sequential launch gates (verifier v2)

A follow-up review found the first verifier version did not include cycle
preflight and predecessor-chain readiness in its computed launch eligibility.
The v1 report is superseded for readiness decisions. The verifier now reports
each cycle's preflight and prior-history-chain gate separately. For later cycles
it calls the campaign's append-only chain verifier over every predecessor and
requires campaign binding, history-seed boundary, runtime-admission, and
cognition-recovery checks to pass. A missing or incomplete predecessor or
preflight is a closed gate.

The replacement private mode-0600 report is
`sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle-launch-card-verification-v3.json`
SHA-256: `61375fcc340c9e2f4b01337ba9ff626d5c31c6080c30231f99eeb9925099e17a`.
At capture (2026-11-28 05:19 UTC), cycle 27 had verified preflight and initial
history-boundary gates; cycle 28 was explicitly held closed because its
sequential preflight was not bound and cycle 27 was incomplete. GPU utilization
was 39%, above the 25% threshold, so neither cycle was eligible. No inference
was performed.
