# Deterministic local model selection

`sentientos.local_model_selection:v1` is the canonical metadata planning boundary from a supplied read-only host inventory and trusted model metadata to exactly one eligible artifact. It performs no probing, network access, download, installation, loading, inference, commissioning, host mutation, or authority grant.

## Curator custody and deployment identity

A **CURATOR MANIFEST** (`sentientos.model_manifest:v2`) references local curator
escrow. Its full validator opens and hashes the curator-held GGUF and proves the
associated checksum, `LICENSE.txt`, `MODEL_CARD.md`, and `SOURCE.json`. Curator-only
promotion then independently hashes those bytes and publishes a **DEPLOYABLE LOCAL
MODEL CATALOG** (`sentientos.local_model_catalog:v1`). The catalog retains the exact
immutable source commit, source filename, curator-approved license, content-addressed
artifact filename, byte size, SHA-256, trusted `models.sentientos.org` HTTPS URLs, and
explicit execution routes. It deliberately does not retain `artifact.escrow_path`.

Catalog validation is pure metadata validation. It does not need a GGUF on the
deployment host and does not access the curator tree, network, Hugging Face, hardware,
llama.cpp, or a model loader. Thus identical verified escrow evidence at different
curator filesystem roots has identical catalog semantics and digest.

`source_artifact_filename` is the exact upstream repository-relative POSIX GGUF
path, such as `quantized/model-Q4_K_M.gguf`. It is intentionally different from
`artifact_filename`, the content-addressed SentientOS escrow and mirror identity;
promotion never reconstructs upstream provenance from that local name. Before
promotion, the manifest hash, streamed GGUF hash, and original escrow `.sha256`
sidecar must all agree, and the streamed size must equal the manifest size. All
curator evidence must be non-symlink regular files.

Portable catalog publication uses an atomic no-overwrite link: a concurrent
identical regular catalog is accepted, while conflicting bytes and symlinked paths
fail closed without overwriting the competitor. These checks stay curator-side;
deployment validation and selection remain metadata-only after escrow is removed.
The file planner dispatches by exact schema: catalogs use the deployment validator;
legacy manifest schemas retain their curator validator and are never silently reinterpreted as a
production catalog.

The authority states remain distinct: curator escrow verified ≠ deployment artifact
acquired; catalog entry selected ≠ artifact acquired; artifact acquired ≠ GGUF
compatible; GGUF compatible ≠ model loaded; model loaded ≠ commissioned; commissioned
≠ inference authorized. Catalog promotion is curator-controlled metadata publication.
Catalog validation and selection grant no network, download, runtime, model,
commissioning, inference, or other execution authority. A later acquisition stage must
cross-bind the selected model route, runtime provisioning plan, and sealed backend
receipt before it may fetch any bytes.

The immutable hardware profile records inventory identity/digest, OS and architecture, exact total RAM bytes, optional available storage, tri-state AVX/AVX2/AVX512 facts, explicit accelerator observations/vendor/family/VRAM/backend, missing facts, and warnings. The adapter uses `HostInventoryManifest` fields directly. It never derives instruction sets from CPU text, VRAM from labels, or runtime backends from hardware brands. Facts not explicitly supplied remain `unknown`.

RAM minimums use GiB (`ram_gb_min * 1,073,741,824`) despite the historical field name; no guessed OS overhead is deducted. Architecture aliases are limited to `amd64`/`x86_64` and `aarch64`/`arm64`. Required CPU features pass only on explicit true, fail as incompatible on false, and remain unresolved on unknown. Historical curator `avx` booleans retain their literal manifest meaning; the planner does not reinterpret classifier history.

Legacy manifest file planning calls `hf_intake.manifest.validate_manifest()`, preserving pinned checksum, URL, license, and escrow custody. Production catalog file planning instead calls `validate_local_model_catalog()` and never reads model bytes. Mapping planning for legacy manifests is pure and intended for already-trusted metadata and tests. CPU-capable (`gpu: false`) entries may qualify. Manifest v1 `gpu: true` cannot describe CUDA, ROCm, or Metal compatibility and therefore remains unresolved as `manifest_accelerator_backend_unspecified`; filenames are never used as evidence.

Manifest schema v2 is identified independently of the curator's content version by
`schema_version: sentientos.model_manifest:v2`. Every artifact entry has a non-empty,
canonically ordered `execution_routes` list. Routes require `route_id`, `engine:
llama_cpp`, one bounded `backend_family` (`cpu`, `cuda`, `rocm`, or `metal`), and an
integer `route_priority`; optional constraints include explicit accelerator vendor or
family, minimum VRAM bytes, OS families, and architectures. V2 forbids the ambiguous
`requirements.gpu` field. These declarations come only from curator-controlled escrow
`SOURCE.json` metadata in explicitly requested v2 generation. Filenames,
quantization, classifier GPU heuristics, hardware brands, and prose never create a route.

The planner ranks eligible artifact-route pairs by model priority, route priority,
model id, then route id. CPU requires no accelerator. CUDA requires observed NVIDIA
hardware, ROCm observed AMD hardware, and accelerated routes fail closed when presence
or vendor is unknown. Metal likewise requires explicit observed facts rather than
platform folklore. A declared VRAM minimum is ineligible below the minimum and
unresolved when VRAM is unknown. An unresolved accelerated route does not block an
eligible CPU route or a proven route on a lower-priority model.

Selected v2 entries include stable artifact identity plus route identity,
`runtime_requirement`, `runtime_availability_status: not_evaluated`, and
`runtime_provisioning_required: unknown`. Selection never imports or probes llama.cpp,
CUDA, ROCm, or Metal. The future chain is hardware observation → artifact and route
selection → runtime provisioning → artifact acquisition/hash verification → exact
artifact/runtime commissioning. Exact `gpu_layers` planning is deliberately deferred.

Candidates are classified `eligible`, `ineligible`, or `unresolved`. Only eligible candidates rank, by ascending curator priority then stable model id. Canonical JSON-compatible content, sorted semantic candidates, and no timestamps make profile, manifest, and plan SHA-256 digests deterministic and insensitive to input model ordering.

The installer dry-run retains its legacy `HardwareProfile` only as an explicit adapter and consumes the planner-selected id rather than `models[0]`. `manifest-v1.json` remains a tiny demo fixture, not production weights. Future composition is: selection plan → acquisition and exact hash verification → explicit GGUF commissioning. Commissioning does not re-select. `gpu_autosetup.py` retains historical NVIDIA/CUDA, AMD/ROCm, Apple/Metal, and CPU-fallback intent, but its probes and package installation are not this boundary.

The usable input pipeline is now **bounded read-only hardware observation →
`HostInventoryManifest` → `LocalInferenceHardwareProfile` → deterministic
selection plan**.  The disk adapter consumes the collector's established
`free_bytes`; the existing memory collector's `total_bytes` remains the only RAM
source.  Unreadable sources omit their fact, so the profile records `unknown`
rather than manufacturing `false`.

CPU instruction support is observed separately from CPU names and architecture.
On Linux x86, complete `/proc/cpuinfo` `flags` records explicitly answer AVX,
AVX2, and AVX512F; all processor records must contain a token for the host fact
to be true.  On Windows x86, the direct read-only
`IsProcessorFeaturePresent` API answers those three facts when available.  API
absence remains unknown.  macOS and non-x86 hosts currently leave x86 AVX facts
unknown/not applicable; Apple Silicon is not assigned fake negative values.

Linux accelerator observation enumerates `/sys/class/drm/card*` and may record
PCI vendor/device identifiers plus a driver's explicit
`mem_info_vram_total`.  Known PCI vendor IDs normalize only hardware identity.
A complete empty DRM enumeration is explicit absence; missing/unsupported DRM,
permissions, Windows, and macOS accelerator sources remain unknown.  Windows and
macOS have no accelerator implementation in this task because no safe
standard-library/direct-API source was established.  Dedicated VRAM remains
unknown when the driver does not expose it; shared/unified RAM is never relabeled
as VRAM.

Every observed accelerator remains in a deterministic device list.  Only one
device can populate singular v1 vendor/family/VRAM fields.  Multiple devices
leave those fields unresolved instead of selecting a guessed “best” GPU.
Hardware presence, runtime/backend availability, and runtime commissioning are
three separate states: vendor identity never populates `backend_family`, and
observation grants no download, installation, loading, commissioning,
inference, provider, network, or host-mutation authority.  Consequently,
manifest-v1 `gpu: true` remains unresolved even when GPU hardware is observed.

`python -m scripts.local_inference_hardware_observation` renders canonical JSON
for operator review and can optionally evaluate a supplied local pinned manifest.
It invokes no shell or subprocess and performs no network or mutation.  Runtime
backend/version observation and commissioning remain future, separately governed
work.

## Runtime provisioning handoff

The metadata-only handoff is specified in [`local_runtime_provisioning.md`](local_runtime_provisioning.md). Route hardware compatibility, exact runtime target selection, and actual runtime installation/commissioning are three separate states; neither selection planner claims installation.

## Production filesystem custody

Safe curator evidence reads independently require descriptor-relative `open`,
no-follow and directory-only flags, `fstat`, and descriptor-safe traversal.
Production publication additionally requires descriptor-relative `mkdir`,
Linux `O_TMPFILE` support on the pinned destination filesystem, and one usable
fd-bound `linkat` route. Direct `linkat(AT_EMPTY_PATH)` requires
`CAP_DAC_READ_SEARCH` on Linux, so ordinary production publication instead uses
the documented, mechanically fixed `/proc/self/fd/<fd>` source with
`AT_SYMLINK_FOLLOW` when direct linking is unavailable to the caller. This
kernel fd exposure grants no general pathname authority. If neither route is
usable, publication fails closed. There is no named staging fallback, and no
privilege escalation is requested or granted.

Evidence files are opened relative to pinned escrow directory descriptors.
Publication descent and destination inspection remain relative to the pinned
final-parent descriptor. The deterministic bytes are written and fsynced through
an unnamed temporary-file descriptor, and the no-overwrite publication primitive
links that exact inode into the parent. Success additionally requires the opened
destination to have both the staged inode identity and approved bytes (or, for an
identical concurrent publication, the exact approved bytes), followed by a
successful parent-directory fsync. The externally requested publication chain is
revalidated by directory identity before and after publication.

Failures after linking deliberately do not unlink the destination by name: a
racing actor may already have replaced it. Such failures preserve any residual
entry and report a hard publication/durability error rather than risking deletion
of a competitor inode or returning a successful receipt. These controls grant no
acquisition, model loading, inference, commissioning, or network authority.
