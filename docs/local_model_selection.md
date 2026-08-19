# Deterministic local model selection

`sentientos.local_model_selection:v1` is the canonical metadata planning boundary from a supplied read-only host inventory and a trusted pinned escrow manifest to exactly one eligible artifact. It performs no probing, network access, download, installation, loading, inference, commissioning, host mutation, or authority grant.

The immutable hardware profile records inventory identity/digest, OS and architecture, exact total RAM bytes, optional available storage, tri-state AVX/AVX2/AVX512 facts, explicit accelerator observations/vendor/family/VRAM/backend, missing facts, and warnings. The adapter uses `HostInventoryManifest` fields directly. It never derives instruction sets from CPU text, VRAM from labels, or runtime backends from hardware brands. Facts not explicitly supplied remain `unknown`.

RAM minimums use GiB (`ram_gb_min * 1,073,741,824`) despite the historical field name; no guessed OS overhead is deducted. Architecture aliases are limited to `amd64`/`x86_64` and `aarch64`/`arm64`. Required CPU features pass only on explicit true, fail as incompatible on false, and remain unresolved on unknown. Historical curator `avx` booleans retain their literal manifest meaning; the planner does not reinterpret classifier history.

Manifest file planning first calls `hf_intake.manifest.validate_manifest()`, preserving pinned checksum, URL, license, and escrow custody. Mapping planning is pure and intended for already-trusted metadata and tests. CPU-capable (`gpu: false`) entries may qualify. Manifest v1 `gpu: true` cannot describe CUDA, ROCm, or Metal compatibility and therefore remains unresolved as `manifest_accelerator_backend_unspecified`; filenames are never used as evidence.

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
