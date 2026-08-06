# Governed maintenance candidate collector

The maintenance candidate collector is a bounded, externally invoked bridge from
canonical diagnostic evidence to the existing candidate inbox.  It is proposal
intake only: writing a candidate is not admission, consent, a grant, a lease, an
implementation instruction, validation, or landing authority.  The selector,
task journal, activation profile, watchdog, grant, lease, foreman, validation,
and publication components retain their existing authority boundaries.

## Closed source boundary

The collector accepts only explicitly configured source roots and these canonical
source forms:

* `governed_improvement_signal_plane_evaluation:v1`, after validation by
  `governed_improvement_signal_plane.validate_evaluation`; and
* `sentientos.normalized_work_item_packet:v1`, whose remaining fields must be the
  exact closed `NormalizedWorkItemPacket` produced by `work_item_intake`.

Arbitrary JSON, raw issue metadata, explicit candidate-authoring manifests, and
unknown schemas are not sources.  The existing governed-signal and work-item
adapters create candidates, existing candidate normalization resolves duplicates
and contradictions, and the existing selector performs exact eligibility checks.
No objective, path, validation expectation, evidence reference, authority class,
constraint, kind, or budget is derived by the collector.

## Configuration and bindings

`sentientos.maintenance_candidate_collector_config:v1` explicitly binds repository
identity/root and exact base SHA; the activation-profile manifest and production
watchdog config; private external collector state and receipt custody; the exact
candidate inbox; separate governed-signal and normalized-work-item roots; allowed
schemas and kinds; scan, write, and byte bounds; mandatory evaluation time; and an
optional private STOP marker.  `doctor` verifies those bindings, the profile
bundle, watchdog agreement, repository HEAD, custody, STOP state, global lock,
and production API availability.  Warnings never become readiness.

Every written filename binds candidate ID and revision.  Candidate bytes are the
adapter's canonical bytes plus one newline.  A digest-chained receipt binds source
path/bytes/semantic identity, candidate identity/revision/bytes, profile and
selector digests, repository and base, destination identity, and write status.
Exact destination bytes are reused without rewrite.  Different bytes at the same
destination, a receipt without its candidate, chain tampering, an unsafe source,
or a malformed source fails closed.  If a crash writes the candidate before its
receipt, the next collection verifies the unchanged bytes and appends the missing
receipt.  Sources are never rewritten, acknowledged, archived, or deleted.

## CLI and external scheduling

Run `scripts/maintenance_candidate_collector.py` with `--config` and, except for
receipt inspection, `--evaluation-time`.  Commands are `doctor`, `scan`,
`collect-once`, `inspect`, `inspect-receipts`, and `print-run-command`.  Output is
canonical JSON; the run command is a structured argv array with no interpolation.
`scan` is read-only with respect to the inbox.  `collect-once` does not invoke the
watchdog or install a scheduler.

An operator-controlled external scheduler may invoke the printed collector argv.
Scheduling a separate watchdog cycle is deliberately outside this component; do
not combine the commands without a separately reviewed authority and failure
policy.  Manual canonical candidate authoring remains available, while automatic
governed intake removes only the operator's message-courier role.
