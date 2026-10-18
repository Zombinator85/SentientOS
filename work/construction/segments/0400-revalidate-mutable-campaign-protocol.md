# Sequence 400: revalidate the campaign protocol before trusting progress

A frozen `ProductionSelfReflectionProtocol` still contains mutable nested mappings. The campaign previously validated its protocol only when constructed or reconstructed. A caller could mutate `model_a`, assessment bindings, or campaign policy in memory after readiness was issued; `run_one` then reached the executor before receipt creation discovered the altered model identity. This crossed the trial boundary with stale protocol identity.

Campaign `state()` and `_verify_progress()` now call the canonical protocol verifier before reading or accepting progress. A regression mutates the nested model identity after campaign creation, then proves `run_one` fails with `protocol_tampered` before invoking the executor and leaves the persisted trial state untouched. The readiness receipt's stale protocol digest cannot authorize the altered object. No activation, inference, transition, or other authority was added.

Verification on the isolated construction workspace: `tests/test_production_self_reflection_campaign.py` passed 30/30 with zero skips; `py_compile`, `git diff --check`, and focused mypy with imported modules followed silently passed. The repository mypy baseline wrapper could not resolve mypy from the isolated venv; this is recorded as an environment limitation, not a passing baseline result. Exact-source hosted verification remains pending.

Source parent is verified main `ae55461e13be358c2754c7686b381ae2d72daa63`, tree `43736a4f450483cb16a6df0c73c16d7c10a68ee6`.
