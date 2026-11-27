# Rootless Hermes developmental-cycle GPU placement

## Milestone goal and acceptance

Make the rootless developmental cognition runner request a configured, bounded
GPU layer count through the production Ollama session path, while retaining the
generic epistemic session's CPU-only default. The setting must be rejected
before experiment setup when malformed or outside 1–128, and the requested
placement must be retained in run and inference resource evidence.

Acceptance requires focused tests for configuration bounds, developmental
session forwarding, unchanged generic CPU defaults, and evidence recording. A
real-model follow-up is a separate, newly preregistered experiment. It must
verify actual GPU residency and governed release; the requested layer count by
itself is not evidence that the model used the GPU.

## Finding

The developmental cycle's resource guard already requires observed GPU model
placement and stops on CPU fallback. However,
`RootlessExperimentalOllamaDevelopmentalSession` previously omitted the
underlying session's `gpu_layers` argument, leaving its default at zero. The
runner therefore requested CPU-only inference while requiring GPU placement.
The generic `RootlessExperimentalOllamaEpistemicSession` keeps its existing
zero-layer default.

## Implementation

The developmental session now forwards an explicit bounded layer count. The
cycle runner reads `SENTIENTOS_HERMES_GPU_LAYERS` (default `99`), accepts only
ASCII decimal values from 1 through 128, and records the configured request in
the preregistration, initial resource sample, per-inference resource records,
and terminal result or failure record. This records intended placement; runtime
telemetry remains responsible for establishing observed placement.

## Experiments and current limitation

The first 2026-11-19 attempt for task family
`rootless_integer_affine_transfer_low_range_v5` stopped before model inference
after observing CPU-only placement. Its immutable failure record is retained in
the external experiment custody. It does not demonstrate cognition behavior.

A second one-shot attempt used source commit `2b05ac7003e029d1e7b802183a34a7ab2bcf795b`,
seed `20261120`, protocol digest
`742ccee197d4c4a2ec1550cb422dfc2f8fa92e804ebffdf222e119715d2e9ecf`, and a
requested layer count of 99. The run again observed `size_vram_bytes: 0` and
`cpu_only`, timed out without a model response, then recorded a successful
governed unload. No cognitive behavior was measured. The Ollama server log
identified its active inference backend as `library=cpu`; the model load record
reported `layers.offload=0`. This supports an environment/runtime limitation,
not a failure to forward the requested setting. The run's immutable failure
artifact is `cycle-failure.json` in the private experimental custody.

The Windows Ollama 0.12.9 runtime exposed only `library=cpu`. An isolated
official Ollama 0.40.16 payload was then verified without replacing the
installed application. Its startup log detected the RTX 3060 through CUDA, and
`ollama ps` reported the bound 14B Hermes model at `100% GPU`, context 8192.
The runtime packages and model were hash-bound in the external protocol and
experiment custody.

The Windows follow-ups exposed two separate boundaries. Seed `20261122` reached
the owner with caller-asserted synthetic proprioception, but the prompt asked
about the “current” pose; the existing freshness rule correctly changed the
answer to a request for a fresh observation. The prompt now explicitly frames
this as hypothetical planning and labels the proprioception unverified. The
freshness rule was not weakened. Seed `20261123` produced a lineage-verified
`reach` proposal with a consistent `reach` prediction, then stopped because the
secure consequence store does not support Windows descriptor-relative
publication.

Seed `20261124` ran commit `fbe942cb4a6cd125354017834e97010f05d37616` in an
isolated Ubuntu 24.04 WSL checkout, with experiment custody on ext4 and a
separate copy of only the bound Hermes model. The protocol digest was
`ee2b7b53d7fcecb395c8975f07b28e956d5eda310cb892d10da4ab6089142afd`. Runtime
telemetry again observed GPU offload. The pre-action record contains one
source-linked synthetic fact, a verified response lineage, the proposal
`reach` with prediction `reach`, and `action_executed: false`. The synthetic
action was simulated for the fixture; no production action occurred.

The cycle then stopped during governed developmental writeback with
`developmental_inference_not_completed`. The inference receipt records
`runtime_governor:deferred_background_inference_under_host_pressure`. Resource
samples showed `disk_pressure` and `sensor_unavailable`; a later sample also
showed `gpu_pressure`. The runtime governor was preserved as the boundary, and
the experiment did not reach the history-present/withheld/restored comparison.
Governed unload confirmed the model was no longer resident, and GPU memory
returned near its pre-run level. This demonstrates GPU placement and one
synthetic, evidence-linked proposal, not experience retention, learning,
transfer, or improved later decisions.

### Pressure deferral recovery

The pressure-limited run also exposed an opaque handoff: a governor-deferred
writeback surfaced as the same generic incomplete-inference error as other
failures, even though the selected fact identities were not marked processed.
The resident owner now recognizes only the exact governed host-pressure
deferral receipt, completes that tick with an explicit deferred status and
selection identity, and leaves the source facts eligible for a later distinct
tick if the same immutable fact identities are present in a later snapshot. It
does not retain unadmitted evidence payloads in composition state, replay the
deferred tick, or weaken any governor decision.
Malformed output, other denials, and unrelated writeback failures remain
fail-closed. A controlled CPU fake verifies that a deferred tick does not
consume its facts and a subsequent tick writes a record bound to those same
fact identities after an owner restart and a later snapshot with changed
observation times. This validates the retry handoff in software; it does not
remove host pressure or substitute for repeating the full real-model transfer
comparison under a newly preregistered protocol.

The current blocker is a pressure-compliant run of the full developmental
writeback and transfer comparison. Any further attempt requires a new
protocol and seed; prior protocols and failure records are immutable and must
not be retried or overwritten.

### Fresh protocol preflight, 2026-11-20

A new isolated WSL workspace bound the exact Ollama 0.40.16 runtime and the
`hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M` manifest. CUDA detected
the RTX 3060, the requested model was not resident, and 10.7 GiB of GPU memory
was free. The current Windows worktree was snapshotted into a separate ext4
checkout; the original prepared checkout and prior custody were left intact.

The first fresh attempt used seed `2874193361` and external protocol digest
`bde1f57cd48d0c39cc9090c7cbd3df4fc55a6699b6eca6156e24e04fc1089b15`. It
stopped at `synthetic_pre_action_cognition` before any model invocation. The
owner reported a 19,156-character prompt against a hard-coded 16,384-character
budget, with zero selected history records. The failure artifact records no
inference receipts, no developmental records, and a verified model unload.
This is a prompt-budget configuration failure, not a cognition result. The
rootless decision owner now uses the runner's explicit 20,480-character bound,
which accommodates the observed prompt while remaining below the session's
48,000-character ceiling. The invocation was accidentally launched from the
mounted Windows checkout rather than the ext4 snapshot, so its run-level source
provenance is recorded as unavailable. A follow-up must launch from the ext4
snapshot with this correction and a new source-bound protocol and seed; the
failed protocol and its artifact remain immutable.

The corrected retry used seed `1894517263`, external protocol digest
`b66499dbebdf1c66aa091355d3999dbc6503b170741270e95dbb5dc4b8b18856`, and
the ext4 source snapshot. Run provenance verified revision `498bf41` and the
complete staged-worktree digest. The model completed the synthetic pre-action
decision: response lineage was verified, with proposal and prediction both
`reach`; the fixture simulated the action and recorded no production action.
During that call the runtime observed full GPU offload, with 1,232 MiB free.

The subsequent developmental writeback was denied by the enforced runtime
governor as `deferred_background_inference_under_host_pressure`. Its bound
host-resource report named `gpu_pressure` and `sensor_unavailable`; the policy
selected both GPU-pressure and incomplete-telemetry rules and did not authorize
automatic readiness. Governed writeback produced no developmental record, so
the run did not reach task-family acquisition, the history ablation, or held-out
transfer. The model was verified unloaded afterward. This provides a verified
synthetic proposal under GPU execution, not retained experience or learning.
Any further cycle needs a new protocol and seed, plus enough governed GPU and
telemetry headroom for the writeback inference; the governor must not be
bypassed.

The next fresh cycle used seed `1736051987`, protocol digest
`f4809bef322b89875140d70529fdc85bc9fa14f6531d1966087b72dd29663561`,
and the ext4 source snapshot. It bound 32 of the model's 40 layers to the GPU
and 8 to CPU. Runtime telemetry reported about 7.97 GiB resident and 3.2 GiB
free, below the configured 85% GPU-pressure threshold; telemetry was complete
and the governor deferred only for `sensor_unavailable`, which did not prohibit
the governed calls. The synthetic pre-action decision again had verified
lineage, proposal `reach`, prediction `reach`, and no production action.

Governed developmental writeback succeeded and retained history record
`devrec-127c73ee74991bbcf4ef11fc`. The run then stopped at task-family
acquisition: the history-present response was 1,455 bytes and exceeded the
objective suite's 1,024-byte scoring bound; the history-withheld response was
1,199 bytes and did not provide the required `answers` shape. No held-out
transfer comparison completed, so this is evidence of governed writeback and
retention, not evidence of learning or transfer. The immutable failure record
is `cycle-failure.json` in private custody under run
`rootless-cognition-cycle-e0d11de9dc7640259f3a`.

The scorer now verifies the complete response digest before classifying an
oversized response as `invalid_answer`, without parsing or retaining the
response bytes. This allows malformed or over-bound answers to remain explicit
negative evidence and permits a comparison to continue when its protocol
allows it. Objective acquisition now uses a simple task-specific JSON schema
(`answer` for a single probe, `answers` for a suite) instead of a `oneOf`
schema. These changes address the observed scorer abort and response-shape
ambiguity; they do not retroactively change the failed run. A subsequent
experiment requires a new source-bound protocol and seed.

### Fresh follow-up: compact history prompt bound

A new source-bound run used seed `3417259081` and protocol digest
`40bb1e62080e33bbd0840bf05b3fb7842116bc534104598d7f1aeb560069a7cf` against
the pinned model manifest and isolated Ollama 0.40.16 runtime. The runtime
verified CUDA placement with 32 requested GPU layers; the run's GPU samples
stayed below the 85% pressure gate. Synthetic pre-action reasoning again
produced the lineage-verified `reach` proposal and matching prediction, with no
production action. Governed writeback retained record
`devrec-4683d0ffa6ff08c614e7e6d1`.

The run stopped before objective task-family acquisition. Its history-present
prompt remained 21,198 characters after the most compact `compact_refs_only`
projection, exceeding the runner's 20,480-character input cap. The failure
artifact is `cycle-failure.json` in private custody under run
`rootless-cognition-cycle-7a737477009d4d7bbe58`; it confirms target-model
unload and return to 1,142 MiB host GPU use. The history-present, withheld, and
restored calls did not produce scoreable objective evidence, and no transfer
comparison completed. No learning claim is supported.

The rootless runner's bounded input cap is now 24,576 characters, still below
the cognition owner's 48,000-character maximum. This accommodates the exact
observed compact prompt with about 16% headroom while leaving model context,
output limits, selection policy, and governor behavior unchanged. The next
cycle requires a new source-bound protocol and seed; the failed run remains
immutable.

The next cycle used seed `3417259082` and protocol digest
`805ac3f3672e787f7cc03bb913eafd4ca6cf5f87abb77ddb6caab9eb45e62b98`, with the
same pinned model and 32-layer placement. The 24,576-character bound allowed
the complete run to proceed through acquisition and into held-out transfer.
The acquisition suite was scored at 3/3 correct in all three conditions, with
no history-associated correctness change; this is a control outcome, not
transfer evidence. Governed writeback produced records
`devrec-8d2624edfa92112f26dfe3fc` and `devrec-8c029ca8f2b3b0f518cd5202`.

The held-out task-family transfer comparison itself completed with scores 0/3
correct in history-present, 1/3 in history-withheld, and 0/3 in
history-restored. The present/restored equality and difference from withheld
are a stable history-associated response effect for this one episode; its
direction is worse performance with the admitted history. It is evidence of a
possible history-associated interference in this task, not a general learning
claim. The acquisition control remained 3/3 in every condition.

After that comparison, the follow-on developmental writeback stopped with
`experiment_history_binding_drift`. Its protocol had no objective task
descriptor and bound both extant records, consistent with a general cognition
writeback comparison; the failed call did not persist its actual selection
diagnostic, so the precise source of the drift is not yet established. The
write-once failure artifact is `cycle-failure.json` under private run
`rootless-cognition-cycle-4d83d0e99c704fa2af92`; it verifies model unload and
return to 1,151 MiB GPU use. The fail-closed history-binding check remains
intact. The owner now records protocol and actual selection identities,
digests, and available/omitted record metadata when this check fails, so the
next source-bound run can identify and correct the specific preflight mismatch
without weakening the condition binding.

### Fresh follow-up: hosted recall input bound

Seed `3417259083`, protocol digest
`23ad89d5f14c272168df5ae47c390d9dbdf2aa4b625ca5a422677d02e8d955a5`, passed
the objective transfer and reached the hosted companion history-recall path.
The acquisition task scored 3/3 in all conditions. The held-out task scored
0/3 in all conditions; its responses differed and restoration was unstable,
so the comparison did not show usable transfer or a correctness gain.

The run then stopped with `cognition_input_budget_exceeded` in the hosted
historical-recall request. The immutable failure record for
`rootless-cognition-cycle-455a60d4a21e426d8e25` shows a 16,384-character cap:
even the zero-history prompt was 19,883 characters, while the compact
two-record prompt was 23,168. The model was unloaded afterward, returning GPU
use to 1,151 MiB. The intervention and replay owners now share the rootless
runner's 24,576-character limit, allowing the observed two-record prompt to
fit without changing history ranking or governance.

### Fresh follow-up: delivered-history lineage

Seed `3417259084`, protocol digest
`0498e81bd342dc7dd083d31c747e0330f2a7e98b43b88031be5d92d2953a18b4`, passed
the hosted-recall prompt budget. The acquisition control scored 3/3 in all
conditions; the held-out task scored 0/3 in all conditions and restoration was
unstable, so it provided no evidence of transfer or a history-linked accuracy
gain.

The hosted history-recall response reached resident cognition and cited one
record within the retrieved set, but delivery verification failed. The chat
linkage advertised three available prior records while the observation bound
two records after prompt-budget selection. This was an owner-to-transcript
lineage mismatch, not evidence that the requested historical field was
recognized; the response disposition was `ask`. The failure artifact for
`rootless-cognition-cycle-4aaf822a6dd2454d8b9e` verifies governed unload and
return to 1,152 MiB GPU use. `ResidentCompanionInteractionResult.prior_record_ids`
now uses the observation's selected record IDs, so transcript lineage names
only the history actually delivered to the model.

### Fresh follow-up: withheld-history citation violation

Seed `3417259085`, protocol digest
`62e1f4646eb1b4e98a8842c807f1ca6f075562920298dbfda6ceef5b746de006`,
passed hosted-recall delivery verification. The ordinary recall response was
delivered through resident cognition and cited a record in the selected
history, but its disposition was `ask`; this is not a successful recognition
of the target field. In the subsequent controlled history intervention, the
`history_present` response cited an allowed record. The `history_withheld`
response cited `devrec-1a0d4317c50cbaba8f42b18f`, which was not available in
that condition, so strict history binding correctly rejected it and stopped
the run before `history_restored`. The terminal failure is
`companion_interaction_decision_invalid` in run
`rootless-cognition-cycle-0cfa1c47de4d49bea4cd`; the governed model unload
returned GPU use to approximately 1,159 MiB.

The owner now retains a bounded diagnostic containing condition ID, protocol
ID, parser validation code, and output digest when this validation fails. It
does not retain or surface the invalid response as an accepted decision. This
improves failure attribution while preserving fail-closed citation behavior.
The next experiment should determine whether this was an isolated fabricated
citation or a repeatable failure mode; no transfer or stable intervention
effect can be inferred from this incomplete comparison.

### Fresh follow-up: interrupted cycle after persisted transfer scores

An initial preregistered attempt with seed `2718281828` stopped at model
manifest preflight with `pinned_hermes_manifest_outside_experimental_custody`
before model load or inference and before a run failure artifact could be
created. A read-only resolver check then confirmed the pinned manifest was
present under the private experiment workspace. The seed was not reused.

The citation-diagnostic change was copied into the isolated ext4 source
checkout, and the checkout's source and worktree fingerprints were bound in a
new protocol. Seed `3141592653`, external protocol digest
`655e3ea148c6c8ebf463c1cc4d0782307935f2aa3e4dd2dcbd414de9426cd4d9`, used the
pinned Hermes 4 14B Q4_K_M manifest and requested 32 GPU layers. The run
persisted all three-condition objective acquisition and transfer experiment
records: acquisition scored 3/3 in history-present, withheld, and restored;
held-out transfer scored 0/3 in all three conditions. The transfer run's
history restoration was unstable, and neither objective comparison showed a
history-linked correctness gain.

The rootless runner then disappeared before writing either its terminal
`cycle-result.json` or `cycle-failure.json`. Its run directory retains 15
completed inference receipts and the valid acquisition and transfer
experiment payloads, but no completed hosted history-intervention result.
When checked, the runner process and Ollama server were absent and GPU use was
back near baseline; because the governed unload receipt is missing, this is
recorded as an externally interrupted, incomplete cycle rather than a
verified unload. The persisted objective comparison payloads support the
bounded scores above; the overall cycle is censored and supports no learning,
transfer, or model-independent continuity claim.

The runner now writes a private, write-once stage checkpoint at phase
boundaries, including the source and preregistration bindings but excluding
prompts and model output. This should make the last entered phase observable
after a future external interruption even when the runner cannot write its
normal terminal artifact; that crash-recovery behavior remains to be exercised.

### Fresh follow-up: stage journal and repeated invalid withheld citation

Seed `1618033988`, external protocol digest
`c290a0949751530c97282793b84450d5cb8784d00ebb649ed2fb16f0ca881839`, ran
against the journal-enabled source. Six write-once stage checkpoints were
persisted, including `controlled_history_intervention`, confirming that the
journal captures entered phases with source and protocol bindings. The
acquisition suite scored 3/3 in all three conditions; disjoint-probe transfer
scored 0/3 in all three conditions. Neither showed a history-linked
correctness change.

The controlled intervention again rejected the `history_withheld` response
with `companion_interaction_history_binding_invalid`. This time the failure
artifact retained the bounded diagnostic (condition ID, protocol ID, parser
code, output digest), and governed unload was verified at 733 MiB host GPU
use. The overall cycle remained incomplete because rejection stopped the
trial before history restoration.

Across two source-bound runs, an unavailable record citation has now repeated
in the withheld condition. The trial owner now has a scoped outcome path for
completed controlled responses that fail schema or citation validation: it
normalizes them to a rejected abstention, stores only the receipt/output
digest and bounded validation code, and continues the preregistered remaining
conditions. Ordinary hosted chat retains its fail-closed behavior. This
behavior was exercised in the subsequent run below; the prior runs remain
immutable and incomplete.

### Fresh follow-up: rejected-response continuation exercised

Seed `1414213562`, external preregistration digest
`41e1b4e623b6cf9858ff35981f7932368cd59d6cfd47cef0cdcf268e4db4955f`, ran
against the source-bound rejection-and-continue implementation with the pinned
Hermes 4 14B Q4_K_M model and 32 requested GPU layers. The run completed as
`rootless-cognition-cycle-1e3f877fb56242c5b2c0`; all six stage checkpoints,
including the controlled intervention and complete-result persistence, were
written.

The `history_withheld` decision again failed history binding with
`companion_interaction_history_binding_invalid`. The controlled experiment
recorded that response as `rejected_invalid_output`, normalized it to abstain,
and continued to the `history_restored` condition, which was validated. The
run's semantic qualification is `invalid_condition_response_rejected`; it
observed no history-associated decision difference, no cognition change, no
new action-decision change, and no established performance improvement. The
objective acquisition suite was scoreable but scored 0/3 in each condition.
For the history-present acquisition, the model's answers for inputs 3, 4, and
5 were 8, 11, and 14; the preregistered mapping was `3*x+2`, whose values are
11, 14, and 17. The history-transfer stage was skipped because the withheld
baseline did not meet the preregistered competence threshold. This is direct
evidence of a systematic intercept error in this small arithmetic probe, not
evidence of learning or transfer.

The repeated withheld-condition rejection exposed a diagnostic limitation:
history citation validation collapsed malformed IDs, duplicate IDs, and
well-formed but unavailable IDs into one code. The parser now reports these
bounded failure classes separately (`...history_ids_not_list`,
`...history_ids_too_many`, `...history_id_format_invalid`,
`...history_ids_duplicated`, and `...history_id_not_allowed`). It records no
raw citation values or response text. This is a measurement-quality change;
the earlier immutable run artifacts retain their original generic code, and
the reason for their rejection cannot be recovered from those artifacts. A
future preregistered run can now distinguish model formatting from condition
binding errors while preserving the existing fail-closed behavior.

The transfer gate now preserves the precise reason a retained-history
precondition failed. Missing or malformed selected facts are reported as
`retained_history_facts_unavailable`; a readable history set with no matching
consequence record is reported as
`retained_history_does_not_match_probe_pattern`. Both cases skip the probe,
but only the latter supports the narrower claim that the available records
were checked and did not match. Earlier persisted run records are immutable
and retain their original reason code.

The terminal result records `governed_release_completed`; its host-wide GPU
sample afterward was 901 MiB used, 3% utilization, and 47.3 C. This is a
synthetic rehearsal of the scoped response-handling path, not evidence of
developmental learning, real-world consequence attribution, or cognitive
continuity. The stage journal's normal-completion path is exercised; crash
recovery remains untested. Raw model responses are not included in this
record.

The runner now writes new stage checkpoints as digest-bound v2 records and adds
a bounded journal-integrity summary to new failure artifacts. The summary
checks filename/sequence agreement, run binding, checkpoint digests, and
sequence continuity; it does not reconstruct execution state or resume a
cycle. Earlier v1 checkpoints and failure artifacts remain unchanged.

### Follow-up prompt refinement: explicit affine parameter derivation

The 0/3 acquisition result identifies a more specific next-step hypothesis
than the earlier citation failures: despite receiving two verified calibration
examples and the affine formula, Hermes returned the sequence for `3*x-1`,
indicating that the intercept was misderived. The task descriptor now states
the calculation explicitly for both settings: for an acquisition mapping,
take `b` from the output at input 0 and compute `m` as the difference between
outputs at inputs 1 and 0; for history-conditioned transfer, compute
`m=(y2-y1)/(x2-x1)` and then `b=y1-m*x1` from two distinct evaluator-correct
rows, checking the resulting formula against all correct rows. Incorrect or
unscored history remains excluded as mapping evidence.

The history projection now derives a bounded negative pattern when one
score-bound source record contains at least three incorrect points fitting one
integer affine rule. It stores the relation as `rejected_affine_guess`, binds it
to its source run, task, score, and incorrect-example digests, and marks it as
an exact-evaluator-rejected model guess. The projection validator rederives
this pattern from the retained incorrect rows before prompt binding. The v19
projection also binds the complete prompt digest, and the owner checks that
against the governed inference request. Before issuing it, the owner verifies
that each canonical selected task-family record packet is present as a
substring in the exact prompt and records only its answer-free digest and
presence flag. This is a serialization check, not evidence of model attention.
The owner also verifies that each complete serialized negative-example
packet, including any rejected guess, is present in the prompt and that the
guess count matches the projection. Projection
validation requires the negative rows to have the exact
integer input/output shape and an explicit incorrect score before deriving the
guess. The task prompt tells the model not to reuse or extrapolate the rejected
relation. It remains excluded from the candidate strategy fitter; only
evaluator-correct examples can support the mapping. This lets history rule out
a demonstrated failed strategy without promoting that strategy into knowledge.

The owner preserves the distinction in the prompt projection: evaluator-correct
rows populate `examples`, while evaluator-incorrect rows populate the separate
`prior_incorrect_examples` field. The compact history projection retains the
score-bound example rows, so this instruction has access to the negative
examples when that history packet is selected. The projection now also rejects
any nonempty history in the `history_withheld` condition, keeping this derived
negative strategy out of the no-history control arm.

For run `rootless-cognition-cycle-1e3f877fb56242c5b2c0`, the retained
history-present errors at inputs 3, 4, and 5 were 8, 11, and 14, each scored
incorrect. That cycle skipped task-family transfer because the withheld
baseline threshold was not met, so it never invoked this new path. If a later
same-family, history-enabled call receives this record, those points fit
`output = 3 * input - 1`, which should be exposed as a rejected guess. This is
a derivation from the stored scores, not an observed execution of the new
projection path.

These prompt and projection changes are source changes, not results. The
persisted objective follow-up records below do not bind the exact source
revision or report whether a rejected guess was included, so they do not verify
this specific projection path. A fresh source-bound run is still needed to
measure whether explicit derivation improves acquisition; transfer remains
gated on its withheld baseline competence threshold.

### Current learning boundary: negative scores are retained, not fitted

The existing score-to-history path retains each typed acquisition answer with
its exact evaluator result and source score digest. The task-family projection
surfaces incorrect examples in a separate `prior_incorrect_examples` field,
marked as errors rather than mapping evidence. The affine strategy fitter
requires at least three distinct evaluator-correct inputs and rejects any
incorrect row as support. Separately, the transfer gate requires at least two
correct probes in the history-withheld baseline. Consequently, a 0/3
acquisition can durably preserve failure evidence and, when the errors support
one, derive a rejected guess, but it cannot derive a positive candidate
mapping or enter held-out transfer. The prompt refinement above targets
initial acquisition accuracy; the rejected-guess projection adds negative
strategy guidance without changing the positive-evidence policy. Neither
change proves that the model uses stored experience to revise its strategy. A
later history-driven improvement still requires a valid acquisition followed
by a source-bound transfer result under the preregistered controls.

### Persisted objective follow-up records, 2026-11-20

Read-only reconciliation of the persisted resident-cognition experiment records
under the private rootless campaign found two valid controlled observations for
the same model artifact digest
`ebb2efeea46036ca7f276589e710729aff06c3a4b7b7b970c09da1712daf0989`.
These are resident endpoint receipt observations; the model identity was not
independently attested.

The acquisition record `devexp-run-de53a8746dc111c094c293cc` (protocol
`devexp-protocol-07254f066cac987b184d0aa1`, digest
`sha256:07254f066cac987b184d0aa1eb2407219436f7b6ba89d3c0d897794c061ae459`)
scored 3/3 in history-present, history-withheld, and history-restored. The
history-present and restored outputs matched the withheld output under the
recorded downstream-cognition digest comparison. This shows correct answers
for that prompted acquisition suite, with no measured history-associated
change; it does not show that history caused the competence.

The held-out same-family record `devexp-run-04ec6a6cf796c864024dca29`
(protocol `devexp-protocol-4ead291a152a39d105ba73ed`, digest
`sha256:4ead291a152a39d105ba73ed7098ab3a478544146570633183e16d091ab81ab6`)
scored 0/3 in all three conditions. Its history-present and restored
downstream-cognition digests differed from each other and from the withheld
condition, so restoration was unstable. The selected history contained
`devrec-5ce950e254690f736a4bacc6`; the withheld arm selected no record. The
record therefore shows an output association without a correctness gain or
stable restoration, and does not establish transferable learning.

Two additional valid controlled observations in this private campaign lacked
objective task scores and were not counted as acquisition or transfer evidence.
The bounded result across these records is: acquisition competence is now
observed on one three-probe suite, but history did not alter that result; the
held-out suite remained 0/3 despite history exposure. The next evidence-bearing
step is a fresh, preregistered history intervention that preserves the held-out
scorer and checks whether the specific retained strategy evidence changes
probe-level correctness with stable restoration. No Hermes run was started for
this reconciliation.

A read-only check of the persisted per-probe score rows confirms that all three
acquisition probes were correct in each condition and all three held-out probes
were incorrect in each condition. These rows contain no abstentions. Thus, the
aggregate ties are not hiding a probe-level correctness swap; the nonmatching
transfer output digests reflect answer variation that did not change correctness
on any scored probe. This characterization is limited to these two suites and
does not establish why the answers varied.

### Probe-level objective outcome reporting

Completed acquisition and transfer summaries now preserve the independent
scorer's correctness status for each ordered probe across history-present,
history-withheld, and history-restored conditions. Each row identifies its
probe input and reports correctness and abstention only; it omits the model's
answer value. Each summary binds the common task digest and all three
condition score digests. It rejects conditions whose probe order differs, whose
counts do not match their probe rows, or whose abstention and correctness
fields disagree. For v4/v5 selective score records it also reconciles the
aggregate answered and abstained counts with the probe rows and checks that the
score status matches those outcomes (including v4's legacy selective-as-
incorrect status). For v3 nonselective records it checks that the aggregate
correct/incorrect status matches the per-probe correctness count. This makes
equal aggregate counts distinguishable when the
model succeeds or fails on different probes, and records restoration per probe
instead of only as an aggregate count. The summary remains a measurement of
scored outcomes; it does not show which history content caused a change or
establish learning. Deliberately unscoreable conditions remain unknown at each
probe, and the report identifies those conditions rather than aborting the
cycle. This reporting change has not yet been exercised in a new Hermes cycle.
The acquisition classifier likewise retains invalid or truncated scorer
outcomes as unscoreable probe evidence, counts no typed correct/incorrect
examples from those outputs, and leaves transfer ineligible unless the
withheld baseline and acquired examples meet their existing score threshold.

### Consequence-store platform preflight, 2026-11-21

Read-only reconciliation of the private 2026-11-19 campaign found one run
whose pre-action proposal was admitted, response-lineage verified, and
classified `goal_met_ready_for_synthetic_action`; it then failed during
`synthetic_pre_action_cognition` before consequence evidence was persisted.
The run directory had no consequence-store artifact, and its failure record
did not preserve the underlying validator code. Code-path inspection found
that the next operation creates a `ConsequenceStore`, which requires POSIX
descriptor-relative custody unavailable to native Windows. This is a likely
explanation, not a recovered failure cause. A separate pair of attempts timed
out and were rejected for CPU fallback before a verified GPU invocation; those
remain model-placement failures, not cognition outcomes.

The runner now checks the consequence-store platform prerequisite immediately
after creating its private run directory and before constructing the model
runtime. Unsupported platforms record a bounded incomplete-run cause and do
not spend a model call. Run this experiment from the supported WSL/Linux path;
the check does not make the synthetic consequence an independent physical
observation, and the prior proposal remains evidence of a decision only. The
failure reporter now extracts only the validated code prefix from typed
`EmbodiedConsequenceError` messages, omitting any colon-delimited detail, so a
future failure can confirm or refute this diagnosis without retaining raw
exception text.

The same campaign has two additional failures on the pinned artifact at 99
requested GPU layers: both timed out and were rejected as CPU fallback before
a verified inference completed. An earlier developmental cycle at 32 layers
reached scored acquisition and held-out transfer. A separate four-call
epistemic series completed at 99 layers, so this does not establish a general
99-layer failure. The longer developmental-cycle runner now defaults to 32
layers, retaining the explicit environment override. Each run records the
selected layer count in its preregistration; do not change it within a matched
cohort. This is a conservative starting configuration for this cycle, not a
guarantee of GPU residency or performance.

### Source fingerprint completeness

The recent campaign's run artifacts reported `untracked_paths_present` and no
worktree content digest, even though they retained a status digest. The runner
now emits source-provenance schema v2 and fingerprints tracked Git diffs plus
each untracked path, file mode, and file content in deterministic byte order.
It retains only the final digest, not paths or file contents. The 32 MiB and
4,096-entry limits remain fail-closed. Symlinks, non-regular entries, files
that change during hashing, and submodules report an incomplete fingerprint
instead of a false complete one. The fingerprint also rejects `assume-unchanged`
and `skip-worktree` index flags, which can hide local edits from normal Git
inspection. Git-ignored files are outside this digest;
runtime dependencies have their separate runtime observation. Older run
artifacts remain immutable and cannot be retroactively source-bound. This binds
the observed worktree snapshot; it does
not prove which bytes the Python interpreter loaded. New runs now require a
complete fingerprint that is unchanged between module initialization and
pre-inference startup, then compare it again after model release. Incomplete
or changed source state prevents inference or converts the run to an incomplete
artifact carrying both provenance snapshots. The completed-cycle schema is
v12 and the failure schema is v7. The final check detects mid-run worktree
changes but does not stop them or prove which bytes the interpreter loaded.

### Scheduled order for objective history conditions

The rootless cycle's validated history-order trial index now controls the
invocation order of objective acquisition, transfer, and companion-history
conditions. New objective protocols use
`sentientos.developmental_history_intervention_protocol:v11`; new companion
protocols use v10. Both bind the task/history selection, scheduled index, and
one of six condition permutations. Across each six-trial matched block, each
condition appears twice at every invocation position. Exact retained history
is revalidated immediately before the restored-condition invocation, which
can now occur in any position. Observation and score arrays remain in
canonical condition order, so scoring and history lineage stay condition-keyed.
The resident owner allocates the next objective index under its tick lock and
persists a protocol-bound schedule claim before inference. An explicit
`SENTIENTOS_HERMES_HISTORY_ORDER_TRIAL_INDEX` override must name that next slot.
For a matched six-run cohort, keep the experiment seed and complete context
binding fixed; changing task, model, current projection, selected history,
generation posture, inference budget, or prior self-model/epistemic state starts
a separate schedule. Legacy v12 objective artifacts retain fixed order while
persisting answer-free per-probe correctness and restoration outcomes for
scored suites in `objective_evaluation`.
Run recovery recomputes this summary from the independently verified score rows
and rejects mismatches. For legacy v2 affine suites without retained per-probe
rows, it derives correctness booleans from the verified answer list and frozen
task plan, without copying answer values into the summary. Unscheduled companion
interventions retain the fixed historical order. Existing v8/v9 artifacts keep
their original alternating-first, restoration-third semantics. Recovery of
scheduled v8-v11 runs requires all condition receipts and strictly increasing
timezone-aware receipt event times in protocol order. Those are owner-reported
local timestamps, not independent time authority. A fresh objective cycle has
now exercised the scheduled path through acquisition, but no complete cycle or
six-run block establishes the balance in live use. The deterministic schedule
does not randomize nuisance variables.

### Fresh follow-up: objective-family evidence projection bound, 2026-11-21

Seed `4173934892`, protocol digest
`6834b458b113d45fcb920ccb540e06ace41b6f751152f6160b6ffff79a8ea76b`, ran
the current ext4 source snapshot against the pinned Hermes 4 14B Q4_K_M
manifest with 32 requested GPU layers. Source provenance was complete and
unchanged; runtime telemetry observed 32 layers on GPU and 8 on CPU. The
synthetic acquisition suite scored 3/3 in history-present, history-withheld,
and history-restored, with no measured acquisition correctness difference.
The cycle stopped before held-out transfer while retaining the acquisition
experience: the developmental-history projection was 13,082 bytes, above the
10 KiB generic projection check. The selected-evidence path already recognized
this validated task-family record as eligible for a separate 12 KiB cap, so
the projection and selection bounds disagreed. The failure artifact is
`cycle-failure.json` under private run
`rootless-cognition-cycle-ac48f9a8d8b94536b8a1`; it records
`developmental_history_projection_over_bound`, a stable source fingerprint,
and verified governed unload. No transfer outcome or learning claim resulted.

The projection now applies its objective-task-family-specific bound, raised to
16 KiB to contain the observed answer-free evaluation, acquisition examples,
condition receipt identities, and model identity while keeping the generic
developmental-experiment bound at 10 KiB. The corresponding selected-fact
prompt allowance is 24,576 characters, matching the rootless runner's existing
input ceiling and remaining below the owner model-context limit. This is a
bounded payload correction, not evidence of learning. The fresh follow-up
under a new source-bound protocol is recorded below.

### Fresh follow-up: corrected projection reached disjoint transfer, 2026-11-21

Seed `2270215760`, external protocol digest
`b416c0ccb229978abd1ac6427ffdc5e11b408e9f3199f0db885dbfdef07ca196`, ran
the corrected ext4 source snapshot against the same pinned model manifest with
32 GPU layers requested. The source fingerprint was complete and stable from
startup through completion. The cycle completed as
`rootless-cognition-cycle-724d354bc544461b80f6`; all eight stage checkpoints
were retained, the result used cycle schema v12, and the model was verified
unloaded through governed release. GPU memory was 1,130 MiB used before the
run and 1,141 MiB afterward. Ollama reported `size_vram=7968516996` bytes
during inference; host samples showed about 3.2 GiB free while the model was
loaded.

The acquisition suite again scored 3/3 in history-present, history-withheld,
and history-restored, with zero abstentions and no correctness difference.
The owner retained the acquisition record and verified its task-family
lineage. The transfer run's present, withheld, and restored scores were each
0/3, but a later custody audit found the history treatment was not delivered:
the persisted governed-request prompt digest matched its task-family projection,
yet that projection recorded one selected history record and zero task-relevant
records or examples in both history-present and history-restored. The withheld
projection correctly recorded zero. The run therefore does not qualify as a
history-transfer comparison. Its score tie is neither evidence for nor against
history use or durable learning.

The transfer summary now also records a digest of each condition's ordered
answer vector when the exact-scored probe rows are complete. It reports whether
history-present differs from withheld and whether restored matches present,
separately from correctness deltas. The digest includes the task digest and
probe order, while keeping answer values in the existing score artifact. The
comparison is undefined if task-and-probe scope digests differ or any
condition lacks a complete typed answer vector. This
distinguishes changed behavior from changed correctness without upgrading a
behavioral difference into evidence of improvement or causal reliance. The
already completed run predates this summary field and is not rewritten. A
separate pre-inference guard now rejects a history-required condition when its
bound prompt projection contains no task-relevant record. It also checks that
each selected task-relevant experience is present in the exact prompt bound by
the governed request digest. A record-selection claim alone can no longer
stand in for delivered examples.

The audit traced the omission to a projection mismatch: writeback validated and
retained the acquisition examples, then compacted the objective score rows
without their history-present `probe_results`. The later task-family reader
requires those score rows to revalidate the examples and consequently excluded
the record. The compact family projection now retains the already validated
history-present probe rows only; withheld and restored answer vectors remain
omitted from that acquisition record. A read-only post-run call to the same
task-family projection owner found one task-relevant experience with all three
score-bound acquisition examples. Rechecking applicability against the cycle's
exact active model identity classified the source as the same model, so the
record was not withheld for cross-model uncertainty. This confirms the
record-delivery and same-model applicability path on the persisted artifact.
The objective transfer was still skipped because acquisition did not establish
baseline competence, so model use of those examples on delayed probes remains
unverified.

The separate embodied decision probe was skipped because the retained record
did not meet its preregistered predicted-reach/observed-idle evidence pattern.
Ordinary historical recall returned `ask` and did not demonstrate history use.
The later controlled companion comparison rejected an invalid withheld-history
response and classified the comparison as unqualified; it showed no
performance improvement. The synthetic observer did not establish a real
physical consequence or operator observation. These paths remain distinct
from the objective transfer attempt and do not change its unqualified status.

### Source-bound follow-up and completed run

A new isolated ext4 source snapshot was created at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261121-wsl/source-cognition-next-history-delivery`.
It starts from revision `498bf41f5fb54ed35d1e5da319f824d67f12b46d`, applies
the current 31 tracked-file changes, and includes the 20 untracked source and
documentation files. Generated `glow/test_runs` artifacts were excluded. The
31 tracked paths and the three cognition-critical Python files were compared
against the Windows checkout with line endings normalized; all matched. Its
complete source fingerprint was then sealed into a new protocol.

Protocol seed `3141592654`, digest
`f4ca3ba102ccd2584faed87a99a40dc60b702aca83c316336730de016f1bcf1b`, is stored
with private custody under
`/home/zombinator/.local/state/sentientos-cognition-followup-20261121-wsl/protocols/hermes-developmental-cycle-20261121-3141592654.json`.
The protocol digest recomputes correctly, and its revision, cognition and runner
hashes, tracked-diff digest, and worktree-status digest matched the prepared
snapshot. The first source-bound attempt stopped at dependency preflight
(`psutil` missing). After using the existing private venv, a retry stopped
before inference because the runner's default model alias did not match the
pinned manifest. An exact model-name retry completed acquisition and transfer,
but failed in controlled-history diagnostics: a history-binding mismatch path
referenced an undefined `metadata` local and raised `NameError`. The failure
artifact records no learning claim, and the model was unloaded.

The diagnostic now reads the selection from the cognition `context`, where the
bound developmental-history selection is stored. A new protocol was sealed
against that source revision, with a fresh seed rather than reusing the failed
attempt. Seed `3141592655`, protocol digest
`4bdbe97d3766cdfb14a94015356dad58f2bdcec6895c3bc4e10cc60ecb8c6bb3`, completed
as run `rootless-cognition-cycle-abb770979813482c9361`. Its result is stored at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261121-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-abb770979813482c9361/cycle-result.json`.

The exact-scored acquisition was incorrect on all three probes. Its persisted
history record was reloaded through `_task_family_history_examples`; the owner
projected one task-relevant experience containing three score-bound examples,
all marked incorrect by the exact oracle. Rechecking that experience against
the cycle's active model identity yielded `same_active_model_identity`. The
preregistered transfer was therefore skipped because the history-withheld
baseline did not demonstrate competence. Record persistence and task-family projection are now evidenced;
delayed-probe use and transfer remain untested. No performance-improvement
claim is supported. A separate controlled companion-history comparison found
a stable difference in downstream cognition identity across history presence
and withholding; the recorded interpretation is bounded observed association
only.

A separate answer-free retrospective audit is persisted at
`artifacts/experiments/rootless_cognition_cycle_abb770979813482c9361/retrospective_acquisition_history_audit.json`.
It revalidates the developmental record's owner digest and posture, recomputes
the acquisition run's outer digest, confirms the source run and history-present
score binding, and reproduces one projectable same-model experience with 0/3
correct examples. Its digest is
`567ec40463fe3230fbd7f508c088bc961b8d41225a6e9968f4b60b6ef60f78cd`. Invocation
receipts could not be independently verified because this retrospective audit
had no receipt verifier; that limit is explicit in the artifact. It contains no
answer values, does not establish prompt delivery or model attention, and does
not change the immutable cycle result.

A second, read-only offline replay is recorded in
`artifacts/experiments/rootless_cognition_cycle_abb770979813482c9361/retrospective_acquisition_history_audit_v2.json`.
Unlike v1, it reloads the acquisition run through `DevelopmentalExperimentStore`
with the persisted rootless receipt verifier and verifies each condition's
receipt against the run observation, condition linkage, preregistration, model
identity, and runtime digest. The resulting audit digest is
`6ab8446df36c9224fe9275f7ae8d4a74eee2d2074537905229bc9e162c55a549`.
This verifies local persisted receipt integrity and the owner's run reload; it
does not reconstruct a live session or independently attest the Ollama backend.
No inference was performed, and the audit still makes no learning claim: all
three acquisition conditions remain 0/3, with transfer skipped because the
history-withheld baseline scored 0/3 against a required baseline of 2.

### Persisted projection audit for future cycles

The post-run audit revealed that a skipped transfer result did not itself say
whether its acquisition history was projectable. The runner now computes an
answer-free `sentientos.task_family_history_projection_audit:v6` from the
retained acquisition record before applying the transfer eligibility gate. It
records projectable experience, record, and example counts; correctness and
abstention counts; and source-model identity relations. It identifies its scope
as persisted acquisition projection only, excludes answer values, and does not
assess prompt delivery or make a learning claim. Its target-model relation
counts compare source identities with the exact supplied target mapping and
include that mapping's recomputed digest; the audit does not independently
attest the serving identity. V6 adds answer-free independent-input anchor
coverage: per-run counts and digests of evaluator-correct inputs, the number
of source-run pairs with distinct correct inputs on both sides and at least
three distinct inputs in their union, and the best pair's coverage counts.
Failure status distinguishes fewer than two eligible runs, fewer than three
distinct correct inputs, no pair reaching a three-input union, and no pair
with a unique correct input on each side; conflicting correct answers for a
repeated input are reported separately. Input and answer values remain
excluded. This diagnoses input-anchor
availability; it does not establish a strategy fit or learning. A read-only
invocation against the completed run reproduced one projectable same-model
experience with three incorrect examples. The existing immutable cycle result was not
rewritten; this field will appear in future source-bound cycle results. It is
null when acquisition does not yield an admitted history record.

The audit states the record-count scope explicitly: it counts the containing
durable history candidate record, while source runs remain a separate count.
Multiple score-bound source runs can appear as facts within one selected history
packet, so source-run IDs are not interchangeable with prompt-inventory record
IDs. This count establishes projectability within that packet; it does not
claim that the model attended to it.

The offline acquisition-audit utility now emits outer schema v3 for a fresh
replay and resolves the task family from both the cycle summary and retained
source facts, accepting the registered v5 and v6 IDs only. When replaying the
historical v5 family, its nested projection audit
preserves score-bound counts as `audited_legacy_*` while reporting zero
projectable examples and `task_family_contract_quarantined`. It writes a new
artifact version and leaves the existing v1/v2 audits immutable. The raw cycle
directory is not present in this checkout, so this updated replay has not been
executed here.

For a future eligible transfer, the runner now reopens and verifies each
condition's governed inference receipt. Its answer-free
`sentientos.objective_task_family_prompt_delivery_evidence:v5` summary checks
the task-family projection digest against the exact request prompt digest,
projection condition/treatment, task-relevant record and example counts, and
record IDs/digests against the cognition observation. It also requires
canonical SHA-256 record-digest shapes, recomputes the selection digest, and
verifies that the observation's selected record references agree with the
retrieved inventory before emitting the summary. It rejects malformed or
negative per-record example counts and requires the projection's historical,
non-truth, and no-authority posture. The output now exposes those
two checks as explicit booleans, so a reader can distinguish verified selection
integrity from prompt binding without inferring either from a status label.
This makes the persisted result show the prompt-binding chain that was
previously only implicit in the receipt. It also carries per-record references
pairing selected record IDs and digests with canonical packet digests and
presence flags, without packet contents, so later review can identify which
selected packets were bound. The summary does not include prompt or
answer values and does not
claim model attention or learning. Projections v24-v29 also
carry an owner-recomputed overlap count for the current probes against selected
score-bound history. The transfer summary reports `exact_probe_reuse_posture`
as overlap detected, no overlap detected, or measurement incomplete/legacy
unmeasured. V5 also records whether the digest-bound v8 accumulated strategy
was present in each condition's projection, its anchor-run digests, and its
supporting-run and distinct-input counts, and owner-verified prompt-substring
posture; the withheld condition must contain no candidate. For v28/v29
projections, the owner verifies the canonical strategy substring in the exact
prompt; v26/v27 projections leave prompt inclusion unmeasured. This binds
strategy projection and, where available, prompt-substring evidence to the
verified request projection, not model attention or use. Exact input reuse does
not qualify transfer by itself. Verified outcomes remain available to future
cognition. The completed
cycle had no eligible delayed
transfer, so it does not contain this new summary. Any future protocol must
bind the updated source fingerprint.

A retrospective audit of the incomplete seed `3141592654` run found governed
transfer requests for all three conditions. The history-present and restored
receipts each bound one task-relevant record with three examples; withheld
bound zero. Each v18 projection digest recomputed, and its governed prompt
digest matched the exact request's prompt digest. This confirms request-level
delivery evidence for that incomplete run, not a complete-cycle result or a
learning effect. The new cycle summary will surface the same binding directly
when a future eligible transfer completes.

The forward receipt verifier now accepts the registered task-family projection
schemas v19 through v23. When a projection supplies a nonzero
`prior_incorrect_example_count`, it also requires the exact answer-free
`task_family_negative_example_prompt_guidance` row in the governed request,
recomputes its instruction and evidence digests, and checks its prompt and
projection bindings. The persisted delivery summary records whether that row
was verified and its digest; it still makes no claim about model attention or
learning. Legacy v19 receipts remain readable without this newer row because
that projection schema predates the field. This is forward verifier behavior
only and does not amend the completed or incomplete historical artifacts.

The acquisition transfer gate now always rebuilds probe-level condition
comparisons from the three score artifacts before using acquisition counts.
It recomputes each score-row digest, verifies score-row shape, probe alignment,
requires exact answered versus abstained row forms for the registered score
schemas, verifies probe alignment and correct-count totals, and requires any persisted
`objective_evaluation.probe_level_outcomes` summary to exactly match the
recomputation. This prevents a supplied summary or altered score row from
standing in for score validation. The change strengthens evidence integrity
for future runs; it does not alter the historical 0/3 acquisition audit above
or relax the withheld-baseline gate.

Future rootless objective cycles now use task family
`rootless_integer_affine_transfer_low_range_v6`, with a fixed hidden affine
mapping across source runs and seed-varying disjoint acquisition and transfer
inputs. The prior v5 generator varied multiplier and offset while reusing one
family ID, contrary to the task contract that one family shares one mapping;
cross-run strategy accumulation could therefore combine examples from
different rules. Both the rootless generator and `ObjectivePredictionTask`
now enforce the v6 mapping contract. Persisted objective-plan verification
reconstructs the task through that same class before accepting a plan, so a
stored v6 plan with different parameters also fails. The v6 identifier prevents older
variable-mapping v5 records
from entering the new family. Resident cognition also quarantines the v5
family from prompt projection and all affine strategy derivation, while
leaving its stored records available for audit. The fixed mapping makes future
same-family history semantically comparable. This changes only future
source-bound protocols and history selection; prior cycles and artifacts
remain immutable. GPU inference has not been run for v6.

Each cycle is created under a fresh UUID-named `RUN_ROOT`, with its own resident
cognition history and state stores. The v6 comparison therefore measures
acquisition-to-transfer within one cycle; it does not measure accumulation of
experience across cycles. A longitudinal follow-up must explicitly bind its
shared state lineage, acquisition and transfer probe schedules, and cross-run
probe-overlap audit before inference. The general task-family selector ranks
exact probe overlap as useful recall, so its retrieval ranking is not a
held-out-transfer gate. A shared-state experiment should record that overlap
and qualify or withhold its transfer claim when prior answers to the tested
probes are present in the prompt. Transfer outcomes should remain available to
subsequent cognition as experience; the overlap rule belongs to experiment
eligibility, not a global ban on using verified history.

Before any longitudinal inference, preregister a campaign manifest that binds
the fixed-family contract, model identity, ordered run IDs and seeds, the
shared history-owner identity, and the initial complete history boundary. For
each run, retain the predecessor and successor boundary digests plus the
verified writeback receipts; require the successor inventory to preserve every
predecessor record and receipt exactly. A broken link or non-append mutation
keeps that run in the audit trail but makes it ineligible as accumulated
evidence. Bind acquisition and follow-up probe schedules before the first run,
and report exact input overlap between prior answered examples and every
evaluated follow-up prompt. Label a follow-up as held-out only when its inputs
are absent from the eligible prior answers actually delivered in that prompt.
The accumulated-strategy claim additionally requires at least two distinct
score-bound source runs, the owner-verified anchor pair, and three or more
distinct correct inputs. Preserve failed and skipped runs in the manifest; do
not select later seeds based on observed scores. This gate would establish
traceable accumulated evidence and a valid test schedule, not model attention,
causal use, transfer, learning, or improvement.

`work/rootless_history_boundary_campaign.py` provides an offline boundary plan
and verifier for that future chain. The v3 plan records the initial history
record and receipt file digests, the fixed v6 family, one expected model-identity
digest per cycle, and ordered cycle IDs, task-generation seeds, and backend seeds. It deliberately
does not preregister `devexp-run-*` source IDs: those IDs are content-derived
from completed run artifacts and cannot be known before inference. The audit
discovers each source ID from its terminal cycle record and verifies the run
digest, family, model identity, seeds, and retained acquisition history record.
The cycle runner accepts `SENTIENTOS_HERMES_CYCLE_ID` so each planned cycle ID
can be allocated before launch and bound to the corresponding run. After
execution, `verify` requires completed or incomplete cycle roots in planned
order. It reports any prior record or writeback receipt that disappeared or
changed. Incomplete cycle artifacts stay in the chain with their failure stage
and code; the source run ID remains unavailable when acquisition never
completed, while any partial history files remain in continuity checks. The
runner now accepts the campaign plan path and checks the plan digest, cycle ID,
task/backend seeds, and seed-source boundary before model preflight; it checks
the active model identity after runtime construction but before inference. It
rechecks the source after copying and requires the private run's record and
receipt files to match that same boundary before inference. A seeded run
without a valid campaign plan is rejected. The final campaign audit
also requires the terminal cycle artifact to repeat the exact campaign ID,
plan digest, and ordered cycle index. Every
planned ID currently needs a cycle root, so not-started skips still need an
explicit retained cycle artifact. The closed plan and audit shapes are
described by the adjacent v3 plan and v4 audit schemas. V2 plans remain readable
for retrospective verification.
Outputs are immutable and must be written outside the evidence roots.
Both boundary inventories are non-atomic; capture them while the history
collections are quiescent. The initial history root must contain the store's
`records/` and `receipts/` directories.

The runner now accepts an explicit prior-history seed through
`SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT`. Before preregistration and before the
first inference, it reloads the source with `DevelopmentalHistoryStore`, checks
that every receipt refers to a matching durable record and every record has a
receipt, copies records and receipts into that cycle's private history root,
reloads the copy, and binds a digest of both inventories into preregistration
and the cycle result. A configured seed requires a nonzero external protocol
digest; the audit recomputes the retained preregistration digest and checks its
seed summary against the prior boundary. Each new cycle history now creates its
`records/` and `receipts/` collections before the seed-copy boundary check, so
an empty seed has the same valid store shape as populated history. The evidence
marks model attention as unverified. The default remains an empty isolated
history. To build a sequential chain, point
each later invocation at the preceding cycle's
`resident-cognition/history` directory. The verifier can then compare retained
history inventories across cycle roots. The audit recomputes the declared seed
digest from the prior boundary and requires every prior record and receipt to
be present unchanged in the cycle root. This is a verified copy boundary; it
does not establish that the model attended to, used, learned from, or improved
because of seeded history. A seed failure is retained as an incomplete
pre-inference cycle when the runner can persist its failure report.

Example preparation and finalization commands are:

```powershell
python work/rootless_history_boundary_campaign.py prepare --history-root <initial-history-root> --campaign-id rootless-history-campaign-<20-hex> --task-family-id rootless_integer_affine_transfer_low_range_v6 --model-manifest-path <pinned-ollama-manifest.json> --model-name <exact-ollama-model-name> --gpu-layers 32 --cycle-id rootless-cognition-cycle-<cycle-1-20-hex> --cycle-id rootless-cognition-cycle-<cycle-2-20-hex> --task-generation-seed <seed-1> --task-generation-seed <seed-2> --backend-seed <seed-1> --backend-seed <seed-2> --output <plan.json>
python work/rootless_history_boundary_campaign.py verify --plan <plan.json> --cycle-root <cycle-root-1> --cycle-root <cycle-root-2> --output <audit.json>
```

For a wide-range v7 campaign whose first cycle may fail before copying its
seeded history, an optional portable seed bundle lets the offline verifier
recompute transfer-probe overlap from the original record bytes:

```powershell
python work/archive_rootless_history_campaign_seed.py --plan <plan.json> --history-root <initial-history-root> --output <private-directory>\initial-history-bundle.json
python work/rootless_history_boundary_campaign.py verify --plan <plan.json> --cycle-root <cycle-root-1> --cycle-root <cycle-root-2> --initial-history-bundle <private-directory>\initial-history-bundle.json --output <audit.json>
```

The bundle copies private developmental records and receipts, so the writer
requires a private output directory. It is plan- and boundary-digest-bound,
and the v9 audit records the bundle digest and whether it was verified. Without
the bundle, incomplete first-cycle overlap remains explicitly unrecomputed.
This verifies overlap inputs, not model attention, learning, or transfer.

For each planned launch, set `SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH` to the
immutable plan, set `SENTIENTOS_HERMES_CYCLE_ID` to that cycle's preallocated
ID, set `SENTIENTOS_HERMES_EXPERIMENT_SEED` and
`SENTIENTOS_HERMES_BACKEND_SEED` to its planned seeds, and bind the campaign
plan digest as the external preregistration digest. Source run IDs are recorded
from the resulting terminal artifacts by the offline audit; they are never
guessed before the model produces the run content.

Repeat either command with `--verify-existing` to recompute the expected
artifact and compare its exact serialized bytes with the immutable file already
at `--output`.

Each planned backend seed changes the model's generation configuration digest,
so a single active-model identity pin cannot represent a multi-seed campaign.
The v3 prepare command derives one expected identity digest for each ordered
backend seed from the exact model manifest, model name, GPU-layer bound, and
session configuration. This derivation is local and performs no model load or
inference. The runner compares the observed identity to the pin for that cycle
before the first inference; the offline audit repeats that comparison from the
terminal artifact. A changed manifest or runtime configuration requires a new
plan.

The plan's digest and local file publication do not independently attest when
pre-registration occurred. The verifier establishes file-level continuity,
seed-digest and preregistration binding, and run identity; it does not
independently revalidate the source scorer or owner semantics of writeback
receipts, prompt delivery, model attention, or learning. Each cycle still has a
separate private history root; sequential explicit seeding carries verified
prior records and receipts forward so the boundary verifier can evaluate an
append-only chain. The utility does not schedule or execute a campaign, select
later seeds, or bind follow-up probe schedules. Each cycle still has one
acquisition source run. Retrospective audit schema v16 can now inspect a retained
history record containing multiple source runs when all corresponding run
artifacts are present in that cycle root. It reloads each run independently,
checks the three condition scores, and binds that run's projected examples or
legacy aggregate fact to its history-present score. The report exposes the
per-run results and marks aggregate score binding verified only when every
source run passes. This audit extension does not create a multi-run campaign,
verify a shared history boundary across separate cycle roots, or establish
delivered held-out probes, model attention, causal use, transfer, learning, or
improvement.

### Windows source-fingerprint byte fidelity

On Windows, the source fingerprint now opens untracked files in binary mode
before hashing, preventing CRT newline translation from turning stable CRLF
files into apparent short reads. The path-to-handle race check relies on device,
file identity, size, modification time, and mode; the handle-to-handle check
also compares change time. This preserves the content and race checks while
allowing a stable NTFS checkout to produce a complete source fingerprint.

### Windows secure-store preflight, 2026-11-22

The freshly source-bound v6 attempt used seed \`2026112201\` and protocol digest
\`81ca67070c4cbaf6fcb2c365850d237bafb849f0a7a771f3e8a42d2f46ba659d\`. It
stopped at \`synthetic_consequence_store_secure_platform_unavailable\` before
loading Hermes because the consequence store requires secure descriptor-
relative publication that the Windows implementation does not provide. The
write-once failure artifact is under private run
\`rootless-cognition-cycle-427d1b2f2e454e45bdd1\`. No inference occurred and
the GPU model remained unloaded. The seed and protocol will not be reused.
A supported POSIX runner is required for the next model cycle.

Accumulated affine strategies now use schema v7 and include an owner-derived
cross-run probe overlap count, digest, and fixed posture. Projection recomputes
the complete strategy from selected records and binds it in the prompt
projection digest. The audit can distinguish exact probe
inputs that recur across supporting runs from inputs seen in only one run,
without listing the overlap inputs in the summary. This is provenance about
replay versus novel probe coverage; repeated inputs may still be useful history
and the model instruction treats overlap as provenance only, not independent
support. The fields do not change retrieval eligibility, establish independent
observations, or qualify a transfer claim. The evidence remains provisional and
history-only. A longitudinal experiment still needs to bind a shared state
lineage and independently scored, preregistered follow-up probes.

### Prompt-projection evidence in incomplete runs

Retrospective receipt inspection was needed because the v7 failure artifact
listed receipt identity and output digests but omitted task-family prompt
projection bindings. Future incomplete runs now use failure schema v8 and add
an answer-free per-receipt projection summary (schema v2) when that evidence
is present. Each selected-record reference includes its packet digest and
checked presence flag, without packet contents.
It recomputes projection and history-selection digests, checks the request
prompt digest, compares selection references with the request inventory, and
checks that projected records belong to the selected history. It only labels
the local bindings consistent when the exact registered v19 projection and
task family match, every projected packet carries the checked presence flag
and digest, selected counts match the request inventory, and a withheld
condition has no projected examples. The summary labels this as receipt-file
observation and explicitly records that governed receipt verification was not
performed; it is useful for triage and does not promote an interrupted run to
a verified experiment. Existing immutable failure artifacts are not rewritten.
Ordinary historical recall asked for a fresh observation and did not
demonstrate history use. The synthetic action observer contradicted the
predicted reach with an idle observation; this is not a real-world consequence
or independent operator observation. The cycle completed with
`governed_release_completed`; Ollama reports no resident model and GPU use
returned to its pre-run footprint.

### Offline audit of quarantined v5 acquisition and transfer

The completed cycles `rootless-cognition-cycle-abb770979813482c9361` and
`rootless-cognition-cycle-1e3f877fb56242c5b2c0` have separate offline audits:
`artifacts/experiments/rootless_cognition_cycle_abb770979813482c9361/retrospective_acquisition_history_audit_v5.json`
and
`artifacts/experiments/rootless_cognition_cycle_1e3f877fb56242c5b2c0/retrospective_acquisition_history_audit_v5.json`.
Historical v4 objective plans replay their original public question text, so
later prompt edits do not invalidate the saved descriptor. The store still
checks the reconstructed task specification, commitment, and descriptor
against the persisted plan and protocol. The audit verified the owner run
reload and local invocation receipts without inference. All three conditions
scored 0/3, v5 history remains quarantined, and the withheld baseline gate
skipped transfer. No learning claim was made.

The first cycle's v2 audit had treated v5 history as projectable. The current
v5 audit supersedes that classification: it audits one retained legacy
experience but projects zero experiences because the v5 family reused an
identifier across variable mappings. Its per-experience score digest is
verified against the owner-verified run. The second cycle's v3 audit found no
per-experience projection, so its v5 audit verifies the legacy aggregate trial
fact's run digest, plan digest, three condition score digests, counts, statuses,
and ordered score-digest list. Both audits mark
`history_record_score_binding_verified: true`; the first uses
`per_experience_projection`, the second `legacy_aggregate_trial_fact`. This
establishes record-to-run score attribution; it does not make quarantined v5
experiences projectable or show that the model used history. Both cycles remain
0/3 in every condition, transfer was skipped, and no learning claim was made.
No Hermes or GPU-dependent testing was performed.

### Owner-verified held-out transfer audit

Audit schema v6 also reloads any completed held-out transfer run through the
same experiment store and receipt verifier, checks its run digest and task
family, and requires the cycle's condition score summary to match the verified
run. If transfer was skipped, the audit records that no transfer run was
present. The v6 artifacts are:

- `artifacts/experiments/rootless_cognition_cycle_724d354bc544461b80f6/retrospective_acquisition_history_audit_v6.json`
- `artifacts/experiments/rootless_cognition_cycle_abb770979813482c9361/retrospective_acquisition_history_audit_v6.json`
- `artifacts/experiments/rootless_cognition_cycle_1e3f877fb56242c5b2c0/retrospective_acquisition_history_audit_v6.json`

For cycle `724d354bc544461b80f6`, v6 verified acquisition at 3/3 in each
condition and the held-out transfer run at 0/3 in each condition, including
the transfer summary-to-run score binding. The cycle's controlled history
intervention records a stable exact-output difference between present and
withheld history and an exact prompt/output replay when history is restored.
This is evidence that history availability was associated with output in that
intervention; it did not improve held-out accuracy, and the transfer records
remain quarantined under the reused v5 family. The other two cycles each have
owner-verified acquisition at 0/3 in all conditions and no transfer run. Across
these audits there is no evidence of durable learning or transfer improvement.
No inference or GPU work was performed for the audits.

Audit schema v8 also resolves each controlled-history intervention condition
to exactly one persisted local receipt by purpose, condition, prompt digest,
output digest, model identity, and generation settings. It verifies each
receipt through the rootless session verifier, checks that the receipt's
history selection IDs match the condition summary, and reloads the referenced
developmental records through their owner digest verifier. All three completed
cycles pass this binding. In each, the present and restored conditions have
matching prompt and output digests, while the withheld condition differs. This
was initially read as a repeated, receipt-bound output association. Field-level
inspection was still needed because the measurement used the full structured
output digest.

Audit schema v9 adds explicit parity checks for active model identity,
generation configuration, and rootless session across all three conditions.
It records whether present/restored prompts and selected record IDs match,
whether the withheld selection is empty, and whether the present/withheld
prompts differ. All checks pass for each of the three v9 artifacts. This
establishes same-model, same-session, same-generation controls and verified
selected record references, but does not by itself distinguish response
content from citation metadata.

Audit schema v11 compares the structured response content with its history
citation field and binds that comparison to the persisted later companion
decision. The v11 artifacts are:

- `artifacts/experiments/rootless_cognition_cycle_724d354bc544461b80f6/retrospective_acquisition_history_audit_v11.json`
- `artifacts/experiments/rootless_cognition_cycle_abb770979813482c9361/retrospective_acquisition_history_audit_v11.json`
- `artifacts/experiments/rootless_cognition_cycle_1e3f877fb56242c5b2c0/retrospective_acquisition_history_audit_v11.json`

In every cycle, the response text and all non-citation output fields are the
same across conditions. The withheld response includes a history ID absent
from its selected history, so the companion owner rejects it as
`rejected_invalid_output`; the present and restored responses validate. The
later decision summary reports `history_changed_cognition: false` and
`invalid_condition_response_rejected`. Thus the earlier full-output digest
difference came from history citation metadata, not a changed substantive
response. The repeated intervention supports no semantic history-use,
performance-gain, or durable-learning claim. Held-out transfer remains 0/3 in
all three conditions in the cycle where it was run.

The v11 acquisition score summaries make the per-cycle outcome explicit:
`rootless-cognition-cycle-1e3f877fb56242c5b2c0` scored 0/3 in all three
conditions, `rootless-cognition-cycle-724d354bc544461b80f6` scored 3/3 in all
three, and `rootless-cognition-cycle-abb770979813482c9361` scored 0/3 in all
three. Only the middle cycle met the withheld-condition baseline threshold and
has an owner-verified delayed run; that run scored 0/3 in every condition.
The other two audits report transfer skipped because the withheld baseline was
0/3 against the required 2/3. These are separate cycle outcomes, not a pooled
trend: the scored conditions show no accuracy advantage for history, while the
unqualified cycles provide no transfer comparison. The output-content audit
above also finds no substantive response difference, so none of these results
supports history-dependent learning or improvement.

`python work/summarize_persisted_experiments.py` reads the latest retrospective
audit available for each cycle under `artifacts/experiments`, verifies each
audit's canonical digest and cycle-directory binding, and prints condition-level
acquisition and transfer outcomes without pooling them. The source cycle stores
were found in the existing Ubuntu WSL state directories; offline v13 and v14
audits were generated for all three cycles. The latest audits are now v14:
acquisition was 0/3 in two cycles and 3/3 in one; only the latter completed a
transfer comparison, which scored 0/3 in every condition. The v13 probe-level
vectors show no per-probe accuracy change between acquisition conditions or
between transfer conditions. All three audits report no semantic cognition
change in the history intervention, and none establishes learning or
improvement. The script consumes audit artifacts only and performs no
inference. V14 now provides the latest audit for all three cycles. For the one
completed transfer, it verifies that each receipt-bound v18 task-family
projection had zero task-relevant records and examples; the available/restored
conditions each selected one legacy record, but v5 quarantine excluded it from
the task-family projection. The withheld condition selected none. The exact
probe-reuse posture remains `exact_probe_reuse_evidence_unbound`, and raw
prompt serialization is not reconstructed, so this does not qualify the
transfer probes as unseen or establish what the model attended to.

Summary schema v4 now surfaces the projection quarantine reason, projectable
experience count, task-relevant record/example counts, and prompt-delivery
status per cycle, while preserving an absent model-attention field as unknown
instead of converting it to false. It marks each stored audit as current,
older than the summarizer, or newer than the summarizer, so absent fields from
older audit schemas are not mistaken for current negative evidence. The three
older v5 audit files remain v14, while the current audit producer is v17; their
accumulated-strategy delivery fields are therefore unassessed by those stored
audits. For newer audits it also exposes the
per-condition accumulated-strategy projection and prompt-substring evidence,
including anchor-run digests; legacy audits retain an unknown value. The
those three v5 cycles all report
`unstable_mapping_reused_under_one_family_id`, zero projectable experience,
and zero task-family examples. The fixed-mapping v6 family now has completed
cycles; the new campaign evidence is recorded below.

The retrospective audit producer needs the original cycle root, including
`cycle-result.json`, resident history records and state, and invocation
receipts. The checked-in `artifacts/experiments/rootless_cognition_cycle_*`
directories contain retrospective audit summaries, not the complete cycle
roots, so they cannot regenerate v17 audits. Preserve each complete cycle root
in an accessible evidence location alongside its audit output; otherwise future
audit-schema improvements cannot be applied to that run's source evidence.
After a cycle completes or records a failure, create an answer-free inventory
outside the cycle root with
`python work/export_rootless_cycle_evidence_manifest.py --cycle-root <cycle-root> --output <manifest.json>`.
The manifest binds the cycle ID/status and sorted relative file paths, byte
counts, and SHA-256 digests; it does not copy the source tree or include file
contents. Verify it later against the preserved tree by adding
`--verify-existing`. The inventory's digest is integrity evidence within the
local filesystem trust boundary, not an atomic snapshot, independent signature,
or backup. The source tree should be quiescent while the inventory is created.
The closed artifact shape is defined in
[`rootless_cycle_evidence_manifest.schema.json`](rootless_cycle_evidence_manifest.schema.json).

The owner-side accumulated affine candidate now records a deterministic
two-run anchor pair whose correct probe inputs differ and cover at least three
distinct inputs. Other eligible runs remain corroborating score-bound evidence;
they do not make global uniqueness across every run a requirement. The
candidate is digest-bound under schema v8 inside task-family prompt projection
schemas v26-v29. The owner rederives it from retained history during recovery;
the rootless runner and retrospective audit accept those projection versions
and bind their projection digests. This improves evidence selection and
replayability, but there is not yet a completed v6 model cycle demonstrating
projection delivery, model use, or transfer.

Retrospective audit schema v15 records the v5 prompt-delivery summary's
accumulated-strategy status, digest, anchor-run digests, supporting-run count,
distinct-input count, and prompt-substring posture for each transfer condition.
It binds those fields to the verified receipt projection digest and rejects a candidate in the withheld
condition. The audit does not independently rederive the strategy from model
behavior or establish that the model attended to or used it. Legacy v4 delivery
summaries remain explicitly unmeasured for accumulated-strategy delivery.

Retrospective audit schema v12 added per-probe outcomes to the prior v11
aggregate counts. It projects each validated score's
per-probe outcome as `correct`, `incorrect`, or `abstained`, keyed by probe
index. It hashes each probe input and only emits paired condition comparisons
when the three inputs match in order. This makes offsetting probe-level changes
visible without retaining model answer text. Paired summaries count unchanged
and changed outcomes, correctness direction, and abstention involvement. They
explicitly mark their scope as scorer outcomes only; response text, model
attention, and learning are not assessed. Missing or incomplete score rows
remain explicitly unavailable; legacy verified score rows that omit the
abstention field retain the experiment verifier's non-abstained default. The
comparison carries no authority. Existing v11 audit artifacts remain
unchanged.

The retrospective audit schema advances to v13 to retain exact-probe-reuse
evidence from the scored transfer conditions. It reloads each owner-verified
receipt, checks the projection digest and overlap fields against the
cycle-summary evidence, binds those receipts to the experiment run, checks the
current probe-list digest against the run descriptor, reloads each selected
history record through the developmental-history store, and recomputes overlap
from the reconstructed task-family packets. It then checks the aggregate reuse
posture against the two history-available conditions. The audit artifact
retains the recomputed count and digest per condition separately from the
receipt-derived summary, so reviewers can compare the two evidence paths.
This carries forward whether exact probe inputs were detected, absent,
incomplete, or legacy-unmeasured. It does not reconstruct the full prompt:
raw prompts are intentionally not persisted, so the audit does not independently
establish exact prompt serialization or model attention. The measure does not
establish transfer, learning, or authority. Earlier v11 and v12 audit artifacts
remain unchanged. V13 has now been generated from the original cycle stores for
all three cited cycles; the audit artifacts record `inference_performed: false`
and retain the verified owner-run and receipt bindings.

### Legacy task-family projection delivery audit, schema v14

V14 adds an audit for the completed legacy transfer, whose v18 task-family
projection did not carry the newer exact-probe overlap summary. It binds each
condition's verified receipt to the owner-verified run and cycle summary,
checks the receipt prompt digest against the projection digest, matches the
selected record references in the receipt and run, and reloads selected
records through the developmental-history owner. All three conditions had
zero task-family records and examples in the projection. History-present and
history-restored each selected one v5 record, but the quarantined v5 family
contributed no task-family examples; history-withheld selected none. V14
therefore clarifies what eligible task-family material entered the projection
while preserving exact probe reuse as unbound. Raw prompt serialization,
model attention, held-out transfer, and learning remain unestablished.

### Bounded diagnostics for Python name-resolution failures

The persisted failure artifact for cycle
`rootless-cognition-cycle-7b5eca6905ce473aafef` records `NameError` at
`controlled_history_intervention`, but has no diagnostic or traceback and no
receipt or cognition observation for the later companion-decision request. Its
resident state retains the later-decision tick as `in_progress` with no
observation IDs. The failure point is therefore before a controlled condition
observation was persisted; its missing identifier cannot be reconstructed from
that immutable artifact. Future rootless cycle failures now include a bounded
`python_failure_diagnostic` for `NameError`: unresolved identifier, module,
function, and line, with exception text and source lines excluded. The same
diagnostic is stored in the failure artifact and emitted in the runner's
failure summary. This improves triage; it does not identify or retroactively
fix the cause of the earlier failure.

An offline inventory of the Nov 20 and Nov 21 WSL runtime roots found 12
incomplete failure records alongside the three completed cycles. Their failure
codes include two `cognition_input_budget_exceeded`, two
`companion_interaction_decision_invalid`, and one each for
`developmental_history_projection_over_bound`, `experiment_history_binding_drift`,
`governed_developmental_writeback_deferred_under_host_pressure`,
`history_context_budget_exhausted`, `hosted_cognition_delivery_unverified`,
`NameError`, `objective_task_scoring_failed`, and
`ollama_model_digest_unverified`. The portable summary tool reports these
records with an explicit posture of
`incomplete_failure_record_not_independently_authenticated`; they diagnose
experiment execution paths and do not count as completed conditions or
evidence of learning. The completed-cycle inventory contains no v6 task-family
cycle, and the three completed cycles' audited evidence still establishes no
semantic cognition change or history-dependent performance improvement.

### WSL cognition follow-up, 2026-11-22

The first WSL attempt (seed `2026112202`, protocol digest
`9d81faea30212986cf9205680132fd38b28100d05ef4cc525aa6032ac5af1e9a`) stopped
before inference because the runner's configured alias did not match the
verified Ollama tag name. The model store exposed the content-addressed model
as `hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`, with digest
`ebb2efeea46036ca7f276589e710729aff06c3a4b7b7b970c09da1712daf0989`. The
failure artifact is `rootless-cognition-cycle-3d7bb2cef5654d258030`; no model
was resident afterward.

The next attempt (seed `2026112203`, protocol digest
`38d81af13d9e00a724563139699139ae03a41b2193a02545798dc633903207ef`) used that
exact tag and completed three acquisition conditions. Each condition scored
3/3 on the independently scored affine probes, with identical output digests
and no observed condition difference. The cycle then stopped because the
runner recomputed probe correctness and abstention outcomes but omitted the
answerability fields persisted in the experiment's `objective_evaluation`.
The saved run independently passes the corrected recomputation at 3/3 in each
condition. The failure artifact is `rootless-cognition-cycle-c8492c84cc794a82a2c6`.
The verifier now also recomputes per-probe answerability and its present/withheld
and restoration labels from the abstention rows before comparing the summary.
This is a consistency fix; it does not change any inference or score.

A fresh attempt (seed `2026112204`, protocol digest
`e8912df54968aa6eb61bbe850485736c845bb9e6625369c3182763f7d8b748e8`) used the
source-bound verifier fix. Acquisition again scored 3/3 in each condition, but
the run stopped during the next governed history writeback with
`history_intervention_primary_classification_binding_invalid`. The writeback
failure is retained as `rootless-cognition-cycle-77117c5cfe9f4b639d78`; its
failure artifact records the target model unloaded. No transfer condition
completed. The classification-binding source needs offline diagnosis before
another cycle is preregistered. None of these runs establishes learning,
transfer, or history-dependent improvement.

### Classification-binding failure observability

Offline reconstruction of the v3 acquisition-run projection for
`rootless-cognition-cycle-77117c5cfe9f4b639d78` produced the expected
classification, scope, and response-assessment posture, and that reconstructed
fact passed the history-context binding guard. This does not reproduce the
actual failed candidate or independently authenticate its invocation receipts;
the original failure artifact lacks the field-level values needed to determine
which live binding differed.

The v3 binding guard now attaches a bounded diagnostic to
`history_intervention_primary_classification_binding_invalid`. It reports
boolean equality checks for the fact disposition and each projected
classification field, plus whether the response assessment and decision list
were present. It excludes classification text and model output. This improves
triage of a future occurrence without relaxing the fail-closed check. The
mismatch source has now been isolated. `_developmental_history_interpretation_projection` compacted the v3 source fact but dropped `primary_classification`, `classification_scope`, `full_structured_output_classification`, and `response_text_assessment_posture`, while retaining the v3 source schema. Downstream cognition correctly rejected that incomplete v3 projection. The compact projection now preserves those four source-bound fields. An offline replay of the saved acquisition run through the compact projection and history-context validator produced one valid history context without rejection. The replay is a structural compatibility check; it does not independently authenticate the invocation receipts. The answer-free field diagnostic remains in place for other binding failures.

### Reused history-instruction control binding

The follow-up cycle `rootless-cognition-cycle-75d63a4655604c88ac3a` stopped at
`experiment_control_drift` before the next cognition invocation. Its persisted
v5 protocol pins instruction digest
`sha256:a34910f988d0aa923a7a9f8d3c3887529ad136fa6442c8bebc9e2b7b7803dbb6`.
Recomputation showed this exactly matches the base experiment instruction plus
`HISTORY_INTERVENTION_MEASUREMENT_INSTRUCTION`; it does not match the base
instruction alone. Protocol creation included that suffix when current
World-State contained an intervention-run fact, but `_cognize` checked only the
base instruction. Both paths now use one instruction-template builder, and the
control-drift failure carries boolean-only checks for each protocol binding.
The saved protocol matches the shared builder offline. No model output or
inference receipt was changed by this source fix.

### Completed source-bound v6 cycle, 2026-11-22

The fresh cycle used seed `2026112206`, protocol digest
`63dac1986ead6aabb882ba1a2d20dfd805c223fdb713b533b510899b7966d10a`, and
source content digest
`85e730af7943caedf0160e460b5a1ad79baa8a121ca4983788f0f1602ff0c4c0`. Cycle
`rootless-cognition-cycle-515800da0a8749fb8ffc` completed with stable complete
source provenance and governed Hermes unload. Its terminal artifact is
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-515800da0a8749fb8ffc/cycle-result.json`.

Acquisition scored 3/3 in each of history-present, history-withheld, and
history-restored. The owner bound three correct examples to retained record
`devrec-dec0f183ac5255063b0c87d8`. On disjoint transfer probes `[6, 7, 9]`,
with targets `[13, 15, 19]`, history-present scored 2/3, history-withheld 0/3,
and history-restored 2/3. The runner verified the task-family history lineage,
projection-bound prompt delivery, exact-example counts of 3/0/3, restoration
stability, and no exact probe reuse. This is within-run evidence of a
history-associated transfer difference for this fixed synthetic task and model.
It is not evidence of durable learning, weight change, general intelligence, or
improved real-world performance; the independent cycle assessment correctly
keeps `performance_improvement_established` false.

The separate structured companion-recall measure rejected the withheld
condition because its response cited a history record that was not available in
that condition (`companion_interaction_history_id_not_allowed`). That measure
therefore reports no qualified history-associated decision difference. The
synthetic body consequence was contradicted, with no real action or operator
observation. These findings do not invalidate the independently scored
objective transfer comparison, but they remain separate and the failed recall
condition stays visible. No additional model inference was performed after the
cycle completed; the private WSL Ollama server was stopped and the GPU returned
to idle.

### Offline retrospective audit

The CPU-only retrospective audit `retrospective-audit-v16.json` independently
reloaded the acquisition owner run, verified its per-experience score binding,
and verified all three condition receipts, their prompt/output digests, history
selection, and retained-record bindings. Its transfer audit reloaded and bound
the condition score summaries and recomputed the no-exact-probe-reuse result
from the verified selected records. The audit does not attest the inference
backend independently, reconstruct the live model session, or establish model
attention or learning. It marks the separate transfer projection-delivery audit
as absent; prompt-delivery claims above come from the completed cycle runner's
persisted evidence, not from this retrospective auditor. The audit digest is
`f601ed4cc64b09c15523e10586a57eac1cbc5ed075d4c8d1ed38ccae588bd15c`, and it
binds the terminal cycle-result SHA-256
`7f5152decd551def531fe552ba7c5912278e03fc810a9d9d580cefe559c94e3b`.

### Transfer delivery audit v17

The follow-up CPU-only audit
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-515800da0a8749fb8ffc/retrospective-audit-v17.json`
now independently binds each v5 condition delivery summary to its persisted
invocation receipt, governed request digest, projection digest, and selected
history references, then reloads the referenced records and verifies their
digests. It reports `verified_v5_request_projection_and_history_refs` for all
three conditions (one selected record in present/restored, zero when withheld).
This closes the v16 transfer-audit gap where that auditor reported the newer
projection-delivery audit as absent. The v17 audit still cannot reconstruct
ephemeral prompt text from its digest or establish model attention, causal use,
learning, or improvement; those claims remain false. Audit digest:
`84318f67c371c5bd47f0a3625efd208f6921f69eea154cf7d2f934e08faac6e0`.

### Per-cycle model identity pins and seeded admission preflight, 2026-11-22

Campaign plan v4 stores one expected model-identity digest per ordered
backend seed. The runner's model configuration digest includes the backend
seed, so a single identity pin could not describe a campaign whose cycles use
different seeds. The offline plan builder derives these pins from the exact
Ollama manifest, model name, GPU-layer bound, and session configuration without
loading the model. A regression check reproduced the persisted seed-45 Hermes-4
identity exactly. The earlier v3 plan is
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/protocols/rootless-history-campaign-83be20cd614a9f7230a1.json`,
digest `9c5bfd1b7fb809cdbf71cfe943e46e83d863412b5f0f26095d80952525b91656`.
Its two identity pins, cycle IDs, seeds, and six-file initial history boundary
were re-derived and byte-verified before launch. Plan and audit schemas are now
v4 and v5; v2 and v3 plans remain available for retrospective verification.

The first planned cycle stopped at `synthetic_pre_action_cognition` with
`developmental_history_recovery_failed`. It copied and reloaded all three
history records and receipts, but the new run's owner could not resolve their
`admission_id` values because the corresponding `runtime_admissions.json` was
not seeded from the source cycle. The failure artifact contains no inference
receipts, the Hermes model was not resident, and the GPU remained at 0% with
890 MiB in use by unrelated host processes. This is not a cognition result.
It identifies a continuity gap: a cross-cycle history seed needs its verified
writeback-admission evidence alongside records and receipts before the next
owner can recover them. The existing run roots for the earlier pre-inference
plan and identity-pin failures are retained as incomplete artifacts; none
performed model inference or supports a learning claim.

Plan v4 also binds the canonical runtime-admission ledger from the initial
history source, including its byte digest, admission and revocation counts, and
sealed per-entry digests. The runner validates that ledger, copies its verified
snapshot into the new private state before owner recovery, and records the
resulting ledger boundary in each terminal artifact. The v5 campaign audit
checks that prior admissions and revocations remain present and unchanged across
each cycle. The offline gate found a validator mismatch: `AdmissionLedger`
represents binding digests as `sha256:<hex>`, while the campaign plan loader
accepted only bare hexadecimal values. The loader and JSON schema now validate
the namespaced digest format, with a regression fixture. The admission-aware
campaign loader and seed-copy path passed an offline check against the existing
v6 source: all three records, receipts, and admission bindings were copied to a
temporary run store and reloaded with matching boundaries. No model was loaded
and no inference occurred.

A fresh v4 plan pins the runner's default 32 GPU layers at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/protocols/rootless-history-campaign-d013c18d0e4b37a1f166.json`,
digest `7c5eda8de5201fab56d106749234c25f4d19ecd91417f80e29e85d53091e90da`.
The earlier draft pinned 33 layers and is retained as a superseded artifact;
it was never launched. The corrected plan passed campaign launch validation
and the temporary seed-copy check again. The WSL runner carries the exact
ledger boundary into terminal artifacts, so the audit can follow admission
continuity as well as history continuity.

Hermes inference remains pending. The Windows Ollama endpoint is healthy, but
WSL cannot reach its loopback address at `127.0.0.1:11434`; no relay or broader
network binding was started. No inference occurred, so this offline validation
is not evidence of model attention, learning, or improvement.

The admission-boundary helper now has direct regression coverage: a later
ledger may append new admissions and revocations, but removing or changing any
previous admission or revocation binding fails the continuity check. The
focused campaign suite passes all nine cases, including the namespaced digest
format accepted by the persisted runtime ledger.

## 2026-11-22 CUDA continuation

The Windows Ollama service exposed no CUDA device, so this continuation used
the private WSL Ollama 0.40.16 runtime, which detected the RTX 3060. The model
was pinned to `hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`, the
verified local manifest, and 32 GPU layers. Resource samples observed roughly
8.6 GiB allocated during inference and no CPU fallback; the model unloaded
after each attempt.

Campaign `rootless-history-campaign-99bd17468bbfa45586ba` retained the earlier
CPU-fallback failure and was superseded. Its first CUDA attempt,
`rootless-cognition-cycle-510329c126e2c0004cb5`, completed pre-action cognition
and governed developmental writeback, then stopped because the WSL runner's
probe-outcome summary omitted answerability fields that were already present
in the persisted objective evaluation. No learning claim is made from that
attempt. The isolated runner was updated to recompute the same answerability
fields and to include the cognition recovery-state boundary in failure
artifacts.

A fresh two-cycle plan was then sealed as
`rootless-history-campaign-6d3f61c8e3f108aa752d.json`, digest
`b350077fd5a4ea7c0a471ae0469d2464ed825f723d428534aa554e472f9ab1bc`. Its
first cycle, `rootless-cognition-cycle-2b4c31c1011a779adfab`, ran on CUDA and
reached objective-family acquisition. It stopped in the governed cognition
writeback path with
`history_intervention_primary_classification_binding_invalid`. Offline replay
of each persisted seed record passes the same context validator, locating the
failure in a fact assembled during the live acquisition tick. The terminal
failure artifact does not provide a usable recovery-state binding, so the
second cycle in this plan was not launched and this chain cannot support a
learning claim.

The classification-binding diagnostic now records bounded schema and
classification fields alongside its boolean checks. It excludes model output
text. This should make the next acquisition failure distinguish missing
bindings from mismatched values without treating either as cognitive evidence.
No regression suite was run during this continuation.

The first plan created for that diagnostic follow-up pinned an out-of-range
Ollama backend seed and stopped at model preflight before inference. It is
retained as an unused failed plan. A corrected plan,
`rootless-history-campaign-30f056611fba91a7bf5f.json`, digest
`07302eddb787cdb1d7b0beb5a79ed3bf44a3a10c3af04dad7515d2965b2f7861`, pinned
backend seeds within the runner's accepted range. Its first cycle,
`rootless-cognition-cycle-4ce05c05e331ea124e2c`, stopped at
`synthetic_pre_action_cognition` with `history_context_budget_exhausted` after
31 retained inference receipts. The model unloaded and GPU free memory returned
to 11,222 MiB. An offline compact-packet size read over the five persisted
records totaled 13,222 characters, but it did not reconstruct the full cognition
prompt or target-identity projections. The artifact therefore proves that the
assembled history-conditioned prompt could not admit a history record; it does
not isolate the history packets as the only source of pressure. No improvement
or learning claim follows. The
classification-binding v2 diagnostic was not reached, and the plan's second
cycle was not launched. The next experiment needs a preregistered, auditable
history-context budget strategy before another model cycle.

The context-budget failure path previously discarded the binder's existing
size-only attempts and history-selection summary when it rejected an empty
selection. `_cognize` now attaches a bounded diagnostic containing the input
limit, retrieval policy, task-family ID, available/selected/omitted counts,
selection digest, and filtered prompt-size attempts. It records neither record
IDs nor prompt/model text and keeps the fail-closed requirement that a
history-required cognition step must receive history. This is an observability
improvement; it does not resolve the accumulated-history budget issue. The new
diagnostic has not yet been exercised by another model cycle, and no tests were
run during this continuation.

An offline projection review found repeated invocation-receipt IDs and digests
inside score-linked condition evidence. The compact prompt projection now
retains each condition's receipt-verification status and posture, and binds the
omitted receipt identities with a collection digest. Full identities and
receipts remain in the durable source records; the complete source-model
identity mapping remains in the prompt because cross-run strategy aggregation
recomputes its digest. Applying the old and new compactors to the same raw
task-family example reduced its serialized size from 4,330 to 4,111 characters
(219 fewer). This packet-only measurement does not prove the full prompt now
fits. No model inference or tests were run, and this reduction makes no learning
claim.

An offline continuation plan is sealed against the current retained history
and recovery state at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/protocols/rootless-history-campaign-5c8a2f3d9b1e7046c2a1.json`.
Plan digest: `fecb91c3ff42985899f4fc3a7c59e7011cb0f8aab58b342dda48f45bb39569c4`;
initial history boundary digest:
`5eee38e4b5d3b696e8899c98530f81bda68f422426fa57f6302da9848ac10923`. Its
ordered cycles are `rootless-cognition-cycle-1b3e9ad0475268c1e621` and
`rootless-cognition-cycle-87fd4520b689ac31f0c4`. The plan pins the verified
Hermes manifest, task family, distinct task/backend seeds, and 32 GPU layers.
Preparation and `--verify-existing` agreed on the digest; both report no
inference and `preregistration_timing_independently_attested: false`. The first
planned cycle was launched when the operator released the GPU, then stopped at
`synthetic_pre_action_cognition` with `history_context_budget_exhausted`. Its
failure artifact records 31 admitted completed inference receipts. The bounded
prompt-size attempts show that even a single-record `compact_refs_only` candidate
was 24,799 characters against the 24,576-character limit; the next candidate
was rejected before inference. GPU residency returned to the idle baseline.
The paired second cycle was not launched: prompt construction is being changed,
so continuing under the old plan would mix implementations. The run establishes
neither model attention to retained history nor learning.

The prompt-only history selection was changed to carry record coverage counts.
Full available and omitted identities remain in durable custody metadata and
selected packet/citation bindings; the prompt does not need duplicate IDs and
digests for omitted records. A fresh plan is required before another comparison.
The previous campaign remains a valid record of the incomplete attempt, not a
preregistered evaluation of the new prompt projection.

The prompt-compaction update was exercised in a fresh campaign,
`rootless-history-campaign-c8a3e2d41f7096b5c4a7` (plan digest
`bd0771b47bd22dd520fbe2b80f97bb5a863e19ed8811b4708f1737a5302903fc`). Its
first cycle, `rootless-cognition-cycle-a4509d783fc512b0d1e7`, advanced through
`synthetic_pre_action_cognition` and `governed_developmental_writeback` before
stopping at `objective_task_family_acquisition` with
`history_intervention_primary_classification_binding_invalid`. The failure
diagnostic showed that the retained v3 summary classification matched its fact
disposition, while all explicit payload-level class/scope bindings were absent.
The cycle wrote 39 admitted-completed local inference receipts, then unloaded
Hermes; the post-run GPU sample was back at 892 MiB used and 0% utilization.
No causal or learning claim was made. The second cycle was left unlaunched
because the next code change addresses compatibility with this summary-only
history shape. That compatibility change is documented separately and still
needs a fresh model cycle before it can be treated as exercised.

A new two-cycle continuation is prepared against the resulting history boundary
(`267cab2e3857de2f46197c2a10150c51d832e866e9384850e94fec53a8c653e8`) at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/protocols/rootless-history-campaign-83f91a4d0c6e275b921a.json`.
Its digest is
`90d467c53b5a98a70e646ba8de20f92464eec7f132521d1ddf17ad59cd7209fe`;
its cycles are `rootless-cognition-cycle-d014bdb4dd2b3f9c8a71` and
`rootless-cognition-cycle-f29a8b1c7d4e6305a2c8`. The new cognition source is
byte-identical between the workspace and WSL runner
(`4cd8916b982e94e9dd226bba83cc0bb9585ba16017a5d1a0ce578e4eb429aa7e`).
Plan preparation and `--verify-existing` agree. No inference was performed
during preparation; independent preregistration timing is not attested. This
continuation was launched after the operator released the GPU. Cycle 1
(`rootless-cognition-cycle-d014bdb4dd2b3f9c8a71`) completed. Its objective
transfer recorded `[3, 0, 3]` correct probes across present, withheld, and
restored conditions, with restoration matching present. This remains a single
synthetic same-model episode and does not establish learning or generalized
improvement. Its companion intervention rejected an invalid withheld response.

Cycle 2 (`rootless-cognition-cycle-f29a8b1c7d4e6305a2c8`) terminated during a
later transfer writeback with `experiment_history_binding_drift`: expected
history selection contained three records, while live selection contained two.
The immutable transfer run file records `[3, 0, 3]` and stable restoration,
but the parent cycle did not complete and semantic receipt verification of the
run artifact is still pending. Treat these scores as recorded, not independently
verified; they are excluded from completed longitudinal episodes. The campaign
audit verified append-only history and seed-boundary chains, but found planned
cycles incomplete and learning unestablished. Hermes was unloaded after the
cycle; the GPU returned to idle baseline.

The local diagnostic path now preserves the durable selection summary,
prompt-selection counts, protocol digests, and bounded prompt-size attempts
when this drift occurs, without including prompt or model output. A fresh
preregistered campaign is needed to exercise that diagnostic and resolve the
selection mismatch. Independent preregistration timing remains unattested.

The follow-up objective preflight now uses the objective inference packet modes
when sizing its admitted history. Two launch attempts against the next prepared
campaign stopped in preflight before cognition: the first used a model alias
that did not match the pinned Ollama tag; the second used backend seeds above
Ollama's signed 31-bit limit. Both failures made no learning claim; the GPU
returned to idle. Campaign preparation and backend-seed parsing now reject
seeds above `2**31 - 1`, matching the Ollama backend contract. A fresh plan
must pin the actual tag `hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`
and valid backend seeds.

With the corrected model tag and seeds, cycle
`rootless-cognition-cycle-34f3af0dc5546816a3a1` reached acquisition writeback
and then failed on history-selection drift. The bounded diagnostic showed four
available records, three selected in preflight, two selected in the actual
22,978-character prompt. This exposed another preflight difference: the
preflight omitted active-model identity context that `_cognize` added before
inference. The cognition owner now captures the identity before retrieval and
uses that same value in preflight and each comparison condition. The cycle
produced no learning claim; Hermes unloaded and GPU use returned to idle.

The next campaign, `rootless-history-campaign-c1fdeb89b42fb7d4fd96`, used the
correct model tag, valid backend seeds, and active-model identity shared across
history preflight and inference. Plan digest:
`4065d0960ce1b16caa45748db09711237aeb4b7659db73aacf229042ce6f833e`. The two
cycles (`rootless-cognition-cycle-05bda3c4d231f9a765c5` and
`rootless-cognition-cycle-797e9fd3f02b355e9de4`) both completed with stable
source provenance. In each scored transfer artifact, present and restored
history selections matched, and the withheld selection contained zero records.
The audit at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/protocols/rootless-history-campaign-c1fdeb89b42fb7d4fd96-audit.json`
verified the append-only and seed-boundary chains and confirmed all planned
cycles completed.

The first transfer scored `[3, 0, 3]` correct probes with full answer coverage;
the second scored `[0, 0, 0]`, also with full answer coverage. Restoration was
stable in both. The history-associated correctness difference did not replicate
in the second episode, so this campaign establishes neither durable learning
nor a stable performance benefit. Hermes unloaded after the second cycle; the
GPU returned to the idle baseline.

## Fixed-mapping v6 replication campaign

Campaign `rootless-history-campaign-4e092c83fada7a3dba01` continued from the
last completed cycle above. Its immutable plan is preserved at
[`plan.json`](../../artifacts/experiments/rootless_history_campaign_4e092c83fada7a3dba01/plan.json),
with digest
`80e7f3377f5282e8c4a765f6c47b224f039eb5e4ebc5f894d9448d5fc54b872d`. It
registered cycles `rootless-cognition-cycle-a02be6d3b0e82fe59391` and
`rootless-cognition-cycle-baf4c2d89e35592a4c01` against the fixed-mapping v6
family and the pinned Hermes 4 model. Preparation and `--verify-existing`
agreed; inference was not performed during preparation. Independent
preregistration timing remains unattested.

Both cycles completed with stable source provenance. The v17 retrospective
audits verified owner-run reload and invocation receipts. The first cycle met
the withheld-baseline threshold (3 correct, threshold 2) and completed its
transfer comparison: history-present scored 3/3, history-withheld 0/3, and
history-restored 3/3. The second cycle's withheld baseline scored 1 against the
same threshold of 2, so its transfer comparison was skipped. Both audits found
three score-bound task-family examples in available history, but no
model-attention evidence.

This produces one completed history-associated transfer episode and no
replication. It establishes neither durable learning nor a stable performance
benefit. The paired campaign audit at
[`audit.json`](../../artifacts/experiments/rootless_history_campaign_4e092c83fada7a3dba01/audit.json)
verified all planned cycles and the append-only and seed-boundary chains while
reporting `learning_established: false`. The two v17 cycle summaries are
preserved in
[`cycle 1 audit`](../../artifacts/experiments/rootless_cognition_cycle_a02be6d3b0e82fe59391/retrospective_acquisition_history_audit_v17.json)
and
[`cycle 2 audit`](../../artifacts/experiments/rootless_cognition_cycle_baf4c2d89e35592a4c01/retrospective_acquisition_history_audit_v17.json).
Hermes unloaded after cycle 2; GPU use returned to 0% and memory to 892 MiB.

### Accumulated-strategy projection follow-up

Inspecting the v17 projection fields shows that cycle 1's transfer receipt
bound an explicit `no_candidate_in_projection` result for both
history-present and history-restored; the withheld condition correctly reports
`withheld_condition_candidate_absent`. Cycle 2 has no transfer projection
because its baseline gate failed. Although each audit exposes three
score-bound task-family examples in available history, those counts alone do
not mean the resident cognition path assembled examples from independent
source runs into a strategy. The projection did not bind such a candidate, and
the campaign makes no accumulation or learning claim.

The next useful cognition check is a later cycle whose frozen history boundary
includes completed, receipt-verified source runs with at least three distinct
correct inputs across two independent runs, where each run contributes an
input absent from the other. This is the current v8 candidate builder's
minimum independent-input anchor. Its projection should be inspected before
inference and again in the receipt-bound audit; any candidate remains
historical, provisional, and non-authoritative. Keep the baseline threshold
unchanged and treat a skipped transfer as missing evidence, not a negative
transfer result. This isolates whether accumulated evidence reaches the
reasoning context before spending another GPU cycle on a comparison.

### Two-run accumulated-history follow-up plan

The completed v6 acquisition records supply a concrete setup for that check.
Cycle 1's receipt-verified acquisition used inputs `[3, 4, 5]` and scored all
three correct. Cycle 2's used `[2, 4, 5]`; its present and restored conditions
scored 3/3 while its withheld baseline scored 1/3. Both acquisition records
and receipts are present in cycle 2's retained history store. The runs therefore
have two distinct inputs each and four distinct inputs in their union, with
input 3 unique to cycle 1 and input 2 unique to cycle 2. This meets the
candidate builder's independent-input shape if both structured experiences
remain projectable in the next cognition context; it does not establish that
they were jointly selected or that a strategy was learned.

An offline two-cycle follow-up plan is now prepared from cycle 2's retained
history boundary. The immutable plan is
[`plan.json`](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/plan.json),
campaign `rootless-history-campaign-9cc30cb351fa44ad9d51`, digest
`f556ffcf65946c122fc561e781fc40fc746471a33d6a128a37112ece3272ba91`, with
initial history boundary digest
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`.
The boundary includes 46 files (records and receipts) and is marked
non-atomic. The two planned cycles are
`rootless-cognition-cycle-c4e8743bad34018ac728` and
`rootless-cognition-cycle-d13f48b2c90167ea4420`, using distinct task and
backend seeds. Preparation and `--verify-existing` agreed, and both reported
`inference_performed: false`. Independent preregistration timing is
unattested. The plan is ready for later execution when GPU access is available;
it has not run and makes no learning claim.

The review gate for the first cycle is the actual pre-inference history
projection: confirm that both receipt-verified runs contribute their disjoint
correct inputs and that the accumulated strategy, if emitted, is bound into
the exact governed prompt. Then inspect the receipt-bound post-run projection.
If either source is missing, withheld, unsettled, or not projectable, record
that reason and stop short of treating candidate absence as evidence against
learning. The second planned cycle can assess whether any candidate survives a
new acquisition and whether a later transfer comparison qualifies under the
unchanged baseline threshold.

### Offline anchor audit of the prepared boundary

The plan's exact initial history root was re-audited without inference using
[`audit_task_family_history_anchor_coverage.py`](../../work/audit_task_family_history_anchor_coverage.py).
The read-only audit matched the planned boundary digest before and after the
scan and semantically verified all 23 record/receipt pairs. It found 12 stored
records with v6 task-family facts,
12 projectable source runs, and 36 score-bound examples. Eleven runs supplied
at least one evaluator-correct input; together they cover 8 distinct correct
inputs, with 47 run pairs meeting the independent-input anchor requirement.
No repeated input had conflicting correct answers. The anchor-coverage status
is `independent_correct_input_anchor_available`.

This inventory is strong evidence that the planned history store contains
enough score-bound material for the candidate builder's input-anchor stage.
It is not evidence that retrieval selects those records together: prompt
selection remains unassessed. The reported model identity is cycle 2's
completed identity as a reference, not the future cycle's seed-specific
identity. Other strategy gates, prompt binding, transfer, and learning remain
unestablished. The answer-free audit is preserved at
[`initial_history_anchor_audit_v3.json`](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/initial_history_anchor_audit_v3.json),
digest `648e81084d45ce40c71c79631fb026dc0fd8e8841c2b13fb88b67cefe4901370`.

### Prompt audit of the next transfer cycle

The GPU-backed follow-up used a fresh two-cycle plan, campaign
`rootless-history-campaign-975971fcfac690515967`, plan digest
`31a4b780c3dd5d0cb7ac7d7d4eccaf3976a2664c7f56347c05da6695b208aa4c`.
Its timing was not independently attested. Cycle
`rootless-cognition-cycle-63d115b84ec6036b2bdd` completed acquisition and
transfer inference, then stopped at `objective_task_family_transfer` because
the post-run validator rejected projection schema v32. This was a runner
compatibility defect: the projection validator's accepted-version range ended
at v29 even though its later validation logic handled v30 through v33. The
range now includes v33. The terminal cycle artifact remains intact and was
not retried.

An offline revalidation of the persisted present, withheld, and restored
receipts passed with the corrected validator. Present and restored each had
one selected task-family record with three relevant examples; withheld had
none. The present/restored prompts had no accumulated multi-run strategy
candidate, despite the broader history inventory containing many projectable
runs. The observed objective scores were 3/3, 0/3, and 3/3. This is one
within-cycle history-associated pattern, not a replicated transfer result;
receipt evidence establishes request projection, not model attention. No
durable learning or authority is established. The answer-free, digest-bound
[prompt audit](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/cycle_63d115b84ec6036b2bdd_prompt_audit_v1.json)
records the three validator results and their limits. The second cycle in the
plan has not run.

### Additional retained records in transfer retrieval

A later fresh plan, campaign `rootless-history-campaign-6a8c5606c73665926428`,
used plan digest
`141ad240526784f039c7be0d223600a15a3f7b15d570986b0f6b191a8bb47491` and
cycle `rootless-cognition-cycle-48dcc6e5c13a544f9b5a`. Its acquisition
completed, and its transfer run generated receipt-bound present, withheld, and
restored conditions. The runner then stopped because a post-run check required
the present/restored retrieved-record lists to equal exactly the single new
acquisition record. Offline projection validation showed that both conditions
had also selected the same older retained record. The new acquisition record
was present in both; withheld selected none. The prompt projection passed all
three condition audits, so this was another overly strict runner check. It now
requires the acquisition record in both exposed conditions and identical
present/restored selection lists, while permitting additional retained
records.

The persisted transfer task scored 0/3 in all three conditions. Neither the
acquisition record nor the older record formed an accumulated multi-run
candidate in the prompt. This establishes no transfer advantage and no
learning. The immutable [offline prompt audit](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/cycle_48dcc6e5c13a544f9b5a_prompt_audit_v1.json)
contains the answer-free receipt and projection bindings. The campaign did not
complete: its next planned launch stopped in model preflight before inference,
so there is no second cycle result to compare.

### Correct-example-aware history ranking

The retrieval audit found that the exact-probe match `devrec-d476d487664a5dc051c71d75`
had no usable evaluator-correct examples, while the same available set included
two other records with three evaluator-correct examples each. Probe overlap
ranked the score-incomplete record ahead of those positive source runs. The
task-family selector now ranks distinct, verified correct-input coverage
before model identity and exact-probe overlap; all score and model qualifiers
remain attached. The prompt-bound policy identifier is v9, and the family
policy without a target model identity is versioned v4.

A CPU-only reprojection against the unchanged 13-record history boundary
selected a different two-record suffix. The candidate builder accepted those
records as a provisional two-run, six-input affine candidate. This is a
counterfactual retrieval result: no exact prompt was assembled, no inference
was performed, and it does not show the model would attend to or use the
candidate. The immutable [ranking reprojection](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/cycle_48dcc6e5c13a544f9b5a_retrieval_rank_reprojection_v1.json)
binds the source boundary, prior selection, simulated suffix, and limitations.
A later governed receipt is needed to determine whether the new rank reaches
the exact prompt.

The counterfactual rank was then replayed directly through the resident
owner's `_prior_projection` against the persisted composition state. With the
same 13 family records and four-record cap, the owner selected
`devrec-97839cfc90a8bd497154936a`, `devrec-4fd52036e8b17c28ac02994c`,
`devrec-01e35780a28a539aee7c5fb6`, and `devrec-83bc0097864882302ae02efd`;
the previously selected score-incomplete exact-overlap record was absent.
The history boundary matched before and after this CPU-only replay. The
[owner reprojection artifact](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/cycle_48dcc6e5c13a544f9b5a_owner_reprojection_v1.json)
captures the direct result. It still does not assemble the full cognition
prompt or establish that a two-record suffix fits in its exact input budget.

### Planned first-cycle owner preflight

Before inference, the first cycle in campaign
`rootless-history-campaign-9cc30cb351fa44ad9d51` was replayed against its
frozen initial history. The audit matched the plan's history, cognition
recovery-state, and runtime-admission boundaries before and after replay. It
derived transfer probes `[6, 7, 8]` from the planned seed and reproduced the
plan's target-model identity digest.
The runner and this replay now use the same shared seeded-task constructor,
so the audit does not maintain a second copy of the probe-generation logic.

The v8 audit includes the runner's shared synthetic pre-action body-observation
shape, built with a fixed-length timestamp placeholder, and derives the
current-evidence prompt payload from that snapshot. Four records were ranked;
the binder selected two into a provisional strategy supported by two source
runs and four distinct evaluator-correct inputs. The task-family prompt
projection passed schema v32 validation. The prompt measured 22,836 of 24,576
characters, including 2,019 characters of current evidence. Adding a synthetic
extra-evidence field retains the strategy through 1,696 padding characters
(1,729 serialized evidence characters, leaving 11 prompt characters). At 1,712
padding characters (1,745 serialized evidence characters), the binder selects
one record and emits no accumulated strategy; the prompt then shrinks to 19,247
characters because a history record was omitted. A 16-character-resolution
sweep found no strategy reappearance through 2,048 padding characters. The v3
sensitivity is superseded because it padded `snapshot_id`, a committed
identity field; v4 preserves evidence identities and counts the synthetic
field's JSON overhead, and v5 adds the finer transition sweep. V7 also replays
16 alternate deterministic task seeds (2026112212–2026112227) against the same
frozen history. The seeds cover all four transfer probe triplets from inputs
6–9; all retain a two-run, four-input strategy at the same 22,836-character
prompt length. The relation remains `output = 2 * input + 1`, and all rows have
the same normalized candidate-core digest. The binder chooses two different
record sets, so the full evidence-bound strategy digest has two variants
tracking different selected history lineage. This post-hoc CPU sensitivity
audit does not alter the campaign's planned seed or establish a model outcome. The planned
descriptor's nonce-derived digest is zeroed for repeatability. The
model-generated acquisition record is absent and the observation timestamp is
a placeholder, so the exact cycle prompt is not reconstructed. The exact
runtime gate must still be checked before inference. The answer-free [owner
preflight report](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/planned_cycle_c4e8743bad34018ac728_owner_preflight_v8.json)
is reproducible with
[`replay_planned_cycle_owner_preflight.py`](../../work/replay_planned_cycle_owner_preflight.py).
No model inference, attention, learning, or authority is established.

The planned Hermes launch remains unexecuted. The Windows-mounted checkout
cannot yet provide a usable WSL source observation: its `.git` pointer contains
a Windows drive path, WSL Git status on the mount exceeds the runner's time
bound, and native Windows fingerprinting fails closed on the WSL-created
`bin/python` reparse point. The first ext4 mirror at
`source-cognition-next-live-20261122` completed its content fingerprint but
reported noisy status from the Windows line-ending representation. I prepared
a normalized ext4 mirror at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/source-cognition-next-normalized-20261122`
from the same revision, 46 changed tracked paths, and 176 non-ignored
untracked paths. It uses `core.autocrlf=false` and `core.filemode=false`, with
tracked changes normalized to LF and untracked evidence copied as-is. Its
source provenance reports `worktree_content_status=complete` and matched
across two consecutive observations. Git reports 168 collapsed status lines;
expanded porcelain contains 222 entries (46 modified and 176 untracked), which
matches the provenance parser's count.
The tree is intentionally dirty, but the content snapshot is bounded and
stable. Replaying the plan-bound CPU preflight there produced the v8 audit
digest `sha256:1a556005bc056de21c69e1ba463cd6f33652cc3ca5e47cd2cad8837a82d9d676`.
The report records both the prompt-budget transition and alternate-seed
sensitivity. No model inference was performed, and the GPU-dependent cycle remains paused.
No model inference was performed, and the GPU-dependent cycle remains paused.

The v9 CPU-only follow-up adds per-seed, per-record probe-overlap descriptions
to the owner preflight. These report which projected historical inputs overlap
the current transfer probes; they do not establish that overlap caused owner
ranking, and they do not alter the campaign plan. The [v9 audit
artifact](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/planned_cycle_c4e8743bad34018ac728_owner_preflight_v9.json)
was generated without model inference. Hermes/GPU-dependent testing remains
paused while the GPU is in use.

The v10 CPU-only report additionally captures the exact task-family retrieval
comparator for each eligible history record and checks it against the owner's
selected set across the planned seed and alternate-seed sweep. The diagnostic
is carried only in opt-in retrieval metadata and is not prompt content. Across
all 16 alternate seeds, the binder retains exactly the owner's top two records.
Probe overlap ties at three across all 12 eligible records, while usable-input
coverage and checkpoint order distinguish the top records. This characterizes
the observed history selection and does not establish a performance effect.
See the
[v10 report](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/planned_cycle_c4e8743bad34018ac728_owner_preflight_v10.json).

The planned-seed overlap follow-up makes the held-out qualification explicit.
For seed 2026112211, the transfer probes are `[6, 7, 8]`. One binder-selected
history record contains examples for `[6, 8]`; the other contains examples for
all three probes. Their union covers `[6, 7, 8, 9]`, the full v6 transfer
sampling range. Since v6 draws three transfer inputs from those four values,
no alternate v6 seed can produce a transfer set disjoint from these selected
history records.
This is reused-input recall evidence, so this planned condition cannot be
described as a held-out transfer test. The v11 replay code now includes
per-record overlap for both
the owner-selected history and the actual binder-selected prompt records, plus
a qualification flag that is true only when overlap measurement is complete
and zero. It remains a CPU preflight and does not establish learning. The
[reproducible probe-reuse audit](../../artifacts/experiments/rootless_history_campaign_9cc30cb351fa44ad9d51/planned_cycle_c4e8743bad34018ac728_probe_reuse_audit_v2.json)
uses the resident owner's task-family projection, recomputes the 46-file
history boundary, verifies the selected records against their stored digests,
and binds the v10 report file digest. Its audit digest is
`sha256:d42f4a126b460c90464220aa3f7c066eb1b3e7f01c2daab19d6aad98012d957b`.
The [audit script](../../work/audit_planned_cycle_probe_reuse.py) can reproduce
it from the source mirror and frozen history root without model inference. The
[audit schema](planned_cycle_probe_reuse_audit.schema.json) defines its exact
record, boundary, classification, and no-inference fields; input reads are
bound to one stable file handle and output creation refuses overwrite.
The updated preflight could not be regenerated against the existing normalized
WSL mirror: its current candidate configuration digest differs from the frozen
plan's target identity, and the prior v10 replay fails the same check. The
existing plan and report were left unchanged. Hermes/GPU inference remains
paused while the GPU is in use.

### Versioned wide-range transfer family

The v6 generator samples every transfer probe from `[6, 9]`; the selected
initial history already covers that entire domain. No v6 seed can therefore
produce a held-out transfer set for this history. A new opt-in family,
`rootless_integer_affine_transfer_wide_range_v7`, retains the fixed mapping
`2 * input + 1` while separating acquisition inputs `[2, 9]` from transfer
inputs `[10, 1000]`. The v6 task constructor and v5 campaign-plan path remain
unchanged, preserving all frozen seed digests. The wide-range family uses
campaign-plan schema v6 and audit schema v8; the plan validator binds each
schema version to its matching family.

The resident task-family registry, rootless cycle runner, owner preflight, and
campaign plan/audit now accept the v7 family. The preflight also represents a
valid empty owner-ranking trace for a family with no prior records, which is
the expected initial state when starting v7 from the v6 history. Its no-history
preflight cannot establish that the post-acquisition record reached the later
transfer prompt. The run must still verify acquisition retention and measured
probe disjointness in its exact prompt-delivery evidence. This prepares the
next experiment design. A CPU-only v7 plan is now prepared for campaign
`rootless-history-campaign-8d7c96a4e6b140d3a1f2`, with digest
`81d71c8ae2006072f926d5902848163d6db7cba2cde48f9edf4a2083455c6583`; a
second `--verify-existing` preparation reproduced it byte-for-byte. The
[campaign plan](../../artifacts/experiments/rootless_history_campaign_8d7c96a4e6b140d3a1f2/plan_v1.json)
binds two ordered cycle IDs, task seeds, backend seeds, model identities, and
the frozen initial history boundary.

The [first-cycle owner preflight](../../artifacts/experiments/rootless_history_campaign_8d7c96a4e6b140d3a1f2/planned_cycle_a480d2b53c69471e9f01_owner_preflight_v1.json)
has digest
`sha256:2d68c44adddf0ad3a6437fa17c0dd1fcaa1f62e724e929b66af62a70292a3238`.
It matched the planned model identity, selected no initial v7 history, and
measured no input overlap for acquisition `[2, 4, 5]` and transfer
`[125, 178, 921]`. The planned second seed uses acquisition `[2, 6, 7]` and
transfer `[155, 579, 701]`; that transfer set also avoids the first cycle's
probes. These are schedule and initial-history checks only: no acquisition
record exists yet, so the later exact prompt, delivery, model use, and learning
remain unestablished. No GPU inference was performed.
Hermes/GPU inference remains paused while the GPU is in use.

The original prior-history cycle `rootless-cognition-cycle-baf4c2d89e35592a4c01`
was not present among the Windows-local history stores during the initial
audit, so the owner replay then could not reopen its source records. The read-only
[`audit_prepared_v7_owner_preflight.py`](../../work/audit_prepared_v7_owner_preflight.py)
therefore verifies only report integrity and bindings to the plan, cycle seed,
model identity, deterministic probes, and recorded reuse summary. Audit v4
recomputes both the campaign-plan digest and the 46-file boundary-manifest
digest, and checks the manifest's paths, sizes, hashes, ordering, and counts.
It still cannot establish that the unavailable source files match those hashes.
The [v4 audit artifact](../../artifacts/experiments/rootless_history_campaign_8d7c96a4e6b140d3a1f2/prepared_owner_preflight_integrity_audit_v4.json)
has digest `sha256:3805e66e5d7e17a3371251bdff3095c3cb1ec75b6f9df5895d8b1f2d60da2630`.
The result retains the report's held-out claim and explicitly sets
`held_out_transfer_independently_verified` to false because the source bytes
were unavailable. Its output contract is
[`prepared_v7_owner_preflight_audit.schema.json`](prepared_v7_owner_preflight_audit.schema.json).
For future campaigns, [`archive_rootless_history_campaign_seed.py`](../../work/archive_rootless_history_campaign_seed.py)
can create an optional portable snapshot containing the complete source record
and receipt bytes, bound to the plan and frozen boundary digest. Its output
contract is [`rootless_history_campaign_seed_bundle.schema.json`](rootless_history_campaign_seed_bundle.schema.json).
The source cycle's history was later recovered from the ext4 campaign mirror.
Its live boundary recomputed to the plan's exact 46-file digest. The optional
snapshot was created in a private WSL state directory with bundle digest
`2c306a35e01539c144970e20e9d1cba02c9ef5061aa475c4c0287d51c3f29c44`.
The [v5 source-history audit artifact](../../artifacts/experiments/rootless_history_campaign_8d7c96a4e6b140d3a1f2/prepared_owner_preflight_integrity_audit_v5.json)
reopened and matched all 46 boundary files, reprojected 36 v6 examples across
inputs `[2, 9]`, found zero overlap with transfer probes `[125, 178, 921]`, and
bound the projection implementation digest. This independently verifies
input-level held-out disjointness for the frozen history. It still does not
verify model attention, learning, or a transfer outcome; the planned cycle
roots remain absent and no inference was run.

### Replacement plan with a current model-identity pin

Before any cycle inference, the original plan's target identity was replayed
using its documented model manifest, exact Ollama tag, 32 GPU layers, and both
planned backend seeds. The recomputed identity digests did not match the
frozen plan. That plan remains unchanged and unlaunched.

A replacement CPU-only plan was prepared from the same frozen history boundary
and task/backend seeds, using current identity code. Campaign
`rootless-history-campaign-33ddd4949b735cb3b96e` has plan digest
`5b9577bce6aea09347d18d6459636a31ce38ec54510e84e297207397a07cabe5`; its
[plan](../../artifacts/experiments/rootless_history_campaign_33ddd4949b735cb3b96e/plan_v1.json)
reproduces with `--verify-existing`. Its private initial-history bundle has
digest `f8f59674ef741e232c914d9fae172ab616b39598fdfdabf7a785bab2185e7974`
and also reproduces with `--verify-existing`. The bundle is stored at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/private-seed-bundles/rootless-history-campaign-33ddd4949b735cb3b96e-initial-history.json`;
pass it as `--initial-history-bundle` when the eventual offline campaign audit
is run.

The current-code CPU owner/binder replay for first cycle
`rootless-cognition-cycle-50bb292220abafa1cc5b` matches its model-identity pin,
selects no prior records, and measures zero overlap for transfer probes
`[125, 178, 921]`. It covers 16 alternate deterministic task seeds without a
candidate strategy in the initial history. The
[owner preflight](../../artifacts/experiments/rootless_history_campaign_33ddd4949b735cb3b96e/planned_cycle_50bb292220abafa1cc5b_owner_preflight_v1.json)
and [source-history audit](../../artifacts/experiments/rootless_history_campaign_33ddd4949b735cb3b96e/prepared_owner_preflight_integrity_audit_v5.json)
are bound to the replacement plan. No inference was performed; both planned
cycle roots remain absent. This plan corrected the stale identity pin, but it
stored only the resulting identity digest. It remained unlaunched and was
superseded by the schema-v7 plan below, which records the recipe needed to
recompute that identity before inference.

The rootless runner now repeats the transfer-input overlap check at the cycle
launch boundary for v7 campaigns. Before dependency checks, model residency
inspection, or inference, it loads history through the durable history store,
matches record IDs and serialized-byte hashes to the frozen boundary manifest,
projects the verified records into every source family declared by the transfer
task, and measures transfer-probe reuse. For the v7 wide-range task this
includes low-range v6 and wide-range v7 history. It verifies that the boundary
did not change while it read the records.
The preflight is digest-bound into the run
preregistration and campaign binding; incomplete overlap evidence or any exact
reuse stops the launch. Failure artifacts preserve the preflight when the gate
itself rejects the campaign. This covers prior history at launch; it does not
establish model attention, transfer performance, or learning. The v6 launch
path is unchanged, and no GPU inference was run while adding this gate.
Preflight schema v2 binds the ordered `history_task_family_ids` alongside the
seed, target family, probe sets, boundary digest, and measured overlap. The
offline campaign audit recomputes overlap from manifest-bound prior records
across those declared families for completed cycles and verifies the preflight's
seed, family list, input sets, boundary digest, and self-digest, and rejects conflicting copies across
the terminal artifact, campaign binding, and preregistration. For an incomplete
launch that stopped before copying history into its run root, the audit verifies
the digest and plan bindings but marks overlap as not recomputed; the artifact
does not claim an independent overlap measurement in that case.

### First schema-v7 recipe-bound plan

Campaign `rootless-history-campaign-2a36a80f2612a56bfab0` was the first schema-v7 recipe-bound plan. It has digest
`e8f53f5270a8d2eef46f0a6dbb480a980d7beab1f6b27f369df2156cb825184b` and a
recipe digest `f09655fda1b0f7ea3429641907d1639789ca1943167d2bbd40f2c4f3d5e95c08`.
The [plan](../../artifacts/experiments/rootless_history_campaign_2a36a80f2612a56bfab0/plan_v1.json)
binds the exact manifest path and hash, Ollama model tag, 32 GPU layers,
runtime and generation options, and normalized hashes of the model-identity
implementation files. The plan binds two ordered cycles and retains the frozen
46-file initial history boundary.

Before any cycle inference, run `verify-plan` under the same repository code
and workspace that created the recipe. For this campaign the workspace is
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl`, set
as `SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE`; the recipe's absolute manifest
path is intentionally custody-sensitive. The verifier recomputes the
manifest, implementation, and identity digests without loading a model or
performing inference. The rootless cycle launcher also verifies this recipe
before model or dependency checks, so a changed manifest, runtime option, or
identity implementation fails closed.

The first-cycle CPU owner preflight is bound to the plan and selects no initial
records; it measured zero overlap with transfer probes `[125, 178, 921]` over
16 alternate seeds. The [preflight artifact](../../artifacts/experiments/rootless_history_campaign_2a36a80f2612a56bfab0/planned_cycle_36d6607e2ca2eeb45e61_owner_preflight_v1.json)
has digest `sha256:303edaae409432db778d61874ec55612959675a9b01b1c9e502442071f53a2b9`.
The [v5 source-history audit](../../artifacts/experiments/rootless_history_campaign_2a36a80f2612a56bfab0/prepared_owner_preflight_integrity_audit_v5.json)
reopened the source boundary, projected 36 v6 examples over inputs `[2, 9]`,
and found no overlap with those transfer probes; its digest is
`sha256:36e3564cee64ee024c9ae4c36e8cdf15902b81a442ab6718b2b4429b286aa4a1`.
The private portable seed bundle is stored at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/private-seed-bundles/rootless-history-campaign-2a36a80f2612a56bfab0-initial-history.json`
with digest `5e81b55d5a1727246d8e59a4d88aa109ef3f87dc13b1a3c2702dbeec24134f2f`.

These checks establish source and plan integrity, held-out input disjointness, and a reproducible identity pin. Its first launch attempt exposed a schema-v7 admission-boundary branch omission. After that branch was fixed, the runner reached source provenance and stopped before inference because Linux Git could not read this Windows worktree pointer. The failed attempt is preserved at `/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-36d6607e2ca2eeb45e61/cycle-failure.json`. This plan remains immutable and is not reused.

The fresh plan’s first cycle was then launched with the pinned model and
preregistration. Schema-v7 boundary validation, exact identity verification,
history copying, held-out launch preflight, and source provenance all passed.
The runner stopped at GPU preflight with `gpu_memory_headroom_insufficient`,
before model loading or inference. Its failure artifact records 6,436 MiB free
on the 12 GiB RTX 3060 and 87% host-wide utilization at the check. See
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-9cf3b1f3bff547c1820b/cycle-failure.json`.
The cycle root is now occupied by this incomplete pre-inference attempt; do not
reuse its ID. The second planned cycle was not launched. A later retry needs a
fresh campaign and cycle IDs after the GPU has enough headroom. No model use,
learning, or transfer outcome is established.

### Evidence-preserving retry after a pre-inference GPU block

A GPU headroom failure consumes the original preallocated cycle ID because the
runner has already copied the bound history before checking headroom. I added
[`replan_unstarted_rootless_history_campaign.py`](../../work/replan_unstarted_rootless_history_campaign.py)
to create a successor plan only when the prior plan is schema v7 and its first
cycle has a digest-bound `gpu_memory_headroom_insufficient` failure at
`model_and_runtime_preflight`. It also requires complete source provenance, a valid stage journal, proof the pinned model was not resident, and no result artifact. Before replanning, it independently reopens the failed run root and matches copied history, admission and recovery state, and the local receipt inventory against the frozen plan and failure summary. It validates the on-disk stage checkpoint schema, digest, plan and source-provenance bindings against the summary, and each local receipt must pass `validate_receipt` with matching ID, digest, and correlation; none may be bound to the failed cycle. It reopens the exact initial boundary and identity recipe,
then preserves the task seeds, backend seeds, history, admission/recovery
state, and model identity while assigning fresh cycle IDs. The output record binds the old plan, raw failure artifact, GPU observation, and replacement plan. Re-running the tool with `--verify-existing` reopens the same failure and history, recomputes both artifacts, and requires canonical byte-for-byte matches. It grants no authority and makes no learning claim. Its contract is
[`rootless_history_campaign_preinference_retry.schema.json`](rootless_history_campaign_preinference_retry.schema.json).

This CPU-only replan was applied to the verified headroom failure above. The
new [plan](../../artifacts/experiments/rootless_history_campaign_c1e23b4a09872dd9ab53/plan_v1.json)
has digest `8f477ee16185e00829c81a5e4b3dc4afa6ed11efc227bdebad17e18878799ebf`.
The [retry binding](../../artifacts/experiments/rootless_history_campaign_c1e23b4a09872dd9ab53/preinference_gpu_retry_v1.json)
has digest `6cc16ed419d86ccc458e008d28dede0b155207fa7a7d94460e26a67c5a18a68d`;
it preserves task seeds `[2026112401, 2026112402]` and backend seeds
`[1112233445, 1987654321]`. Fresh cycles are
`rootless-cognition-cycle-3b40b1d8be605e29657f` and
`rootless-cognition-cycle-6af5bd2a3a4e59c8d101`. The source-history audit
reopened all 46 files and independently verified held-out disjointness; the
owner preflight found no selected records and no overlap for transfer probes
`[66, 711, 820]` or the 16 alternate seeds. The private bundle digest is
`ebee75e7faad83610d95071c08ddb0921936b6bc732a122c5a26201a16a3c63f`.
The saved first-cycle preflight audit originally bound an older projection
implementation digest. Its source boundary and reported checks still matched,
but `--verify-existing` correctly rejected it as a byte mismatch against the
current implementation. A fresh [current-code audit](../../artifacts/experiments/rootless_history_campaign_c1e23b4a09872dd9ab53/prepared_owner_preflight_integrity_audit_current_v5.json)
was generated and then reproduced with `--verify-existing`; it reopens and
matches the same 46 source-history files and retains the independently verified
zero-overlap result.

The CPU owner-preflight replay now accepts `--cycle-index`, so every ordered
cycle can be prepared against its own task seed, backend seed, and model
identity while using the same frozen initial history. The second-cycle
[owner preflight](../../artifacts/experiments/rootless_history_campaign_c1e23b4a09872dd9ab53/planned_cycle_6af5bd2a3a4e59c8d101_owner_preflight_v1.json)
and [source-history audit](../../artifacts/experiments/rootless_history_campaign_c1e23b4a09872dd9ab53/prepared_owner_preflight_integrity_audit_cycle2_v5.json)
are now prepared and reproducibly verified. The second cycle selects no history
records; its transfer probes `[39, 215, 923]` have zero measured overlap with
the source history, and its 16 alternate seeds likewise select no records.
Both planned cycle roots remain absent. These are CPU-only owner/binder and
input-overlap results: no model load or inference occurred, and learning or a
transfer outcome is not established. Hermes remains paused while the GPU is in
use.

## History-transfer readiness audit

The read-only `work/audit_history_transfer_preconditions.py` summarizes
persisted `cycle-result.json` artifacts while keeping the history-conditioned
new-action probe separate from objective task-family transfer. It reports
precondition reason codes, seed status, and the separate objective-transfer
status. It never runs inference and explicitly marks skipped probes as neither
negative results nor learning claims.

The six persisted readiness records say the pattern did not match, but a
read-only scan of their selected history records found the exact structural
reach/predicted-reach/observed-idle pattern in all six. Each fact is attribution
schema v2 with `observation_independence_posture: unverified_caller_assertion`;
none has authenticated observation lineage. The historical skip reason is
therefore imprecise, and these records still do not satisfy the evidence gate.
The audit v2 recomputed each selected World-State source envelope: all six
source digests and attribution payload bindings verified, while zero facts
passed the authenticated-observation requirement. The shared failure is the
unverified observer posture, not a broken record digest.
The versioned readiness predicate (`sentientos.history_transfer_evidence_precondition:v2`)
now distinguishes a structural match from eligible evidence and reports
`retained_history_observation_provenance_unverified` for this case. It only
admits a matching v2 fact only after the selected World-State source envelope
recomputes to its recorded source digest, its source and subject IDs match the
attribution payload, and `verify_consequence_attribution` validates the durable
raw observation receipt bound to that observation.
Separately, the resident cognition projection derives a bounded receipt summary
for model context only after the same verifier succeeds. That summary binds its
schema, observation ID/digest, observer source, signed-envelope digest,
transport-authentication flags, and source-distinctness flag under the
[`observation_authentication_receipt_summary.schema.json`](observation_authentication_receipt_summary.schema.json)
contract. It is a retrieval anchor and participates in bounded typed
historical-report selection when prompt-budget compaction is active; the packet
binds the full report set, selected summary set, and observer-summary omission
count. It does not retroactively change prior results.
Five cycles separately completed
their scored objective task-family transfer intervention; the sixth correctly
withheld that transfer because baseline competence had not been demonstrated.
These are distinct measurements. The cycle artifacts report
`model_attention_verified: false`, so a copied and reloaded history seed is not
evidence that the model attended to that history. No action was executed and
no performance improvement was established by the skipped probe.

The next preregistered history-transfer campaign should first acquire the
specific action/outcome antecedent through the existing governed consequence
path, preserve its source and independent-observation provenance, and only then
ask the matched new-action question. The probe must continue to skip if the
retained evidence does not match; generating a convenient synthetic matching
record would defeat the test. This audit makes the current prerequisite gap
visible without modifying prior run records or changing the readiness gate.

The runner now routes its deterministic synthetic outcome through the actual
signed loopback observer protocol. Its key is ephemeral and held by the same
experiment process, and the versioned pre-action evidence labels this as a
`signed_loopback_same_process_synthetic_fixture`; it explicitly records that no
physical observation was established. This can exercise receipt validation,
durable projection, and history-conditioned decision plumbing in a future
cycle while remaining synthetic protocol evidence. It is not evidence of an
external observer, physical consequence, or developmental improvement.

### Schema-v8 experiment implementation binding

Wide-range campaign plans with model recipes now use schema v8. In addition to
recomputable model identity pins, they bind normalized SHA-256 hashes for every
Python file in `sentientos/` and the cycle runner, campaign planner, owner
preflight, offline history-transfer audit, and embedding entrypoint. `verify-plan`, campaign launch, and CPU
owner-preflight replay compare that frozen inventory with the current source
before allowing new work. A source edit therefore requires a newly bound plan.

Schema-v7 plans remain loadable for historical audits and model-identity
verification, but they are explicitly reported as not bound to the experiment
implementation. They cannot start new wide-range work. The inventory describes
the experiment source used by a run; it does not establish what source a model
actually attended to, or demonstrate learning. Source verification is CPU-only
and does not load a model.

### Source-bound schema-v8 retry plan (superseded)

A successor plan is now prepared at
[`plan_v1.json`](../../artifacts/experiments/rootless_history_campaign_683039d369f0608a7d92/plan_v1.json)
with digest
`17e8c13ef0a5aa1fea33c14c7d27714feb947a336aee707a9cb888d458435ddd`.
It preserves the 46-file seed boundary (`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`), task seeds `[2026112401, 2026112402]`, and backend seeds `[1112233445, 1987654321]`, while assigning fresh cycle IDs. Model identities were recomputed from the pinned manifest and recipe, and the v8 source inventory matched all 1,192 included files. Plan creation and verification performed no inference.

CPU owner preflights are stored beside the plan for both cycles. Each is schema v12 and binds the same source inventory digest. Both select zero history records and zero binder records; the planned transfer probes remain disjoint from the selected history. The first probes `[66, 711, 820]` and its preflight digest is `sha256:4ac426cbccb578643f05f47e684b14ab0c68c5a3e8d6016a626a8b3cc2b371a2`. The second probes `[39, 215, 923]` and its preflight digest is `sha256:72c6adcae10a5cd4b02155f10549fae3dd30b6b0c4d1510783ac92b871eec3a9`. These establish the planned owner/prompt boundary and zero measured record overlap only; they do not establish model attention or learning. The launch remains pending while the GPU is in use.

### Synthetic observer receipts stay synthetic in history

Reviewing the signed loopback fixture showed that its durable ingress receipt
previously had the same shape as a separately configured observer's receipt.
Although the cycle summary disclosed same-process synthetic key custody, that
caveat was not present in the attribution written to durable history. A later
history-transfer precondition could therefore mistake the fixture's reported
outcome for eligible observer evidence.

Authenticated observer receipts now use schema v2 when they originate from the
same-process synthetic fixture and carry
`observer_fixture_posture: same_process_synthetic_fixture`. The history-transfer
readiness gate and its offline audit report this posture as ineligible, while
the resident cognition summary preserves it in context. Existing v1 receipts
remain readable. The receipt schema is documented in
[`authenticated_observer_ingress_receipt.schema.json`](authenticated_observer_ingress_receipt.schema.json).
This corrects the fixture boundary only: transport authentication still does
not prove physical observation, key custody independence, causal effect, or
learning.

This initial v8 plan is retained as an immutable preparation artifact. The
subsequent synthetic-observer provenance correction changed the bound source,
so this plan and its preflights no longer authorize a launch. Use the successor
plan below.

### Successor plan with synthetic-provenance exclusion

The signed synthetic observer receipt now carries a v2 fixture marker, the
history-transfer gate and offline audit reject it as independent history, and
the resident cognition projection retains the marker. The correction is bound
into a fresh [schema-v8 plan](../../artifacts/experiments/rootless_history_campaign_f6a13749f17dd8aad14f/plan_v1.json),
digest `4a5ea64d75a39c592fd9a3193b886f178ed351c1995ce76e3cfc4eda09cbd286`.
It uses fresh cycle IDs `rootless-cognition-cycle-0882062e7659e527a1cc` and
`rootless-cognition-cycle-000bc1b7f8ac1d2571db`, retains the same 46-file
initial history boundary and task/backend seeds, and verifies 1,193 source
files with inventory digest `84ab0c24096a6068aa9c72ef3ee13103337d01a81d5bf81f327f19cbb90058dd`.
Model identity and current source pins both recompute; no model inference was
performed.

Both CPU owner preflights were regenerated for this plan. They each select no
history or binder records and confirm zero selected-record overlap with their
held-out transfer probes. The first-cycle preflight digest is
`sha256:deb40e120b30bc5e9f73c307936286c734d031a52d872e2960f4bb47ecfa6977`
for probes `[66, 711, 820]`; the second is
`sha256:2096ed866d165f6bb86b427eee9d10a77c13cfe541055dab527feaf7b07d0caf`
for probes `[39, 215, 923]`. They are CPU-only preparation evidence, not model
attention or learning evidence. Launch remains paused while the GPU is in use.
### Runtime history snapshot binding

The history-transfer precondition now stores the canonical digest of the exact
durable record snapshot it inspected before deciding whether to run the
history-conditioned probe. The offline audit recomputes that digest from the
final record and counts a match as runtime evidence only when the digests agree.
Older cycle artifacts that contain only a record ID remain auditable, but any
pattern found in their final record is labeled retrospective and cannot be
attributed to the precondition decision.

The CPU-only schema-v3 audit of the six persisted cycles found six
source-bound structural pattern facts, zero verified observer facts, and zero
runtime snapshot-bound matches. All six readiness artifacts predate the
snapshot digest and are classified as retrospective-only. The report is stored
privately at
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/audits/history-transfer-precondition-audit-v3.json`
with SHA-256 `8031491580c21f39599de0d060466919c384146485ab43bcfaebccaa7fab395f`.
It made no inference or learning claim.

The preceding successor plan is also superseded: this snapshot-binding change
updates the runner and audit implementation. It is preserved as a historical
preparation artifact and must not be used to launch.

### Successor plan with runtime snapshot binding (superseded)

The current [schema-v8 plan](../../artifacts/experiments/rootless_history_campaign_b091c8863e72bfd543ca/plan_v1.json)
has digest
`eee28961e2e7a1b15207a6aaeb859fe3af4ffcd6330b96bd5e5454bd5558b733`.
It binds 1,198 Python source and JSON contract files with inventory digest
`42e7730ad58d499fd12487d810021a8c8e5969ee86494426a30b69ae295c9a29`, and the
model identity and source inventory were recomputed successfully. Fresh cycles
are `rootless-cognition-cycle-e86fe7761e217d3436a1` and
`rootless-cognition-cycle-8b1b683901a626cc6e24`; the seed history and ordered
task/backend seeds remain the same. Both regenerated CPU owner preflights are
bound to this plan, select zero records, and report zero selected-record
overlap. Their audit digests are
`sha256:d12b828482474b1c48386b0c5421b4d019af84c140a3f599efb2753915019c49`
for probes `[66, 711, 820]` and
`sha256:903be69fa7dc07bee48717970c2598a1cce35f157322e1d8f7bf2f3b5b6c8238`
for probes `[39, 215, 923]`. No inference was performed. Launch remains
paused while the GPU is in use.

This plan is preserved, but the campaign audit has since been strengthened to
verify the precondition digest against the exact record bytes included in each
cycle manifest. A new source-bound plan is required before launch.

The campaign-chain audit now emits schema v10. For each cycle it reports
whether the terminal result's history-transfer precondition digest exactly
matches the named history record in that cycle's manifest. Legacy preconditions
are marked unbound, and completed-cycle snapshot-chain verification remains
false unless each completed cycle has an exact match. This binds the retained
record to the run artifact inventory; it does not establish observer truth,
model attention, or learning.
### Current source-bound preparation plan

The current schema-v8 preparation plan is [plan f77f497556b94c8c35b9](../../artifacts/experiments/rootless_history_campaign_f77f497556b94c8c35b9/plan_v1.json), digest `10bc787ce27c3fae5d22c3ee37991d63828126c4104347c1ead425410cf88a82`. It binds 1,199 source and JSON contract files with inventory digest `28c762c3945d5f93842ad81544d0282b542b78d3864da076a74242f20ab1f52d`; plan verification recomputed the model identity and source inventory successfully. Fresh cycles are `rootless-cognition-cycle-be20292d19035e478c5a` and `rootless-cognition-cycle-dfdfdd0264657976474c`.

Both CPU-only owner preflights are bound to this exact plan and source digest. They select zero records, report zero selected-record overlap, and record `inference_performed: false`. Their audit digests are `sha256:625c05a1c81c478960cdc5fc5ac0a6384e81c5ca434890e5df28a1bf88f4bb87` for probes `[66, 711, 820]` and `sha256:7ed85845cf1d9b8f34a0dc84ffeceab701f7536dbc3bf64112c5a102298942f6` for probes `[39, 215, 923]`.

This is preparation only. No Hermes or other model inference was run, and campaign launch remains paused while the GPU is in use. The campaign audit v10 snapshot-chain behavior has not yet been exercised on fresh cycle results.

### Current plan after observer-receipt retrieval correction

The current schema-v8 preparation plan is [plan a48d7f9eef15455185db](../../artifacts/experiments/rootless-history-campaign-a48d7f9eef15455185db/plan_v1.json), digest `0e1667882d44ce64a3bd9e0320be66ab5c6370a5dbdfc41da11324eb5fb532ed`. It preserves the prior plan's 46-file initial history boundary (`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`), task/backend seeds, and recomputed model identities, while binding the updated retrieval source inventory. Verification reports 1,199 implementation files, a matching current source digest, verified identity digests, and no inference.

Both cycle owner preflights are bound to this plan, select zero records, and report zero held-out probe overlap. Their audit digests are `sha256:81d057a60690913983af086dacfcc02c50548bc1e7755c47e7c068a8f9f7b113` for probes `[66, 711, 820]` and `sha256:37cdde26221193165788d635d76dac69f196187bff690be731ffb356d7d8c4b1` for `[39, 215, 923]`. They are CPU-only preparation; no model inference was performed. Campaign launch remains paused while the GPU is in use. The v10 snapshot-chain audit still needs fresh cycle artifacts before its runtime behavior can be confirmed.

### Review of the latest completed cycle artifacts

A read-only audit of the full current rootless cycle store found six valid
`cycle-result.json` artifacts and no artifact errors. All six had structural
pattern matches, but zero verified source-pattern facts and zero matches bound
to an exact runtime snapshot. Every record lacked a record-snapshot binding
and failed the independent-observer provenance gate with
`observation_independence_posture_unverified`. The audit is preserved at
[`history_transfer_precondition_audit_v3.json`](../../artifacts/experiments/rootless-history-campaign-eb1cfbe07ad74ab8a1d8/history_transfer_precondition_audit_v3.json),
SHA-256
`8031491580c21f39599de0d060466919c384146485ab43bcfaebccaa7fab395f`.

The separate task-family transfer ran in five of these six cycles. Its recorded
history-present, withheld, and restored oracle counts varied, and the run
artifacts keep `performance_improvement_established` and `learning_established`
false. They are descriptive transfer observations, not evidence that the
history-conditioned action-decision gate passed. The current runner labels its
same-process observer as a synthetic fixture and the precondition rejects that
posture explicitly. The next decisive experiment needs a receipt from an
observer outside the experiment process, plus the runtime snapshot digest now
recorded by the current runner. This finding does not justify relaxing the
independence gate. No inference was performed for this audit.

### Persisted cognition summary: prompt evidence limits

The persisted-experiment summary now emits schema
`sentientos.persisted_cognition_audit_summary:v6` and carries forward the v17
transfer outcome, baseline gate counts, paired probe outcomes, prompt digest
binding, and selected-history reload status. For the completed cycle
`rootless-cognition-cycle-a02be6d3b0e82fe59391`, the summary reports a 3/3
withheld baseline against a threshold of 2, verified prompt-digest binding and
history-reference reload, and matching present/restored versus differing
withheld prompt and output digests. It also preserves that exact prompt
serialization reconstruction and prompt-delivery assessment are false.
Therefore, the records support a history-associated scored intervention, but
do not establish what exact serialized prompt reached the model or that the
model attended to the history. The paired cycle
`rootless-cognition-cycle-baf4c2d89e35592a4c01` remains explicitly skipped:
its withheld baseline was 1/3, below the threshold of 2. These fields are
summarized by
[`summarize_persisted_experiments.py`](../../work/summarize_persisted_experiments.py)
from the digest-verified v17 cycle audits; they do not upgrade either result to
a learning claim. Hermes testing remains paused while the GPU is in use.

### Superseded source-bound two-cycle preparation

The previously verified v8 plan was
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-eb1cfbe07ad74ab8a1d8/plan_v1.json)
for campaign `rootless-history-campaign-eb1cfbe07ad74ab8a1d8`, digest
`4bbf81bb099e344b738cb60a15b30b3a21bdc7dd8e8585a1b0329faa322e82fd`. A fresh
offline `verify-plan` recomputed the 1,200-file experiment implementation
inventory and both model identity digests successfully; inference remained
false. The plan freezes a non-atomic 46-file, 23-record history boundary with
digest `f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`.

I reran both owner-preflight integrity verifiers against the reopened source
history using `--verify-existing`. Each returned `verified_existing`; all 15
checks passed, including exact plan and report digest bindings, source-boundary
reopen and stability, deterministic held-out probes, and zero source/probe
overlap. The audit digests are
`sha256:88440764fb24a3aaa6e44029ee8d1cd13f701dcb8f353ece03f6f475e28c328a`
for cycle `rootless-cognition-cycle-f63512f478d14f29b514` and
`sha256:2982ff5ecaf0b859e0be3ca08c8d50d8cfd4d9b3cbb8a4234c9d73dcaa06e9d3`
for cycle `rootless-cognition-cycle-89f4d78f71d948168bf8`. Both reports
select no prior records in the owner preflight and leave model attention and
learning unestablished. This is repeatable preparation evidence, not an
experiment outcome; launch remains paused until GPU access is available.

### Superseded plan after observer key-custody gate (audit v4)

The action-decision census now uses audit schema v4. A valid v1 bridge HMAC
receipt proves that a configured key authenticated a message, but the persisted
receipt does not show that the key was held outside the experiment process.
Such a receipt is now classified as
`observer_key_custody_provenance_unverified` and cannot add a fact to the
verified-source set. The v2 same-process synthetic marker remains rejected as
well. This keeps transport authentication separate from independent source
custody. The updated full-store report is
[`history_transfer_precondition_audit_v4.json`](../../artifacts/experiments/rootless-history-campaign-70cbaf1b256c78a1b9ff/history_transfer_precondition_audit_v4.json),
SHA-256
`ad8e36fac1d21e51290a8b34326da68902f56c0366cef755763d5d5c47987ec1`.
It covers the same six valid cycle artifacts: zero verified source facts, zero
runtime-snapshot-bound matches, and no inference. The new key-custody failure
count is zero because these six records have caller assertions without v1
receipts; they still fail the unverified-posture gate. The earlier v3 report is
preserved as historical output.

Because the audit implementation and schema are included in campaign source
pins, the earlier plan is not current for launch. The new v8 source-bound plan
is [`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-70cbaf1b256c78a1b9ff/plan_v1.json)
for campaign `rootless-history-campaign-70cbaf1b256c78a1b9ff`, digest
`d0cfd460f521cbad504ff2526a9d0bd700c9f3b6cb87aac9f85f12ab64c9b846`. Fresh
verification matched all 1,200 pinned implementation files and both model
identity digests. It preserves the non-atomic 46-file, 23-record history
boundary `f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`
and uses new task seeds `[2026112501, 2026112502]` and backend seeds
`[1112233447, 1987654323]` for cycles
`rootless-cognition-cycle-a3ccf3d1e8048acad74f` and
`rootless-cognition-cycle-86595f319331453fa10a`. Both refreshed CPU owner
preflights bind to this plan, reopen a stable history boundary, independently
verify held-out transfer probes, select no prior records, and report no
inference. Their audit digests are
`sha256:478fd27bc798116f8a5eb06ce6ffbbacea157b946e2476936aea4d939fc7ff76`
and
`sha256:50f5ba8a938968be33f5e71734ae231e7817e10f7c59d3ae6a9397ca928468f2`.
Preregistration timing is still unattested, and no learning claim is made.
Campaign execution remains paused while GPU use is high.

### Current plan with custody-audit v5

Audit schema v5 keeps the fail-closed custody rule and names its aggregate
correctly: it counts records with unverified observer key custody, rather than
calling those records facts. The full-store v5 report is
[`history_transfer_precondition_audit_v5.json`](../../artifacts/experiments/rootless-history-campaign-2c0a5bcb49a3ba6c1457/history_transfer_precondition_audit_v5.json),
SHA-256
`a8bf2577c4ff798989a4aeec4f95fdd3a65bd2343cf180ca5ca6f1fb63c6a9bc`.
It validates against the v5 schema and reproduces six valid cycle artifacts,
zero verified source facts, zero runtime-snapshot-bound matches, and zero
records with valid v1 transport receipts but unverified key custody. All six
current records remain caller assertions without authenticated observer
posture.

The current source-pinned v8 plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-2c0a5bcb49a3ba6c1457/plan_v1.json)
for campaign `rootless-history-campaign-2c0a5bcb49a3ba6c1457`, digest
`911df1cbebb9f4ee5b8abf2ac63a582a1ff21e598062110315eb2df6cc37d9b9`. Plan
verification matches all 1,200 implementation files and both model identity
digests. It freezes the same non-atomic 46-file, 23-record history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e` and
assigns new task seeds `[2026112601, 2026112602]` and backend seeds
`[1112233449, 1987654325]` to cycles
`rootless-cognition-cycle-8e0301344685cd442d92` and
`rootless-cognition-cycle-4a8db718f9c744853659`. Both CPU preflights reopened
the stable boundary, verified held-out transfer probes, selected no prior
records, and passed all 15 integrity checks; a second `--verify-existing` run
confirmed both persisted preflight audits byte-for-byte. Their audit digests are
`sha256:2f6d98e0d5e26b08aa791e3315b3e762705dacf8165d21ad20d1630b2f007fb9`
and
`sha256:85bfcb8a86899dd7440f756364861674b3412f5d2b12f378ddabcf5428408f91`.
No inference was performed. The source-key custody gap remains open, and
campaign execution remains paused while GPU access is occupied.

### Exhaustive action-decision gate census

I reran the read-only history-transfer precondition auditor across the full
current rootless cycle store. It found six `cycle-result.json` artifacts; all
six parsed and bound without artifact errors. Each had a structural pattern
match, but the audit found zero verified source-pattern facts and zero matches
bound to a runtime snapshot. All six reported
`observation_independence_posture_unverified`, a missing record-snapshot
binding, and `skipped_history_evidence_precondition_not_met`. The separate
task-family transfer completed in five cycles and skipped one at its baseline
gate; that score evidence does not satisfy the action-decision gate. The
reproducible offline audit is
[`audit_history_transfer_preconditions.py`](../../work/audit_history_transfer_preconditions.py).
No inference was performed. The next useful evidence must come from an
observer outside the experiment process whose authenticated receipt binds to
the exact retained record and runtime snapshot; changing the gate would erase
the distinction this experiment is meant to measure.

### Combined persisted cognition summary v7

[`summarize_persisted_experiments.py`](../../work/summarize_persisted_experiments.py)
now accepts the optional `--history-transfer-audit` v5 report. It checks the
report posture, row shapes, and aggregate counts again, then includes the
report's byte digest and readiness counts in a separate
`history_transfer_gate_audit` section. This keeps action-decision eligibility
separate from scored task-family transfer and acquisition outcomes. The current
combined output reports five persisted cognition cycles, no incomplete runs,
five completed task-family transfers and one baseline-gated skip, alongside
six action-gate artifacts with zero verified source facts and zero
runtime-snapshot-bound matches. Its pooled learning claim remains false.
The summary ran without inference and emits
`sentientos.persisted_cognition_audit_summary:v7`.
Its JSON contract is
[`persisted_cognition_audit_summary.schema.json`](persisted_cognition_audit_summary.schema.json).
The digest-bound current snapshot is
The current snapshot is preserved at
[`persisted_cognition_audit_summary_v7.json`](../../artifacts/experiments/rootless-history-campaign-2c0a5bcb49a3ba6c1457/persisted_cognition_audit_summary_v7.json),
SHA-256
`3e9cfcf009c21e531655f76c0ddfb4a8867116f0bc26be72a61f369027c317e3`;
it validates against that schema. The five cycle audits comprise three v14
and two v17 summaries. Both scored interventions remain the only completed
comparisons; three were baseline gated. None of the five establishes model
attention or prompt delivery, and the aggregate learning claim remains false.

### Offline paired-outcome readout

I re-read the two completed transfer summaries in the persisted v7 snapshot
without loading a model. In `rootless-cognition-cycle-724d354bc544461b80f6`,
all three conditions scored 0/3; the audit could not independently recompute
probe overlap (`exact_probe_reuse_evidence_unbound`). In
`rootless-cognition-cycle-a02be6d3b0e82fe59391`, history-present and
history-restored each scored 3/3 while history-withheld scored 0/3; the v17
audit recomputed overlap from verified selected records and found no exact
probe reuse. The present/restored scores match, and present/withheld differs on
all three probes in that cycle.

This is one positive within-cycle scorer contrast and one all-failure cycle,
not evidence of durable learning across cycles. Both audits leave model
attention unestablished and prompt delivery unassessed; the later cycle's
accumulated-strategy projection contains no candidate. The next cognition run
should target independently attested prompt delivery and repeat the held-out
contrast across fresh seeds before any developmental-learning claim. These
results are scorer outcomes only; no response-text or preference judgment was
used. No inference was performed for this readout.


### Source-bound plan after worker RPC allowlist hardening

The condition-worker RPC dispatcher now requires an explicit per-worker
`allowed_operations` set. Omitting it can no longer grant every registered
operation. The three current bootstrap paths pass separate fixed lists for the
profile-state probe, baseline inspection, and recovery worker. This is an API
least-privilege safeguard; it does not establish process isolation or effective
filesystem denial.

That implementation is included in the broad source pin, so the previous
campaign plan was retired before inference. The replacement v8 plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-5bda38a8a0016b2f4825/plan_v1.json)
for campaign `rootless-history-campaign-5bda38a8a0016b2f4825`, digest
`8a741050efea8a5f3f04d745b4dce275dd34bce346a9b3647b8d8ce8599df56e`. Offline
verification matched all 1,200 pinned implementation files and both model
identity digests. It preserves the 46-file history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`,
with fresh cycles `rootless-cognition-cycle-5bda38a8a0016b2f4826` and
`rootless-cognition-cycle-5bda38a8a0016b2f4827`.

Both regenerated CPU owner preflights are preserved beside the plan. They
reopened the pinned history boundary, verified the held-out transfer probes,
selected no prior records, and kept the serialized prompts within the
registered bound. Their audit digests are
`sha256:1ed25f39ac672a5bd708f8cba5b15e99dc79c478835ed04adb8b52073548dbf6`
and
`sha256:8a9abc5fdcfc7ba62359fbab4b4777c4c32918c77697b3c0910f0fc3d79454ca`.
The preflights performed no inference. Preregistration timing remains
unattested, and no accumulated strategy candidate was found. Campaign
execution remains paused while the GPU is in use.


### Source-bound plan after retrieval-review blinding correction

The semantic retrieval packet builder now applies stratum concealment to gate
versions v9 through v12, including the finite-sample v11/v12 protocols. Since
that module is included in the broad experiment source pin, campaign
`rootless-history-campaign-7c3a1d0e9b8f4a6c2d01` supersedes the prior plan.
Its v8 plan digest is
`7498b980ccea581c211244879cc1331a9badc35044352a4356f19db3d98446d4`.
Offline verification matched all 1,200 pinned implementation files and both
model identity digests. It retains history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`,
with new cycle IDs ending `...2d02` and `...2d03`.

The regenerated CPU owner preflights verified both held-out probe sets, selected
no prior records, stayed within the prompt bound, and performed no inference.
Their audit digests are
`sha256:b08f7f002eab3c6c48ea8e5d8d75a17763cb70f631b24a66cd1c7219699f1b9f`
and
`sha256:9b7cf1c05e453fd9ad529436025e212a0b34aff8201574e9b4a0494fea316b2d`.
The preflights found no accumulated strategy candidate. Preregistration timing
remains unattested, and campaign inference stays paused while the GPU is in
use.


### Source-bound plan after finite-sample scoring correction

The v11/v12 evaluator now emits per-query nonrelevant-selection indicators
before aggregating the registered finite-sample summaries. Campaign
`rootless-history-campaign-f2b186e8cba9437f06d1` supersedes the prior plan;
its v8 plan digest is
`6166aceea9bd78fadf51090b8dcc86de3a5b529bb381609fb89aa4bcee52a734`. Offline
verification matched all 1,200 pinned implementation files and both model
identity digests. It retains history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`,
with fresh cycles ending `...06d2` and `...06d3`.

Both CPU owner preflights verified held-out probes, selected no prior records,
and stayed within the prompt bound. Their digests are
`sha256:72b25aff9a1303ace6ea863358e7f5f539e9ab6db91dcbb8fc653cf342c74da4`
and
`sha256:5de5480b5f313641c4d56c7b5bd2de810e7a5da7a5faae1ba1553e4e22b50322`.
They performed no inference; no accumulated strategy candidate was found, and
preregistration timing remains unattested. Campaign execution remains paused
while the GPU is in use.


### Source-bound plan after adjudication protocol binding guard

The retrieval packet builder now fails closed if its generated reviewer rubric
does not match the digest frozen in the cohort protocol. Because this edit
changes a pinned experiment implementation file, campaign
`rootless-history-campaign-e3edb24d2f014b88a2ab` refreshes the plan using the
same 46-file initial history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`.
The new plan digest is
`1bb5b48b3aa1bfb71e6dbbfad1fbb592297a32d75b17653789322d6952a60d3b`; offline
verification matched all 1,200 pinned implementation files and both model
identity digests. The plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-e3edb24d2f014b88a2ab/plan_v1.json).

Both regenerated CPU owner preflights qualified the held-out probes, selected
no prior records, stayed within the prompt bound, and found no accumulated
strategy candidate. Their audit digests are
`sha256:894f09a6e5a34d6785a2d2abdf6dca4ed177f61a618b16cd953baee1399de0fb`
and
`sha256:af6d4e7294584ffac5942c28bbdf820a53b4fef0a043b79bc275591294c1c6ce`.
Neither preflight performed inference. The plan verifies model identity from
its pinned manifest; no model was loaded, and campaign inference remains
paused while the GPU is in use. Preregistration timing is still not
independently attested, and no learning or transfer outcome is established.


### Source-bound plan after model-replacement context binding v2

New model-replacement contexts now derive their IDs from the exact compact
manifest fields as well as the full-context digest. The protocol already pins
the context ID, so a changed context manifest cannot be accepted merely by
recomputing its local manifest digest. Context v1 retains its prior verification
path; v2 still omits raw projected content and does not claim to rederive
payload-to-reference correspondence after reload.

Because the context implementation is source-pinned, campaign
`rootless-history-campaign-940ce57d2afe4d0c80a8` refreshes the offline plan.
It preserves the initial history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`.
Plan digest:
`b91d5cd5093f0a7faa5532a71aa8aa2d0f5c58871336bef2d5a428345396737a`.
Offline verification matched all 1,200 pinned implementation files and both
model identity digests. See
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-940ce57d2afe4d0c80a8/plan_v1.json).

Both CPU-only owner preflights qualified their held-out probes, selected no
prior records, stayed within the prompt bound, and found no accumulated
strategy candidate. Their audit digests are
`sha256:33ea56432756acd61c1dc67e9ddd6e32581f5235125a6e82bedacc1d151433a6`
and
`sha256:e43d509a47875d91fa0a8faa3d50ca2a99925a070e368383653c5b6dfe215c78`.
Neither performed inference; no learning or transfer outcome is established.
Hermes remains paused while the GPU is in use.


### Source-bound plan after legacy continuity downgrade

New World-State projections now mark model-replacement history as bound only
when the frozen context uses the v2 manifest identity. V1 run artifacts remain
readable, but their history continuity is projected as unavailable; existing
stored projections are not rewritten. This keeps the weaker legacy manifest
binding from supporting a new continuity summary.

The implementation update changed a pinned source, so campaign
`rootless-history-campaign-de084e6796664d72a6ae` refreshes the plan again,
preserving history boundary
`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`, task
seeds `[2026112601, 2026112602]`, and backend seeds `[1112233449, 1987654325]`.
Its plan digest is
`821e28c5d822db553c3e381e15084ab0e52efb21b93bbfc7e0b3f28c23f756af`;
offline verification matched all 1,200 pinned implementation files and both
model identity digests. See
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-de084e6796664d72a6ae/plan_v1.json).

Both CPU-only owner preflights qualified held-out probes, selected no history
records, stayed within the prompt bound, and found no accumulated strategy
candidate. Their audit digests are
`sha256:56a08b2497957632173332a1e02f0a5eb542dca81572a24a05b58da57bc85b0a`
and
`sha256:dad5a9b6045c960ed32092031b6f0403e41fa6e79fd83dbe1d74804a0288a70a`.
No inference or learning result was produced; the GPU remains reserved by the
operator.


### Why the current transfer preflights select no records

I inspected metadata only in the exact 23-record boundary used above. All 23
are `resident_developmental_writeback:v1` records with untrusted historical
interpretation candidates; 12 candidates cite one selected fact and 11 cite
eight. Across those selected facts, 88 carry no objective task-family tag and
12 are tagged `rootless_integer_affine_transfer_low_range_v6`. The latter
contain 36 evaluator-scored acquisition examples: 32 correct and four
incorrect, spanning eight distinct inputs in the range 2–9.

The planned `wide_range_v7` selector requires an exact task-family match, so it
correctly selects none of these v6 examples. Its held-out transfer range is
10–1000, disjoint from the recorded source inputs. The verified affine mapping
contracts for v6 and v7 match. Task contract v6 now supports an explicit,
digest-bound `history_task_family_ids` relation for the v7 target. That relation
admits correctly tagged v6 records only when the task lists the source family;
it leaves historical labels intact and makes probe-overlap checks span every
listed family. The next offline owner preflight should establish whether the
exact bounded history now yields selected source records and still-disjoint
v7 probes. This protocol change does not establish transfer or learning;
model inference and independently scored outcomes remain necessary. No example
values or answers were printed or changed in this audit.

### Offline cross-range source-family preflight

Task contract v6 is now in the current experiment implementation. The refreshed
plan [plan_v1.json](../../artifacts/experiments/rootless-history-campaign-21cef90426854173ae04/plan_v1.json)
binds the same 23-record starting boundary and two independently seeded wide
transfer tasks. Its digest is
`5bb2c723f042d62499c49afd63e0dd51592154585299595a195de5da9f289486`; plan
verification matched all 1,200 pinned implementation files and both model
identity digests. The manifest identity was computed offline. No model was
loaded and inference remained false.

CPU-only owner and prompt-binder replays are persisted as
[cycle 0](../../artifacts/experiments/rootless-history-campaign-21cef90426854173ae04/owner_preflight_cycle0.json)
and
[cycle 1](../../artifacts/experiments/rootless-history-campaign-21cef90426854173ae04/owner_preflight_cycle1.json).
Each selects the same four records from the explicitly listed low-range v6
source family. The selected historical inputs are all in 2–9, while the seeded
wide-range target probes are `[228, 412, 728]` and `[754, 862, 894]`.
Owner-level and exact prompt-binder overlap checks both report zero shared
inputs, with complete overlap measurement. Correctness-labeled source examples
now pass through prompt packet projection, which had previously filtered by
the target family alone. The binder derives one provisional accumulated
strategy from two source runs and six distinct evaluator-correct inputs. The
same strategy is retained for all 16 alternate probe seeds. Prompts are
23,835 characters against a 24,576-character bound, leaving 741 characters of
measured headroom.

Preflight schema v13 separately binds the task's declared source-family list
to the strategy provenance. Both cycle reports verify the exact list
`[rootless_integer_affine_transfer_low_range_v6,
rootless_integer_affine_transfer_wide_range_v7]`; both supporting source refs
are from the low-range v6 family, no supporting refs were omitted, and their
shared source-ref digest is
`sha256:f7d305ff5487361073fae1a706a76a5e03929800a9af146db940b5ee4700fe17`.

This establishes that the explicit relation reaches the prompt and supports a
reproducible, score-bound candidate strategy while preserving the held-out
probe separation. It does not establish model use, transfer, durable learning,
or improvement. Inference remained false for every preflight.

### Compact score-effect context and corrected retention sensitivity

The transfer preflight prompt projection now sends a compact summary of a
validated historical controlled-task effect: its comparison digest,
classification, posture, restoration label, and historical-only qualifiers.
The full probe transitions remain bound by the durable source record and are
not repeated in model context. Invalid or unbound effects remain uncompressed
so downstream validation can reject them. This reduced each planned prompt
from 23,835 to 23,513 characters and increased its measured margin below the
24,576-character bound from 741 to 1,063 characters.

I also corrected the CPU preflight's retention-transition calculation. It now
compares each sensitivity row with the baseline's actual strategy support
counts and checks the complete ordered padding sweep. The previous calculation
assumed four distinct inputs and skipped the 1,536-character row; this campaign
has six distinct source inputs. The corrected sweep retains both records and
the two-run, six-input candidate strategy through 1,024 synthetic padding
characters, then first loses the strategy at 1,536. This is 256 characters
farther than the earlier observed loss at 768. At the loss boundary the owner
selects one record, so the transition describes retrieval sensitivity; it is
not a model-context truncation or learning result.

The refreshed [plan](../../artifacts/experiments/rootless-history-campaign-08ede5a8969e41a9b871/plan_v1.json)
binds implementation digest
`6287bf036111fc23fb0fb8aa7cbf5e614388982b1b4d3966eb779b1390e37b03` across
1,200 source files. Its [cycle 0 preflight](../../artifacts/experiments/rootless-history-campaign-08ede5a8969e41a9b871/owner_preflight_cycle0.json)
and [cycle 1 preflight](../../artifacts/experiments/rootless-history-campaign-08ede5a8969e41a9b871/owner_preflight_cycle1.json)
both retain the same two records and strategy; all 16 alternate task seeds
also retain it. Their planned wide-range probes remain disjoint from selected
history inputs. This is offline owner and prompt-binder evidence only: no
Hermes inference was performed, and transfer, model use, or durable learning
is not established.

## 2026-11-23: Calibrated history-score retention and two-cycle follow-up

The acquisition history projection was dropping the v6 confidence vector and
Brier score totals while retaining the per-probe confidence values. The
task-family projector correctly rejected that incomplete calibrated score.
`resident_developmental_writeback.py` now preserves those three bounded score
fields for v6 rows. An offline projection audit against the preserved failed
run confirmed the added fields restore the exact source-run score binding
without retaining answer text beyond the existing typed probe examples.

The fresh [campaign plan](../../artifacts/experiments/rootless-history-campaign-91a0cb4f42be41c19d11/plan_v1.json)
was verified against 1,203 implementation files. Cycle 0's CPU owner preflight
passed with a 23,509-character prompt and held-out probes disjoint from the
selected historical inputs. Both preregistered Hermes cycles completed; the
[campaign audit](../../artifacts/experiments/rootless-history-campaign-91a0cb4f42be41c19d11/campaign_audit_v1.json)
verified append-only history, seed, runtime-admission, cognition-recovery,
and transfer-precondition snapshot chains.

Cycle 0 acquired three correct examples. Its held-out objective scores were
3/3 with acquired history, 0/3 with history withheld, and 3/3 after
restoration. Cycle 1's fresh acquisition scored 0/3, so its transfer stage
was skipped. These results show one bounded history-associated transfer and
a failed replication opportunity; they do not establish reliable development
or improvement. Both runs report learning unestablished. The companion
history-decision intervention also rejected its `history_withheld` response,
so no companion decision difference was established. The synthetic body and
observer did not establish physical action or real-world consequence. Hermes
was unloaded after each cycle, and the GPU is now clear.

Private cycle artifacts remain in experimental custody under
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/`:
`rootless-cognition-cycle-64e9e8a2bb1b4b6995f7/cycle-result.json` and
`rootless-cognition-cycle-3f1cd7832e9a4ba7aa11/cycle-result.json`.

The paired acquisition scores also expose a confidence failure worth tracking:
all 18 answered probes were assigned 10,000 basis points, including all six
incorrect answers in cycle 1. I added the CPU-only
[`audit_rootless_campaign_confidence.py`](../../work/audit_rootless_campaign_confidence.py)
reporter to verify each sealed score vector, recompute Brier totals, and bind
the aggregate to the campaign plan and audit without emitting answer values.
Version 2 also compares the matched history-present, withheld, and restored
probe outcomes and checks whether selected source examples expose a derivable
mapping relation to the current task. Its
[diagnostic artifact](../../artifacts/experiments/rootless-history-campaign-91a0cb4f42be41c19d11/confidence_diagnostic_v2.json)
records 12/18 correct, 6/18 wrong at maximum confidence, and a normalized
mean Brier score of 333,333 millionths. The three matched conditions and
repeated task family are correlated observations, so this is a descriptive
confidence-error signal, not a calibration estimate. Calibration, learning,
and authority remain unestablished. The reporter was added after the Hermes
campaign and did not change or re-interpret its execution source snapshot.

The v2 matched comparison shows cycle 1 scored 0/3 with history present and
restored versus 3/3 with history withheld; all three probe correctness labels
changed, and restoration exactly repeated the present condition. The two
selected prior records with this task family yielded one mapping match to the
current descriptor and one unknown relation; no mapping conflict was
verified. This locates the effect alongside incomplete source mapping
evidence, without identifying a cause. A future experiment should preregister
an ablation that separates full historical examples from the compact derived
strategy before changing retrieval policy.

## 2026-11-23: Answer-free historical-example ablation preflight

The CPU owner preflight now constructs a second, offline prompt reconstruction that removes the raw `examples` arrays from selected task-family experience records. It retains the selected record IDs and digests, per-record candidate strategies, the accumulated candidate strategy, and all other bound context. The report carries only an example count and a digest of the withheld material; it does not serialize example answers. This creates the missing prompt-level comparison between full historical examples and compact derived strategy, without changing retrieval policy or the normal binder.

The new `historical_examples_ablation` report section binds baseline and counterfactual prompt digests and lengths, source-record bindings, and retained strategy checks. It explicitly records `runtime_condition_created: false`, `inference_performed: false`, `model_attention_established: false`, and `learning_established: false`. The variant is not passed through the regular history validator or sent to a model. This is a preparation improvement only; it does not yet identify the effect of raw examples. A future paired inference must use fresh held-out probes, independent scoring, and the same sealed history boundary for both variants, while varying only whether raw historical examples are included. The report contract is in the [historical-example ablation schema](rootless_planned_cycle_historical_examples_ablation.schema.json), and the owner report has advanced to v17 so older reports remain distinguishable.

The new schema is now included in the campaign implementation pin. Any future owner-preflight report requires a newly created plan bound to the current source snapshot; existing plans and v16 reports remain historical evidence. No Hermes or other model inference was performed for this change.

## 2026-11-23: Verified historical-example preflight

A fresh two-cycle plan was created from the same sealed starting history boundary, with new cycle IDs and task/backend seeds. Its implementation pin covers 1,204 source and schema files. The plan and Hermes identity recipe were verified without loading Hermes. Cycle 0's CPU owner preflight selected the same historical source boundary (`f091bb019eaed937a347c4ac557ab970e93f92f7d7749852d97b85a5866d6d0e`) and produced a 23,513-character baseline prompt within the 24,576-character bound.

The new ablation reconstructed a prompt with six raw examples omitted, reducing the serialized prompt by 357 characters to 23,156. It retained both per-record candidate strategies and the accumulated strategy, and verified that selected source IDs and digests stayed bound. The report contains an example count and digest only. The read-only verifier accepted the v17 report against the fresh plan and current 1,204-file implementation pin. This proves the CPU prompt reconstruction and report binding work on real selected history; it does not prove model exposure, attention, response differences, transfer, or learning. No inference was performed and Hermes was not loaded.

Artifacts: [fresh plan](../../artifacts/experiments/rootless-history-campaign-218f38275e0d4ee289bf/plan_v1.json), [v17 cycle 0 owner preflight](../../artifacts/experiments/rootless-history-campaign-218f38275e0d4ee289bf/owner_preflight_cycle0_v17.json). Plan digest: `bcf0cc9ee12801f76bd6bc3d60fef8d6268affed31641271e34d0a1e668f446e`; verified report digest: `sha256:4de35932aa1dfce1d1cc86b9a8cc8dac7cee578810a09e2c813927851cc9dd22`.

The v17 verifier now reconstructs the owner preflight from the pinned plan, its recorded prior-history cycle, the bound manifest, and current source. It compares the regenerated prior-history boundary, selected record IDs/digests, baseline prompt digest and size, and the historical-example ablation report with the saved artifact. The same CPU reconstruction independently verified the artifact above. This strengthens evidence that the saved ablation was derived from the selected source packets, while remaining an offline prompt audit rather than an inference result.

## 2026-11-23: v18 held-out overlap binding

Version 18 promotes the historical-example ablation to a source-reconstructed report contract that binds its held-out transfer probe set. The counterfactual changes only the `developmental_history` context field; the omission count, withheld-material digest, prompt lengths, and overlap evidence are report metadata and are not added to the prompt. The existing full-history and example-ablated prompts therefore do not differ by an extra ablation announcement.

The fresh [v18 plan](../../artifacts/experiments/rootless-history-campaign-94ac0c570e234491a44e/plan_v1.json) verified against 1,204 implementation files and the fixed initial history boundary. Its [cycle 0 CPU preflight](../../artifacts/experiments/rootless-history-campaign-94ac0c570e234491a44e/owner_preflight_cycle0_v18.json) selected six raw historical examples and three held-out transfer probes. Overlap measurement was complete: zero historical probe-input overlap and zero overlapping examples. The baseline prompt was 23,511 characters; omitting the examples produced 22,995 characters. Both per-record strategies and the accumulated strategy remained present and unchanged. The read-only verifier reconstructed the report from current source and history, then accepted its plan, prompt, overlap, schema, and report bindings.

This establishes that the proposed pair is source-bound and uses disjoint held-out inputs in CPU preparation. It still does not establish model exposure, response differences, transfer, or learning; Hermes was not loaded. The live one-shot strategy intervention remains strategy-specific, so implementing a governed raw-example pair executor and receipt contract is still required before this ablation can be run as an inference condition.

Plan digest: `4ffc12c7a00ff8d23db03c708dd8febcb3167807776e84436ec48eb26d9731c8`. Verified v18 report digest: `sha256:7713ac5b5fe2743b9fed085d0bd484ed189a3ae26c438ab2646dff481d584fa5`.

## Runtime integration boundary for the raw-example pair

A source inspection of the live owner path found two constraints that must remain explicit before this preflight can be promoted to an inference condition:

- `ResidentDevelopmentalCognitionOwner._cognize` currently verifies that each selected serialized task-family experience is present in the bound prompt. Simply deleting `examples` after binding would fail that check; bypassing it would also discard useful source-to-prompt evidence.
- The existing `preview_objective_strategy_inclusion_pair` and strategy-pair arm executor bind one condition field, `task_family_accumulated_candidate_strategy`, and require each invocation observation to have condition ID `history_present`. They do not represent removal of historical examples.

The owner now has a CPU-only `preview_objective_historical_examples_pair` path. It builds both prompts through the normal owner binder, retains the same record IDs/digests and derived strategies, removes only the raw `examples` arrays from the counterfactual prompt, and binds the pair to the same snapshot, task, model identity, and inference budget. The omitted request uses projection schema v36; the existing packet serialization guard verifies the example-free experience serialization instead of bypassing packet validation. Its typed omission metadata contains counts and digests, not withheld values. Both prompts stop at the existing preview exception before `invoker.invoke`.

The owner now accepts one frozen historical-example arm at a time through `run_objective_intervention_once`. It rebuilds the owner condition and task plan, compares their digests and the final request digest with the frozen protocol, and stops before inference if any binding drifts. The actual call reuses the existing one-condition strategy-arm path, which avoids developmental writeback. Pair coordination and receipt scoring are described below.

For the initial pilot, score the same three disjoint transfer probes independently in both arms and retain per-probe correctness, abstention, and confidence comparisons. Treat the small paired sample as descriptive; any response or score difference is not by itself proof of durable learning. The v18 artifact remains CPU preparation only. The new owner pair preview strengthens prompt construction and binding but does not change that evidence boundary. No model inference was performed for this implementation step.

## CPU protocol freeze for the historical-example pair

Added [`work/historical_examples_intervention.py`](../../work/historical_examples_intervention.py) to turn the owner-bound preview into a content-addressed, pre-inference protocol. Preparation verifies the pair-preview digest, distinct request and prompt bindings, selected history IDs/digests, unique probe bindings, both owner protocol digests, task/model/snapshot/budget bindings, a preregistered answer-key digest, and the digest-only omission summary. The resulting protocol freezes both arms and explicitly records `inference_performed: false`, `learning_established: false`, and `authority: false`. The closed external contract is [historical_examples_intervention_protocol.schema.json](historical_examples_intervention_protocol.schema.json); the saved v2 protocol conforms to Draft 2020-12 validation.

This makes the prompt pair reproducibly preparable and independently verifiable without loading Hermes. The owner now exposes a one-shot arm call that accepts this protocol and binds the invocation to the assigned tick, owner protocol, task plan, and request digests. `build_resident_historical_examples_arm_executor` adapts the owner’s verified observation and invocation-receipt readers to this protocol. Its objective staging request ID is deterministically derived from the frozen protocol digest and arm, and its digest is computed from the reconstructed private task; callers can no longer inject arbitrary per-arm objective request identities. `execute_historical_examples_pair_once` checks the preregistered answer-key digest before invoking either arm, then runs the frozen conditions sequentially with no retry. The resident executor inventories the full developmental-history record set before and after each arm, verifies selected source records against the protocol, and fails if the store changes before the next arm can run. The first receipt is checked for governed request bindings and parsed against the request’s frozen output schema. The paired scorer validates both receipts and emits per-probe correctness, abstention, coverage, and confidence error without answer values or raw output text. It binds each score to receipt, request, prompt, output, protocol, preview, and preregistered answer-key digests. `verify_historical_examples_score_artifact` reconstructs a saved score exactly from that protocol, answer key, and receipt pair. The closed score artifact contract is [historical_examples_intervention_score.schema.json](historical_examples_intervention_score.schema.json).

The first-arm gate now also checks the receipt's generation-configuration
digest against the frozen protocol before the coordinator can start arm two.
The final scorer already enforced this binding, but checking only at that point
could spend the second inference on a pair that was already invalid. This
change fails the pair immediately on generation drift; it has not been
exercised with model calls.

The score contract is now v2 and explicitly records that the current scorer
receives the answer key and arm-labeled receipts in the same process; it fixes
`independent_scorer_attested` to false. This accurately limits a future score
from the pair. The repository's ConditionBlindEd25519DurableLearningScorer and
bounded scorer RPC in sentientos/durable_developmental_learning_experiment.py
provide a custody pattern, but their task-plan contract does not directly fit
this pair. Pair integration must freeze the scorer identity and software digest
before arm claims, provide the scorer opaque arm slots without the slot-to-
condition map, and bind its signed answer-free score to the protocol, task, and
receipt digests. The coordinator must retain the slot mapping until signature
verification; response content may still reveal treatment, so this only hides
explicit condition labels. A signature authenticates a key but does not prove
independent operator or process custody. Until those boundaries are evidenced,
`independent_scorer_attested` and `learning_established` remain false.

`HistoricalExamplesPairJournal` now persists the frozen protocol, each arm's invoke-once claim, the verified receipt body, and the final answer-free score through `DevelopmentalExperimentStore`'s immutable publication and custody checks. Each arm claim is durably published before the owner call. New result v2 records archive the full governed receipt, which is revalidated on reload. The executor also persists digest-bound inventories of both resident history records and writeback receipts before and after each arm, including collection counts and record-set digests; it verifies every receipt still points to a present record with the matching digest and every selected history record has at least one such receipt. The arm inventory digest binds the receipt_record_links_verified finding, and journal reload requires that finding alongside both inventories being stable within each arm and across the pair before score persistence or loading. Score persistence and later score loading reconstruct the private answer key and recompute the score from both archived receipts. A claim without a receipt is treated as an ambiguous outcome and is never replayed automatically. Legacy v1 results remain readable but lack receipt bodies and runtime inventory evidence, so they cannot enter a reconstructed cohort score. No intervention arm has run and no paired receipts have been produced. The paired score can establish only a bounded response difference on its held-out probes; it cannot establish durable or transferable learning by itself.

Added [`scripts/preflight_resident_historical_examples_pair.py`](../../scripts/preflight_resident_historical_examples_pair.py) as the CPU preparation entry point. It reconstructs a selected task and held-out answer key from the deterministic task seed, builds both prompts against a private copy of resident history, checks the arm generation configuration, and persists the content-addressed protocol before any inference. The answer-bearing task specification and commitment nonce are saved only in the private experiment store; the report exposes their digest, not their contents. The first attempt surfaced two boundary bugs: the v36 examples-omission projection treated an optional confidence-effect summary as mandatory, and the preview's raw snapshot digest was not normalized at the protocol boundary. Both were corrected. A further check showed that the task commitment nonce must be persisted privately so later execution can reconstruct the exact task digest; protocol v2 now binds that private task-plan digest.

The preflight then completed against the WSL cycle root `rootless-cognition-cycle-9cf3b1f3bff547c1820b`. Its three probes were `[46, 155, 315]`; an audit of all 23 source history records found no input overlap. Two history records were selected and six raw examples were withheld. The [CPU preflight report](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_v2.json) and immutable journal protocol agree on digest `sha256:8fc596b9e10337e14cdca48baf5f95269810e583b9f4d08970f4080cc5b5f058`; the answer-key digest independently reconstructed from the private task is `sha256:affbddf3176d30f54bb428a523dbf5f76577a322d47b25720597824d77fa92b6`. The journal protocol directory has mode `0700`, and its protocol and private task-plan files have mode `0600`. The report confirms `model_loaded: false`, `model_invoked: false`, and `learning_established: false`. The earlier `preflight_v1.json` artifact predates private task-plan persistence and is superseded; v2 is the runnable frozen protocol.

Added a `--verify-report` mode to the CPU preflight command. It reloads the private task, rebuilds the pair preview against the current source history and receipt, compares the rebuilt report exactly, and verifies the persisted protocol. This read-only reconstruction passed and is saved in [preflight_verification_v1.json](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_verification_v1.json) with report digest `sha256:bb557128eac9b0a0cdd568541c727cfa9492b2e2d3eb0dad57d52ee44f6a1974`. No Hermes inference or GPU work was performed.

### Frozen objective staging identities for the historical-example pair

The resident pair executor now derives each objective staging request ID from
the full frozen pair-protocol digest and arm, and computes its digest from the
private reconstructed task. The same derivation function feeds the CPU
preflight report, so the two exact staging identities can be reviewed before
either invocation. The regenerated [preflight report](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_v3.json)
records request-binding digest
`sha256:832bc5e462a9bcae26a8174dc87199b322fc0fc9d5952e5a1153ba751a155f3c`;
its read-only reconstruction is [preflight_verification_v2.json](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_verification_v2.json)
with report digest
`sha256:57f0c824e36afe5db74bb979dc7fd90bdca27b642c4d20279f573b03d428870f`.
The same task-generation seed produced a new task digest because the task
commitment includes a fresh private nonce; the protocol and private task-plan
digests, rather than the seed alone, identify this exact prepared task. The
verification confirms the owner prompts and journal protocol reconstruct, with
model-loaded, model-invoked, learning, and authority claims all false. This is
still CPU preparation evidence only; neither intervention arm has run.
The report and verification records now have closed Draft 2020-12 contracts in
[`historical_examples_cpu_preflight_report.schema.json`](historical_examples_cpu_preflight_report.schema.json)
and [`historical_examples_preflight_verification.schema.json`](historical_examples_preflight_verification.schema.json).
Both artifacts and the embedded protocol passed schema validation; unknown
fields are rejected, and the fixed non-inference, non-learning, and
non-authority claims are part of their schemas.

The initial v3 order rule alternated by task-seed parity. Review showed this
could couple arm order to task generation, so that rule was superseded before
any model calls.

The current preflight draws a separate 256-bit OS-random assignment seed,
stores it in the report, derives the arm order from that seed, and freezes the
order in the protocol. The verifier reconstructs the assignment from the
recorded seed. The [preflight v5](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_v5.json)
records order `examples_omitted`, then `examples_included`, under protocol
digest
`sha256:6bb2ca5ea5a5e056258403d07415501c5df03e89b14b0b08d053ca10c0e5f06f`.
Its read-only reconstruction is [preflight verification v4](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_verification_v4.json)
with report digest
`sha256:367bbba2eeb4b6997c12182941dc632b094ad96156bd598c612f43019d61d817`.
The report, verification, and embedded protocol pass their closed schemas and
record no model invocation or learning claim.

### Enforced held-out probe separation

The CPU preflight now recursively collects numeric `input`, `probe_input`,
and `probe_inputs` fields from every source history record. It refuses to
freeze the protocol if any relevant field is malformed or if a held-out task
probe exactly overlaps a historical input. The [preflight v6](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_v6.json)
measured 158 input occurrences across all 23 records and found zero exact
overlaps. The report retains only counts and digests for that audit, not the
input values. [Preflight verification v5](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_verification_v5.json)
reconstructed the report with digest
`sha256:320be3da638c191a1769a8351c5386212394281167c20baae6e531a3171c29b2`.
Both artifacts and the embedded protocol passed their closed schemas; no model
was loaded or invoked, and no learning claim is supported.

### Bind the overlap audit to execution

The next revision closes a gap between preflight reporting and execution: the
zero-overlap audit is now bound into protocol v2 by digest and stored as an
immutable journal record before the protocol is published. Protocol loading
and pair execution validate the persisted audit's digest, scope, completeness,
and zero-overlap result. The [preflight v7 report](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_v7.json)
records 158 recursively discovered input occurrences across 23 history
records and no exact overlap with its three held-out probes. Its audit digest
is `sha256:9c18b263c24d8340d8f1f6dd4bbd091aa7f916c7bcd2f0120b9e95246ec3aea8`;
the protocol digest is
`sha256:d50dd2c22254671fa8f2ddf47fa772a91c1169e5f8cce757842178dbe6ff7499`.
[Verification v6](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/preflight_verification_v6.json)
reconstructed the source history and prompt pair and confirmed the immutable
journal protocol, with report digest
`sha256:8335532a54c6507af662e23cc4882c1cc96c5b5063b60679c36a770af492e4f0`.
This remains a CPU-only preflight: no model was loaded or invoked, and it
establishes no learning.

The resident owner's one-shot intervention gate now accepts protocol v2 and
requires a well-formed held-out-overlap audit digest before it will stage an
arm. It had still hard-coded protocol v1, which would reject these newly frozen
v2 protocols before inference. The actual journal audit remains enforced by
`HistoricalExamplesPairJournal.load_protocol` in the pair coordinator; this
owner-level check aligns its protocol gate and digest shape with that journal.
The pure resident-owner gate is now shared with CPU preflight verification, so
each protocol is checked against the exact predicate the owner will use before
an arm can start.

### Preflight a multi-pair replication cohort

Added [`audit_historical_examples_pair_preflight_cohort.py`](../../scripts/audit_historical_examples_pair_preflight_cohort.py)
to require a shared source receipt, model identity, history set, world-state
snapshot, generation configuration, and budget across a set of pair protocols.
It reconstructs each supplied report against the cycle root and immutable
journal, checks each trial's held-out/history separation audit, and rejects
numeric probe reuse across trials. It also requires distinct task digests and
independent OS-randomized arm-order seeds. Its bounded input reader rejects
symlinked paths, oversized artifacts, duplicate JSON keys, and nonstandard
numeric constants before report reconstruction. The [cohort audit schema](historical_examples_preflight_cohort_audit.schema.json)
records only digests, trial seeds, randomized arm orders, and counts; it does
not expose answer-bearing probes.

The [cohort audit v7](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_audit_v7.json)
currently binds five separately seeded pair protocols (preflight v7 through
v11) to 15 unique numeric probes and a common history/model/configuration
boundary. Each report has a matching reconstruction artifact (verification
v11 through v15), and the cohort auditor re-ran those reconstructions and
resident-owner protocol-gate checks before
publishing its manifest. The manifest digest is
`sha256:4602be552773ef4c4c29e7db8f682da1b37015287cba2667bb84ee1e9a443f04`.
This prepares a small replicated response comparison;
it is still CPU-only preparation. No model was loaded or invoked, so there is
no response effect or learning result yet. The five protocols remain
unexecuted until model-inference work is allowed.

The cohort auditor now accepts v6 through v8 CPU reports. For identity-neutral
v8 cohorts, pass one task-bound allowlist file per report with
`--history-record-allowlist-files`, plus the private key with
`--shared-task-commitment-key-file`; it re-derives each task commitment and
reconstructs each policy-enabled report before admitting it to the cohort.
The shared cohort boundary includes the identity policy so policy-free and
identity-neutral trials cannot be mixed silently.

Before any inference, the [cohort analysis plan](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_analysis_plan_v1.json)
freezes the task pair as the analysis unit and the primary summary as the
unweighted mean of each task's included-minus-omitted accuracy. All five pairs
must complete before that cohort mean is reported; incomplete pairs cannot be
replaced, retried after ambiguous outcomes, or dropped to recompute a mean.
Probe-pooled counts remain supplementary because probes are nested within
tasks. The plan specifies descriptive reporting only, no significance tests,
and explicitly leaves independent scoring unattested and durable learning
unestablished. Its digest is
`sha256:3f7f17dee94f8b2a6658a2ba1aabdb3dbecac782b4dff90a4f70536d68b332a9`.

The analysis-plan tool now also has a read-only `--verify-plan` mode. It
reconstructs the canonical plan from the supplied cohort and requires exact
equality with the saved plan, including the cohort digest and analysis-plan
digest. This closes the gap where a plan's internally valid digest could be
presented beside a different cohort. Future cohort scoring should use this
reconstruction as a precondition; verification reports no outcomes and does
not load a model. The CPU-only command is:

```powershell
python scripts/freeze_historical_examples_pair_analysis.py `
  --cohort artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_audit_v7.json `
  --verify-plan artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_analysis_plan_v1.json
```

New analysis plans default to v2: the plan binds the independent raw receipt
scorer's source digest before inference, and aggregate scoring requires one
matching independent verification per frozen trial. Use
`--legacy-same-process-scoring` only to reproduce a historical v1 plan. The
independent scorer recomputes outcomes from archived receipts in a separate
code path; the plan does not attest that a separate person or operating-system
process performed the scoring. Execution-plan construction now reconstructs
the complete analysis plan from the cohort before binding runner IDs, so a
rehashed but altered analysis artifact cannot pass as a preregistered plan.
The canonical freeze and verifier live in the shared
[`historical_examples_analysis_plan.py`](../../sentientos/historical_examples_analysis_plan.py)
module used by the CLI, execution-plan builder, and cohort scorer. See
[`historical_examples_pair_cohort_analysis_plan_v2.schema.json`](historical_examples_pair_cohort_analysis_plan_v2.schema.json).

The identity-neutral CPU-refresh cohort now has a v2 analysis plan and matching
execution plan at
[`analysis_independent_v2.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/analysis_independent_v2.json)
and
[`execution_independent_v2.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/execution_independent_v2.json).
Their digests are `sha256:802aa8b322c3a398a35d294465433b2cd645ec00dcfa2effd68b363e1f0c6ed5`
and `sha256:ddbfb1f93089acbdbcd2b3fa5da966fc59496b62ef08b20afe56c23c934113be`.
Both reconstruct from the frozen two-pair, six-probe cohort. The new runner IDs
`rootless-cognition-cycle-c4d73f9a0e684c45a81b` and
`rootless-cognition-cycle-c4d73f9a0e684c45a81c` now have matched, no-load
identity preflights in
[`runner_identity_preflights_v2.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/runner_identity_preflights_v2.json).
The refreshed identity summary digest is
`sha256:2810bdf727c35eb7de2a61566433aad77d26025c93852104918a11cad0525141`;
the [execution-slot audit](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/execution_slots_verified_v2.json)
digest is
`sha256:37fd0b956ceeeb3ccb3222eb5f1b1ed0b7a267691121518baf0f57351003224f`;
and the [combined CPU runner-binding audit](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/cpu_runner_binding_audit_v4.json)
digest is
`sha256:25f8b0deef8a867ae976c7681fabf513be5f5223b9ca102882c10d495e98a22a`;
it binds the verifier source as
`sha256:e33d8075e65ad5239c5b3807cd03e41931981ee5fa92c4e448754fc5f4225b98`.
All three audits confirm that neither run root was allocated and no model was
loaded or invoked. These remain preflight receipts only; no outcomes exist and
the next model-dependent step must wait until GPU use is available.

A cohort scorer is now available for the later outcome stage. It recovers one
score from the immutable pair journal for every protocol in the frozen cohort,
rejects missing or duplicate trials, reconstructs the analysis plan against
the cohort, and checks each score's internal digest, task binding, probe set,
paired outcomes, and receipt identities against both journaled arm results.
New arm-result journal records preserve each verified receipt body in the
private experiment store. Before score persistence and again during
aggregation, the journal revalidates those receipts, reconstructs the answer
key from the sealed private task plan, and recomputes the score from the
receipts. Legacy arm-result v1
records remain readable, but lack archived receipt bodies and cannot enter the
cohort aggregate. It computes the
preregistered unweighted mean over per-task accuracy
difference using exact rational arithmetic; the rounded decimal is only a
convenience field. This is an immediate response comparison. The artifact
explicitly leaves durable learning, model attention, transfer, model
independence, and authority unestablished. A v1 analysis plan leaves
independent scoring unattested; v2 plans require the pinned raw-receipt
rescore. All new aggregate outputs use the v3 score format. Its
`independent_scorer_attested` field records whether independent verification
was supplied, and it includes the per-trial counts, accuracy differences,
probe outcomes, arm order, complete-trial count, and incomplete-trial posture
required by the reporting contract. Attestation covers the separate code path
and its digest, not a separate human reviewer or process. The output shape is
recorded in [the cohort score schema](historical_examples_pair_cohort_score_v3.schema.json),
and each new archived arm result follows
[the receipt-bearing result schema](historical_examples_pair_arm_result.schema.json).
The command must wait until all five frozen pairs have scores in the journal:

```powershell
python scripts/score_historical_examples_pair_cohort.py `
  --cohort artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_audit_v7.json `
  --plan artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_analysis_plan_v1.json `
  --journal-root <frozen-pair-journal-root> `
  --output artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/cohort_score_v3.json
```
There are currently no completed pair results or journaled scores, so no
cohort score has been produced. Hermes/GPU inference remains paused while the
GPU is in use.

For an independent scoring check after a pair completes, run
[`verify_historical_examples_pair_score.py`](../../scripts/verify_historical_examples_pair_score.py)
once per protocol. It reads the archived receipts and sealed task plan,
validates the governed receipt bindings, then independently parses each raw
answer vector and recomputes correctness, abstentions, confidence error, and
paired outcomes without calling the runtime score function. The resulting v2
verification binds both receipt digests and the scorer source digest. Pass one
such verification per frozen trial with `--independent-verifications` to the
cohort scorer; it emits the v3 cohort score only when every independent result
agrees with the journal score. The cohort scorer reruns the pinned raw-receipt
verification against its own journal view and requires exact equality with
each supplied verification, so a self-digested assertion alone cannot qualify
the aggregate. This adds independent response scoring, not
evidence of model attention, durable learning, or transfer.
The evidence formats are defined in the [pair rescore verification schema](historical_examples_pair_score_verification_v2.schema.json)
and [independently scored cohort schema](historical_examples_pair_cohort_score_v3.schema.json).

```powershell
python scripts/verify_historical_examples_pair_score.py `
  --journal-root <frozen-pair-journal-root> `
  --protocol-digest <protocol-digest> `
  --output <independent-score-verification.json>

python scripts/score_historical_examples_pair_cohort.py `
  --cohort <cohort-audit.json> `
  --plan <cohort-analysis-plan.json> `
  --journal-root <frozen-pair-journal-root> `
  --independent-verifications <trial-1-verification.json> <trial-2-verification.json> `
  --output <cohort-score.json>
```

The rootless Ollama runner now has an explicit historical-pair slot mode. It
loads and validates the slot, journal protocol, private task, source-history
root, runner ID, task seed, backend seed, and external plan digest before model
setup. With campaign mode disabled, it snapshots the source admission ledger
and cognition-recovery boundary, then uses the runner's ordinary history seed
copy checks, model pinning, pre-load GPU headroom gate, and per-invocation
resource guard. The resident owner must reproduce the exact frozen prompt pair
before the journal's no-retry executor can issue its two arms. A terminal is
written only when both per-invocation resource records passed and the stable
history inventory and receipts verify. The slot result remains experimental;
it does not claim learning. The task-level runner intentionally does not claim
to be a full acquisition/transfer cycle, which the current campaign verifier
expects each wide-task
cycle to carry its acquisition/transfer preflight and full-cycle terminal
evidence. A task-level historical-example pair cannot be treated as that full
cycle. The CPU-only [`freeze_historical_examples_pair_execution.py`](../../scripts/freeze_historical_examples_pair_execution.py)
command freezes a pair-level plan against the audited cohort and analysis
plan, including ordered trial slots, protocol/task/probe digests, runner IDs,
the shared source-history boundary, target model identity, and backend seed.
The five-slot plan is frozen at
[`pair_execution_plan_v1.json`](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/pair_execution_plan_v1.json)
with digest `sha256:a06062aa7ad7ba7c11cb5c7cbd2301d08e954bdb89a0f0b0beb937a2be3ff00a`;
its runner IDs and backend seed 42 were reconstructed with `--verify-plan`,
and every slot's protocol digest matches the cohort audit. Use `--verify-plan`
to reconstruct it again. The API also provides a
runner-binding record for each slot (requiring verified source-history seeding
and a passed resource gate) and a terminal record that binds the governed
score, both arm receipts, and stable runtime-history inventory. Schemas live in
[`historical_examples_pair_execution_plan.schema.json`](historical_examples_pair_execution_plan.schema.json),
[`historical_examples_pair_runner_binding.schema.json`](historical_examples_pair_runner_binding.schema.json),
and [`historical_examples_pair_execution_terminal.schema.json`](historical_examples_pair_execution_terminal.schema.json).
The five pair slots are not yet executed. Plan generation records that
preregistration timing is not independently attested, and neither a pair
terminal nor a cohort score proves durable learning. The runner accepts one
slot per process through these additional environment variables:

```bash
export SENTIENTOS_HERMES_CYCLE_ID=<runner_cycle_id_from_plan>
export SENTIENTOS_HERMES_EXPERIMENT_SEED=<task_generation_seed_from_plan>
export SENTIENTOS_HERMES_BACKEND_SEED=42
export SENTIENTOS_HERMES_PREREGISTRATION_DIGEST=<plan_digest_without_sha256_prefix>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_PLAN_PATH=<pair_execution_plan_v1.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_COHORT_PATH=<cohort_audit_v7.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_ANALYSIS_PATH=<cohort_analysis_plan_v1.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_JOURNAL_ROOT=<frozen_pair_journal_root>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_PARITY_AUDIT_PATH=<matched_prompt_parity_v4.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_ALLOWLIST_PATH=<shared_history_allowlist.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_VERIFICATION_PATH=<matched_pair_verification_v3.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_PATH=<left_preflight.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_PATH=<right_preflight.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_PATH=<left_verification.json>
export SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_PATH=<right_verification.json>
export SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT=<source_cycle>/resident-cognition/history
python scripts/run_rootless_ollama_embodied_cognition_cycle.py
```

For tasks using `matched_cross_model_identity_omitted:v1`, the parity audit and
allowlist paths are required. Before model load, the runner verifies their
canonical digests, the allowlist file digest referenced by the audit, task and
target bindings, and the exact ordered history IDs and record digests frozen in
the pair protocol. It independently reruns the parity auditor from the pair
receipt, both reports and verification artifacts, and the archived source cycle
history. It also checks every selected provenance row and its
source-fact bindings, including that source identities differ from both target
identities. Source facts remain bound to their recorded source family; a
preregistered transfer task can target another family. The CPU-only verifier
is implemented in [`identity_neutral_history_binding.py`](../../work/identity_neutral_history_binding.py).
The archived source receipt's active model identity is validated as part of
that receipt, but need not equal the target model identity. This lets a frozen
history-transfer trial test continuity across a model change while keeping
source receipt and target identity separately bound.
When a pair execution plan fixes a backend seed that differs from the campaign
cycle seed, build each CPU preflight with
`--model-identity-backend-seed=<frozen pair backend seed>`. This reconstructs
the campaign model recipe using the pair's actual runtime seed. Cohort auditing
retains that seed in the shared boundary, and plan freezing rejects a pair
backend seed that differs from the preflight identity seed.
The refreshed two-slot seed-42 preparation has a saved CPU input audit at
[`hermes_identity_neutral_slot_input_audit_seed42_v1.json`](../../artifacts/experiments/identity-neutral-execution-cohort-20261125/hermes_identity_neutral_slot_input_audit_seed42_v1.json),
validated by [`historical_examples_pair_identity_neutral_execution_audit.schema.json`](historical_examples_pair_identity_neutral_execution_audit.schema.json).
It records both source-parity reconstructions and hashes the exact reports,
verifications, pair receipts, parity audits, and allowlists that the runner
will recheck before model setup.
The verified canonical and raw-file digests and selection are retained in the
runner's resource evidence. Policy-free historical-pair runs may omit these
identity-neutral evidence paths. The audit and allowlist are parsed and byte
hashed from stable regular-file handles, so the parsed allowlist and its cited
raw-file digest cannot drift due to replacement during the read.
After the GPU/resource gate passes and before session construction, the runner
also writes a private digest-bound pre-load receipt using the
[`historical_pair_identity_neutral_preload_binding.schema.json`](historical_pair_identity_neutral_preload_binding.schema.json)
contract. Its result record points back to that receipt; it attests only the
pre-load input binding, not model behavior or learning.

The ordinary pinned-model manifest and experiment workspace variables still
apply. `SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH` must be unset for this mode; its
full-cycle campaign verifier has a different terminal contract. Each runner
ID is one-shot: an existing run root or ambiguous journal claim fails closed.
Missing GPU telemetry or utilization above the existing 25% threshold is
checked before creating that run root, so a scheduling refusal does not consume
the planned slot. In WSL, telemetry can come from either its Linux utility or
the Windows `nvidia-smi.exe` interop path; the latter is marked as host-wide
and is never treated as process attribution. The later governed and per-call
checks still run independently.
The run-specific preregistration records the copied admission and recovery
boundaries before inference, while the pair-level plan itself does not claim
independent timing attestation.

Before adding that runner, the CPU-only
[`verify_historical_examples_pair_execution_slots.py`](../../scripts/verify_historical_examples_pair_execution_slots.py)
command now reopens every planned protocol and private task from the pair
journal and checks its protocol, task, probe set, arm order, snapshot, model,
history, generation configuration, backend seed, and runner ID against the
frozen slot. It emits only digests and verification status. A run plan is
eligible for governed invocation only after this audit succeeds for all five
slots; the audit itself performs no inference. The current
[`pair_execution_slot_audit_v1.json`](../../artifacts/experiments/historical-examples-pair-20261123-cpu-preflight-01/pair_execution_slot_audit_v1.json)
verified all five slots against the WSL journal with verification digest
`sha256:4f0d4cb5a61b2e321ec4a90b3d84fc2d25e0e79e7a81d22c8604fb11ed7af071`.
Its closed shape is defined by
[`historical_examples_pair_execution_slot_audit.schema.json`](historical_examples_pair_execution_slot_audit.schema.json).

The CPU-only slot verifier was replayed against the current cohort, plan, and
private WSL journal on 2026-11-23. It again validated all five slots and
reproduced the same verification digest. At that check, host GPU telemetry was
76% utilization with about 5.9 GiB occupied, above the runner's 25% pre-load
threshold. No runner was started and no model was loaded or invoked.

A further CPU-only replay reconstructed the five current prompt pairs from
`preflight_v7.json` through `preflight_v11.json` against the live source cycle
and private journal. Every report revalidated its source history, exact prompt
pair, resident-owner protocol gate, and journal protocol; all five retained
their frozen protocol digests. No inference occurred. At the latest resource
check, host GPU telemetry was 80% utilization with about 6.0 GiB occupied, so
the runner's pre-load gate remains closed and the pair slots remain unconsumed.

The complete preflight cohort was then rebuilt from those five reports and
their verification artifacts against the current cycle history and private
journal. The rebuilt artifact exactly matched `cohort_audit_v7.json`: five
distinct task/protocol pairs, 15 unique held-out probe inputs, and cohort digest
`sha256:4602be552773ef4c4c29e7db8f682da1b37015287cba2667bb84ee1e9a443f04`.
This remains preregistration and prompt-custody evidence, not an outcome. At
the latest resource check, GPU utilization was 71% with about 5.9 GiB occupied;
no model run was started.

An individual pair can be audited earlier with
[`verify_historical_examples_pair_score.py`](../../scripts/verify_historical_examples_pair_score.py).
It reloads the protocol, archived arm receipts, and private task plan, then
reconstructs that pair's score. Its verification report is specified in
[`historical_examples_pair_score_verification.schema.json`](historical_examples_pair_score_verification.schema.json).
This permits receipt-level review as pairs finish without publishing or
recomputing the cohort mean before all five are complete. The verifier still
marks independent scoring and learning as unestablished.

The same command supports `--verify-score <saved-cohort-score.json>` in place
of `--output`. It reloads the frozen cohort and plan, recovers all journaled
pair scores, recomputes the per-task and cohort statistics, and requires exact
artifact equality. This is the post-run integrity check for any future
aggregate; it cannot be run until the five pair scores exist and does not load
a model.

Before a pair slot allocates its one-shot run root or loads Ollama, the runner
now reconstructs the developmental session's active-model identity from the
pinned manifest, exact model name, GPU-layer setting, and generation
configuration. It compares that predicted identity digest with the frozen
target identity and fails closed on any mismatch. This catches stale aliases,
wrong manifest paths, and changed generation or placement settings without
loading the model or consuming a slot. Each result is written as a private,
exclusive preflight report under the experiment workspace's
`preflight-failures` directory; a rejected report includes the predicted
identity, both identity digests, trial index, and source receipt binding, while
the process output names the report path. The runner verifies the source
receipt and binds its complete active-model identity to the frozen target; the
report lists which identity fields differ from the candidate prediction. Its
shape is defined in
[`historical_examples_pair_model_identity_preflight.schema.json`](historical_examples_pair_model_identity_preflight.schema.json).
The later post-load identity check stays
in place as an independent runtime assertion. In the current environment the
installed Hermes tag is
`hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`, while the runner's
default alias is `sentientos-hermes4:14b-q4km`; a pair launch must explicitly
bind the preregistered identity before any inference is considered. The frozen
source receipt records model ID
`hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`, 32 requested GPU
layers, and configuration digest
`05df1213b3eb6c8e717ebc9e97612ba344b8afb0349cd0929b0ab66fc006823f`.
Reconstructing that candidate with current session settings produces
`e5620526050577485075f8fc9523936ce11bd474abae9f7ef8a8a00aafd74324`.
The original configuration has not yet been recovered, so the new preflight
rejects the current setup before slot allocation. No model load or inference
has been made for this frozen pair.

Two retained cycles, `rootless-cognition-cycle-797e9fd3f02b355e9de4` and
`rootless-cognition-cycle-05bda3c4d231f9a765c5`, have the same source
worktree-content digest, Hermes model ID and artifact digest, and requested
32-layer placement, but different configuration digests
(`716bd784…` and `05df1213…`). This points to runtime configuration drift
that the old preregistration did not explain; it does not identify which option
changed.

Future developmental and epistemic preregistrations and identity-preflight
reports now also carry the canonical configuration payload whose digest is
stored in `ActiveModelIdentity`: engine, non-path candidate options, context
limit, and generation settings. The session recomputes that payload digest and
requires it to equal the loaded identity's configuration digest. This makes
subsequent model/configuration transitions inspectable; it does not reconstruct
payloads omitted by older receipts. Before preflight, the runner now follows
the source receipt's session link to its preregistration, checks the saved
preregistration digest and model identity, and reports whether a source
configuration payload was retained. The payload observation is specified by
[`active_model_configuration_observation.schema.json`](active_model_configuration_observation.schema.json).

New preflight reports also carry `run_root_allocated: false` alongside the
model-load and invocation flags. The field is optional in the v1 schema so
older reports remain valid; new reports make the full no-side-effect boundary
explicit in persisted evidence.

For source provenance, the runner still hashes the complete tracked diff and
all bounded untracked file contents. The cap is now 64 MiB so this checkout's
54.4 MiB untracked source/evidence set can be fingerprinted without omitting
paths or bytes. In WSL-hosted Windows linked worktrees,
`SENTIENTOS_SOURCE_PROVENANCE_GIT` can name the native Git executable; this
avoids WSL Git interpreting the Windows `gitdir` pointer as a Linux path while
retaining the same status and content-fingerprint checks.

The runtime dependency gate now follows identity and scheduling preflight, but
still precedes run-root allocation. This lets the runner record a precise
identity refusal even though the WSL system interpreter lacks `psutil`. Its
private report is
`/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/preflight-failures/rootless-cognition-cycle-be780c57d0f699195e75-model-identity-8268adaef2a2416d.json`.
It verifies the source receipt and reports
`identity_difference_fields: ["configuration_digest"]`: the source identity
digest is `sha256:ac5acdf45d34cca6abf7844503bd4cb0d4dcf4287e49905923b3a2ae187d368a`,
and the predicted identity digest is
`sha256:35cce0d6df50245cf1cfff5355b36f9953bfd368356f0c2c123f4ba37954daee`.
The source preregistration digest is
`c5df26fa92d3d696111fec8ca41fa95546ac58f64b3da33fd7dfe7cd75671a72`, but its
configuration observation status is
`source_preregistration_did_not_retain_configuration_payload`; the old run's
result and invocation receipts preserve the identity digest but not its
canonical configuration payload. The report validates against its schema and
has mode 0600. It records `model_loaded: false` and `model_invoked: false`, and
the planned run root does not exist. The frozen slot remains available. This
preflight refusal is an identity comparability failure, not a failed cognition
outcome; the missing historical payload cannot be recovered from the digest
alone.
Its configuration payload independently recomputes to
`e5620526050577485075f8fc9523936ce11bd474abae9f7ef8a8a00aafd74324`, and
the payload validates against
[`active_model_configuration_observation.schema.json`](active_model_configuration_observation.schema.json).

### CPU-only reconciliation of current retained cognition audits (2026-11-24)

The read-only
[`summarize_persisted_experiments.py`](../../work/summarize_persisted_experiments.py)
revalidated the latest retrospective audit digest and cycle-directory binding
for each of five local cycle summaries. It found no incomplete runs. Three
older cycles remain on audit v14; two newer cycles have v17 audits:
[`a02be6d3…`](../../artifacts/experiments/rootless_cognition_cycle_a02be6d3b0e82fe59391/retrospective_acquisition_history_audit_v17.json)
and
[`baf4c2d8…`](../../artifacts/experiments/rootless_cognition_cycle_baf4c2d89e35592a4c01/retrospective_acquisition_history_audit_v17.json).

Both v17 cycles use the repaired, score-bound `rootless_integer_affine_transfer_low_range_v6`
family and retain one projectable experience with three task-relevant examples.
The first scored acquisition at 3/3 for all three conditions. The second scored
3/3 with history present and restored, and 1/3 with history withheld. That
withheld baseline is below the preregistered 2/3 competence threshold, so its
delayed transfer stage was correctly skipped. The latter is a promising
single-run acquisition contrast, not an established history effect or a
transfer result.

These two outcomes are not a same-configuration replication: their preregistered
Hermes configuration digests differ
(`103352d5d439131c28a5fbb837d9bc7cf9c1e50b98463dac0eaf1fc98b264cfb` versus
`d302af74006cf42b85641b726fd65447f0ff742eb74866d1a67c09b2cf1fa627`). Each
cycle verifies a common configuration across its own three intervention arms,
but the digest difference across cycles leaves a model-configuration
confound. Their preregistrations retain the identity digests but not the full
canonical configuration payloads, so a later run cannot claim to reproduce
either digest from those preregistrations alone. The 3/3 versus 1/3 pattern
therefore remains exploratory.

The CPU-only
[audit_rootless_cycle_configuration_cohort.py](../../analysis/audit_rootless_cycle_configuration_cohort.py)
now checks sealed preregistration and cycle-result bindings, retained
configuration payloads, within-cycle condition identity bindings, source
content, task family, and cross-cycle model identity. Its
[v1 schema](rootless_cycle_configuration_cohort_audit.schema.json) defines the
closed report. The
[audit of these two cycles](../../artifacts/experiments/rootless-cycle-config-cohort-v1/audit_v3.json)
verifies both cycle bindings and confirms common source content and task family,
but reports unequal model configuration digests, unequal full model identities,
and absent canonical configuration payloads. It fails the configuration-parity
gate for this pair; passing that gate would still not establish scientific or
full protocol eligibility. Use this audit as one pre-outcome check for future
v6 repetitions; it performs no inference.

In both v17 runs, the present and restored intervention prompts and outputs
match. The withheld non-citation response content also matches; its response
is rejected because it cites history unavailable in that condition. Thus the
companion-decision audit reports no semantic cognition change, and neither
cycle establishes learning, attention, or improvement. These audits support
keeping task-score contrasts separate from response-content and citation
validity analyses.

The next useful outcome-bearing step is a preregistered repetition of the v6
acquisition cohort with one canonical model-configuration payload and identity
digest frozen across cycles, followed by enough independent cycles to assess
whether the 3/3 versus 1/3 pattern recurs. New preregistrations can retain that
payload for later replay. Delayed transfer must remain gated on the withheld
arm meeting the existing competence rule.
The GPU was in use during this reconciliation, so no model was loaded or
invoked; this section adds only CPU audit evidence and interpretation.

### Seed-normalized parity diagnostic for newer cycles (2026-11-24)

The v2 CPU-only cohort audit adds a second diagnostic while retaining the
strict exact-configuration gate. It removes only `options.seed` from each
retained Ollama configuration payload, then checks that model identity,
external protocol digest, campaign binding, source content, task family, and
within-cycle condition identity bindings agree. The new
[v2 schema](rootless_cycle_configuration_cohort_audit_v2.schema.json) and
[saved audit](../../artifacts/experiments/rootless-cycle-config-cohort-v2/audit_v2.json)
cover completed cycles 53 and 54.

For this pair, exact configuration parity still fails because the registered
Ollama seeds differ (`1257089217` and `1257089224`), while the separate
seed-normalized diagnostic passes. Both per-cycle preregistration and result
bindings match; the common source digest is
`e7551b385981c89584b01913be65d041dd673b7024f2d84c5debbba99359f701`. The
campaign plan artifact itself was not reloaded, so the diagnostic is not a
campaign eligibility determination. The observed acquisition scores were 0/3
and 1/3 respectively in each arm, and transfer was skipped in both cycles.
These records establish no learning or outcome effect. The report digest is
`sha256:c431d43b885e184f3bdc1416a46dc9cb4573441397cf59f9eba3028ceaae0f36`;
the audit performed no inference.

### 12-probe history projection bound failure (2026-11-25)

A new v7 two-cycle plan froze a 12-probe cross-range transfer stage against
completed cycle 54. Its plan digest is
`24f22baec994a8db861f640238dfb30082e4473b986f344932e2067a5ac22a4e`;
the first cycle used task seed `537803611` and backend seed `42`. Owner
preflight confirmed the transfer probes were disjoint from the selected history
examples. The planned acquisition probes did overlap history, so acquisition
scores from this plan are not an independent held-out measure.

The first Hermes cycle reached the cross-range history-enabled competence stage
and then stopped during evidence projection with
`developmental_history_projection_over_bound` at
`objective_cross_range_history_enabled_competence_writeback`. The cycle is
incomplete. Its withheld-condition objective score was unscoreable, and there
is no complete cross-condition endpoint. The persisted failure artifact and
stage checkpoints remain available in the rootless experiment workspace. The
model was unloaded after the run; no follow-on inference or retry was made.
This run establishes neither learning nor a transfer effect.

The failure exposed duplicated per-probe fields in the history interpretation
projection. The initial compaction retained aggregate score fields and compact
answer-free correctness, answerability, and abstention outcomes, but the
complete family record still exceeded the byte bound. The v4 projection now
stores those outcomes as condition-aligned vectors and omits the duplicate
`acquisition_examples` list. The cognition reader reconstructs examples from
the retained, score-digest-bound history-present score rows. The complete source
evaluation digest, condition score digests, aggregates, and per-probe outcomes
remain bound. A CPU-only audit verified all three invocation receipts without
loading the model, rebuilt the World-State fact, and passed it through the
actual task-family history reader. The 12-probe projection is 14,674 bytes under
the 16,384-byte limit, with all 12 score-bound examples reconstructed in task
order. This establishes projection and reader compatibility only; the source
run has no complete cross-condition endpoint and establishes no learning.

The next live run must use a newly frozen plan and new cycle identity because
the implementation changed and the failed cycle slot is preserved. Hermes and
all GPU-dependent testing are paused while the GPU is in use. Resume only after
the user says the GPU is available.

### Fresh v7 continuation plan and CPU preflight (2026-11-25)

The earlier v10 plan was superseded after its live cycle failed and the history
projection code changed. A fresh two-cycle v10 plan is sealed at
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v2/plan_v1.json),
with digest
`0c9f67f09f709e4cba1a0e907208f2a6c3c4678a3d6e7e0310f1eeee559f48ea`.
It pins the changed 2,523-file implementation closure and the existing Hermes
manifest, and uses new cycle IDs and seeds. Offline plan verification matched
the implementation and both seeded model identities. The initial history
boundary was independently recomputed from cycle 54 and matched the sealed
78-file boundary (`49f0b001d84585daf78be0fda7384d86af0b7e26ef06751a5a88d957433c48b1`).

The cycle-0 resident-owner preflight and source-reopening integrity audit are
saved beside the plan. The audit digest is
`sha256:4378652819d7c301d41be25cdd3774c877e8e58a747fc0ff576caa417cad25aa`;
it independently verified the report and plan bindings, reopened the frozen
history, and found the 12 transfer probes disjoint from selected history. The
prompt remained within its bound. No model inference was performed.

This audit exposed a stale assumption in
[`audit_prepared_v7_owner_preflight.py`](../../work/audit_prepared_v7_owner_preflight.py):
it only reconstructed three transfer probes and treated any selected history
as a failure. It now uses the plan's registered probe count and verifies every
selected owner and binder record against the complete transfer set. The
acquisition probes `[3, 4, 5]` overlap historical examples; acquisition is
therefore not an independent held-out measure. The separately preregistered
12-probe transfer set is disjoint and remains the held-out outcome. These are
preflight conditions only and establish neither model attention nor learning.

Hermes remains paused while the GPU is in use. The fresh plan is ready for
execution when GPU availability is explicitly released; no cycle was launched
as part of this CPU-side preparation.

### v4 compact history projection and current plan (2026-11-25)

The v4 compact projection removes redundant serialized history-present examples
and stores cross-condition per-probe correctness, answerability, and abstention
as vectors aligned to the descriptor's probe order. Cognition reconstructs the
examples from the history-present score rows, whose score digest remains bound.
The implementation also uses this reconstruction when ranking persisted history
for task-family relevance.

The CPU-only
[`audit_rootless_history_projection_compaction.py`](../../work/audit_rootless_history_projection_compaction.py)
validated the failed cycle's source receipts, projected World-State fact, byte
budget, and complete 12-row reader output. Its
[audit artifact](../../artifacts/experiments/rootless-history-projection-compaction-audit-v1/cycle0_projection_compaction_audit_v1.json)
records 14,674 projected bytes under the 16,384-byte cap, 12 reconstructed
examples, and no inference. The artifact omits answer values.

Because the compact-projection and history-ranking implementation changed, the
previous v10 continuation plan (digest
`0c9f67f09f709e4cba1a0e907208f2a6c3c4678a3d6e7e0310f1eeee559f48ea`) is stale
and must not be launched. The current plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v3/plan_v1.json),
digest `cdf81af8b761c3ef58dd6800ceba07fbb9c418e73aabcbde966492cd83e65f3d`.
Its 2,524-file implementation pin and both model-identity pins verified. The
cycle-0 owner preflight was independently rechecked against the 78-file cycle
54 history boundary; all 12 transfer probes are disjoint from selected history.
The saved integrity audit digest is
`sha256:e78e1fbe93b620650c6eceacb80ef410a4b527ce7e5efab62d32ffbfdf360b95`.

Hermes was not invoked and remains paused while the GPU is in use. The current
plan is ready for a later GPU-authorized run. Its acquisition probes overlap
history; only the separate preregistered transfer stage is held out. Neither
preflight establishes model attention, learning, or a transfer outcome.

### Compact-vector validation hardening (2026-11-25)

The v4 task-family reader now validates the compact outcome vectors before it
admits a historical trial: condition order and keys, descriptor-bound probe
count, boolean-or-unscoreable entries, source-evaluation digest, task digest,
and all three condition score digests must agree. The v2
[projection audit](../../artifacts/experiments/rootless-history-projection-compaction-audit-v2/cycle0_projection_compaction_audit_v2.json)
passes this validation and again verifies all 12 score-bound examples without
inference.

This validator change supersedes the v3 continuation plan above. The current
plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v4/plan_v1.json),
digest `230951b6cd4562e3a834375a65d9e4120e0a643f22499d4551e3abf344248732`.
Its 2,524-file implementation pin and both model identity pins verify. Its CPU
preflight integrity audit
([`preflight_integrity_audit_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v4/preflight_integrity_audit_v1.json))
independently reopens the frozen cycle 54 history and confirms the 12 transfer
probes are disjoint from selected examples. Hermes remains paused until the GPU
is released; this plan has not been launched.

### Private initial-history bundle for incomplete-cycle audits (2026-11-25)

The current plan's initial history is now archived for robust boundary checks if
the first cycle stops before copying the seed. The bundle contains 78 source
records and receipts (1,042,791 bytes), is bound to plan digest
`230951b6cd4562e3a834375a65d9e4120e0a643f22499d4551e3abf344248732`, and has
bundle digest
`25dce9a338951c7acb21cf33edbd1243b67731e02c3d18ef1585e440d76c4ea6`.
It is stored outside the repository under the private rootless workspace at
`private-campaign-seeds/rootless-history-campaign-90de3f4e019c6f0c9f95/initial-history-bundle_v1.json`;
the directory is mode `0700` and the bundle file is mode `0600`. The archive
command's `--verify-existing` replay confirmed exact plan and boundary binding.
A future campaign audit can pass this bundle with
`--initial-history-bundle` to recompute overlap even when cycle 0 is incomplete
before its history copy. No inference was performed.
The campaign verifier's own initial-bundle loader has also accepted this private
bundle. Replaying its 39 records through the cognition task-family reader found
zero overlap for the preregistered 12 transfer probes against both declared
source families (`rootless_integer_affine_transfer_low_range_v6` and
`rootless_integer_affine_transfer_wide_range_v7`). The answer-free
[seed-bundle overlap audit](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v4/initial_seed_bundle_replay_audit_v1.json)
has digest
`ff8051c140ddc1ff75acaaa8bd568193806a12f93f53d9a8b9bc137530a8f95e`; this
provides a retained overlap result for an incomplete-cycle audit.

### Model-free historical receipt verification (2026-11-25)

Historical rootless invocation receipts can now be checked through
`verify_rootless_historical_invocation_receipt` without constructing an Ollama
session, pinging the backend, or loading model weights. The session method uses
the same verifier, and the projection-compaction audit now calls this supported
model-free path. Replaying the saved failed run verified all three condition
receipts and preserved the same 14,674-byte v4 projection and all 12 examples.

That verifier change superseded plan v4. The current plan is
[`plan_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v5/plan_v1.json),
digest `575bf246c537898822c2a15c73083e33451bb0b93d4e2a1a5901c9bb5116e07f`.
Its implementation pin covers 2,524 source files and matches current code;
both target model identities verify. The source-reopening preflight audit
([`preflight_integrity_audit_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v5/preflight_integrity_audit_v1.json))
confirms the transfer probe set is disjoint from selected history. A fresh
private seed bundle was verified against this plan, and its retained overlap
audit ([`initial_seed_bundle_replay_audit_v1.json`](../../artifacts/experiments/rootless-history-campaign-20261125-projection-fix-v5/initial_seed_bundle_replay_audit_v1.json),
digest `9851b61186473b830ee7c8f987f8145878cf4c8dad917afed6a401efe1899e0c`)
records zero overlap with both v6 and v7 source-family examples. No inference
was performed. The v4 and v5 model identity digests differ because the plans use
different backend seeds (`445237`/`445238` versus `445239`/`445240`); the identity
derivation deliberately binds each seed. The model settings and manifest remain
the same. The recipe digest also changes because it pins the historical receipt
verifier source hash. Treat plan/recipe digest changes as provenance changes,
and compare the manifest, runtime settings, and seed-specific identity inputs
separately before interpreting a run difference as a model change. Recomputing
v4's backend seeds (`445237`/`445238`) with the current identity derivation
reproduced both v4 model identity digests exactly. This confirms that the receipt
verifier edit changed the pinned recipe/provenance digest, while the changed v5
identity values are explained by the new seeds. The plan also
sets `preregistration_timing_independently_attested` to `false`: the transfer set is
plan-frozen and its history overlap is audited, but no independent timestamp proves
the plan predates access to relevant outcomes. Describe it as a frozen held-out
transfer design, not independently attested preregistration. A follow-up campaign
should bind an independent timestamp or equivalent external attestation before any
cycle executes. Plans with digests
`230951b6cd4562e3a834375a65d9e4120e0a643f22499d4551e3abf344248732` and
`cdf81af8b761c3ef58dd6800ceba07fbb9c418e73aabcbde966492cd83e65f3d` are
superseded; use only the current plan after the GPU is released.

### Independent pair-score parser hardening (2026-11-25)

The independent historical-pair scorer now rejects duplicate keys in archived
model output, rejects nonstandard JSON constants, validates the frozen closed
output schema before interpreting vectors, and checks confidence bounds and
abstention alignment. This prevents an ambiguous JSON object or a receipt with
a weakened confidence schema from producing an accepted independent score.
`py_compile` passed for the scorer, cohort aggregator, and slot verifier; the
three associated JSON schemas pass `Draft202012Validator.check_schema`. No
model output was available for end-to-end rescoring.

The refreshed seed-42 identity-neutral plan still has two unconsumed slots. A
CPU slot-verifier replay against the candidate private journal failed closed
because its protocols are not present there (`historical_examples_journal_protocol_missing`). The initially guessed journal path was not a valid experiment store.
The run was not launched. Host GPU telemetry was 37% on the initial check,
above the runner's 25% pre-load threshold, and later fell below the threshold;
this did not resolve the missing private protocol state. Restore or locate the
journal that holds the frozen protocols before attempting a slot. This work
produced no inference or learning evidence.

### Deterministic reconstruction of a frozen pair preflight (2026-11-25)

The CPU preflight command now accepts `--arm-order-seed`. The seed is already
stored in each report; supplying it allows an exact reconstruction when the
public report and private task commitment key survive but the content-addressed
journal was moved or lost. This preserves the frozen protocol digest instead
of silently substituting a newly randomized arm order.

Using the archived seeds, the shared commitment key, campaign plans, source
history, and task-bound allowlists, I restored both Hermes trial protocols in
a dedicated private journal. Their task and protocol digests exactly match the
frozen cohort. Both current-code `--verify-report` reconstructions passed,
including source-history and owner-prompt reconstruction. The saved
[recovered slot audit](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/hermes_execution_slot_audit_recovered_v1.json)
verifies both original plan slots and reproduces the prior audit digest
`sha256:4b6eaab8fe90becf4aed3df83d16be2ce60d4006c16598e55a221ed754366803`.
Recovered report/verification artifacts are retained alongside it. No model
was loaded or invoked in this reconstruction.

At the launch check the Windows-hosted Ollama API was reachable with no model
loaded, but host GPU utilization was 31%, above the runner's 25% pre-load
gate. The slots remain unconsumed pending a later below-threshold check. The
execution plan's preregistration timing is not independently attested, and a
future immediate pair score will still be response evidence only, not evidence
of durable learning or transfer.

### Cross-model target identity gate correction (2026-11-25)

The first slot launch stopped in the pre-load identity check. Its predicted
candidate digest equaled the execution plan's frozen Hermes target digest, but
the gate also required every field to equal the archived source receipt
identity. That wrongly rejected the planned transition because the source
receipt used backend seed `1257088909` while the target was frozen with seed
`42`. The failure artifact confirms `model_loaded: false`, `model_invoked:
false`, and `run_root_allocated: false`.

The gate now compares the predicted candidate digest to the frozen target
identity. It continues to validate and retain the archived source receipt
identity separately; source-to-target field differences remain diagnostic and
cannot override a mismatching target digest. That retry passed the identity gate but later allocated the run root and stopped before inference on source-provenance capture. The frozen policy now treats the slot as incomplete and does not permit reusing it.

### WSL source provenance recovery and slot status (2026-11-25)

The remaining pre-inference failure came from this WSL checkout's `.git` file
pointing to a Windows `C:/...` Git directory, which Linux Git could not resolve.
Git source-provenance capture now maps that pointer to `/mnt/c/...`, allows up
to 180 seconds per Git operation, and hashes the complete worktree up to a
finite 512 MiB cap. A CPU replay completed against revision
`498bf41f5fb54ed35d1e5da319f824d67f12b46d`; it observed 10,760 status entries
and produced complete worktree fingerprint
`6bbe5e47c8af45cb64939148e645eb03cb6e40bf61d9263a41e16c8cb6257431`.

The first slot's second launch passed the cross-model identity check and the
project runtime dependency check, then allocated its run root. It stopped before
session construction because provenance was unavailable under the old WSL Git
path. The run is incomplete; no Hermes model was loaded or invoked. The frozen
plan forbids replacing an incomplete trial and requires ordered pairs, so the
second slot was not launched. Both protocols remain recoverable and slot-bound,
but this frozen two-trial cohort cannot produce its planned aggregate. A future
attempt needs a newly frozen execution plan against the still-unobserved cohort
inputs after the source-provenance path is
verified, with fresh run identifiers; this run's partial state remains archived.

### Rebound historical-pair launch and live preview binding (2026-11-25)

The recovered protocol tick IDs use the `raw_examples-preview` namespace. The
runner's live check expected the older `examples-preview` spelling, so it
rejected the first rebound slot before a prompt preview. The check now validates
both included and omitted tick IDs, requires the same base tick, and binds the
preview to the protocol's frozen `history_record_ids` allowlist. This keeps
unrelated recent history records from entering the matched pair preview.

The initial retry also used the runner's default Hermes alias and default
experiment workspace. Those produced a different model configuration identity
than the frozen target. The recorded target is reproducible with the archived
`ebb2efee...` manifest in the follow-up workspace and Ollama tag
`hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M`; the exact canonical
identity digest then matches `sha256:35cce0d6...`. Subsequent launches used
that workspace, manifest, and tag.

The allowlist-bound preview then exposed a second parity issue: the runner was
constructing the owner with only `embodiment` source kinds and narrower 16-fact,
4-record limits, while the CPU preflight used the source history's admitted
kinds, 32 facts, and 8 records. The runner now uses that same bounded owner
configuration for pair modes and takes input/timeout limits from the bound
source receipt. Preview mismatch failures also record per-binding
expected/observed digest metadata, without including prompt or model-output
text. The latest fresh plan
[`hermes_execution_plan_seed42_corrected_v5.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/hermes_execution_plan_seed42_corrected_v5.json)
passed independent plan reconstruction and both CPU slot checks; its first
slot stopped at `historical_examples_pair_live_preview_mismatch` before
inference. Earlier incomplete attempts are retained under their own cycle IDs
and are not reusable. Across these rebound attempts there are no
cycle-correlated inference receipts, no observed pair outcomes, and no learning
claim. The matched owner configuration fix needs a newly frozen plan and a new
slot ID before a launch can verify that the live preview now reproduces the
frozen digest.

The next fresh plan,
[`hermes_execution_plan_seed42_corrected_v6.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/hermes_execution_plan_seed42_corrected_v6.json),
passed both independent plan and slot verification. Its pre-inference failure
artifact now has a privacy-bounded mismatch diagnostic: included/omitted
invocation prompt digests, target identity, and snapshot ID match; owner request
digests differ; the live snapshot digest is the same 64-hex value as the frozen
digest but lacks its `sha256:` prefix. There are still zero receipts correlated
to this run, no pair outcome, no learning claim, and no model in Ollama. The
next CPU-side check should compare the per-arm owner protocol and request
bindings before normalizing digest formats; the request mismatch is substantive
and is not explained by the snapshot prefix alone.

### Stable live-preview bindings (2026-11-25)

The CPU follow-up showed why raw request digests cannot be an equality gate
across the two processes: `LocalModelInvocationRequest.semantic_payload`
includes the authority-map digest and linkage, while the live session adds its
run/session binding and uses a current-time authority-map snapshot. The frozen
preflight uses a fixed authority-map observation time. Rebuilding the map with
the preflight timestamp reproduces its digest exactly (`382509c0...`); rebuilding
with the current observation produces a different digest (`70103848...`). These
are custody/request-envelope fields, not prompt content. The runner now retains
full request digests for diagnosis but gates live parity on stable owner
protocol digests, task-plan digests, selected history IDs/digests, target
identity, normalized snapshot digest, and exact invocation prompt digests. The
owner-generated pair preview must still pass its internal minimal-ablation and
shared-selection checks.

The first run under these stable semantic bindings needs a fresh plan and slot
ID because v6 is incomplete. Current evidence remains pre-inference: zero
cycle-correlated receipts, no observed outcome, and no learning claim.

### Field-level protocol drift diagnosis (2026-11-25)

The first v7 slot reached the live preview with the same target identity,
snapshot, selected history IDs and digests, and invocation prompt digests as its
frozen protocol. The owner protocol digests and dependent task-plan digests
still differed. Because the protocol semantically binds the authority-map
digest, dropping those checks would weaken governance evidence. The v7 attempt
remains incomplete and stopped before inference.

The historical-example protocol is now v3. CPU preflight stores a digest for
each owner-protocol field and the per-arm authority-map digest. Runtime preview
diagnostics compare those fingerprints and list differing field names while
retaining the exact protocol and task-plan digest gates. The JSON schema and
reader continue to accept frozen v2 protocols, but newly prepared protocols
carry the richer bindings. This adds attribution without weakening the
authority binding or recording prompt/output text. It has been syntax/schema
checked only; no Hermes inference or GPU-dependent run was performed.

Code inspection confirms a likely cause of the remaining drift: the authority
map digest hashes each record's `observed_metadata`, including `observed_at`.
The archived preflight map digest is `382509c0...`; the earlier live-time
reconstruction was `70103848...`. Those values are consistent with an
observation-time difference, but the failed v7 receipt predates field-level
fingerprints, so it does not prove that this is the only differing protocol
field.

The authority binding now has two explicit values. The full authority-map
digest remains on each invocation request and receipt. A stable policy
fingerprint covers authority record semantics, including model and
configuration identity, permitted purposes, effect postures, and eligibility,
while excluding observation metadata. New resident owner protocols use schema
v15 and bind this policy fingerprint into their protocol digest; their live
full-map digest is checked against the request and receipt. Historical-example
protocol v3 compares stable owner fields and policy fingerprints while keeping
live observation digests in mismatch evidence. v2 protocols remain readable.

This is a code-level fix, not evidence that the experiment now reproduces its
frozen bindings. Syntax and schema parsing pass; a fresh CPU preflight and
pre-inference runtime preview are still required before resuming Hermes
inference. No Hermes/GPU run was performed.

### Stable authority-policy cohort frozen (2026-11-25)

CPU verification found two version-skew blockers in the follow-up path. The
resident execution validator accepted historical-example protocol v2 only even
though the producer and journal validator now emit/accept v3. The cohort auditor
also stopped at preflight report schema v9 while the fixed-observation-time
preflight is schema v10. The resident validator now accepts both protocol
versions, and the cohort auditor accepts v10 while retaining older report
versions.

Two fresh seed-bound preflights were generated into one shared journal, then
independently reconstructed and cohort-audited. The audit binds two trials and
six unique held-out inputs. The stable policy digest, owner protocol, task plan,
and invocation prompt remain invariant under a changed authority observation
time, while the full observation-map digest remains separately recorded. These
are preflight/reconstruction results only; `model_loaded`, `model_invoked`, and
`learning_established` remain false.

The frozen artifacts are [`policy_v15_cohort_final.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/policy_v15_cohort_final.json),
[`policy_v15_analysis_final.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/policy_v15_analysis_final.json),
and [`policy_v15_execution_final.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125/policy_v15_execution_final.json).
The analysis and execution plans independently reconstruct from the cohort.
Their runner cycle IDs are reserved in the frozen plan; no runner was launched
and no GPU was used. The next experiment step is the separate pre-inference
live-preview gate using those reserved slots, followed by inference only if the
preview reproduces the frozen owner, task-plan, identity, snapshot, history,
and prompt bindings.

### Identity-neutral retry state and runtime history allowlist (2026-11-25)

The identity-neutral v15 artifacts passed CPU reconstruction, cohort audit,
matched-task verification, prompt parity, and execution-slot verification. The
first slot was nevertheless consumed before inference: its initial attempt
stopped before run-root allocation because the runner interpreter lacked
`psutil`; the corrected interpreter then reached the resident owner and
rejected selected history containing records outside the frozen protocol's
history inventory. The pair coordinator had checked that inventory but had not
passed it to the owner intervention. `work/historical_examples_intervention.py`
now passes the protocol's `history_record_ids` as the owner's explicit
`history_record_allowlist`, so runtime history selection is constrained by
the same frozen inventory used by preflight.

The follow-up execution-plan slot also remains incomplete. Its run root has an
incomplete cycle failure, zero resource-preflight samples, and no inference
receipt correlated to its run ID among 502 run-root JSON records. The receipt
directory contains 217 receipts copied with history, so that directory's count
alone is not evidence of run inference. Host telemetry after the failure showed 0% GPU
utilization, 899 MiB allocated, and no resident Ollama model. The root cause
for this second failure was journal state: the earlier attempt had already
published an `examples_included` claim without a corresponding receipt. The
journal correctly classified that arm as ambiguous and refused replay. That
pair's task seeds and protocol must remain spent; a fresh runner ID cannot
reset the arm journal.

The next valid trial therefore needs new task commitments and a new pair
protocol, with a fresh shared-history allowlist generated from the verified
cross-model parity audit and bound to the new task digest. Then both model
preflights, the parity and cohort audits, and the execution slots must be
reconstructed before any invocation. GPU inference remains paused while the
GPU is in use. No outcome or durable-learning evidence has been established by
these attempts.

### Fresh identity-neutral cohort frozen (2026-11-25)

The consumed 13688501/13688502 pair was replaced with task seeds 13688505 and
13688506. Seed scouting measured exact probe overlap against the full source
history before preflight; both selected tasks had zero overlap. Initial
unrestricted prompt previews were rejected because the owner's default history
selection included same-identity records. No protocol or run claim was
published by those rejected previews.

The retry reused only the two records established by the reconstructed prior
cross-model parity audit, binding their existing record digests and the new
task digests in bootstrap allowlists. Both targets then passed preflight with
the same fixed records. For each new task, task-commitment verification and the
cross-model parity audit reconstructed successfully: selected record sets and
digests match, the source identities differ from both target identities, and
the included/omitted prompt digests match by arm. A second pair of preflights
was reconstructed against allowlists generated from those new audits, and the
cohort audit independently reconstructed both Hermes trial reports.

The final cohort binds two task seeds and six unique held-out inputs. Its
analysis plan reconstructs from the cohort. The execution plan reserves two
new runner IDs, and both slots independently verify against the stored
protocols, current task plans, and Hermes target identity. The frozen artifacts
are [`cohort_bound.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/cohort_bound.json),
[`analysis_bound.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/analysis_bound.json),
[`execution_bound.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/execution_bound.json),
and [`execution_slots_verified.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/execution_slots_verified.json).
All were produced on CPU. The reserved slots have not been launched; there are
no outcomes, inference receipts, or durable-learning claims from this cohort.
Hermes/GPU execution remains paused while the GPU is in use.

### CPU runner identity preflights matched (2026-11-25)

Both reserved runner IDs passed the runner's exact model-identity prediction
without loading a model. The predicted Hermes identity equals the frozen plan
identity (`sha256:35cce0d6...`) for both slots. The private identity receipts
record `matched_without_model_load`, `run_root_allocated: false`,
`model_loaded: false`, and `model_invoked: false`; their paths and file digests
are summarized in [`runner_identity_preflights.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/runner_identity_preflights.json).
The preflight also reconstructed each slot's protocol, task, selected-history
binding, and identity-neutral source parity before computing the target
identity.

This is an identity and input-binding gate only; the runtime owner's live
prompt preview and the GPU resource gate have not run. The identity check's
source-provenance stage spent several minutes in WSL `git diff` on the mounted
worktree. The reproducible preflight helper now directs that check to Windows
Git to avoid repeating the mount bottleneck. No model was loaded, no run root
was allocated, and the GPU-dependent experiment remains paused.

The answer-free [`cpu_runner_binding_audit.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/cpu_runner_binding_audit.json)
now joins the evidence chain for each reserved slot: frozen slot and journal
validation, reconstructed identity-neutral history proof, and the private
runner model-identity receipt. It independently verifies that the exact parity
audit, allowlist, matched reports, task, protocol, execution plan, target
identity, and runner ID agree. This closes the pre-run input-binding audit
without importing the full runner or contacting Ollama. It remains pre-inference
evidence; the live owner preview and GPU gate must still run before any model
invocation.

### Current v2 pair-slot audit reconstructed (2026-11-25)

The current independent-scoring v2 execution plan was rechecked against its
protocols in the WSL private journal. Both reserved runner IDs and all frozen
task, protocol, probe, snapshot, and target-identity bindings reconstructed
successfully. The answer-free result is
[`execution_slots_reconstructed_v2.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/execution_slots_reconstructed_v2.json)
with execution-plan digest
`sha256:ddbfb1f93089acbdbcd2b3fa5da966fc59496b62ef08b20afe56c23c934113be5`
and verification digest
`sha256:37fd0b956ceeeb3ccb3222eb5f1b1ed0b7a267691121518baf0f57351003224f`.
This resolves the prior ambiguous local check: the older
`execution_slots_verified.json` is for the predecessor plan and has a different
plan digest; the v2 audit is the one aligned with
`execution_independent_v2.json`.

The reconstructed audit reports `model_invoked: false` and
`learning_established: false`. No run roots or outcomes are present for the two
reserved IDs. This validates slot binding only; it does not satisfy the live
runtime preview or GPU resource gate, and no inference was performed.

The matching Hermes pair reports also carry independent v7 preflight receipts
that reconstruct each owner prompt pair and verify the resident-owner protocol
gate, with `model_loaded: false` and `model_invoked: false`. These receipts
establish the frozen pair's prompt-composition preview. A search of the current
`plan_v1.json` artifacts found no rootless planned-cycle plan with the two
reserved pair runner IDs or their task seeds; the generic planned-cycle runtime
preview therefore cannot be substituted for those pair-bound checks. The
separate execution-time live preview and GPU resource gate remain outstanding.

Both v7 receipts were reconstructed again from the current source against the
private WSL protocol journal. The resulting digests and bindings exactly match
the previously stored verification files; the current reconstructions are
[`hermes_13688505_final.json.currently_reconstructed.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/hermes_13688505_final.json.currently_reconstructed.json)
and
[`hermes_13688506_final.json.currently_reconstructed.json`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1/hermes_13688506_final.json.currently_reconstructed.json).
This confirms the frozen pair preflights still rebuild today, independently of
the separate runner-time preview and resource gate.

### Independent scorer source pin checked before outcome loading (2026-11-25)

The v2 cohort aggregator now checks the analysis plan's pinned raw-receipt
scorer source digest immediately after reconstructing the plan, before reading
pair scores or arm state from the journal. The current frozen v2 plan pins
`sha256:43c41aaf30d459835e074fa06de77d8ee4ed71c47e3e4c2c94e260a299c36158`,
which matches the verifier source. A stale scorer implementation therefore
fails before outcome-score access; v1 plans without independent verification
retain their previous same-process path.

### Task-plan reconstruction preserves the history identity policy (2026-11-25)

The first live attempt for reserved runner
`rootless-cognition-cycle-c4d73f9a0e684c45a81b` stopped while the owner was
reconstructing its private objective task plan. The v6 task specification
does not carry `history_prompt_identity_policy`, while its public descriptor
does. The verifier rebuilt the task without that descriptor-bound policy and
rejected the exact preregistered plan. The verifier now restores this field
from the saved public descriptor, which is itself checked against the frozen
protocol descriptor and salted task commitment.

The failure artifact records no resource-preflight samples, no pre-action
decision evidence, no GPU-before sample, and no newly correlated inference
receipt for the reserved runner ID; this attempt produced no held-out outcome.
The execution policy forbids retrying or replacing an allocated incomplete
slot, so this frozen cohort cannot produce its required complete score. Any
follow-up must scout fresh task seeds, freeze a new pair execution plan, and
repeat the CPU binding and live runner gates. The receipt-set proof work above
is independent of this task-plan failure.

A fresh follow-up reached the next pre-inference check and exposed a second
contract mismatch. The runner's live-preview gate intentionally permits the
full governed request digest to change across processes because it includes
runtime authority and session bindings; it still requires the exact frozen
prompt digest and stable owner/task bindings. The owner and receipt verifier
later compared that runtime digest to the CPU preview digest, even though they
are different digest scopes. Those checks now validate the actual request
digest against the invocation receipt and bind prompt content to the frozen
prompt digest. The first fresh runner slot stopped before resource sampling or
model invocation and is spent under its plan; it produced no outcome. A new
cohort is required before any further execution.

### Cohort scorer now emits the frozen reporting fields (2026-11-25)

The v2 analysis plan already requires per-trial correct counts, accuracy
differences, probe outcomes, arm order, complete-trial count, and an explicit
incomplete-trial flag. The cohort aggregator previously emitted only counts
and the mean. It now binds each cohort trial's task digest, arm order, and
probe-set digest to the journal protocol; emits all six required reporting
fields by name; and includes answer-free paired probe outcomes and arm order
per trial.
The output uses the new
[`historical_examples_pair_cohort_score_v3.schema.json`](historical_examples_pair_cohort_score_v3.schema.json);
the v1/v2 schemas remain available for previously emitted artifacts. The
current cohort has no outcomes, so no cohort score has been emitted or
validated end to end.

### Objective score checkpoints are now observation-scoped (2026-11-25)

The fresh `identity-neutral-journal-recovery` pair passed CPU preflight and
reached one Hermes inference. Scoring then failed because the shared protocol
store already contained the CPU-preview score at the path
`objective-score-{protocol}-{condition}.json`. That preview was a distinct
inference observation under the same task protocol, but the checkpoint key
treated protocol plus condition as a unique observation. Immutable publication
correctly rejected the live score as an identity collision. The reserved slot
is incomplete and spent; it provides no held-out outcome.

Objective score checkpoints are now keyed by protocol, condition, and a
digest of the observation ID. This preserves immutable retries for one
observation while allowing separate preview and live observations under the
same condition. The loader can read a legacy checkpoint only when its stored
observation ID exactly matches the requested observation. Because the scorer
source changed after the frozen cohort was made, that cohort is stale for
further execution. A new source-bound cohort and fresh reserved slots are
required before another model invocation.

### Journal score reload now checks the verified semantic record (2026-11-25)

A new source-bound pair passed all CPU gates and completed both Hermes arm
inferences. It durably published the paired score, then the run failed while
reloading it. `_load_event` had already verified the journal record digest and
returned the semantic record without `journal_record_digest`, while
`load_score` incorrectly required that removed field in the semantic key set.
The loader now checks the four semantic fields that remain.

The existing score was then reloaded from private custody and validated against
both archived arm receipts and runtime history inventories. Each arm answered
all three probes and scored zero correct; the paired result does not show a
history benefit. The runner still records an incomplete, spent slot because the
load failure occurred before successful run completion. The source changed
after the frozen plan, so the remaining slot cannot be used; another experiment
requires a new source-bound cohort and fresh slots.

### Terminal receipt binding uses the governed receipt digest format (2026-11-25)

The next fresh cohort passed its model-free gates. Its first launcher initially
failed before GPU loading because the generated environment retained a prior
plan digest; that reserved runner was retired. A second immutable execution
plan with fresh runner IDs then reached both Hermes arms and persisted a paired
score. Terminal publication rejected the score because it validated the raw
64-character receipt digest as a `sha256:`-prefixed preview digest. Receipt
verification and the persisted arm bindings show the two digest fields have
different formats. The terminal verifier now validates `receipt_digest` as raw
hex and `preview_request_digest` as prefixed SHA-256.

The paired score reloaded and verified from private custody: both arms answered
all three probes and scored 3/3. This shows no difference between history
included and omitted on this task. The run remains incomplete because terminal
publication failed, so the slot is spent and not counted as a completed trial.
Ollama unloaded afterward. Since the source changed after the frozen execution
plan, any further inference requires a fresh source-bound plan and slots.

### Completed independent historical-examples cohort (2026-11-25)

After correcting terminal receipt digest validation, a fresh two-trial cohort
completed both Hermes slots under execution plan
`sha256:bcc8174101beca642a674e60e1ad3dc1b2e69b84425c5ecf44c4a51985971090`.
Both terminal records verified governed unload. The independent raw-receipt
scorer reconstructed both paired scores, and the frozen cohort scorer
reconstructed and verified cohort score
`sha256:9eff051d7f6e587b3b25a4b24bf34d2b4b8d8adb5d9b0c550cd77655dad90d88`.

Seed `13688613` scored 3/3 with examples included and 3/3 omitted. Seed
`13688614` scored 0/3 in both arms; the omitted arm abstained on two probes.
Both per-task accuracy differences are zero, and the cohort mean difference
is exactly zero. This cohort does not show an accuracy benefit from including
the selected historical examples. Durable learning, general transfer, and
model independence remain unestablished. Full score and independent
verification artifacts are in
[`identity-neutral-journal-recovery-20261125-terminal-binding-v1`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-terminal-binding-v1/).

### Higher-resolution transfer cohort and saturated in-family probes (2026-11-25)

The completed 3-probe cohort showed no mean accuracy difference, so the next
preflight added configurable task-family selection and 1-to-16 held-out probes
per task. Matched-task commitment reconstruction now binds the selected family
and probe count; the frozen analysis plan accepts a uniform probe count across
a cohort. The existing low-range family has only transfer inputs 6 through 9
in its fixed task definition. A model-free scan of 1,000 fresh seeds found all
1,000 overlap the source history and zero eligible held-out tasks, so that
in-family contrast is currently exhausted against this history store.

A fresh wide-range cohort used 12 disjoint held-out probes in each of two
trials (24 paired probes total). Both Hermes slots completed, and the raw
receipts were independently rescored. The frozen cohort result is
`sha256:deb3f09fdf49136f8ca3c7577d0f5b5f6dbb9202be127948389cdad3c36b7b47`;
its unweighted mean accuracy difference is `-1/8` (examples included minus
omitted). Seed `13688801` had 0/12 correct with examples and 1/12 without; both
arms answered one probe and abstained on eleven. Seed `13688803` had 3/12
correct with examples and 5/12 without; both arms answered all twelve. Across
these two tasks, the wider sample does not show a coverage shift and points
descriptively toward worse accuracy with the selected examples. This remains a
two-task result with no inferential statistics. Durable learning, general
transfer, and model independence remain unestablished.

The model-free preflight extensions are in
[`preflight_resident_historical_examples_pair.py`](../../scripts/preflight_resident_historical_examples_pair.py),
matched-task reconstruction is in
[`verify_matched_task_commitment_pair.py`](../../analysis/verify_matched_task_commitment_pair.py),
and the verified score artifacts are in
[`identity-neutral-journal-recovery-20261125-wide-power-v1`](../../artifacts/experiments/identity-neutral-journal-recovery-20261125-wide-power-v1/).

### Empty-history acquisition bootstrap failure (2026-11-27)

The two-cycle Hermès campaign frozen as WSL plan v3
(`a8b03c296ff5c9ce5318699c0d3b08775877ece350c1d95f056857a10325a59c`)
used cycle IDs `rootless-cognition-cycle-7c2d379c06ba40baad85` and
`rootless-cognition-cycle-dd37c4649cd14b238b33`. Both cycles terminated at
`objective_task_family_acquisition`. The resident owner recorded
`blocked_no_eligible_history` for the acquisition request; no objective
measurement or score-bound acquisition record was created. These slots are
spent and must not be replayed.

This exposed an initialization deadlock: objective acquisition requires an
eligible prior record even though its task does not require task-family history.
The preceding companion-interaction observations are experiment measurements,
not developmental writebacks, and the non-actuating path creates no consequence
record. Consequently acquisition could not create the first task-family record
needed by later history-enabled transfer. The cycle runner now records the
owner's bounded status, prior-record count, and measurement-presence flag in
`failure_diagnostic` when acquisition does not start, while excluding model
output. This makes terminal evidence distinguish the bootstrap block from an
inference or scoring failure.

The runner now adds a first-record bootstrap only when the verified
resident writeback inventory is empty. It performs one explicitly history-
withheld developmental observation on the same synthetic body-state snapshot,
then verifies the observation, governed invocation receipt, newly written
record, and writeback receipt before beginning the separate exact-scored
task-family acquisition. Existing history skips this bootstrap. The seed record
is not itself score-bound task-family evidence, and successful bootstrap alone
does not establish learning. A fresh source-bound campaign plan is required
before using this new path. The campaign planner's v13 schema declares the
bootstrap trigger and evidence gates in the plan digest; v13 is accepted only
for the wide cross-range design. Any plan made before the latest source change
is retired, and its cycle IDs are not reusable. The two original v3 slots
remain spent and must not be replayed.

No developmental learning or transfer claim follows from these failed cycles.
Their private WSL evidence roots remain preserved under
`~/.local/state/sentientos-cognition-followup-20261122-wsl/cognition-goal-20261127-v2/`.

The replacement v13 plan is frozen as
[`campaign-plan-wsl-v9.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v9.json),
campaign `rootless-history-campaign-ebfb27f3dba02c071383`, digest
`14586b73ee01146065b8f552eda2b5fef6a3188578c81f0caa87c6298d2524d9`.
Its two reserved cycle IDs are `rootless-cognition-cycle-e01bc6cc6598319c9cd8`
and `rootless-cognition-cycle-fa3370e8831a4029a2ed`; task seeds are
`2885016571` and `2844663627`. Model-free verification confirmed an empty initial
history boundary, the declared comparison-disabled bootstrap gates, and the
pinned source and model identity implementations.

The preceding v6 cycle stopped at `objective_task_family_acquisition` with an
`AttributeError` after two inference receipts, before bootstrap or writeback.
After correcting the inventory call, v7 reached `initial_history_bootstrap`
and stopped with `history_withheld_configuration_invalid` after two inference
receipts; the owner permits durable no-history observations only when
comparisons are disabled. Neither failed cycle created a developmental record.
Both runs unloaded the model, and the GPU returned near idle. The bootstrap now
uses the already initialized comparison-disabled owner while sharing the same
writeback store and admission ledger. Both v6 and v7 slots are spent/retired.
Plan v8 was retired before inference after static inspection showed its proposed
history allowlist was incompatible with the non-family acquisition task;
general history retrieval already admits the bootstrap record for that task.
Plans v4 through v8 and their cycle IDs remain reserved.

The v9 first cycle (`rootless-cognition-cycle-e01bc6cc6598319c9cd8`) reached the initial-history bootstrap but terminated before writeback with `cognition_candidate_request_invalid`. The terminal artifact records zero governed developmental records, no learning claim, and a successful target-model unload. The failed cycle is spent. Its answer-free 43-file digest manifest is [`cycle-0-v9-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-0-v9-evidence-manifest.json); the private full evidence remains under the WSL workspace.

The rejected request carried the current optional `authority_map_policy_digest` alongside the older request fields. The writeback validator required an exact legacy field set, so it rejected the otherwise governed cognition candidate before append. The validator now accepts that optional policy digest only when it is a lowercase 64-character SHA-256 value. It remains in the semantic request digest, preserving request binding. This is a code correction based on the recorded failure, not a reclassification of the failed cycle. The next run needs a fresh implementation-bound plan and cycle IDs; v9's remaining slot is not reusable. Durable learning and transfer remain unestablished.

Replacement plan v10 was frozen after the validator correction. Campaign `rootless-history-campaign-b0b968450202458c99c7` has digest `73519c448c9277cdb9a78fe03da31360dde3566c77ba380e4aae353637f644e3`; it preserves the empty initial-history boundary and binds the corrected implementation. Both model identities and all implementation pins verify without inference. Its fresh cycle IDs are `rootless-cognition-cycle-31188dc14bab4ed1b121` and `rootless-cognition-cycle-52a9f5ef3f3b480eb75e`; the remaining v9 cycle ID stays retired. Plan artifact: [`campaign-plan-wsl-v10.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v10.json).

The first v10 cycle (`rootless-cognition-cycle-31188dc14bab4ed1b121`) validated the repaired writeback path: bootstrap evidence reports `created_verified_history_free_seed`, exactly one record and writeback receipt, `retrieved_prior_record_count: 0`, `score_bound: false`, and `learning_established: false`. The subsequent wide-range acquisition still terminated at `history_decision_contrast_invalid`, before producing a score-bound acquisition record. Its failure artifact lists only the unscored bootstrap record and records a governed model unload. The cycle is spent, and v10's second slot will remain unused because the planned two-cycle evidence chain cannot be satisfied after this acquisition failure. The answer-free cycle evidence manifest is [`cycle-0-v10-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-0-v10-evidence-manifest.json).

The new failure is in the existing historical decision-contrast projection during acquisition, after the bootstrap has succeeded. It is separate from the request-schema rejection fixed for v10. I have not relaxed that validation: the contrast is evidence-bearing and needs a precise schema/lineage diagnosis before any new plan. No learning, transfer, or model-independence claim is supported by this cycle.

The v10 failure is now localized to a projection-kind collision. The writeback layer emits `developmental_history_interpretation_projection:v4` for score-bound task-family records, whose compact summary does not carry `history_decision_contrast` unless companion decisions were recorded. The reader treated every v4 projection as a companion contrast and raised when that optional field was absent. The reader now recognizes a task-family v4 projection without a contrast as not applicable, while retaining strict validation whenever a contrast is present. This preserves the distinction between objective task scores and companion decision proposals.

Plan v11 is the replacement for the retired v9/v10 campaigns. It binds commit `86660ef7`, the unchanged empty initial-history boundary, and the wide-range 12-probe protocol. Its campaign is `rootless-history-campaign-659a556f31784d51a19e`, digest `209a260e704bc3c844761d80bd241f245d037d0394c9732d8bcdc1e50c451619`. Fresh cycle IDs: `rootless-cognition-cycle-187636c9aefa402aa4ef` and `rootless-cognition-cycle-bfdac8bfefed4e3dba87`. The frozen plan is [`campaign-plan-wsl-v11.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v11.json).

Plan v11's first cycle completed the bootstrap and the wide-range acquisition with exact score lineage. The acquisition produced 3/3 correct source examples in one score-bound source run. The preregistered transfer analysis skipped because the history-withheld condition did not meet the baseline-competence gate; the history-enabled cross-range audit also correctly skipped because its protocol requires two qualifying source runs. The cycle did not establish improved performance, durable learning, transfer, or model independence. Its answer-free evidence inventory is [`cycle-0-v11-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-0-v11-evidence-manifest.json).

The second v11 cycle admitted the exact prior cycle history and recovery boundary, but stopped before creating a second score-bound source record. The retrieval cognition request timed out at its 120-second budget with a 21,200-character prompt and no output. The terminal record preserves two prior records, 19 invocation receipts, `retrieval_cognition_not_completed`, and confirmed model unload. Its evidence inventory is [`cycle-1-v11-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-1-v11-evidence-manifest.json). This is a context-size/latency limit in the growing-history path; the next protocol revision will give bounded cognition calls 180 seconds, matching the pinned local runtime timeout, while retaining the 24,576-character input cap and 512-token output cap. v11 slots are spent and will not be replayed.

Plan v12 is frozen against the 180-second bounded cognition timeout. It retains the 24,576-character prompt ceiling, the 512-token generation ceiling, the same empty initial-history boundary, and two fresh cycle slots. The plan verifier confirmed current source and model identity pins without inference. Campaign `rootless-history-campaign-b8374f333760426b9792`, digest `184130a2350fd3286a49a70eb7ac202d591fff63e3fbb95854fe85bc1f8ce48a`; cycle IDs `rootless-cognition-cycle-af9a54b10fc3472fa065` and `rootless-cognition-cycle-a431057c1c474623a52e`. Artifact: [`campaign-plan-wsl-v12.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v12.json).

The first v12 launch failed before inference with `ollama_experimental_session_request_out_of_scope`: resident cognition now requested the planned 180-second budget, but the developmental session adapter still enforced a separate 120-second ceiling. It wrote no inference receipts and no developmental records, and the model was not resident at the failure boundary. The terminal slot is retired because it has a failure artifact. The answer-free manifest is [`cycle-0-v12-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-0-v12-evidence-manifest.json).

The session adapter now uses the existing shared `MAX_CALL_TIMEOUT_SECONDS` limit (180 seconds) for both full and runner-owned developmental sessions. v12's remaining slot depends on a completed predecessor and is retired with the campaign. A new plan must bind this paired timeout change before another run.

Plan v13 incorporates the paired 180-second resident and session ceilings. Model-free verification reports matching current implementation pins and model identities. Campaign `rootless-history-campaign-594a27cf28084ba2ab9b`, digest `118c0f49ce0b49a752143706aa03906246623ce613bc1b81a3ddb86397f15e06`; fresh cycle IDs `rootless-cognition-cycle-791551b1aa2d435db65f` and `rootless-cognition-cycle-59ec7e35b3ad43ce88a0`. Artifact: [`campaign-plan-wsl-v13.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v13.json).

The v13 first cycle passed empty-history bootstrap and both objective task-family runs, then stopped at `objective_family_progression_unverified`. The terminal evidence has three governed developmental records, 17 inference receipts, a verified unload, no authority, and no learning claim. Its digest-only file inventory is [`cycle-0-v13-evidence-manifest.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/cycle-0-v13-evidence-manifest.json) (digest `dcc9af7d5e4bcc4c5d7fefbf085f6d39cc397907477808b92bafd041842d79ab`). The transfer run's 12 probes were all abstentions. Owner writeback calls also repeatedly reached the 512-token ceiling and were marked truncated; this is an observed output constraint, not an established cause of the progression failure. The failure artifact omitted the progression gate's derived booleans, so the exact unmet invariant cannot be recovered from that artifact alone. The dependent second slot is retired and must not be run.

The v13 progression mismatch is now localized in the durable condition records. All three conditions in each run had the same generation settings. The acquisition and transfer runs also matched on model identity and generation controls after removing the task-specific `structured_output_schema`; their output schemas differ because the task suites have different answer counts. The old gate compared the full profile digest, including that schema, so it incorrectly treated the controlled runs as different-generation episodes. The progression inspector now keeps the exact profile digests and separately records each output-contract digest, while comparing normalized control digests across episodes. This does not change any v13 result or establish learning.

The runner places a bounded diagnostic in future progression-gate failure artifacts: progression status, episode count, same-generation-control check, task/probe distinctness, and scoreability. It excludes prompts and model outputs, makes no learning claim, and does not relax the remaining gates. A future frozen plan should also address the observed 512-token writeback truncation as a separate intervention and use fresh cycle identities; v13 is not evidence that truncation caused the progression mismatch.

Plan v14 binds the normalized-generation comparison fix and the new progression-failure diagnostic. It keeps the v13 wide-range 12-probe task family, empty-history bootstrap, and cross-range competence requirements, with two fresh cycle IDs and seeds. The plan verifier matched all 2,557 implementation pins and both model identities without inference. Campaign `rootless-history-campaign-53aebe96bc53496ba709`, plan digest `a89ba1e41dd2fe631fc1b5a5db7dc393f25d4ae8c4a46b70dc64045a5366402a`; source commit `ad22afda3de5c731ea026a8acc5855cd41b866d4`. Artifact: [`campaign-plan-wsl-v14.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v14.json). No inference has been performed for v14.

Before launch, a model-free replay of v14's frozen task-generation seeds found three exact probe values shared across its two cycles. v14 is retired and neither cycle may be run. The planner now rejects wide-range plans that reuse a probe within an acquisition/transfer pair or across campaign cycles. This prevents previously scored examples from silently reappearing in later history conditions; a fresh plan must pass this guard before any inference.

Replacement plan v15 passes the new disjoint-probe planner guard: each cycle's 3 acquisition and 12 transfer inputs are disjoint, and the two 15-input cycle suites have no exact overlap. The model-free verifier matched all 2,557 implementation pins and both model identities. Campaign `rootless-history-campaign-fa8a5a732f884f5b9df7`, plan digest `3ec48f1a9f9cd3e71c89baef057f5329d13099f3fc5f4d1677f1e559dd804192`; cycle IDs `rootless-cognition-cycle-e9288c632e9942f4acb5` and `rootless-cognition-cycle-45fbb925f7db426c8a06`; task seeds `130304764` and `4094112148`; backend seeds `527158896` and `841446896`. It binds source commit `e4f3ecd1b6fecd2141195bf43bc4161703f3320b`. Artifact: [`campaign-plan-wsl-v15.json`](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-plan-wsl-v15.json). No v15 inference has been performed.
