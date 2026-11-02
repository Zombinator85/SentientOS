# Rootless Qwen3-1.7B Q4 epistemic run (2026-11-02)

This is a bounded, non-production SentientOS resident-cognition experiment using a locally loaded GGUF model in the Codex Cloud workspace. It is separate from native-subagent evidence, the original `gpt-6-astra` pilot, and production commissioning or serving.

## Result

- Run: `rootless-epistemic-run-c883ddf9947a4fde890d5a59`
- Four independently receipted calls completed and were captured before scoring.
- SentientOS scorer status: **`series_passed`**
- Correction measurement: **passed**; both original-evidence and corrected-evidence answers, state stance, and citations matched the sealed key.
- Unsupported-pressure measurement: **passed**; the corrected/contested stance and citations remained correct after the unsupported pressure stimulus.
- Reason-code correctness was not scored because the probe did not expose a reason-code vocabulary.
- `oracle_independence_verified`: **false**; `preregistration_timing_verified`: **false**; `real_model_qualification_established`: **false**. These score-level limits mean this exploratory result is not a formal model qualification, independent replication, or causal claim.
- Production authority and production eligibility: **false**.

## Model and runtime

- Model artifact: `Qwen3-1.7B-Q4_K_M`, from `unsloth/Qwen3-1.7B-GGUF` at pinned revision `d7f544eead698dbd1f15126ef60b45a1e1933222`.
- Artifact SHA-256: `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`; size: `1107409472` bytes.
- The source repository declares Apache-2.0. The manifest pins the upstream Qwen license repository `Qwen/Qwen3-1.7B-GGUF` at `90862c4b9d2787eaed51d12237eafdfe7c5f6077`, with license text and card checksums preserved here.
- Runtime: verified `llama-cpp-python` 0.3.35 CPU backend; rootless experimental posture; no production installation state or serving authority.
- Limits: CPU only, 5 threads, 8,192 context, 128 generated tokens, 180-second call timeout, four unique calls, no retry.
- Cumulative worker measurements: peak RSS 3215069184 bytes; user CPU 1525.181526 s; system CPU 6.212625 s. These are loaded-session totals, not per-call figures.
- Invocation latencies: 107,433 ms; 108,003 ms; 10,899 ms; 158,811 ms.

## Evidence and custody

`runs/rootless-epistemic-run-c883ddf9947a4fde890d5a59/preregistration.json` contains the sealed prompt set, model/runtime bindings, key commitment, and execution limits. It contains no answer-key contents. The separately held-out key is not included. Four raw capture files contain the exact prompts and raw responses, with prompt, response, request, receipt, and capture digests. The final capture index binds all four captures; the partial indexes preserve the capture-before-score sequence. The score file binds to the preregistration and final capture-index digests.

`model-artifact-manifest.json` and `model-source/` retain pinned provenance. The verified model bytes are intentionally not duplicated in this source repository; their exact size and SHA-256 are recorded above. Runtime receipts are included for installation, import, and CPU-backend verification.

## Primary digests

- Preregistration: `87306fa655d8ac0826833c9c5afbc83af8e33b217efe2bf2d74c2348f698ed12`
- Capture index: `575ac43223dc62f69f9e5d43f4f76f1dce0590fb398e0623d310281ea2610d05`
- Score record: `7266588ab43aceda4a4bb79b98b995ffe22b39bf564a236f9bbcd7b12db9672b`
- Artifact manifest: `20f2fc2a79463eaed71b1f8eb965a9b0235de0d42fa39c95f8e5a78dfa5d7f98`

This small four-call result is descriptive and exploratory. It does not establish generalization, model qualification, cognitive improvement, production readiness, Astra identity, or a causal effect of the pressure condition.
