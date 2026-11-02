# Rootless Qwen3-1.7B Q4 epistemic run (2026-11-02)

This public note records aggregate results and model provenance for a bounded, non-production SentientOS resident-cognition experiment. It is separate from native-subagent evidence, the original `gpt-6-astra` pilot, and production commissioning or serving.

## Aggregate result

- Four local GGUF inference calls completed through SentientOS and were captured before scoring.
- The scorer reported `series_passed`: the original supported stance, corrected contested stance with both evidence citations, and unchanged contested stance under unsupported pressure matched the sealed key.
- Reason-code correctness was not scored because the probe did not expose a reason-code vocabulary.
- `oracle_independence_verified`, `preregistration_timing_verified`, and `real_model_qualification_established` are all false in the score record. This exploratory result is not a formal model qualification, independent replication, causal claim, or generalization.
- Production authority and production eligibility remain false.

## Model provenance

The subject was `Qwen3-1.7B-Q4_K_M`, a public GGUF from [unsloth/Qwen3-1.7B-GGUF](https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/tree/d7f544eead698dbd1f15126ef60b45a1e1933222) at pinned revision `d7f544eead698dbd1f15126ef60b45a1e1933222`. Its artifact SHA-256 was `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` (1,107,409,472 bytes). The model card declares Apache-2.0; license text was independently pinned to [Qwen/Qwen3-1.7B-GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/blob/90862c4b9d2787eaed51d12237eafdfe7c5f6077/LICENSE).

The runtime was the verified `llama-cpp-python` CPU backend in rootless experimental posture. It had no production installation state or serving authority.

## Evidence boundary

Exact prompts, raw responses, preregistration, invocation receipts, capture indexes, score record, and runtime measurements remain in separate restricted task custody. They are not included in this public note. The held-out answer key is separately custodied and is not included in the repository. The run-level package remains in local workspace custody for this task, outside the repository.

This small four-call result does not establish generalization, model qualification, cognitive improvement, production readiness, Astra identity, native-subagent identity, or a causal effect of pressure.