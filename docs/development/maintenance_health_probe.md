# Bounded maintenance health probe

The maintenance health probe is an external, fail-closed source producer. One
`probe-once` invocation runs only the explicitly configured pytest node IDs via
`python -m scripts.run_tests -q`, validates that run's canonical provenance,
adapts its failure report through the governed improvement signal plane, and
writes one canonical evaluation to an external collector source root. Passing
tests create only a digest-bound external receipt.

The intended unattended chain is:

> health probe → governed signal source → existing collector → existing bounded autonomy cycle

Every link remains separately bounded and externally invokable. The probe does
not call the collector, autonomy cycle, watchdog, scheduler, model/provider,
network, Git mutation, candidate admission, publication, or repository-source
mutation surfaces. This capability does not install or modify a scheduler and
does not infer maintenance authority.

## Configuration and commands

Configuration uses the closed `sentientos.maintenance_health_probe_config:v1`
schema. It requires explicit repository/base identity, exact pytest nodes,
timeout and failure bounds, private external state and signal roots, validation
expectations, requested maintenance authority classes, constraints, four
estimates, a caller-supplied evaluation time, and a receipt journal path. Empty
or omitted declarations are rejected; arbitrary executable strings are never
accepted.

The CLI exposes only `doctor`, `probe-once`, `inspect`, and
`print-run-command`, each with `--config PATH`. `doctor` is read-only and
requires a clean exact-base checkout, safe private external custody, existing
test nodes, and the repository-native runner. `probe-once` uses an argv
subprocess with `shell=False`, a timeout, and process-group termination. Signal
writes are atomic no-clobber creations. Exact existing bytes are reconciled so
a crash between the signal write and receipt append can safely finish; unknown
or conflicting bytes block.
