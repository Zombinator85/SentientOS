# World-State Evidence Board

The World-State Evidence Board is a canonical read-only projection that turns bounded typed local evidence into deterministic snapshots, entity stage posture, contradiction findings, staleness posture, and deltas. It is implemented by `sentientos/world_state_board.py`, source-manifest adapters in `sentientos/world_state_sources.py`, the inspection-only CLI `scripts/build_world_state_board.py`, a terminal `sentientosd` maintenance projection, and authenticated dashboard read endpoints.

The board preserves lifecycle separation: observation, proposal, review, admission, execution, rollback, adoption, repository handoff, and repository landing are independent stages. Observation is not proposal; proposal is not approval; review readiness is not admission; admission is not execution; attempt is not completion; receipt existence is not effect proof; model advice is not candidate selection; selected Genesis candidate is not adoption; approved amendment is not repository landing; local commit evidence is not a remote pull request; pull-request evidence is not merge evidence; board display grants no authority.

The manifest is explicit and bounded. Unknown source kinds fail closed, traversal and symlink/path escapes are rejected, maximum source count and artifact size are enforced, byte-identical declarations deduplicate, and missing/malformed/oversized/unsupported/digest-mismatch evidence degrades or blocks truthfully. Semantic identities exclude custody-only values such as observed time, retrieved time, latency, absolute paths, temporary roots, process IDs, dashboard request time, and output locations while binding normalized payloads, source digests, schemas, subjects, lifecycle stages, dispositions, links, effect claims, and proof posture.

Runtime integration builds at most one snapshot per maintenance tick after existing observation/proposal/evaluation stages and persists an atomic bounded artifact beneath the injected runtime-state root. The feedback surface contains only IDs, counts, postures, and artifact references. The board never invokes model generation, Genesis drafting, amendment creation, admission, fulfillment, service restart, host effects, repository mutation, Git, or external transport.

Dashboard endpoints are read-only: `/api/world-state`, `/api/world-state/summary`, `/api/world-state/entities`, `/api/world-state/entities/{subject_id}`, `/api/world-state/conflicts`, and `/api/world-state/delta`. They preserve stable ordering, bounded pagination, source-location redaction, explicit unknown/stale postures, and separate proposal, admission, execution, adoption, handoff, and landing views.

Proof command:

```bash
python -m scripts.run_tests -q tests/test_world_state_board.py tests/test_world_state_sources.py tests/test_build_world_state_board_script.py tests/test_dashboard_world_state.py tests/test_sentientosd_runtime_closure.py
```
