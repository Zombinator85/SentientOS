# Host-local diagnostic lifecycle closure

This read-only subsystem packages one deeply validated completed diagnostic execution bundle and its matching deeply validated completed rollback bundle. The caller supplies both final bundle digests and an explicit closure time. The builder revalidates both public bundle formats before writing anything and rejects inconsistent execution, request, correlation, artifact, rollback-plan, or lifecycle identities.

## Packet custody

Packets are atomically published below an explicit external output root. Fixed paths `bundles/execution/` and `bundles/rollback/` preserve every source byte. `closure_report.json` explains the identities, times, pending-to-complete lifecycle, direct or reconciled rollback posture, historical call counts, zero closure-processing effect calls, exact mutation boundary, sibling preservation, and broader-authority posture. `summary.json`, `receipt.json`, `content_manifest.json`, and `final_manifest.json` bind exact safe membership and bytes.

Validation recursively invokes the public deep execution and rollback validators, verifies the externally bound nested digests, recomputes every cross-lifecycle relationship, and rejects duplicates, extras, symlinks, unsafe paths, substitutions, and changed bytes. It never consults current authority or the live target, so a packet remains reviewable after the source bundles and target are removed.

## Publication and non-authority boundary

Closure identity is deterministic over the two final bundle digests and explicit closure time. A cross-process lock plus atomic rename provides one publication; identical requests replay without writes, while identity, correlation, path, or pointer conflicts fail closed. The CLI provides `build`, `validate`, and deeply validated `latest-summary` commands.

The packet is historical integrity evidence only. Unkeyed digests do not prove authorship or external authenticity. Building, validating, replaying, and summarizing invoke no execution coordinator, transaction orchestrator, rollback coordinator, rollback primitive, provider, network, subprocess, shell, daemon, dashboard, control-plane, or host-mutation surface. No runtime authority scope or capability is registered.
