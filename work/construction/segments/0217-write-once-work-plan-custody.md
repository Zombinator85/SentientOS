# Sequence 217 — Write-once plan and run custody

Work-plan and work-run files were overwritten when an existing identity was persisted again. A replay could silently replace prior outcome evidence and duplicate pulse entries. Persistence now creates each identity once, accepts an exact byte-for-byte replay without appending another index row, and rejects content that conflicts under an existing identity. This does not claim task execution can resume from a partial run; it makes completed plan/run custody append-only.

Validation: 19 parser, persistence, goal executor planning, execution, and goal-state tests passed. Changed modules compiled and diff check passed. Tests verify exact retry idempotency and conflicting replay preservation for both plan and run records.
