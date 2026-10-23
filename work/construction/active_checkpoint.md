# Active construction checkpoint

## Current verified state — sequence 609

Sequences 591–600 establish durable planning and epistemic evidence rules: plans are bound to execution, and stale, foreign, or withdrawn support cannot drive mutation or reactivate after recovery. Sequences 601–606 traced Federation Health's local snapshot boundary, hardened relay parsing and transport framing, and verified bounded relay integration. Sequences 607–608 implemented and verified bounded incremental SSE log consumption. Sequence 609 closes an in-place truncation recovery gap.

Latest verified main: `9971c16dcc3e184958419f830aff339d645d6f20`, tree `f6201ff99694da8b26f01c36d3ea07acbc3e7fde`
Latest construction segment: `work/construction/segments/0609-incremental-stream-truncation-recovery.md`
Latest segment SHA-256: b1de5f5b31eac25649fe031df146cfbb733114424f759992cfc6b840af99b0d0
Sequence: 609 (in-place truncation recovery)

The stream API reads fixed-size chunks, emits only complete records, bounds partial-line retention, and resets its cursor after file replacement or an observed in-place size decrease. The relay still writes to a different JSONL path than Federation Health reads. Peer events remain unauthenticated and do not feed the health report.

The same-inode truncation regression passed in an 11-case isolated focused suite. Hosted candidate checks passed, including strict Administrator audits, exact acceptance, landing finalization, and the separate metadata guard. Post-merge CI, Quality Gate, Docker, docs deployment, Codex CI, invariants, and nightly self-check passed on main `9971c16dcc3e184958419f830aff339d645d6f20`. TestClient still hangs in this sandbox on the pre-change stream test and a minimal finite StreamingResponse; hosted integrated checks passed.

The latest scheduled Federation Health execution remains #39902569701 on source `7a47004a30d41953436df4266d799b0cbb9d6973`. Its report remains stale and is not live telemetry. No current-main scheduled run has been observed.

Next: verify the next real scheduled Federation Health execution against its source SHA and publication receipt. Keep health separate from unauthenticated relay events until operator-provisioned peer identity, freshness, and revocation contracts exist.

