# Local Cognitive Compute Substrate architecture

## Decision and scope

The **Local Cognitive Compute Substrate** is the attributable, replaceable boundary
between SentientOS's governed local-model lifecycle and accelerator execution. The
smallest coherent posture is **governed extension**: retain llama.cpp and
PyTorch/Transformers as mature general runtimes, while SentientOS owns exact compute
identity, correctness and performance evidence, native-code custody, and a narrow
extension boundary for operations whose local ownership is justified by measurement.
It is not a new meaning of `ControlPlaneKernel`.

This document and its machine-readable contract specify architecture only. They add no
kernel, compiler, dynamic loader, runtime patch, model download, benchmark run,
training, allocation, or inference authority. In particular, a faster implementation,
a successful benchmark, a compiled binary, and generated source each grant **no
authority and no adoption**.

## Repository-grounded current state

The present stack already owns substantial custody above inference:

1. Artifact paths are not treated as identity. Hardened paths stream model bytes and
   bind SHA-256 and byte size; catalog records also distinguish source revision,
   artifact identity, and quantization metadata.
2. Selection deterministically compares trusted catalog routes with a supplied host
   inventory. CPU, CUDA, ROCm, and Metal are distinct backend families. Selection is
   metadata-only: it explicitly leaves runtime availability unevaluated, so detected
   hardware is not proof that a compatible runtime, driver, or successful load exists.
3. Acquisition, commissioning, activation, serving, and inference are separate
   custody/admission stages. Activation selects but neither loads nor infers. Serving
   revalidates the exact current activation and artifact, binds the commissioned
   `runtime_id`, and retains the loaded model behind an opaque session. Each generation
   obtains an independent `LOCAL_MODEL_INFERENCE` admission.
4. The exact-runtime llama.cpp worker receives explicit `n_gpu_layers` and `n_ctx`,
   re-hashes the artifact, and reports its interpreter and loaded identity. This is
   meaningful runtime custody, but it is not yet complete identity for the runtime's
   native build, linked backend libraries, compiler flags, driver, or kernels.
5. The Transformers path can choose `cuda`, but the execution is supplied by
   third-party Transformers, PyTorch, and vendor libraries. `Dockerfile.cuda` and
   `gpu_autosetup.py` install/select existing CUDA or backend-specific distributions;
   they do not establish SentientOS-owned CUDA kernels.

The current architecture therefore distinguishes hardware compatibility from runtime
availability, but its identity and evidence become coarse precisely where a mature
runtime chooses a backend, execution graph, and low-level primitive. Delegation is not
a defect; the missing organ is a stable boundary around that delegation.

### The partial llama.cpp tree

`SentientOSsecondary/llama.cpp/` contains seven files: an `examples/server/server.cpp`,
three server CMake helpers, and three tiny public assets. It does **not** contain ggml,
the llama library sources and headers, CPU/CUDA/ROCm/Metal kernels, a complete build
tree, upstream history, or a pinned complete runtime. It is a partial server snapshot,
not an owned accelerator stack and not evidence of a reproducible llama.cpp build.

### “Training” surface classification

Names do not establish weight training:

| Surface | Actual role | Updates model weights? |
| --- | --- | --- |
| `sentientos/codex/self_training_daemon.py` | Scores software diffs, records failure evidence, and triggers preparation of examples/plans. | No |
| `codex_retraining_planner.py` | Clusters failures and writes a JSONL dataset plus Markdown plan. | No |
| `sentientos/codex/retraining_prep.py` | Extracts failure/corpus examples and planning text. Its aspirational fine-tuning wording is not an executor. | No |
| `sentientos/forge_merge_train.py` | A software merge train: queues, checks, rebases, holds, merges, and receipts pull requests. | No |

No inspected surface is a production model-weight training path. Dataset/corpus
preparation, software improvement orchestration, and a software merge train must not be
reported as model training.

## Layer and ownership map

```text
cognitive request                                      SentientOS
  -> governed local-model invocation                   SentientOS
  -> serving lifetime / exact model identity           SentientOS
  -> inference runtime identity                        shared boundary
  -> runtime execution plan                            mostly delegated
  -> accelerator backend                               delegated
  -> low-level execution primitives / kernels          delegated
  -> driver/runtime stack and hardware                 operator/OS/vendor
```

The shared boundary should let SentientOS describe and compare what it delegates. A
llama.cpp route delegates GGUF graph execution, quantized operations, caching,
sampling, offload, and kernels. A Transformers route delegates graph/generation
orchestration to Transformers and tensor/device execution to PyTorch. CUDA, ROCm, and
Metal libraries provide device runtimes and optimized primitives; the operating system
and driver control process, memory, and device execution. SentientOS should continue to
delegate those jobs by default while preserving exact evidence about the selected
implementation.

## Identities that must never collapse

| Identity | Meaning |
| --- | --- |
| Model identity | Semantic identity of selected cognitive machinery. |
| Model artifact | Exact bytes, format, SHA-256, and byte size. |
| Quantization | Numeric representation encoded in or applied to an artifact. |
| Inference runtime | Software that loads the model and orchestrates inference. |
| Runtime build | Exact source/version, compiler, flags, dependencies, recipe, and binary digests. |
| Accelerator backend | Runtime adapter for CPU, CUDA, ROCm, Metal, or another family. |
| Execution primitive | A bounded operation such as attention, GEMM, normalization, sampling, or transfer. |
| Kernel artifact | Exact source or compiled implementation of a primitive, with build provenance. |
| Hardware | Physical processor and relevant capabilities. |
| Driver/runtime stack | OS driver, vendor runtime, and libraries between backend and hardware. |
| Compute profile | All identities and inference configuration fixed for one observation. |
| Performance evidence | Attributable measurements from that profile; not an adoption decision. |

Changing a backend with model artifact and configuration fixed is an experimental
intervention. Replacing a kernel must not silently change model, tokenizer,
quantization, sampling, or runtime configuration. Conversely, keeping a model ID while
changing its bytes is not “the same model” for evidence purposes.

## Selected ownership posture

### Alternatives

**Pure delegation** has low maintenance cost and broad portability/model coverage, but
leaves build identity, equivalence evidence, and substitution competence below the
runtime opaque. It remains the execution default, but is insufficient as the complete
architecture.

**Governed extension** preserves upstream coverage and portability while adding exact
identity/evidence contracts and permitting a narrowly scoped, independently verified
implementation when ownership materially matters. Its numerical risk and maintenance
surface can be bounded per operation. This is selected.

**Independent runtime** offers theoretical control but introduces an enormous graph,
model-coverage, numerical, portability, and maintenance burden. The repository shows
no measured gap that justifies duplicating mature runtimes. It is deferred, not an
ideological objective.

### What SentientOS owns

Above runtimes, SentientOS owns governed requests; model/artifact identity; catalog,
selection, commissioning, activation and serving custody; a complete runtime-build and
compute-profile contract; correctness/performance evidence; and separate review,
adoption, rollback and post-adoption records.

Below the runtime boundary, it should own identifiers and replaceable interfaces for
accelerator implementations, plus source/binary/build custody and reference-candidate
verification **only when an extension is justified**. Compilation, loading, dynamic
linking, backend replacement, and native execution require explicit admission,
content-bound inputs, dependency closure, controlled load paths, receipts, rollback,
and operator policy. Unreviewed generated CUDA or Triton is arbitrary native code.

An extension is eligible for consideration only after a material measured gap, a
stable bounded operation, a reproducible reference, predeclared objective acceptance
thresholds, a maintenance owner, and a custody-safe integration path exist.

## Numerical semantics and functional safety

An optimized implementation is acceptable only relative to an exact admitted
reference compute profile. Bitwise equality is required for deterministic integer or
otherwise exactly specified behavior. Where accelerator arithmetic makes bitwise
identity impractical, the operation contract must predeclare dtype- and
operation-specific absolute/relative tolerances rather than relaxing the result after
measurement.

Applicable evidence includes:

- deterministic fixture vectors spanning shapes, masks, context positions, boundary
  sizes, dtypes, empty/invalid inputs, and overflow/underflow behavior;
- element-wise comparisons and aggregate error bounds;
- logit and token-distribution metrics with fixed thresholds;
- fixed-tokenizer, fixed-seed prompt-to-token regressions;
- perplexity or task-level regression on a versioned locally owned dataset where a
  primitive comparison cannot expose behavioral drift;
- crash, timeout, device-loss, out-of-memory, cancellation, and malformed-input
  behavior; and
- bounds, race, sanitizer, and memory-safety evidence supported by the implementation
  model.

Nondeterministic behavior needs a predeclared sample count, seed policy, metric,
confidence rule, and bound. Missing evidence, changed identity axes, unsafe fault
behavior, or “looks approximately right” fails closed.

## Attributable performance evidence

A benchmark record binds model/artifact/quantization; runtime source and exact build;
backend and kernel artifacts; hardware; OS, driver, vendor runtime and libraries;
compiler and recipe; fixture; context length; input/output token counts; batch and
concurrency; offload plan; warmup; sampling; and power mode.

Raw samples and aggregation record end-to-end latency, time to first token,
inter-token latency, tokens/sec, throughput, peak VRAM, peak host RAM, crashes and
retries, and the correctness result. Memory-bandwidth pressure, power, temperature,
clocking and throttling are recorded where the platform exposes them. Units,
repetitions, monotonic timing, cold/warm separation, environment, and background load
must be explicit. A summary without raw attributable samples is not reproducible
evidence.

Performance, correctness, and adoption remain separate:

```text
candidate optimization
  -> build / compile
  -> functional verification
  -> numerical / equivalence verification
  -> performance measurement
  -> comparison
  -> review / policy
  -> adoption
  -> post-adoption measurement
```

No arrow is implied. A fast incorrect candidate is rejected; a correct faster
candidate can still be rejected on portability, security, maintenance, power, or
policy grounds. Adoption must retain rollback and post-adoption observation.

## Candidate low-level domains

| Domain | Upstream owner today | Benefit of local ownership | Difficulty / specificity / risk | Decision |
| --- | --- | --- | --- | --- |
| Attention, flash/paged attention | llama.cpp, PyTorch, vendor libraries | Context latency and memory | Extreme / high / high | Use upstream absent a stable measured gap. |
| KV-cache layout/movement | Runtime | Capacity and transfer control | Extreme / medium-high / high | Defer. |
| Quantized GEMM/dequantization | ggml, PyTorch, vendor libraries | Large hot-path gain | Extreme / very high / very high | Do not duplicate mature upstream work. |
| Fused normalization/activation | Runtime/compiler/vendor | A bounded fusion experiment | High / high / medium-high | Plausible later extension after evidence. |
| Sampling | Runtime | Determinism/auditability more than speed | Medium / low-medium / behaviorally high | Prefer a reference and upstream. |
| Batching/scheduling/speculation | Serving/runtime | Workload throughput | High / medium / medium-high | Measure a runtime-level gap first. |
| Transfers/tensor layout | Runtime/backend | Expose bottlenecks | High / high / high | Own measurement first, not implementation. |
| Graph execution | Runtime/PyTorch compiler | Broad control | Extreme / medium-high / very high | Do not build an independent graph runtime. |
| Multi-GPU partitioning | Runtime | Capacity | Extreme / high / high | Defer upstream. |
| CPU/GPU offload | llama.cpp/runtime | Host-specific fit | High / high / medium-high | Keep explicit configuration and measure upstream. |

The hard, assistance-intensive areas are real, but difficulty is not a reason to build
them without a strategic gap. Existing upstream breadth makes broad local ownership a
liability today.

## CUDA, Triton, and extension decision

There is currently no technical justification to add CUDA C++, Triton, a custom
PyTorch extension, or a local llama.cpp/ggml patch. Identity, equivalence, benchmark,
and native-code custody foundations—and a measured gap—come first.

For a later bounded tensor operation already integrated through PyTorch, Triton may be
the first experiment when readable rapid iteration and objective comparison outweigh
maximum low-level control. CUDA C++ may instead be correct when vendor-library
integration, stable deployment, or architecture-specific control is essential. A
custom PyTorch extension is an integration vehicle, not a correctness argument.
llama.cpp/ggml changes should normally go upstream; a local patch requires exact source
and build custody plus a strategic need upstream cannot meet. Neither programming model
is automatically superior.

## Portability and durable compute competence

Local cognition is not NVIDIA identity. Model identity remains portable; accelerator
implementations remain replaceable; CPU or another independently specified reference
remains available where practical; and no backend becomes system identity. CUDA may be
a first experimental target only when installed hardware and evidence justify it.

The preservation objective is **durable compute competence**: versioned, locally
custodied source, tests, fixtures, implementations, compiler/build recipes, runtime
configuration, model-independent interfaces, locally owned evaluation data,
performance evidence, and optimization decisions sufficient to understand, rebuild,
test, compare, and deliberately adopt an implementation without the same external
engineering assistant. It does not mean extracting provider internals, preserving
proprietary models, or assuming future assistance will disappear.

Because future capability availability is uncertain, front-load the subtle foundations
that make later work safe and objective: identity schemas, reproducible build manifests,
equivalence fixtures and metrics, benchmark methodology, native-code custody, and
replaceable backend interfaces. These have high leverage and benefit from capable
research/coding assistance. Do **not** front-load an independent runtime or broad
kernel library before a measured need exists.

## Threat and failure model

The substrate fails closed against model or quantization changes hidden inside a
backend comparison; version labels without exact builds; hardware detection mistaken
for backend availability; benchmark cherry-picking and ambiguous units; numerical
drift hidden by sampling; unsafe memory/race/device behavior; source, binary, linked
dependency, or dynamic-search-path substitution; thermal/background-load distortion;
stale evidence after runtime or driver change; and any attempt to treat evidence or
artifact possession as authority.

## Resource-principal boundary

Future compute evidence may bind an exact invocation, causal resource principal,
runtime/backend, hardware, and measured consumption. That supports attribution only.
Resource identity is not entitlement, allocation, scheduling priority, performance
policy, or effect authority. This architecture does not implement `ResourceAllocation`.

The causal-resource authentication roadmap is orthogonal. Its selected next runtime
slice remains `production_purpose_scoped_root_issuer_provenance_signer`, deferred rather
than cancelled and intentionally not implemented here.

## Exactly one next implementation slice

The sole selected next slice is
**`exact_runtime_backend_build_identity_and_benchmark_manifest`**: define and validate
a metadata-only manifest that joins existing model/serving lineage to exact runtime
source/version, interpreter/package and native binary digests, backend, build recipe,
compiler, linked vendor libraries, driver stack, hardware, inference configuration,
fixture identity, measurements, and correctness-result references.

This is foundational because current custody is exact above that boundary but cannot
yet compare the machinery below it. It makes a later benchmark harness, equivalence
harness, implementation registry, or kernel experiment attributable without
duplicating an upstream runtime. The slice must not run GPU benchmarks, compile or load
native code, select/adopt a backend, implement a kernel, or grant inference/resource
authority.

The canonical structured details, closed lists, ownership comparison, and evidence
source inventory are in
[`architecture/local_cognitive_compute_substrate_architecture.json`](../../architecture/local_cognitive_compute_substrate_architecture.json).
