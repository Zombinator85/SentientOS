# Maintenance candidate authoring and first pilot

The candidate-authoring CLI closes the manual JSON gap between a reviewed operator
proposal and the bounded maintenance watchdog. It accepts one closed, versioned,
fully explicit manifest, renders it through the canonical candidate adapter,
verifies it against an already verified activation profile, and copies the exact
verified bytes into that profile's inbox. All CLI results are canonical JSON.

Candidate rendering and enqueue are **not** consent, task admission, execution, or
authority expansion. They do not invoke Codex, run validation, mutate Git, publish,
install a scheduler, or invoke the watchdog. The authoring receipt binds the exact
manifest, candidate bytes, canonical candidate digest, and profile bundle. The
external enqueue journal adds a digest-chained custody receipt without replacing or
deleting any inbox object.

## First manual pilot

1. Complete and verify an activation profile bundle.
2. Run activation `doctor-live` and review its readiness report.
3. Run the empty-inbox `smoke-idle` check.
4. Use `write-candidate-template`, explicitly replace every non-authoritative
   placeholder, and review the resulting candidate manifest.
5. Run `render-candidate`, then `verify-candidate`, and require
   `candidate_ready_for_inbox`.
6. Run `enqueue-candidate` and inspect its external chained receipt.
7. Run `print-pilot-plan`, review the candidate and every readiness report, and
   manually invoke exactly one watchdog `run-bounded` argv.
8. Inspect watchdog task and publication evidence, the base cursor, and activation
   receipts using the printed argv arrays.
9. Only after a successful manual pilot should the operator consider a separately
   controlled external scheduler. SentientOS does not install one.

`print-pilot-plan` emits structured argv arrays rather than a shell command. It
includes activation doctor and idle smoke, candidate verification and enqueue, the
bounded production runner, watchdog inspection, base-cursor inspection, and
activation-receipt inspection. Printing this plan executes none of them.

## Fail-closed posture

Production manifests reject unknown, secret-like, command, environment, placeholder,
absolute-subject, traversal, missing-proof, empty-scope, empty-authority, shortcut
authority, and implicit-budget inputs. Verification reuses the activation profile
bundle verifier, canonical candidate adapter, selector policy, grant, validation
expectation parser, and task-journal discovery. A warning never becomes readiness.
Output and inbox custody reject symlinks and conflicting bytes; exact retries reuse
identical immutable bytes.
