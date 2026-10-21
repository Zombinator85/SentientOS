# Sequence 514 — validate transition context constructor shape

The public frozen dataclass now validates its outer contract before recursively freezing approvals. It rejects non-string stage labels, non-list/tuple approval containers, and approval entries that are not mappings with explicit `TransitionError` reasons. This prevents malformed direct-constructor inputs from leaking incidental `TypeError` and keeps the `.create()` path and direct construction under the same invariant. The regression exercises all three invalid shapes.

Sequences 512 and 513 were verified and merged through PR #2520 as `c10db1dd8bf68a440b4672744a12d3d89d96a18d`, tree `4a4d36bc8350b38c11d618cd37b4ea5c65235ef5`, with ordered parents `dd51df9fc0aa21f8ecac732df590716f14d801bb` and `96fd9900c51dbb60df62936996f6e0c5042ae92b`. Exact-candidate checks passed after correcting the acceptance node shape. The initial sequence 512 CI acceptance mismatch and the stale duplicate Quality Gate title-preflight failure are retained in sequence 513 evidence; the corrected PR CI run `39547569130` and Required Quality Gate `39547571827` passed, including actual Administrator strict audits, hosted finalization, and separate metadata guard.

Post-merge main checks on `c10db1dd8bf68a440b4672744a12d3d89d96a18d` passed: CI `39548093639`, Nightly Self Check `39548093634`, Required Quality Gate `39548093672`, Invariants `39548093607`, Docker Image `39548093590`, Docs Deploy `39548093596`, and Codex CI `39548093602`. Forge Smoke `39548093644` was skipped by workflow condition.

Supplemental local verification passed 91 affected tests with 0 failures and 0 skips. Targeted Mypy, compileall, workflow YAML parsing, diff checks, and custody across 513 predecessors passed. Exact-candidate hosted checks for this increment are pending. No production transition, activation, serving, inference, or writeback was performed.

Verified main base: `c10db1dd8bf68a440b4672744a12d3d89d96a18d`, tree `4a4d36bc8350b38c11d618cd37b4ea5c65235ef5`
Implementation candidate: `2d3539f462b5e6eb6acac5710001dc1b831ed2ce`, tree `833cda415b96db88afee5307c5542503fa53bdc6`
Sequence: 514 (candidate pending hosted verification)
