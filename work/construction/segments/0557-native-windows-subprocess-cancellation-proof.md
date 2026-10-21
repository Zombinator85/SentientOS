# Sequence 557 — prove the Windows subprocess cancellation path natively

The bounded subprocess supervisor now has a Windows-only integration regression that starts a child in its isolated process group, installs a `SIGBREAK` handler, and drives the real `run_supervised` timeout path. The test accepts either delivered console control or the documented forced-kill fallback, requires the attempted-operation flags and bounded completion to be accurate, and keeps Windows descendant confirmation explicitly false. The entire supervisor module runs in Windows Custody.

The first candidate placed this Windows-only node in Linux's exact Quality Gate selection. The hosted Linux reporter correctly rejected it as skipped rather than passed, while the native Windows job passed. The final candidate keeps the Linux Quality Gate's exact 45-node set unchanged and validates the platform-specific node through Windows Custody. The final hosted candidate passed both checks, strict Administrator audits, the privileged landing finalizer, and the separate pre-publication metadata guard.

PR #2572 merged normally into `main` as `60a335fb8f7e46a8715ae16db7305fcebcc7df05`, tree `37d8163fa0a1f0aabd0e0bcc81d1bf1a29f4e6bc`, with ordered parents `fc60cbd57d59354cbaf1568e57e26307e5044c8a` and `04b0632e811ef59ee20880022c42d5613e8fcf0d`. The exact candidate added only the native regression to the supervision test module. Post-merge CI, Required Quality Gate, Docker, Docs Deploy, Nightly Self Check, Windows Custody, Invariants, and Codex CI passed. Forge Smoke was conditionally skipped.

The paired evidence JSON records the initial platform-binding failure and correction, candidate run/artifact identities, native Windows verification, source blob, ordered parents, and exact post-merge runs. The stale sequence-178 workspace and protected workspaces were not touched.

Verified main: `60a335fb8f7e46a8715ae16db7305fcebcc7df05`, tree `37d8163fa0a1f0aabd0e0bcc81d1bf1a29f4e6bc`
Latest construction segment: `work/construction/segments/0557-native-windows-subprocess-cancellation-proof.md`
Sequence: 557 (verified source merge reconciliation)

Next: continue examining bounded Windows subprocess lifecycle and evidence boundaries without claiming descendant termination where the platform cannot confirm it.
