# Offline local runtime dependency custody

Acquisition of a selected five-wheel bundle is a separate operator-confirmed custody step documented in [Local runtime dependency bundle acquisition](local_runtime_dependency_acquisition.md). Selection alone performs no network or filesystem mutation and does not imply that one artifact, the complete bundle, or a runtime is installed.

This capability closes, but does not install, the mandatory Python dependency graph of the curated `llama-cpp-python==0.3.35` runtime. Passive wheel `METADATA` inspection proves the graph:

* `llama-cpp-python==0.3.35` → `typing-extensions>=4.5.0`, `numpy>=1.20.0`, `diskcache>=5.6.1`, and `Jinja2>=2.11.3`;
* `Jinja2==3.1.6` → `MarkupSafe>=2.0`;
* the selected typing-extensions, NumPy, diskcache, and MarkupSafe wheels have no further mandatory runtime requirements. Environment-marker-gated development extras recorded in wheel metadata are evidence, not mandatory edges for these targets.

The curator pins are `typing-extensions==4.16.0`, `numpy==2.2.6`, `diskcache==5.6.3`, `Jinja2==3.1.6`, and `MarkupSafe==3.0.3`. NumPy 2.5.x requires Python 3.12 or newer, and NumPy 2.3.x requires Python 3.11 or newer. NumPy 2.2.6 requires Python 3.10 or newer, so 2.2.6 is deliberately the single common line for the supported CPython 3.10, 3.11, and 3.12 matrix; it is not a dynamic “latest” choice.

The canonical catalog contains 21 exact PyPI wheels: three reusable `py3-none-any` wheels, nine exact CPython/OS NumPy wheels, and nine exact CPython/OS MarkupSafe wheels. Nine sorted bundles cover Windows x86_64, glibc-compatible Linux x86_64, and macOS arm64 for each supported Python minor. Linux compound platform tags are retained verbatim. Their aliases establish a bounded minimum glibc floor of 2.17; selection does not implement general wheel-tag ranking. macOS wheels retain and enforce their 11.0 deployment floor.

`sentientos.local_runtime_dependencies` validates that fixed catalog and maps a supplied `sentientos.local_runtime_environment_profile:v2` to exactly one bundle. It is a bounded lookup, not a PEP 508 solver. The offline verifier compares the catalog with the committed provenance record and performs no network access. Curation used official PyPI release metadata, downloaded each wheel to temporary storage, checked published and observed SHA-256 and byte size, and passively read `WHEEL` and `METADATA`; wheel bytes are not committed.

Selection grants no acquisition or execution authority. It performs no network request, download, subprocess, package installation, runtime import, model load, or commissioning. Dependencies cataloged are not dependencies acquired; acquired wheels are not installed packages; installed packages are not a verified `llama_cpp` import; and an import is not commissioning. Offline installation remains ineligible until both the runtime artifact and this complete exact dependency bundle are present in verified local escrow.
