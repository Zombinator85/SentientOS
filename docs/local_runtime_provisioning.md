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

Wheel compatibility does not establish accelerator readiness. CUDA driver/toolkit, compute capability, ROCm/HIP, and Metal prerequisites remain separate `external_prerequisite_codes` with `prerequisite_status = not_evaluated`. The planner performs no network, index query, download, installation, subprocess, runtime/model import or load, commissioning, host mutation, or authority grant.

Historical `optional_deps`, `gpu_autosetup.py`, and `Start-All.ps1` installer hints are not catalog authority. No trusted production runtime entry is introduced here: `production_runtime_catalog_ready = false`. Tests use only synthetic `.invalid` fixtures. A future curator must separately choose and verify an exact production release and variant before any artifact enters custody.
