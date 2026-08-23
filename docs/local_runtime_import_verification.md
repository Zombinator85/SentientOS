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
installed distribution `RECORD` are reverified. An existing success receipt
does not suppress the current probe. The helper imports `llama_cpp` only in the
installed interpreter, checks both 0.3.35 version witnesses and package origins,
and byte-witnesses the already-loaded packaged library beneath
`llama_cpp/lib/`. It checks binding attribute presence but never calls those
attributes, initializes a backend, loads a model, or performs inference.

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
