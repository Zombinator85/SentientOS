# Governed Improvement Signal Plane

The governed improvement signal plane is the local-only bridge between repository evidence and proposal machinery. It normalizes explicit run-tests, coverage, mypy, covenant, telemetry, capability-gap, and GapSeeker-style findings into deterministic signal batches, routes each signal with explainable receipts, and exposes proposal-only inputs for GapSeeker, SpecAmender, and GenesisForge.

The subsystem is intentionally model-agnostic. It does not invoke providers, assemble prompts, open network connections, dispatch ExternalGapSeeker, run Codex workspaces, call Git, stage files, commit, branch, push, create pull requests, approve proposals, integrate Genesis lineage, promote live daemons, or mutate repository source from `sentientosd`.

## Runtime posture

`sentientosd` admits one `identify_improvement_signals` maintenance stage before Genesis expansion and SpecAmender cycling. That stage builds one immutable batch for the tick and records feedback containing batch identity, source counts, routed dispositions, proposal counts, blocked counts, degraded state, and explicit no-adoption/no-repository-mutation posture.

Genesis runtime intake receives bounded telemetry/vow inputs derived from that batch and uses the proposal-only path. Proposal-ready-for-review is a successful pending status; adoption remains a separate reviewed API and is not called by signal intake.

SpecAmender runtime intake receives existing-spec failure signals from the same batch and can create pending amendments only. GapSeeker-supported diagnostics remain diagnostic receipts unless routed by existing review machinery.

## Evidence and custody

Every normalized signal carries stable IDs, source kind, finding kind, severity, subject/spec/capability/telemetry target, artifact references, SHA-256 evidence binding, caller-supplied observation time, routing eligibility, reason codes, and explicit false authority/effect flags. Invalid paths, unknown sources, contradictions, and authority claims fail closed.

Runtime artifacts are JSON/Markdown review evidence and pending proposals only. Evidence is not authority.
