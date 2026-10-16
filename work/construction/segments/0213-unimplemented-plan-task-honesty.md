# Sequence 213 — Honest outcomes for unimplemented plan tasks

## Source finding

Goal planning emits fetch and doc_update tasks without implementations. The executor previously returned success for either empty task, copied expected artifact paths into the run, and thereby let a no-op count toward deterministic goal progress.

## Change

These task kinds now remain unsupported explicitly: empty command payloads produce a skipped run with reason task_kind_not_implemented and no artifact claims. Injected commands remain rejected. Tests cover both task kinds.

The neighboring goal-state tests were stale against the current API and completion-check contract. Their calls now supply the required context; the transition test uses a controlled completion result so it tests state-transition logic rather than a nonexistent completion-check name.

## Validation

Ten focused executor planning/run and goal-state tests passed. All changed Python modules compiled and diff checks passed. No production activation, provider access, or host actuation occurred.

## Continuation

Sequence 214 should continue the source-backed whole-system review at current resource-to-World-State retention and post-adoption consequence projection, selecting a concrete behavioral defect rather than adding readiness machinery.
