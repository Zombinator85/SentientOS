# 0136 — replay a recovered run through World-State before writeback

- Continues from verified source `5da42b0e69a51a7c7f26e38ad10b4cbeb16591f9`, tree `eb870d4679fe9b6a354a557a8d7fae6f8c7665b7`.
- The child-process recovery test now invokes the daemon's normal World-State projection after recovering a fully scored experiment, then exits before developmental writeback. A second fresh process reopens the same custody and reprojects at a later tick. Exact source ID/digest, fact ID, and payload digest remain stable; the World-State publisher's bounded `latest.json` contains the source while developmental-history custody remains unchanged.
- The parent reconstructs the cognition owner, projects the same source, and continues through the existing ordinary admitted writeback. The preceding child-process receipt substitution control still denies altered lineage without replay.
- Focused developmental suites: **164 passed, 0 failed**. Changed Python compiled. All model/invocation and serving evidence remains fixture-generated; no actual model behavior or production acceptance is claimed.
- Evidence: `work/construction/evidence/0136-world-state-reprojection-after-restart.json` (SHA-256 `be62314b3f67c256c3c5baca8aff2a9854b1bc47b3d52eee31292a4260501038`).
- Next: exercise interruption after candidate/receipt publication and before the cognition composition checkpoint for this recovered source; verify exact admission recovery yields one history record and a later-tick retrievable lesson without duplicate writeback or same-tick leakage.
