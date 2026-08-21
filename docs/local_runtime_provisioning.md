# Local runtime provisioning planning

`sentientos.local_runtime_catalog:v1` remains the published exact-environment contract. Its synthetic entries continue to bind OS, normalized architecture, Python implementation, and exact interpreter SOABI through `python_abi`; existing v1 custody is not reinterpreted.

`sentientos.local_runtime_catalog:v2` is the wheel-compatibility custody contract. Every `python_wheel` entry supplies non-empty curator metadata for `python_tag`, `abi_tag`, `platform_tag`, `supported_python_versions`, and `backend_variant`. The exact distribution, version, Python tag, ABI tag, and platform tag parsed from the filename must agree with those explicit fields. Parsing cross-validates custody; it never creates missing metadata. Catalog order and supported-version order are normalized, while all compatibility and variant metadata participates in the catalog digest.

## Python and ABI facts

SOABI is an observed interpreter property. A wheel ABI tag is artifact compatibility metadata. They are different facts and different namespaces. In v2, `py3` accepts Python 3 only when its exact `major.minor` is also in the curator's bounded `supported_python_versions` allowlist. Exact `cp310`, `cp311`, and `cp312`-shaped tags require CPython and that exact interpreter minor. Floating version expressions are not accepted.

The wheel ABI tag `none` encodes no Python-ABI restriction and is never compared with SOABI; it does not waive the Python-version, implementation, OS, architecture, or platform checks. A supported explicit CPython ABI tag is compared exactly with observed SOABI. Other ABI classes, including `abi3`, remain unsupported and fail closed rather than being guessed.

## Bounded platform compatibility

V2 deliberately is not a generic wheel resolver:

* `win_amd64` requires Windows and normalized `x86_64`. It requires no libc or macOS fact.
* `manylinux_<major>_<minor>_x86_64` requires Linux, normalized `x86_64`, explicitly observed glibc, and glibc at least the encoded floor. Older glibc is incompatible; musl is not glibc; missing or malformed libc identity is unresolved and blocks selection.
* `macosx_<major>_<minor>_arm64` requires Darwin/macOS, normalized `arm64`, and an explicitly observed macOS release at least the encoded deployment floor. An older release is incompatible and an unknown release is unresolved.

Architecture aliases remain deterministic: `amd64` maps to `x86_64`, and `aarch64` maps to `arm64`. Unsupported platform shapes fail closed. The v2 environment profile preserves SOABI and adds bounded standard-library observations for libc family/version and macOS version; missing facts remain explicit rather than becoming compatibility.

## Planning and authority boundary

A selected v2 plan carries catalog schema, runtime id, backend variant, Python/ABI/platform tags, supported Python versions, exact package/artifact custody, route/model identity, prerequisite codes, and deterministic catalog/environment/plan digests. `backend_variant` distinguishes curator-defined CPU, CUDA, ROCm, HIP, or Metal variants but grants no execution authority.

Wheel compatibility does not establish accelerator readiness. CUDA driver/toolkit, compute capability, ROCm/HIP, and Metal prerequisites remain separate `external_prerequisite_codes` with `prerequisite_status = not_evaluated`. The planner performs no network, index query, download, installation, subprocess, runtime/model import or load, commissioning, host mutation, or authority grant. A selected plan hands its exact identity to [local runtime artifact acquisition](local_runtime_acquisition.md), which establishes verified byte custody but not installation, import availability, or commissioning.

Historical `optional_deps`, `gpu_autosetup.py`, and `Start-All.ps1` installer hints are not catalog authority. No trusted production runtime entry is introduced here: `production_runtime_catalog_ready = false`. Tests use only synthetic `.invalid` fixtures. A future curator must separately choose and verify an exact production release and variant before any artifact enters custody.

## Production runtime catalog custody (0.3.35)

`manifests/local-runtime-catalog-v2.json` is the canonical production runtime custody file. Reconstructed after loss of an ephemeral workspace from recorded custody anchors, it pins seven first-party `abetlen/llama-cpp-python` 0.3.35 GitHub release assets with MIT license identity, exact wheel filename and tags, byte size, SHA-256, conservative Python 3.10/3.11/3.12 allowlist, and deterministic priority. Coverage is Windows x86_64 CPU, CUDA `cu124`, and HIP Radeon; Linux x86_64 CUDA `cu124` and ROCm `rocm72`; and macOS arm64 CPU fallback and Metal. The official CPU Linux wheel remains omitted as `unsupported_production_artifact_shape` because its compound `manylinux2014_x86_64.manylinux_2_17_x86_64` platform tag is outside the bounded v2 contract.

The upstream accelerator-wheel release stream need not advance in lockstep with the normal PyPI display, so custody uses exact official release tags rather than PyPI “latest”. Recovery downloads reproduced every recorded SHA-256 and size and matched the official GitHub release-asset digests. Passive ZIP inspection confirmed `METADATA` name `llama_cpp_python`, version `0.3.35`, and each `WHEEL` tag. `docs/development/production_runtime_catalog_provenance.json` records this evidence without becoming a second selection authority.

CUDA entries retain unevaluated prerequisite codes for a CUDA 12.4-compatible NVIDIA runtime/driver and supported compute capability. ROCm entries retain unevaluated ROCm 7.2 or Windows HIP Radeon runtime requirements. CPU and Metal entries add no speculative accelerator prerequisite. All four canonical backend families have independently reproduced entries, so the offline verifier derives `production_runtime_catalog_ready = true`; this grants no installation or execution authority.

Run `PYTHONPATH=. python scripts/verify_production_runtime_catalog.py` offline to cross-check canonical validation, exact release URLs, hashes, sizes, tags, license, anchor reproduction, and provenance. The next boundary is separately governed runtime acquisition and installation; this catalog does not download at runtime, install, import, execute, load a model, or commission anything.
