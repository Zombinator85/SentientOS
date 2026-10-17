# Sequence 336: require verified model and software lineage for production resident transitions

## Gap and bounded change

The live resident A→B→A daemon composition accepted a non-synthetic transition protocol even when its references to the underlying A/B model-replacement protocols were absent or incomplete. Consequently, transition readiness could omit the exact model-development provenance and the frozen software-generation context already carried by those protocols.

Non-synthetic composition now requires exact references for predecessor A and successor B. It independently loads each model-replacement protocol and provenance manifest from the configured artifact store, matches the active model identity to the transition's A/B identity, verifies the referenced frozen causal context, and requires a nonempty repository-generation declaration bounded to 512 characters. Missing, substituted, mismatched, or unavailable lineage fails before the live transition ingress is enabled.

The read-only transition status and model-succession provenance projection now preserve both declarations and their protocol/context identities. Their posture is explicitly `frozen_context_declaration_not_running_observation`; this does not identify the daemon's running source generation. Synthetic rehearsals remain a separate, explicitly synthetic path. No model activation, serving, inference, history write, or other authority was added.

## Verification

Local Python compilation, whitespace validation, construction-custody verification, and static checks for all 29 exact Required Quality Gate nodes and their shell continuations passed. Targeted mypy was run and reported the repository's broad existing baseline (793 diagnostics across 120 imported files); no new diagnostic appeared in the added helper or operator-status fields.

The canonical selected-node runner was attempted but its dependency bootstrap failed before collection because this sandbox could not reach its package proxy to install `setuptools>=78.1.1`. The archived runner provenance records `bootstrap_failed`, zero tests executed, and an empty selected-node set. No test result is claimed from that local attempt, and the airlock was not bypassed. Exact candidate-hosted acceptance, strict Administrator audits, finalizer, full CI, and post-merge runs remain pending for the construction PR.

Sequence 286 provenance-loss evidence and the stale sequence-178 workspace remain untouched. Production A→B→A still requires commissioned model identities, exact deployment artifacts, and an operator-approved protocol.
