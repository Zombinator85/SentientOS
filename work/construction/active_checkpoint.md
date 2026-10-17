# Active construction checkpoint

Sequences 324–326 added Linux process-generation evidence for resident child recovery and exact hosted acceptance coverage. The first hosted positive recovery case exposed a latched recovery path; sequences 327–328 diagnosed it without clearing panic or repairing persisted evidence.

Sequence 329 identified and fixed five double-escaped newline byte literals in procfs, receipt-journal, and state-snapshot boundaries. The positive case now asserts valid journal acceptance and genuine truncation rejection. Compilation and diff checks pass; exact hosted recovery, adverse same-generation behavior, strict Administrator finalization, and all required CI checks remain pending. The PR is not ready to land.

Base main: `8a2ab13333574d9112442ef826351596077f267a`. Candidate before sequence 329: `8460e836fe59607bd4ea2b0bda6327c648b3e629`, tree `f30fd47021f95b8907eb68b58dc580b7ee445ce1`.

Federation scheduled evidence remains bound to earlier source commits, not current main. The changed-output fixture still needs a manual workflow dispatch unavailable to this session; current-main nightly execution evidence remains unverified. Sequence 286 provenance loss and stale sequence-178 workspace remain preserved.

Latest construction segment: `work/construction/segments/0329-fix-resident-newline-boundaries.md`
Sequence: 329
