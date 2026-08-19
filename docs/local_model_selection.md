# Deterministic local model selection

`sentientos.local_model_selection:v1` is the canonical metadata planning boundary from a supplied read-only host inventory and a trusted pinned escrow manifest to exactly one eligible artifact. It performs no probing, network access, download, installation, loading, inference, commissioning, host mutation, or authority grant.

The immutable hardware profile records inventory identity/digest, OS and architecture, exact total RAM bytes, optional available storage, tri-state AVX/AVX2/AVX512 facts, explicit accelerator observations/vendor/family/VRAM/backend, missing facts, and warnings. The adapter uses `HostInventoryManifest` fields directly. It never derives instruction sets from CPU text, VRAM from labels, or runtime backends from hardware brands. Facts not explicitly supplied remain `unknown`.

RAM minimums use GiB (`ram_gb_min * 1,073,741,824`) despite the historical field name; no guessed OS overhead is deducted. Architecture aliases are limited to `amd64`/`x86_64` and `aarch64`/`arm64`. Required CPU features pass only on explicit true, fail as incompatible on false, and remain unresolved on unknown. Historical curator `avx` booleans retain their literal manifest meaning; the planner does not reinterpret classifier history.

Manifest file planning first calls `hf_intake.manifest.validate_manifest()`, preserving pinned checksum, URL, license, and escrow custody. Mapping planning is pure and intended for already-trusted metadata and tests. CPU-capable (`gpu: false`) entries may qualify. Manifest v1 `gpu: true` cannot describe CUDA, ROCm, or Metal compatibility and therefore remains unresolved as `manifest_accelerator_backend_unspecified`; filenames are never used as evidence.

Candidates are classified `eligible`, `ineligible`, or `unresolved`. Only eligible candidates rank, by ascending curator priority then stable model id. Canonical JSON-compatible content, sorted semantic candidates, and no timestamps make profile, manifest, and plan SHA-256 digests deterministic and insensitive to input model ordering.

The installer dry-run retains its legacy `HardwareProfile` only as an explicit adapter and consumes the planner-selected id rather than `models[0]`. `manifest-v1.json` remains a tiny demo fixture, not production weights. Future composition is: selection plan → acquisition and exact hash verification → explicit GGUF commissioning. Commissioning does not re-select. `gpu_autosetup.py` retains historical NVIDIA/CUDA, AMD/ROCm, Apple/Metal, and CPU-fallback intent, but its probes and package installation are not this boundary.

Live one-click selection still needs explicit collectors for CPU feature booleans, exact RAM, accelerator presence, backend/runtime availability and version, vendor/family, VRAM, and relevant free storage. Those collectors are deliberately out of scope.
