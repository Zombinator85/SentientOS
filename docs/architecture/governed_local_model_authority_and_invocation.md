# Governed local model authority and invocation

SentientOS routes local model use through one local-only authority and receipt plane:

* `sentientos.local_model_authority` builds a deterministic Local Model Authority Map from `ModelConfig` and `ModelCandidate` records. It verifies local artifacts with streamed SHA-256, records sidecar/config digests, rejects provider-like engines, and separates observed paths/timestamps from semantic identity.
* `sentientos.governed_local_model_invocation` admits only `local_user_chat` and `genesis_proposal_advice` requests through `AuthorityClass.LOCAL_MODEL_INFERENCE`, enforces prompt/output budgets, calls the already configured local backend, and emits digest-bound receipts under an injectable runtime root.
* `sentientos.chat_service` no longer calls `LocalModel.generate` directly from the request path; chat requests use `GovernedLocalModelInvoker` and receive truthful unavailable/denied fallback text.
* `scripts/build_governed_local_model_invocation.py` builds/validates authority maps, inspects posture, executes explicit local fixture invocations, and validates receipts. It does not use providers, network calls, tools, memory retrieval/writes, Git, repository mutation, relay paths, or adoption.

The authority map grants no action by itself. Invocation receipts keep raw chat prompts out of durable artifacts by default and record only digests, sizes, admission references, generation limits, status, latency metadata, truncation/fallback posture, and explicit false provider/network/tool/memory/action/adoption/repository-mutation effect fields.

Genesis model advice is an untrusted structured proposal-advice purpose. It is schema checked, bounded, and may only enter the existing proposal-only Genesis evaluation pipeline as candidate material; it cannot approve, execute, adopt, mutate source, or bypass IntegrityDaemon, router scoring, sandbox trial, SpecBinder, AdoptionRite, or repository mutation custody.

Legacy `model_bridge.py` and `relay_server.py` remain noncanonical/operator-invoked compatibility surfaces. The governed local path does not import or route through them.

## Genesis proposal advice closure

`genesis_proposal_advice` is consumed by `sentientos.genesis_model_advice.GenesisModelAdviceCoordinator` and `sentientos.genesis_forge`. The model output is validated as bounded structured advice, converted into at most one untrusted candidate inside the total proof budget K, and sent through the same IntegrityDaemon/router/sandbox path as deterministic variants. Missing evidence, denial, malformed output, timeout, oversized output, or unavailable models fall back to deterministic Genesis candidates.
