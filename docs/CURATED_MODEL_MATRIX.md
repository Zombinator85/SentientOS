# Curated Model Family Matrix (Curator Scope)

This matrix lists license-safe model families appropriate for curator-managed deployments. It focuses on families (not individual checkpoints), typical quantization tiers, and license survivability. All entries assume offline execution with no automatic downloads.

## Default Baseline
- **Mistral-7B-Instruct (Apache-2.0)** — preferred baseline for all platforms. Typical quantization: Q4_K_M for general use; Q5_K_M where memory permits.

## CPU (8–12 GB)
- **Mistral-7B family (Apache-2.0)** — Q4_K_M, Q4_0 baseline tiers.
- **Dolly-v2 3B/7B (Databricks Terms, derivative-friendly)** — Q4_K_M fallback only when Mistral is unavailable.

## CPU (16–32 GB)
- **Mistral-7B / Mixtral-8x7B families (Apache-2.0)** — Q5_K_M or Q6_K if latency budgets allow.
- **Llama 2 7B/13B (Llama 2 license)** — Q5_K_M for recall-sensitive tasks when Apache-2.0 coverage is not required.

## NVIDIA GPU (8–12 GB)
- **Mistral-7B (Apache-2.0)** — Q4_K_M or TensorRT-friendly FP16 where available.
- **Llama 2 7B (Llama 2 license)** — Q4_K_M or FP16 with low-layer offload.

## Apple Silicon
- **Mistral-7B (Apache-2.0)** — Metal-optimized Q4_K_M / Q5_K_M.
- **Llama 2 7B (Llama 2 license)** — Metal-optimized Q4_K_M.

## Excluded from Default Recommendations
- Falcon 40B and larger — advanced/manual only.
- GPT-NeoX and older Eleuther families (except Dolly-v2 fallback).
- Any non-commercial, RAIL, or revocable licenses.

## Minimum Viable Escrow Targets
Document escrow should track family + size only (no download automation):
- Mistral-7B-Instruct (Apache-2.0)
- Mixtral-8x7B (Apache-2.0)
- Llama 2 7B/13B (Llama 2 license)
- Dolly-v2 3B/7B (Databricks Terms)
