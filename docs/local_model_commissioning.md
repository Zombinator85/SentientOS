# Production-local model commissioning

The historical `sentientos.local_model_commissioning:v1` bundle described below is
retained as a **legacy, non-production inspection and calibration handoff**. It is
not accepted by production activation. Production v2 lives in
`sentientos.local_model_production_commissioning`: it reconstructs the selection,
provisioning, installation, import-verification, backend-verification, and acquisition
objects through their canonical composers; runs the exact installed interpreter in an
isolated bounded subprocess; and constructs llama.cpp in `vocab_only` mode. That probe
does construct bounded model/vocabulary state, but performs zero generations and grants
no commissioning or inference authority.

Production v2 derives `n_gpu_layers=0` for CPU routes and a conservative single-layer
offload for a verified accelerator route. The latter proves only a conservative
accelerated construction, never full-model offload. Ambient torch/CUDA discovery is
not used. A digest-bound authorization naming the exact commissioning-plan digest is
required before load. Exactly one repository-owned smoke prompt then passes through
`GovernedLocalModelInvoker` and the control plane before a deterministic commissioning
receipt can be written.

Activation is a separate atomic replacement of one activation JSON file and performs
no inference or daemon startup. Setting `SENTIENTOS_LOCAL_MODEL_ACTIVATION` to that file
makes the existing chat service revalidate the embedded commissioning receipt, current
GGUF bytes, exact active identity, and authority map before using the existing governed
invoker. Without a valid activation, the production path cannot load acquired bytes;
legacy null/echo development fallback remains machine-distinct simulation.

Commissioning proves that one exact, operator-supplied GGUF and one exact existing
`ModelConfig` can occupy SentientOS's governed production-local model slot. It binds
the resolved artifact path, byte size, SHA-256, optional adjacent JSON sidecar digest,
candidate index, configuration digest, and the existing `LocalModelAuthorityMap`
preview. It does **not** prove model quality, discernment quality, adoption, consent,
policy, trial suitability, or authority.

Model selection and acquisition remain external prerequisites. This workflow never
downloads, copies, converts, quantizes, modifies, recommends, or redistributes model
bytes. Its runtime library performs no network/provider inference, semantic
generation, calibration cases, trial enrollment, memory/goal/action mutation, Git
operation, or repository write.

## Custody and safe roots

Both roots are explicit operator inputs. `--allowed-root` must already exist and the
GGUF must be a readable regular file beneath it. Traversal, URL-like inputs, symlinks
(including symlink escape), missing artifacts, non-regular artifacts, provider engines,
and simulation backends fail closed. Legitimate external roots remain supported.

`--state-root` must have an existing parent and must be outside this repository. Render
creates a new private directory and refuses to overwrite a nonempty one. It stores only
bounded JSON metadata: `commissioning-manifest.json`, `artifact-identity.json`,
`model-config.json`, `authority-preview.json`, `verification-result.json`, and
`calibration-handoff.json`. The model itself remains in operator custody.

## Stages

1. **Inspect** streams the external file for SHA-256 and size, identifies the adjacent
   sidecar used by `LocalModel`, records local `llama_cpp` availability, and calculates
   the canonical candidate configuration digest. It writes nothing.
2. **Render** writes deterministic JSON accepted by the existing `ModelConfig` schema,
   then calls the existing authority-map builder. The preview exposes its model/map
   IDs and digests, semantic/content/sidecar/configuration identities, candidate index,
   resolved path, eligibility, purposes, provider/tool/memory/action posture,
   disposition, and reasons. A preview is not an authority grant.
3. **Verify** independently re-reads every artifact, recomputes manifest links,
   re-inspects the external bytes, and reconstructs configuration, authority preview,
   and handoff. Replacement, size/content changes, path/index/sidecar/configuration
   changes, or mixed observations block verification.
4. **Verify with load** optionally instantiates the candidate through the real
   `LocalModel` backend path and requires
   `LocalModelAuthorityMap.record_for_active_identity` to match its exact
   `ActiveModelIdentity`. It performs no generation. Missing `llama_cpp`, an unavailable
   model, or loader failure is reported as `external_prerequisite_unavailable`; no
   echo/null/simulated result is labeled production proof.
5. **Doctor** is zero-generation and runs zero calibration cases. It reports artifact,
   configuration, dependency, production/fallback, preview, optional exact-load,
   live-discernment, and calibration-attempt posture.
6. **Handoff** emits deterministic, non-authoritative coordinates for the existing
   `sentientos.discernment_calibration` subsystem. It neither runs calibration nor
   enrolls or submits a blind-trial participant.

Inspection, authority preview, process-real load verification, live calibration, and a
blind trial are distinct gates. Commissioning completes only identity plumbing; an
operator must separately invoke the existing calibration CLI and separately decide any
later trial action.

## JSON-only examples

```console
python scripts/local_model_commissioning.py inspect --model-path /models/a.gguf --allowed-root /models
python scripts/local_model_commissioning.py render --model-path /models/a.gguf --allowed-root /models --state-root /custody/a
python scripts/local_model_commissioning.py verify --state-root /custody/a
python scripts/local_model_commissioning.py verify --state-root /custody/a --load
python scripts/local_model_commissioning.py doctor --state-root /custody/a --require-load-verification
python scripts/local_model_commissioning.py handoff --state-root /custody/a
```

After a successful process-real proof, an operator may point
`SENTIENTOS_MODEL_CONFIG` at `/custody/a/model-config.json` and invoke the existing
`scripts/discernment_calibration.py doctor` or `run` command with an explicit external
runtime root. Commissioning never performs that handoff automatically.
