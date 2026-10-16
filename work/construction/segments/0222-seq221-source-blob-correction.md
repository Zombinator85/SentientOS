# Sequence 222 — Repair and verify the sequence 221 source blob

Independent readback after sequence 221 found that the published strategic adaptation source blob was not valid UTF-8. The test blob and append-only records were intact. The source file was re-encoded from the isolated workspace and published as an append-only correction; remote readback now decodes the full file and matches its expected Git blob identity. No semantic source change was made by the correction.

Validation was rerun against the corrected source: 9 strategic adaptation, goal progress, and goal-state tests passed; both affected Python files compiled; `git diff --check` passed. The source identity was independently read back as `a6d7fde0b02dc737fcd6a8bd98866473acab6ef7`.

The correction preserves the sequence 221 implementation and makes its source custody independently reconstructible.
