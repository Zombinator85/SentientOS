# Active construction checkpoint

Sequence 324 adds process-generation evidence to maintenance-resident child launch provenance. PID reuse is accepted only when the recorded process generation is shown to have ended.

Sequences 325–326 put both behavior-specific tests in the strict hosted Quality Gate and repaired the shell continuation. Run `39075517162` executed the positive and adverse tests; positive recovery failed with `panic_latched`, adverse same-generation blocking passed. Sequence 327 added state/receipt validation before reconstructing. Run `39075726571` then localized the failure to `parent_receipt_journal_truncated` while parsing the stored receipt journal. Sequence 328 captures the trailing byte count and bytes before invoking the canonical parser. The exact receipt defect remains unresolved; no repair or bypass has been applied.

Base main for sequence 324: `8a2ab13333574d9112442ef826351596077f267a`, tree `3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7`. Sequence 328 starts from candidate `31f0509604b9f058b42c26bd4e8a32a86b36c676`, tree `4c90ccac8a1103baa7b517eed4c6324fb0267741`.

Prior green suite runs omitted these task-specific tests. The current candidate requires a passing exact 25-node Quality Gate, privileged finalizer, and every required CI check after the journal failure is resolved.

Federation scheduled evidence exists for source `f0564c9f...` and `b91969c1...`, not current main. The changed-output fixture still requires workflow dispatch unavailable to this session; operator action request is pending. Nightly current-main scheduled evidence remains unverified. Sequence 286 provenance loss and stale sequence-178 workspace remain preserved; production A→B→A proof awaits the commissioned operator-approved setup.

Latest construction segment: `work/construction/segments/0328-report-resident-receipt-boundary.md`
Sequence: 328
Segment SHA-256: `aae03bd7754e16307b5c88aa64cc136409d3ce3c4ce4b8edd1b6832382d513f5`
