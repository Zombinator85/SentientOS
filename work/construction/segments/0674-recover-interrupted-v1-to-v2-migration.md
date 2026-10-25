# Sequence 674: Recover an interrupted v1-to-v2 index migration

The first migration implementation activated the v2 root before restoring the frozen v1 index and checkpoint. This order fails closed during an interruption, but a rerun originally stopped at the existing v2 root even when its root, shard, and checkpoint bytes exactly matched deterministic reconstruction. The migration command now verifies those prepared bytes and safely completes the frozen-anchor restore on retry; conflicting or tampered preparation remains a hard error.

A regression injects interruption immediately before replacement of the v1 index. It confirms the v2 root has been activated, the operation reports failure without claiming custody readiness, and an identical retry finishes with the v1 index/checkpoint unchanged and custody ready. The focused custody and publication suites pass 27/27. The documentation build generated 616 pages, Python compilation and diff checks passed, and the pre-append candidate guard passed against verified main before this sequence record was added.

No external publication was attempted. The candidate keeps `work/construction/index.json` and its original checkpoint byte-identical to verified main; any later external update must use the platform-supported exact-action approval path and ordinary PR validation.
