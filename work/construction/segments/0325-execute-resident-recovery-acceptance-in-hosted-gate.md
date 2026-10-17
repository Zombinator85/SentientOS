# Sequence 325: execute resident recovery acceptance in hosted Quality Gate

## Source and reason

This continuation starts from sequence 324 candidate `a29f85842b7fdc4495c9e7f12b7d84d76cfa437a`, tree `a36e6438670c2e2722e14f615349d08fc9104ee5`, based on main `8a2ab13333574d9112442ef826351596077f267a`.

Review of hosted artifacts exposed a verification gap: the Required Quality Gate assembled a fixed list of 23 generic call-phase nodes and never selected sequence 324's two required PID-generation recovery tests. The default Docker run passed 143 tests with 13 skips, but its selected-node provenance also did not include either recovery test. Those results could not establish sequence 324's behavior.

Earlier candidate attempts remain in branch history: run `39074573697` failed the mypy baseline after finding the launch PID's mapping lookup remained typed as `object`; a repair attempt was then pushed through an output-truncated blob, producing a syntax failure in run `39074775155` and Docker run `39074775107`. The complete source blob `ced4ebe7200fcbec4decad1ac35061a5c7e24c0e` was independently read back and matched byte-for-byte with the complete local source. Quality Gate `39074893248` then passed strict Administrator verification, exact gate acceptance, mypy baseline, audit immutability, and its finalizer; however, that gate still selected only its 23 generic nodes. Docker run `39074893273` passed pre-commit and 143 tests with 13 skips, while provenance confirmed the recovery nodes were not selected.

## Change

The required Quality Gate's call-phase selection now includes the positive PID-reuse recovery node and adverse still-live same-generation node. Its exact-node cardinality check now requires 25 selected call-phase nodes. The workflow contract test asserts both recovery nodes are present and the 25-node count. The normal acceptance machinery then binds those outcomes to the current candidate SHA and run provenance; neither test receives privileged authority.

## Verification boundary

Sequence 324's complete source passes compilation, targeted mypy, and diff checks. Sequence 325's workflow and contract-test changes still require fresh hosted execution, including both exact acceptance nodes, strict Administrator finalization, and all required PR checks. Those results are not claimed passed by the earlier generic 23-node gate or 143-test default run.

No production Federation telemetry, model transition, commissioning, provider invocation, or authority expansion is claimed. Sequence 286's provenance loss remains unresolved; the stale sequence-178 workspace remains untouched.
