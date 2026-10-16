# Sequence 257 - Bounded selected proposition trace

Added `ResidentEpistemicDevelopmentRuntime.trace_proposition()` as an explicitly selected, read-only trace for a configured proposition. It validates the bounded receipt inventory, returns source run and digest identities with original observation time, active/inactive relation, state generation and predecessor/successor digest chain, event identities and matching admission receipt IDs. When a caller supplies a cognitive tick it also records the exact verified prior projection identity and state digests. Output is capped at one selected proposition, sixteen events, and 32 KiB; receipt recovery must verify and the trace makes no truth or authority claim.

Extended the recovered task-family test to inspect the trace after fresh-owner reconstruction and verify source identity, event-to-state binding, both mutation receipt stages, and the same state digest passed to later cognition. The invalid event bound is rejected.

Validation: the targeted recovered task-family end-to-end node passed. The combined epistemic development and causal-introspection scope completed 57 passing tests. Python compilation and `git diff --check` passed. The large cognition test blob was reconstructed in verified chunks; source blob identities matched local Git hashes before publication.

Limits: this is still one positive deterministic fixture outcome. A separate later scored contrary outcome, contested revision and behaviorally evaluated later decision remain unfinished. Outcome-informed goal planning remains queued.
