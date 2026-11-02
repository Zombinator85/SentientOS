# Pre-GLORP local-model baseline reproduction

This is a new, one-shot reproduction of the prior harmless rootless smoke prompt. The earlier attempt and evidence were not modified or replayed. This run has a unique intent/correlation, uses the same pinned model artifact and verified CPU runtime, and is not production commissioning, serving, GLORP hardware evidence, an epistemic observation, or a native-subagent result.

- Run: `rootless-experimental-intent-502dda7b8c0b4041a19904de`; correlation: `rootless-experiment-c952252afb2d437594bba0cefb76c024`.
- Model: `Qwen2.5-0.5B-Instruct-Q4_K_M`, artifact SHA-256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.
- Runtime: `llama-cpp-python-0.3.35-cpu-linux-x86_64`; CPU-only, context 512, 5 threads, at most 16 output tokens.
- Prompt SHA-256: `9c18ab99f3ca99acc7ddfd486926856a2f00ac2457eb55e88d199ce3dce55ee2`; response SHA-256: `beeebad30c71c8ad18c365e1e2736902e020dea8844eb21f10eeca13ca24c557`.
- Response: `ROOTLESS-SMOKE-OK`; invocation latency 544 ms.
- Intent digest: `19b09e1598e8c0f3d425e921c8130caa1d4b645143b43b5377c313345bea96a2`; result receipt digest: `ec679d05dec47467d873631d14e007303cdc6e0fe722da8043a428e2f6fdc780`.
- Production authority and eligibility flags are false in the preserved receipt.

The exact prompt, output, invocation receipt, admission/governor decisions, runtime receipts, and model source manifest are retained here. The GGUF is not copied into the repository; its pinned source and artifact digest are recorded. See `custody-manifest.json` for per-file sizes and hashes.
