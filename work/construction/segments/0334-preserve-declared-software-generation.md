# Sequence 334: preserve declared software generation lineage without claiming observation

## Resolved reporting mismatch

The frozen model-replacement causal context already binds an optional `repository_generation_identity`, and run projection separately reported it as a frozen declaration. The World-State report nevertheless emitted `software_generation_identity: null` with posture `not_bound_by_selected_protocol`. This dropped useful bound context and made its lineage summary contradict its own declaration. Sequence 334 carries the exact declared value through the existing software-generation fields while naming the posture `frozen_context_declaration_not_running_observation`. Missing identity stays `unknown`; this is not a running-process observation.

The context verifier now accepts only `None` or a nonempty string of at most 512 characters for this identity. The new regressions cover exact declared-value projection and reject empty, oversized, and non-string values. Required Quality Gate selection binds the positive-path node and asserts all 28 exact nodes execute; its workflow contract test tracks that count and node.

## Verification boundary

`py_compile`, `git diff --check`, a direct behavior probe (one positive and three invalid-identity invocations), and local static assertions for the 28-node QG selection pass. The canonical `python -m scripts.run_tests` bootstrap was attempted and blocked because the sandbox could not reach its package proxy to install the required `setuptools>=78.1.1`. Direct naked pytest was also blocked by the repository airlock and was not bypassed. Targeted Mypy reports the repository baseline (357 errors across 74 files, including an existing redundant cast at line 305 of the changed module); no baseline or suppression was changed. Exact candidate hosted tests, strict audits, and finalizer remain pending.

No production A→B→A outcome or running-software observation is claimed. The real transition still needs commissioned model identities, a prepared production installation, and an operator-approved protocol. The Federation Health changed-output publication fixture still requires a hosted `workflow_dispatch`, which is unavailable from this session's GitHub connector.
