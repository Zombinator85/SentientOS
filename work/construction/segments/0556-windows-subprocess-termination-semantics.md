# Sequence 556 — report Windows subprocess termination accurately

Windows cancellation in the bounded subprocess supervisor now requests `CTRL_BREAK_EVENT` for the isolated process group, waits for the configured grace interval, then uses `kill()` only when the child remains alive. The reported flags describe attempted graceful and forced termination; Windows descendant confirmation remains explicitly unclaimed. Three regressions cover a graceful group exit, unsupported console signaling with forced fallback, and grace-period expiry. Windows Custody runs the supervisor regressions.

The exact hosted acceptance grew to 45 nodes, but both the pre-commit and candidate reconstruction paths still required 42. Their stale bounds are now 45, with workflow contract coverage for both checks. The first hosted attempt exposed the mismatch; the next exposed the landing contract's PR-title/latest-commit-subject binding. Both were corrected, and the final exact candidate passed the complete Quality Gate, hosted privileged finalizer, separate pre-publication metadata guard, and strict Administrator audits.

PR #2570 merged normally into `main` as `287188335576efb45c2ab94d7f7ade7c004c2b77`, tree `0d7148d4d7542b57a9c28b052889e6f210ed05f8`, with ordered parents `9718b3ebd75050ed8d44b5c6b283ee0e81dd0f2d` and `6e9d65e073fda487c4da55dfe712c7a443fcd8d5`. GitHub's main ref and commit/tree endpoints independently returned those identities. All post-merge CI, Quality Gate, Docker, Docs Deploy, Nightly Self Check, Windows Custody, Invariants, and Codex CI passed. Forge Smoke was skipped by its configured condition.

The paired evidence JSON records exact candidate and post-merge run IDs, artifact digests, source blobs, merge parents, and the two repaired pre-publication failures. The stale sequence-178 workspace and protected workspaces were not touched.

Verified main: `287188335576efb45c2ab94d7f7ade7c004c2b77`, tree `0d7148d4d7542b57a9c28b052889e6f210ed05f8`
Latest construction segment: `work/construction/segments/0556-windows-subprocess-termination-semantics.md`
Sequence: 556 (verified source merge reconciliation)

Next: continue checking Windows subprocess lifecycle and cancellation boundaries, retaining the explicit descendant-confirmation limit and source-bound acceptance.
