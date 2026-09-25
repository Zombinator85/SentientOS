# Linux CPU two-model production curation

## Established repository capability

The production runtime catalog can represent and select the exact verified Linux x86-64 CPU `llama_cpp` wheel. The frozen successor package for Qwen2.5-Coder 7B and the frozen Microsoft Phi-3 Mini package each bind an exact GGUF identity to a Linux x86-64 CPU route. The deterministic candidate catalog contains exactly those two models.

The candidate is inspection-only, not authoritative deployed custody. On the observed `primary` hardware (Linux x86-64, AVX/AVX2/AVX-512 present, about 64.8 GiB RAM, and accelerator state **unknown**) both CPU routes are eligible. Accelerator unknown is preserved and does not become accelerator absence; CPU eligibility does not depend on either conclusion. Generic selection still returns exactly one best candidate. The experiment must bind A and B explicitly from the independently established eligible identities (or make two preregistered invocations with an exact exclusion); the generic selector is unchanged.

## Frozen identities

Model A is `qwen2.5-coder-7b-instruct-q4-k-m`, artifact SHA-256 `509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c`, through route `qwen25-coder-q4-cpu-linux-x86-64`. Its successor curator package preserves the original package by digest rather than rewriting it.

Model B is `phi-3-mini-4k-instruct-q4-k-m`, from first-party repository `microsoft/Phi-3-mini-4k-instruct-gguf` at immutable revision `a64113399c2f6b8ad3e11c394733a2ddadaa7f33`. The streamed 2,393,231,072-byte artifact matched both its upstream LFS identity and SHA-256 `8a83c7fb9049a9b2e92266fa7ad04933bb53aa1e85136b7b30f1b8000ff2edef`; its first four bytes were `GGUF`. It uses route `phi3-mini-q4-cpu-linux-x86-64`.

The exact candidate is `docs/development/two_model_linux_cpu_catalog_candidate.json`. The two immutable publication intakes are in `docs/development/two_model_mirror_publication_intake.json`.

## External boundaries and next host action

No production provider for `models.sentientos.org`, provider credentials, publication grant/lease, publication receipts, or catalog-deployment authority were available. Status is therefore `model_mirror_provider_configuration_required`. Nothing was uploaded, no publication was faked, and the candidate was not deployed. Publication must use the existing create-only controller with exact local GGUF custody and genuine external authority. Only two successful receipts, complete remote streamed verification, and a genuine installation-scoped deployment transaction may make the catalog authoritative.

Python support remains 3.10–3.12. The observed CPython 3.14 process is not compatible under this production contract. Establish CPython 3.12 externally, then—after publication receipts and authoritative deployment exist—resume on `primary` with:

```bash
python3.12 -m scripts.verify_local_model_catalog_consumer_custody --installation-identity primary
```

This is a planning/selection continuation, not permission to acquire, install, commission, or serve.
