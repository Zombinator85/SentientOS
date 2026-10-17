# Sequence 329: repair resident newline boundaries

## Root cause

Required Quality Gate run `39075887413` executed both resident recovery cases and failed the positive PID-reuse case while parsing the persisted receipt journal. The exact parser exception was `parent_receipt_journal_truncated`, although the captured bytes ended in a real newline. Inspection of the candidate source found five Python byte literals written as `b"\\n"` in source: the procfs record terminator, receipt journal terminator and split delimiter, and state snapshot terminator and canonical-byte comparison. These literals match the two characters backslash and `n`, not the newline byte.

This caused the receipt parser to reject valid records, the state snapshot validator to reject valid persisted state, and Linux process-start-time observation to return unavailable for normal procfs records.

## Repair

Sequence 329 changes all five byte literals to `b"\n"`. The positive recovery acceptance also confirms the canonical parser accepts the complete persisted journal and continues to reject the same journal with its final newline removed. No journal repair, panic reset, weaker identity check, or recovery bypass is introduced.

## Verification boundary

Python compilation and `git diff --check` passed locally. Local pytest cannot run in this isolated source projection because its repository conftest requires the canonical minimal test installation; the hosted Required Quality Gate must run the exact positive and adverse recovery tests and the privileged finalizer. The previous run's failed call phase was correctly not treated as validation evidence.

## Provenance

The source candidate was fetched from PR #2323 at commit `8460e836fe59607bd4ea2b0bda6327c648b3e629`, tree `f30fd47021f95b8907eb68b58dc580b7ee445ce1`. This segment follows sequence 328. Sequence 286 provenance loss and the untouched stale sequence-178 workspace remain preserved.
