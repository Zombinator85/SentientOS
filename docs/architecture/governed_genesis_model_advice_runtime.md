# Governed Genesis Model-Advice Runtime

SentientOS may ask the already-governed local model for one bounded Genesis proposal opinion per eligible need and maintenance tick. The opinion is advisory only: it cannot approve itself, invoke tools, write memory, mutate the repository, call SpecBinder or AdoptionRite, or bypass the IntegrityDaemon, proposal router, proof budget, or sandbox.

## Contract

`sentientos/genesis_model_advice.py` defines schema version `genesis_model_advice.v1` with only these normalized fields: `objective_refinement`, `proposed_directives`, `testing_requirements`, `rationale`, and `capability_interpretation`. Parsing rejects missing or extra keys, malformed types, duplicates, control characters, oversized fields, URLs, command/source/import requests, role injection, hidden-reasoning requests, authority claims, adoption instructions, memory operations, and repository/Git/tool/host actions.

## Custody and linkage

A `GenesisModelAdviceRequestContext` binds the Genesis need identity, capability, source kind, bounded need text, signal batch ID/digest, signal IDs/digests, Local Model Authority Map ID/digest, model ID/artifact digest, purpose `genesis_proposal_advice`, caller, lifecycle phase, correlation ID, generation budget, review-evidence digest, expected schema, and proposal-only boundary. Observation timestamps and machine paths are excluded from semantic identity.

A `GenesisModelAdvicePacket` binds the request, governed invocation receipt, normalized-output digest, model and authority-map identity, signal batch and need identity, validation findings, fallback posture, candidate digest, and explicit false downstream-effect fields. Packet validation fails when nested semantic fields are tampered.

## Runtime path

`GenesisModelAdviceCoordinator` reuses `GovernedLocalModelInvoker`; it does not create another inference gateway. Missing or invalid review evidence records truthful deterministic fallback. Valid advice can create at most one untrusted `ForgeProposal`, and only when K is at least two. K remains the total candidate ceiling, at least one deterministic candidate is preserved, and K escalation reuses the cached advice packet rather than calling the model again.

`GenesisForge` passes the precomputed packet into `ForgeEngine.draft_variants`; every candidate then goes through the same stage-A, promotion, stage-B, router, `choose_candidate`, and `TrialRun` path. Model candidates receive no score bonus or sandbox exemption.

`sentientosd.RuntimeMaintenanceSurfaces` can receive the already-loaded daemon `LocalModel` through a single authority-map / `GovernedLocalModelInvoker` / `GenesisModelAdviceCoordinator` composition and reports compact feedback without raw prompts or raw model output.

## Evidence

Focused lane: `genesis_model_advice_runtime_closure_tests` runs the advice contract, CLI, governed invoker, GenesisForge, and sentientosd runtime closure tests. The CLI `scripts/build_genesis_model_advice.py` renders deterministic JSON/Markdown inspection artifacts and never bypasses control-plane admission, fabricates approval, calls remotes, executes tools, mutates source, invokes Git, or promotes adoption.

## Reviewed adoption boundary

Governed Genesis model advice remains proposal-time evidence only. The reviewed
adoption coordinator consumes a sealed packet and explicit operator decision; it
does not invoke the model or request fresh advice during adoption.
