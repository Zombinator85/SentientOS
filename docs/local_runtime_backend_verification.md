# Local runtime selected-backend verification

This operator-confirmed boundary asks the exact custody-verified
`llama-cpp-python==0.3.35` installation what backend machinery is visible on
the current host. Its chain is deliberately strict:

`cataloged ≠ acquired ≠ installed ≠ import verified ≠ selected backend visible
≠ model compatible ≠ model loaded ≠ commissioned ≠ first boot complete`.

The parent SentientOS process does not import the runtime. After fresh wheel,
installation, and import custody checks, the exact absolute virtual-environment
interpreter runs with `-I -B` in a newly created empty private directory outside
the repository. Injection and synthetic-device variables are stripped while
legitimate loader and device visibility variables are retained. The helper
calls, once each, only `llama_supports_gpu_offload`, `llama_supports_rpc`, and
`llama_print_system_info`. The first query may itself cause pinned upstream
backend registry loading and device discovery.

`llama_supports_gpu_offload=true` does **not** intrinsically mean that the
selected local accelerator is verified: at the pinned llama.cpp revision its
predicate also includes RPC support. Direct-local success therefore excludes
RPC, requires the selected accelerator registry, and rejects competing known
accelerator registries. CPU selection instead requires CPU visibility and does
not require the offload predicate to be false. Thus **CPU-selected does not mean
accelerator-absent**; CPU plus MTL is representable without selecting Metal.

The bounded system-information witness is strict UTF-8, at most 64 KiB, and is
parsed only as pinned `REGISTRY : feature = value | ...` records. Registry-like
words in values or arbitrary text are never evidence. Every syntactically valid
registry identifier, including unknown identifiers, is retained in order;
unknown non-CPU registries make accelerator attribution ambiguous. It is represented
authoritatively by its digest and ordered registry names. Installed
native files under `llama_cpp/lib/` are bound from RECORD by relative path,
size, and SHA-256 before the query and rechecked afterward with the complete
symlink-aware environment manifest.

The exact provisioning plan is required and digest-linked to installation. Its
`external_prerequisite_codes` are retained as catalog provenance: they describe
what the curated route expects and are not claims that individual driver versions
were measured. `backend_prerequisites_verified` means only that runtime-observable
prerequisites needed for this exact backend to be visible are currently
satisfied. It does not certify driver versions, every vendor compatibility
edge, an arbitrary model, model loading, offload layer selection, or execution.
GGUF acquisition, model compatibility/loading, execution-route composition,
inference, commissioning, and first boot remain deferred. General runtime
execution authority remains false.

Success is atomically published beneath the plan-bound receipt root and plan
digest as a private, immutable canonical `runtime_backend_verified` receipt.
Symlinked paths and conflicting existing bytes fail closed. A repeat never skips
installation, fresh import, or the backend probe; only after reconstructing an
identical canonical receipt does it return the operational status
`already_verified_current`, without changing the stored semantic identity.
