# Local runtime import verification

This boundary gives an operator one narrowly authorized, digest-bound probe of
the exact private environment created by offline installation. The probe uses
that environment's absolute interpreter with isolated mode (`-I`), bytecode
disabled (`-B` and `PYTHONDONTWRITEBYTECODE`), a non-repository working
directory, no shell, and a 60-second timeout. It strips Python/package-manager
injection variables and `LLAMA_CPP_LIB_PATH`, while retaining genuine host
loader discovery such as `PATH`, `CUDA_PATH`, `HIP_PATH`, `LD_LIBRARY_PATH`, and
`DYLD_LIBRARY_PATH`.

Before every executed probe, all six plan-bound source wheels and every
installed distribution `RECORD` are reverified. The llama-cpp-python `RECORD`
also supplies a deterministic import-source manifest for the exact package
initializer, low-level Python module, and selected packaged native library.
An existing success receipt does not suppress the current probe. The helper
imports `llama_cpp` only in the installed interpreter, checks the interpreter's
actual executable, Python version, implementation and SOABI, checks both 0.3.35
version witnesses and exact module paths, and hashes the imported Python and
loaded native bytes while the child is running. Those observations must equal
the pre-probe `RECORD` custody, and full installation verification runs again
before an immutable receipt is published. The complete installed environment
file manifest must also remain unchanged.

SentientOS does not explicitly call backend initialization, GPU-offload or
system-information queries, or construct `Llama`. Import is nevertheless Python
execution: llama-cpp-python 0.3.35 runs its own package initialization and native
binding code, including its upstream `_lib.llama_max_devices()` call. That
third-party import behavior does not constitute a SentientOS backend capability
query, backend selection, model load, commissioning, inference, or execution
authority.

The custody chain is intentionally non-transitive:

- cataloged **does not mean** acquired;
- acquired **does not mean** installed;
- installed **does not mean** import verified;
- import verified **does not mean** selected backend verified;
- backend verified **does not mean** model loaded;
- model loaded **does not mean** commissioned;
- commissioned **does not mean** first boot complete.

Success proves only that the exact installed Python package imports and its
exact packaged native llama shared-library bytes can be loaded by this host at
that time. Backend prerequisites, GPU/device capability, model artifact
acquisition, GGUF loading, inference, commissioning, and first boot remain
deferred. General runtime execution authority remains false.
