# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

The fresh remote checkpoint at the start of the recent construction continuation was `96ca1cf4134e3f28ce21c54cb20ca6fc1aade920` (tree `4d45c3df6fd3cef4692f505a03a4a65b3632333d`). The branch later reached `970427376dee3d9fa59bf90704698db630036466` (tree `15609366636954e35b86e7f6afefb1a1ac405e20`), which is the source base for the checkpoint appended below. Local Git `HEAD` is not authoritative.

## Current constructed connections

- Windows has an import-safe `flock` facade, reparse-safe bounded custody readers, and an installation-scoped read-only view. The view derives the fixed machine root from installation identity, validates it by held Windows handles and exposes no write or lock methods. POSIX mutation behavior remains unchanged.
- Windows daemon recovery can read the exact configured resident model-transition protocol and journal. A separate transition-custody inspector verifies request packets, bounded receipt chains and journal references without consuming a packet, appending a receipt, retrying a stage, or invoking inference. Process transition remains POSIX-only.
- Successor software and model-replacement readers preserve canonical identities, bounded evidence and incomplete/interrupted posture. Reconstructing an interrupted model replacement does not replay its inference endpoint.
- World-State has an explicit proposal-review projection; a new fulfillment-receipt bridge now additionally binds the full v2 receipt, preserves proposal/review/handoff references, rejects duplicate identity conflicts, and emits only a digest-bound fulfillment claim. It marks receipt creation time separately from effect time and asserts no authority or actual effect.
- The projection config accepts the existing v1/v2 selections and a v3 explicit fulfillment selection. The daemon re-reads selected receipts on each board build, reports degraded/missing/omitted selections, and makes verified historical claims available to existing configured epistemic and later-tick self-model paths as interpretation, with unknown freshness.
- Strategy proposal records now distinguish the invocation request's experiment linkage from authenticated resource-allocation linkage carried by the invocation receipt. The resident World-State builder joins selected proposal records to the separate resource-ledger record by invocation, allocation, attempt, consumption-receipt and effect-receipt identity, checks principal binding and ledger completeness, and emits a bounded historical lineage record. It carries exact principal/allocation identities, model/software-generation posture, and experiment/history context. Missing or conflicting selected custody is degraded; legacy unlinked invocations remain unlinked. The joined lineage is prioritized for later resident cognition and carried into review/self-model interpretation as lineage, not consequence or objective.
- The same bounded ledger join now covers the five-condition model A/B replacement experiment. Its World-State observations preserve request/model identities, inference and consumption receipts, condition/history context, model provenance, and unknown software-generation posture. Resource compact records now extract request/model ids from the nested invocation request for exact comparison. The epistemic adapter carries the ledger event time into the historical evidence binding; incomplete derived lineage remains contextual.
- Developmental writeback now applies a digest-bound compact projection to joined resource invocation lineage. Long experiment-history context and consumption-receipt lists cannot exceed the writeback's smaller evidence budget silently; omissions are marked and the complete source payload remains bound by its digest.
- Model-replacement resource facts preserve both the run artifact identity and the exact World-State source record identity/digest. Developmental writeback carries these values through its compact projection, including the separate model identity/provenance and causal-context bindings.
- The strategy experiment's retained-history scope now verifies receipt-bound invocation lineage as well as whole-ledger records, and supports factual proposal assertions only when they cite the exact verified resource source ID and digest. Consequence citations, external-effect claims and body-modification authority remain separate.
- A resource-source digest match establishes citation provenance only; claim semantics remain unverified and produce an explicit `unverified_resource_claims` outcome. Model-replacement history scope additionally requires exact run/source-record, model-provenance and causal-context identities. Unknown software-generation identity stays separate. The bounded resource-lineage join now chooses recent candidates by timezone-aware historical consumption receipt times from digest-valid, complete projections, and binds omitted candidate identities in its degraded retention record.
- The strategy task schema is versioned v3 and explicitly asks for exact source-ID/digest citations, separates citation identity from claim truth, and rejects physical resource inferences from invocation counts, latency, or output size. Resource-lineage projection now orders bounded candidates by verified historical receipt event time, leaves unknown or conflicting times first and unknown, and emits digest-bound identities for omitted candidates; only digest-valid, reconciled, complete ledger projections can influence this selection.
- Windows adoption inspection now verifies the original configured cadence directory through the existing reparse-safe held-handle reader before normalization. Wake configuration files use the existing explicit-file custody read as the security decision; Windows mutation/effect paths remain blocked.
- Successor-generation recovery now uses handle-bound known-path reads for Windows presence checks instead of `Path.exists()` on generation and receipt artifacts. Read-only `inspect()` exposes an incomplete handoff with its bounded pending phase; start and mutation remain blocked without POSIX flock support.
- Earlier local construction continues to harden epistemic state, developmental history, resource evidence, admission, and invocation recovery. Writes stay fail-closed where equivalent atomic Windows publication and custody are unavailable.

## Verification and limits

Changed Python files compile and `git diff --check` passes. No pytest, mypy, runtime execution, Windows execution, provider/model activation, real-world observation, or production verification was performed. Cross-platform installation-backed mutation, activation, serving, transition execution and atomic publication remain unsupported. The fulfillment receipt is a fulfiller claim only; it does not demonstrate that an external action occurred. Current embodied independent-observation input still lacks an authenticated observer issuer. The strategy/model-replacement resource joins, compact writeback projection, and Windows artifact reads are source-implemented but not runtime exercised; joins are bounded to the configured projected ledger tail.

## New construction checkpoint — Windows daemon import closure

- A bounded AST walk of the `sentientosd.py` import graph found one reachable unconditional `fcntl` import: `maintenance_initial_posix_resident_commissioning.py`. The module's commissioning flow is intentionally POSIX-only and `doctor()` already blocks non-POSIX hosts, but importing it from the daemon could fail before that gate on Windows.
- Replaced the unconditional import with the existing `platform_fcntl.FLOCK_SUPPORTED` capability and made the doctor consume that explicit capability. This keeps module import possible while preserving POSIX-only commissioning and failing closed where native flock is unavailable.
- Source-checked this single import-chain issue only; no Windows runtime execution was performed.

## New construction checkpoint — model-replacement event time

- Governed model-replacement experiment observations bound invocation request/receipt identities and output digests, but omitted the genuine invocation receipt's `observed_at`. The durable run therefore could not preserve exact inference event time through World-State and epistemic evidence.
- New observations now carry the original timezone-aware receipt timestamp text inside their own digest-bound identity. Verification accepts historical rows without the optional field, validates any present value, and World-State run projections retain the per-condition times. The epistemic adapter selects the latest valid event time from those bound observations without promoting the historical experiment to current freshness.
- Missing time remains unknown; no reconstruction or tick timestamp is substituted. Construction is not production-verified.

## New construction checkpoint — succession evidence into longitudinal self-model

- The actual experimental serving endpoint now returns the invocation owner's original `observed_at`; it is captured in the digest-bound condition observation with posture `invocation_receipt_metadata_unverified` because the historical invocation receipt digest intentionally excludes that custody metadata.
- The durable five-condition model-replacement World-State fact now has a compact longitudinal self-model interpretation with exact run/protocol/context identities, A/B model and provenance identities, each bounded condition's observation/receipt IDs and resource-link digest, preserved event-time text/posture, completion and classification. It explicitly records unknown software-generation identity and no current truth/effect/authority.
- Historical observations missing the optional timestamp remain compatible and undated. The new interpretation is emitted only as a predicate consumed when the existing explicit predicate allowlist selects it; no default epistemic rule or self-model predicate selection was activated.
- Resident developmental cognition now selects verified model-replacement run evidence ahead of generic World-State facts and selects consequence chains/comparisons before strategy proposals, after active running identities and resource/transition evidence. It requires the `embodiment` source kind for these priorities, preserving source-kind distinctions.
- Windows read-only `ConsequenceStore` construction previously used `Path.exists()` as its only root-custody check before later handle-bound artifact reads. It now validates the explicitly configured root through `verify_explicit_directory()` and maps missing versus unsafe/unavailable roots separately; POSIX behavior is unchanged.
- Legacy model-replacement conditions without timestamp fields now project an explicit `unknown` time posture, preserving their receipt identities without leaving an ambiguous null posture.
- The POSIX-only initial-resident commissioning inspector's shared artifact loader no longer relies on `is_file()` plus `read_text()`. It now uses the existing bounded no-follow explicit-file reader on both platforms; commissioning authority and effect execution remain POSIX-gated.
- Epistemic adaptation of expectation, renderer, observation, attribution and comparison records now reads event time only from their digest-bound owner payload fields. Consequence-chain summaries preserve the latest valid bound event across expectation, command, renderer, claimed observer and comparison while retaining each source time separately. Nonsemantic World-State `observed_at` metadata no longer seeds a new historical evidence identity for those records.
- Repeated resident succession snapshots no longer timestamp stable serving-session identities or recovered journal posture with each daemon tick. Those rows keep time unknown when the owner does not retain a session/event timestamp. Model and software transition journal events use their digest-bound payload event time; resident-software launch lineage carries its bound startup timestamp in payload for adaptation.

## Next executable task

The daemon computes proposal/resource lineage immediately after collecting those source records, then orders raw ledger records and their joins before dependent proposal/model experiment sources at the World-State 128-record cap. It exposes a degraded projection status for omitted, incomplete, otherwise non-verified, or source-identity-conflicted lineage records. The daemon and developmental cognition owners pass these facts through normal World-State selection when the explicit source-kind configuration allows `resource_governor`; no checked-in epistemic rule configuration was found, and no default or selector was added. World-State records with failed source digests or source-identity conflicts remain contextual only in epistemic development; their event time is withheld and they cannot inherit a configured `supports`/`contradicts` relation. Repeated source IDs with different observation timestamps now produce an explicit World-State conflict; epistemic event-time comparisons use timezone-aware UTC while preserving the selected source timestamp text in stable evidence identities; malformed/naive values remain undated. The resource-lineage projection can now prioritize actual known event time inside its bounded tail without letting reconstruction time or invalid source rows reorder evidence. Consequence-chain World-State summaries retain expectation, command, renderer, claimed observer, and comparison times separately inside the digest-bound payload. Their top-level `observed_at` remains null because that World-State metadata is intentionally outside the record digest; the epistemic adapter reads only the payload-bound claimed observation time, and still labels observer independence unverified. Consequence evaluation rejects comparison times before their contributing events and rejects command/renderer order reversals. Caller-supplied embodied observations remain contextual until an authenticated observer issuer is composed.

### New checkpoint — prediction comparison continuity

- Longitudinal self-model now retains a compact historical prediction-outcome lineage claim for digest-verified consequence attribution/comparison facts. It binds the exact source record, comparison, expectation, and optional observation IDs/digests; preserves bounded per-field result labels and counts without copying expected/observed values; carries only the attribution's original evaluation time; and marks the claim historical with no truth, effect, or authority.
- Resident cognition's context instruction now makes missing/indeterminate comparisons non-satisfied and treats contradiction as revisable evidence rather than a belief or action command. The existing configured predicate allowlist and source-kind selection still control consumption; no epistemic rule or authority path was enabled.
- Python compilation and diff whitespace checks passed for the changed files. This is source construction only; no runtime, platform, behavioral, or production verification was performed.

Next inspect whether admitted later history can carry an authenticated external consequence source through the existing observer interfaces. No observer issuer is currently present; keep caller claims contextual and continue other implementation while that dependency remains unavailable.

### New checkpoint — prioritize retained outcome evidence

- Resident cognition now selects digest-verified consequence-chain, attribution, and comparison facts ahead of proposal/review/fulfillment rows when bounded fact selection requires truncation, after current identity, resource, transition, and controlled model-replacement evidence.
- This priority only affects the existing explicit source-kind selection. Contradictory or incomplete comparisons remain historical evidence and do not gain freshness, truth, objectives, or permission.
- Compilation and whitespace checks passed for the modified Python modules. Runtime and production behavior remain unverified.

UTC tick ordering is now checked in durable self-model and resident-history selectors; see the checkpoint below. The next source task is to determine whether an authenticated external consequence source can be composed from an existing owner. If none exists, retain that exact dependency and continue with source-backed succession continuity.

### New checkpoint — host snapshot continuity

- The longitudinal self-model now has an optional historical claim for digest-verified `host_resource_runtime:snapshot` World-State facts. It carries exact snapshot/source digests, only the owner-reported scalar fields within the record's size bound, and explicit unknown fields. The quality posture remains unqualified; it creates no per-invocation attribution, truth, effect, or authority.
- The claim is `historical_interpretation`, which keeps self-model freshness unknown. It reaches later cognition only when the existing `resource_governor` source selection and explicit self-model predicate allowlist include it; defaults remain unchanged.
- Python compilation and diff whitespace checks passed. Host-specific execution and runtime evidence have not been tested.

### New checkpoint — exact prediction comparisons

- Reconciled the two campaign-owned modules that had local source ahead of their remotely published versions: the proposal/consequence owner now includes bounded review, fulfillment and World-State projection paths, and the daemon composes those explicit selectors through the existing read-only source owner. These paths retain their existing no-effect and configured-opt-in boundaries.
- The embodied consequence comparator now uses recursive JSON-type-sensitive equality for `exact` policies. Booleans no longer compare equal to numbers, including inside arrays and objects; numeric tolerance remains the separate declared policy.
- Python compilation and whitespace checks passed for both modules. No behavioral or production execution was performed.

### New checkpoint — restart-safe temporal projection

- Durable self-model cognitive projections and resident developmental-history retrieval now require a parseable timezone-aware tick and select only records whose source tick is strictly earlier. Same-tick, later, malformed, or timezone-naive history is withheld, including after restart; an opaque tick no longer risks treating a future generation as prior history.
- The daemon supplies UTC ISO tick IDs. Non-ISO callers will receive no resident history projection; no alternate ordering token is currently bound into those owners.

### New checkpoint — preserve host observation event time

- The epistemic adapter now reads host snapshot event time only from the digest-bound snapshot payload, never the World-State retrieval timestamp. Missing or malformed source time remains unknown; host resource evidence remains historical with unknown freshness.

### New checkpoint — separate declared from running software lineage

- Model-replacement World-State evidence now retains the exact `repository_generation_identity` already bound by its frozen causal context under the explicitly declared name and posture `frozen_context_declaration_not_running_observation`.
- The observed/running software-generation identity remains `None` with its existing unbound posture. The self-model exposes the declaration only under separate opt-in lineage predicates; a commit or declared context cannot imply the running generation.

### New checkpoint — finite consequence comparisons

- Canonical consequence serialization rejects non-JSON non-finite floats. Numeric-tolerance policies must be finite and representable; exact comparisons retain recursive type-sensitive semantics. Numeric deltas outside the finite float range remain `indeterminate` instead of producing misleading output.
- No numeric measurements or observed outcomes were generated; the change only tightens how supplied evidence is compared.

### New checkpoint — enforce epistemic tick cutoff across recovery

- The resident daemon captured durable epistemic state before cognition, but its owner selected each proposition's latest generation without checking that generation's persisted update tick against the current cognition tick. On clock rollback or interrupted/recovered sequencing, a future-dated latest state could enter a projection.
- `PersistentEpistemicStateOwner.cognitive_projection` now accepts an optional exact current tick and excludes a proposition when its latest generation is at or after that tick. It does not fall back to an older generation for that proposition. The resident daemon passes the timezone-aware current tick as the same integer epoch seconds used by epistemic development; missing/naive times fail closed. Existing direct owner callers retain the legacy capture behavior when no cutoff is supplied.
- This is construction-only. Python compilation and diff whitespace checks passed for the edited modules; no behavior tests or production verification were run. Next inspect adjacent durable writeback/developmental-history chronology boundaries for equivalent recovery-time gaps, then proceed to a more consequential causal continuity connection.

### New checkpoint — persist the cognition interruption boundary

- Resident cognition previously learned a tick was interrupted only when at least one cognition observation had already been atomically persisted. A process loss after starting inference but before that observation left no durable boundary, permitting a same-tick attempt on restart.
- The owner now atomically records the exact tick and World-State identity as `in_progress` before any model call. A subsequent owner entry marks leftover intents `interrupted_recovered`; the same tick remains rejected. Normal completion removes the marker in the same state publication that appends the completed tick. Later ticks remain eligible, and no inference/effect is replayed by recovery.
- Python compilation and `git diff --check` passed for affected modules. No behavior tests or production verification were run. Next inspect how incomplete cognition inference receipts relate to call-conservation custody, then pursue another substantive source-backed developmental connection.

### New checkpoint — recover epistemic state/event publication

- Epistemic mutation previously wrote its state and update event as two independent immutable files. Interruption after the first write left an unmatched record that `verify()` rejected, with no information to reconstruct the missing peer.
- State updates now first publish a bounded digest-bound transaction containing the exact state/event pair and, for separately admitted updates, the candidate, admission, operation, and correlation binding. Verification deterministically reconstructs missing pair members from valid transaction custody and rejects malformed, contradictory, or generation-colliding transactions. The update compare-and-swap is serialized with the import-safe POSIX flock owner lock; non-POSIX mutation remains blocked.
- The mutation controller now writes a bounded immutable intent before state mutation. On restart it reconstructs a missing receipt only when the exact transaction, update, successor state, candidate, and historical admission all reconcile. An intent without a completed pair remains incomplete and is never replayed. Receipt/intent publication is atomic and bounded, and recovery reads are no-follow/descriptor-safe on POSIX or handle-bound on Windows.
- The corresponding evidence-binding path now publishes an admission-bound immutable intent before appending a binding and reconstructs a missing receipt only if the exact binding is present and the historical admission still verifies. Intent without an appended binding remains incomplete; recovery never performs the append. Existing evidence receipts are now read through bounded no-follow descriptors before enforcing separate-stage admission.
- Windows recovery now verifies already complete state/event pairs from held-handle reads without trying to publish. It still refuses a transaction whose pair is incomplete because an equivalent atomic Windows writer is not implemented.
- Python compilation and `git diff --check` passed for affected epistemic modules. No behavior tests, crash injection, or production verification were run. Next inspect whether later cognition consumes candidate/receipt lineage without elevating interpretation to authority, then move to another consequential causal continuity path.

### New checkpoint — prevent replay of an interrupted epistemic intent

- Reusing the same operation/correlation after an interruption could previously encounter an identical immutable intent and continue the mutation path as if it were a fresh invocation. Immutable publication now reports whether it created a new custody object; state/evidence mutation refuses an existing identical intent as `mutation_intent_replay_blocked`.
- Startup recovery remains responsible for reconstructing a receipt only when the completed state/event or evidence binding is already present and reconciles. An incomplete intent remains durable and non-replayable under its original identity; a separately admitted operation is required to try again.
- This prevents duplicate execution under one operation identity without replaying a mutation during recovery. Python compilation and `git diff --check` are required before publication; no behavior tests, crash injection, or production verification are performed in construction mode.

### New checkpoint — keep conversation history readable without POSIX imports

- `conversation_session.py` imported `fcntl` unconditionally, which prevented importing ordinary chat/session code on Windows even when only reading a prior session. Session loads now use the repository's bounded, held-handle explicit-file reader. POSIX locking and publication requirements are explicit; unsupported Windows writes fail closed instead of reaching an `O_DIRECTORY`/`flock` failure after partial setup.
- This is read-path compatibility, not Windows chat write support. The latter still needs an atomic publication and interprocess lock contract; no Windows runtime behavior was exercised. Python compilation and whitespace checks passed; no behavioral tests or production verification were run.
- Next high-value frontier: determine whether ordinary persistent user-chat can preserve exact model-succession continuity without treating a proposed/activated model as observed or mixing private session memory into resident developmental history.

### New checkpoint — bind production transcript custody to installation

- Production sessions previously lived directly under the common `SENTIENTOS_DATA_DIR`, although each chat service was established against a specific authenticated installation and exact serving identity. Production conversation files are now stored under that installation handle's `chat/conversations` directory. Explicitly retained canonical user memory remains in its existing shared root, preserving the separate retention contract.
- Existing unscoped transcripts in the legacy common `conversations` directory are left untouched and are not migrated: source custody cannot prove which installation/model lifetime owns them. The new production path uses installation-handle directory creation; Windows write support remains unavailable under the current installation-state contract.
- Python compilation and `git diff --check` are required before publication. No behavior tests or production verification are performed.

### New checkpoint — preserve model identity across chat continuation

- A persisted session previously rejected any later serving identity whose digest differed from the model that created the session. This stranded transcript continuity after an authorized serving/model change. A same-installation explicitly selected session can now continue; each completed assistant turn stores the exact active model identity taken from its authenticated invocation request, the previous assistant identity digest, and an explicit `model_identity_changed_predecessor_relation_unverified` posture when they differ.
- Later prompt context carries those identity digests as untrusted provenance. For production, the exact serving identity is separately checked against the invocation's digest-bound serving lifetime and caller session/turn linkage; the loaded-model identity is retained independently. The context snapshot digest binds the turn-linkage digests as well as turn text, so provenance actually consumed by the model is covered by its snapshot identity. No identity switch is promoted to proof of model succession or quality.
- Python compilation and whitespace checks only; no behavior tests or production verification.
- Session reconstruction now also checks the stored session model-identity digest, turn sequence/IDs, exact text byte/character counts and digest, timezone-aware timestamps, and any persisted active/loaded identity digests. Legacy per-turn records without the newer identity payload remain readable; their predecessor relation stays unverified.
- Production chat now persists invocation receipt ID and source user-turn ID with each assistant turn. Its serving inference owner can re-open one exact bounded receipt through installation custody, revalidate receipt/request identities and caller linkage, and recover the exact prior serving/loaded model identities without inference. The active serving binding includes the predecessor activation-state digest from the verified activation receipt; when it equals the prior verified invocation's activation digest and generations are adjacent, the session labels the relationship `activation_predecessor_bound_to_prior_observed_invocation`.
- This proves the prior chat call and exact activation-state predecessor relation, not model quality, broader developmental provenance, or running software-generation succession. Legacy history without invocation receipt IDs stays usable as untrusted text and cannot establish the transition. Python compilation only; no behavior tests or production verification.
- Canonical-memory review: `CanonicalMemoryStore` is a shared raw user-memory store, not an authenticated World-State source. Its current deterministic retention gate does not preserve a separately verifiable admission receipt, and no World-State source selector exists for it. The current user-facing contract authorizes retention/retrieval for chat; it does not authorize copying private retained text into resident developmental cognition. Keep this domain separate unless a future explicit admission/source owner establishes that new scope.
- Next implementation frontier: bind actual chat-process software generation to its invocation evidence through an explicitly injected existing runtime owner. The current `MaintenanceResidentRuntimeAdoptionController` observes the `sentientosd` process and its launch generation; `scripts/local_model_chat.py` is separately composed. Do not join the daemon's process generation to chat receipts without a current process-instance binding. Existing model activation and runtime IDs do not prove which SentientOS software generation executed each chat call.


### New checkpoint — repair receipt recovery stage and bind chat process posture

- Fresh GitHub branch inspection verified `codex/construct-sentientos` at `e05619f6711ebb25691b381cd2189828d738b1d5` (tree `7dd211547e3dfe88006d53ba3f614519a711e509`). The stale local checkout was not used as branch state.
- `ResidentEpistemicStateMutationController._recover_state_receipts()` now dispatches recovered evidence-binding and state-update receipts to their verifier-defined `evidence` and `state` stages. Windows recovery stays read-only: it accepts an already present byte-identical receipt and reports `mutation_receipt_recovery_publication_unsupported` if repair would require a write. Identity, admission, and no-replay bindings remain intact.
- Source review found no authenticated issuer for the separately operating chat process. `MaintenanceResidentRuntimeAdoptionController` observes the maintenance daemon's exact process, and neither that identity nor the model activation nor repository commit proves which software generation executed chat. Production invocation requests now bind an explicit unavailable posture with null generation and process identities. Stored chat receipts revalidate this posture; transcript provenance carries it forward. No runtime identity has been inferred.
- The package command `sentientos-chat` previously entered `run()` without invoking explicit production composition. It now routes through the existing CLI configuration flow (installation identity, serving operation, and optional resource provisioning); direct `run()` fails before binding the server when chat is unconfigured.
- Invocation output and persisted assistant text are now reconciled. When the transcript is not truncated, the saved text must match the invocation's digest-bound backend output or chat refuses the turn. When output is truncated, the backend output digest and transcript text digest remain separate with posture `truncated_transcript_original_output_relation_unknown`; no equality is claimed. Recovery checks this relation against installation-scoped invocation custody when available.
- Existing-session chat requests can now opt into bounded request-ID idempotency. The session owner atomically deduplicates by request-ID digest, rejects altered text/retention intent, returns a completed receipt-verified response without another inference, and reports an unanswered interrupted turn without replay. Requests without an explicit ID keep existing behavior; idempotency requires an already known session ID. Interrupted retention is reported as unreplayed/incomplete.
- Construction checks: Python compilation for changed modules and no-index diff whitespace checks. No pytest, runtime, concurrency, crash-injection, Windows execution, provider call, or production verification.

**Next implementation dependencies:**

1. A genuinely authenticated chat-process launch/runtime issuer must bind a fresh process instance to the code generation actually loaded by that process and publish that evidence into invocation custody. No such issuer or observer is present in the current source; do not fill it with self-report, Git state, the chat package version, activation identity, or the separately observed daemon generation.
2. First-request idempotency without a known session ID requires an existing authenticated client/session-creation identity. The current chat endpoint has no such principal; keys are therefore deliberately scoped to an existing session.
3. For truncated assistant output, only the original backend-output digest and separate persisted transcript-text digest exist. Proving the deterministic transformation would require a receipt-bound returned-output digest or retained output material; no change was made that widens transcript retention.

Continue with the next source-backed lifecycle gap while preserving these limits.


### New checkpoint — compose the chat runtime's actual child-launch owner

- Source review located the existing canonical launcher in `sentientos/runtime/startup.py` and `LocalModelChatServiceAdapter`; this supersedes the earlier note that no launch owner existed. The runtime opens the configured installation handle before child construction and injects that exact owner into the adapter.
- The adapter publishes a bounded (256 launch records; 1 MiB per record; bounded Python source member/count/total sizes), immutable installation-scoped handoff after `Popen`. It binds the child PID and parent PID, fixed argv, executable path, working directory, launch timestamp, environment digest, and a content digest over the `sentientos/` and `scripts/` Python source files. The child waits briefly for the parent's record and verifies its live process identity, environment, argv and current source bundle before serving; the inference owner repeats live verification before each local-model call.
- Production invocation receipts carry the launch handoff, software-source generation digest and process-instance identity as separate lineage from model activation/loaded-model identities. Installation-scoped receipt recovery validates the historical immutable handoff without claiming that an old process is still running. Normal direct/manual chat remains explicitly unattributed because it has no parent-issued record.
- Publication is POSIX-only and fails closed; no Windows write path was added. This is a local runtime-owner handoff over installation custody, not hardware/OS memory attestation; its explicit generation scope is SentientOS and scripts Python source, not the Python interpreter or third-party dependencies.
- The package command enters explicit configuration, but the separately supervised canonical runtime remains opt-in. No runtime was launched during this construction pass.
- Changed modules compile and no-index diff whitespace checks pass. No tests, runtime execution, concurrency/crash exercise, Windows execution, model activation, provider access, or production verification.

**Next implementation dependency:** connect the current and predecessor handoff identities through `ProductionLocalModelChatRecoveryController` and its durable startup/recovery records. A subsequent launch is individually attributable now, but the recovery receipt does not yet explicitly join the previous chat-process generation to its successor, especially across supervisor restarts. Preserve the existing separately admitted restart path and never infer continuity from a serving operation alone.

### New checkpoint — bounded restart-generation lineage in invocation custody

- Corrected the parent/child verifier boundary: the daemon verifies the handoff against its actual Popen PID, launch parameters, and current bounded source manifest; the child independently verifies its own PID, parent, argv, environment and source bytes before serving and again before inference.
- Supervised children now hold a nonblocking installation-scoped lifetime lock. A canonical restart will not start a second supervised chat process when a cooperating predecessor remains alive.
- Handoff schema v2 embeds the complete prior digest-checked startup snapshot and its prior process-handoff summary, bounded to 64 KiB. The prior handoff record is separately verified. The relation is explicitly a reference to a prior snapshot; direct process predecessor, overlap, and intervening generations remain unknown.
- Bounded lineage reconstruction follows exact prior handoff IDs/digests, validates each immutable record and nested snapshot digest, and rejects missing, conflicting, cyclic, or over-bound chains. The verified nested attribution flows through the existing invocation receipt and transcript provenance; canonical user memory remains separate.
- Receipt-stage recovery correction remains in the tree: evidence-binding receipts publish to `evidence`, state mutation receipts to `state`, with the existing immutable identity and Windows read-only behavior.
- Construction commits through `dcb333fbd8695721fd34c5e95aa532c0ad5eba13` are remotely verified on `codex/construct-sentientos`. Changed Python files were compiled; bounded source/whitespace checks were performed. No tests or runtime, concurrency, crash, Windows, provider, activation, or production verification occurred. Construction remains unverified.
- The launch issuer is a local launcher/custody observation, not a cryptographic platform attestation or proof of in-memory imported modules, interpreter, or third-party dependency generation.

**Next implementation dependency:** inspect the actual startup/recovery receipt consumers for a safe read-only way to expose the reconstructed process-generation lineage to later chat cognition after restart, without mixing it into canonical retained user memory or claiming direct succession. Also review the recovery transaction’s crash window between successful readiness, startup-snapshot replacement, and final recovery receipt publication; represent incomplete progress without effect replay or false completion.

### New checkpoint — recovered software provenance enters later cognition

- Current production chat now verifies the newly written invocation receipt through the existing durable receipt verifier before attributing software generation to the assistant turn. It no longer substitutes the historical “unavailable” posture for a live child handoff.
- The next chat turn receives a compact, depth-bounded projection of the latest receipt-verified software-generation chain in a separate provenance-only context block. The projection is non-authorizing, marks prior-snapshot references and overlap limits, and remains distinct from canonical retained user memory. Request linkage binds the predecessor handoff and software-generation digests.
- The context change uses the existing session serializer and verified invocation owner; no model prompt assembler or canonical memory contract was changed.
- Changed Python files compile; no tests or runtime checks were run. This remains unverified construction.

**Next implementation dependency:** recovery currently advances the startup snapshot after the restarted child is observed ready but publishes its final durable recovery receipt afterward. Add bounded, immutable recovery-phase custody so a crash between those publications can be reconstructed without replaying a restart or claiming readiness that was never durably recorded. Preserve exact predecessor/successor handoffs and incomplete outcomes.

### New checkpoint — interrupted recovery is reconstructable without replay

- The recovery controller durably records three installation-scoped phases: an admitted attempt before the child restart call, semantic readiness with predecessor/successor handoffs, and completion after the startup snapshot is durably advanced.
- Phase custody is immutable, canonical, bounded per record and per phase directory, idempotent on exact duplicates, and rejects conflicting records or broken phase predecessors. Phase records bind the approved intent, approval, restart decision, supervisor generation, serving receipt, and exact handoff identities.
- On restart, a completed phase reconstructs the same terminal recovery receipt; a readiness phase without durable snapshot completion returns an incomplete receipt; an attempt phase without a terminal observation returns an incomplete receipt with restart outcome unknown. No branch retries a restart or claims unobserved readiness. Reconstruction time is absent from semantic identity.
- Startup snapshots now have a bounded size, digest verification, no-follow regular-file reads, unique same-directory temporary publication, file fsync, atomic replacement, parent-directory fsync, and readback verification. The completion phase follows that durable boundary.
- Python compilation and bounded source/whitespace review only. No runtime, crash, concurrency, Windows, test-suite, activation, provider, or production check was run.
- Remote branch verification: `codex/construct-sentientos` at `b9f87a7c84521f4d1b716629bf961440b241698b`.

**Next implementation dependency:** perform another source-only composition review of normal chat startup, recovery reconstruction, and the verified-lineage context projection. In particular, ensure recovery phase receipts remain bound to the current request file and that retained session history exposes only verifier-qualified evidence while preserving the separation from canonical user memory. Continue into any concrete owner-level gap found.

### New checkpoint — recovery launches bind the immediate observed predecessor

- Source tracing found that the child adapter retained the daemon's original startup snapshot across authorized in-process recovery. It now rebinds to the exact current digest-checked snapshot immediately before the recovery action, after verifying its handoff through installation custody. The replacement child's immutable v2 handoff therefore references the actual snapshot used by that recovery request rather than a stale earlier snapshot.
- This preserves exact request predecessor → launched successor linkage and makes the recovery phase's predecessor/successor verification consistent across repeated authorized restarts. No restart action is added and no effect is replayed.
- Changed Python sources compile; no runtime or crash checks were run. Branch verified at `e5ad86d169c82e4fac332aec6ebb2dbb03c713f7`.

**Next implementation dependency:** continue source-only review through model-serving activation and recovery semantics to ensure the chat software-generation chain does not imply model continuity, and that incomplete or stale serving receipts remain distinct from the process handoff lineage. Preserve both as separate evidence chains in later cognition.

### New checkpoint — source identity captured before child launch

- The supervised adapter now hashes the bounded SentientOS/scripts Python source manifest immediately before Popen, passes that expected digest in fixed argv, and publishes the prelaunch manifest only after confirming the source bytes remain unchanged through handoff publication.
- The child entrypoint checks the expected digest before importing `chat_service`; the handoff continues to bind the actual child/parent PID, argv, environment, cwd, executable, and installation custody. This narrows the source-generation claim without asserting interpreter, dependency, or in-memory page attestation.
- Direct/manual launch without the explicit handoff remains software-generation-unavailable. Model activation identity remains separately verified. Python compilation only; no runtime or production evidence.
- Remote branch verified at `c3b1746908aa3aa19fcb93bac0b43a582955fd61`.

**Next implementation dependency:** inspect cross-restart model-serving receipt composition after the new source binding, then correct any concrete mismatch between generation evidence, serving identity, and recovered chat cognition. Preserve direct predecessor and overlap as unknown where no owner can establish them.

### New checkpoint — bounded transcript storage keeps receipt reconstruction authoritative

- Assistant session turns now persist a compact software-generation summary and exact predecessor snapshot/handoff digests instead of copying the nested lineage on every turn. The durable invocation receipt remains the authoritative full chain.
- On later turns, the existing receipt verifier reconstructs the full software lineage; compatibility accepts prior full summaries and current compact summaries only when they match the verified receipt. The full bounded chain is then emitted into a separate provenance-only cognition block, not canonical memory.
- This avoids repeated chain growth against the existing 8 MiB session bound without dropping receipt custody or changing user-retention authority. Python compilation only; no tests or runtime execution.
- Remote branch verified at `da56d4b2ebd9c7c2bd98ecdf7139135b7873ce44`.

**Next implementation dependency:** inspect the model-serving and succession owner interfaces for any remaining state where a software handoff could be mistaken for an active model, or where recovered model-transition receipts are not cross-bound to their own predecessor/successor evidence. Keep the two lineages separate.

### New checkpoint — model activation and serving history stay separately attributable

- Read-only current-activation verification now reconstructs the exact committed selection chain from installation transactions, checking bounded custody, each generation and predecessor digest, intent and projection identity, stored admission and approval bindings, canonical activation receipt, and the finalization's matching transaction/state/receipt references. Missing, ambiguous, malformed, substituted, or interrupted lineage fails closed. It does not load a model or replay activation.
- The serving owner binds the reconstructed history digest into its serving admission/session receipt and rechecks it for currentness alongside the selected state and loaded-model identity. A new non-mutating `observed_current_session()` gives World-State a read-only opaque session observation; stale sessions are omitted instead of being invalidated by the observation path.
- The daemon emits a source record for an observed running model even when the optional A/B transition protocol is absent. It carries the actual session's loaded identity and exact activation receipt, predecessor and chain digest references. Session event time and model-development provenance remain unknown without their respective owners. This is serving-owner evidence, not independent hardware observation, truth, or authority.
- Changed modules passed Python AST compilation. No tests, runtime, crash, concurrency, platform, model-load, inference, or production verification was run.
- Remote branch verification: `72cf4ae88d7bd71d79c23674e49ac545b9b6cc28`.

**Next implementation dependency:** verify that the new running-model record reaches only configured World-State and epistemic/self-model selectors, then carry activation-history linkage through the resident model-transition stage binding and recovered later cognition without conflating selected, loaded, serving, or observed identities.


### New checkpoint — resident serving and transition journal preserve activation-chain identity

- The canonical resident serving controller now requires the activation verifier's reconstructed selection history, binds its digest into the serving admission/session, and rechecks it during currentness. It exposes `observed_current_session()` for read-only World-State capture; unlike `current_session()`, this does not invalidate or unload a stale model.
- The actual A→B and B→A transition adapter re-reads the committed activation history after the activation owner returns and confirms the resulting state/receipt still match. Version 2 stage-serving bindings carry the exact activation-history digest and compare it with the resident serving session. The transition World-State projection preserves that digest.
- Activation journal projections now call the selected model identity `selected_active_model_identity` and record `model_load_posture=not_loaded_by_activation`; the later serving-stage row retains the separately observed loaded identity. No active selection is presented as proof of loading, serving, or inference.
- The daemon's read-only running-model projection uses the resident controller's non-mutating observation method, including when the optional transition protocol is absent. When the protocol owner is absent, model-development provenance and session time remain unknown.
- Modified modules passed Python AST compilation and the branch was re-fetched at this checkpoint. No runtime or transition execution was performed.
- Remote branch verification: `6f8e4c9e02830e54fcb09767d210c11ea5158811`.

**Next implementation dependency:** ensure this running-model and activation-chain evidence reaches configured World-State and epistemic-development selectors without being promoted to current truth, then review durable A/B transition recovery for stage-semantic validation beyond journal hash-chain integrity.


### New checkpoint — recovered model transition stages are semantically re-bound

- Activation verification now exposes the digest-bound commissioned model identity and stable activation-history digest. A read-only historical-selection verifier proves a journaled activation against the current complete activation chain, exact transaction state, receipt, generation, chain-prefix digest, and retained hardened commissioning receipt.
- Transition activation now prechecks the exact commissioned identity against the protocol's intended predecessor/successor before the activation owner is called, then verifies the resulting state/receipt/identity after publication. Serving checks the currently selected identity and receipt again before loading.
- Transition journal reconstruction now validates completed activation records against the historical activation verifier; validates v2 serving binding digests, exact session identity, activation state/receipt/history references and intended model; and binds resume evidence to the exact preceding serving session. Missing verifier or inconsistent lineage yields a blocked incomplete transition, never a replay.
- Both model serving owners now compare the worker's live active identity with the loaded identity bound at establishment. The read-only observer returns no session on mismatch without unloading; mutating inference/current-session paths remain fail closed.
- Python AST compilation passed for the five modified modules; the branch was fetched back at this checkpoint. No crash/restart, runtime, concurrency, model load, test-suite, Windows, or production verification was performed.
- Remote branch verification: `45f13e15c63348199773cac91e4a6223b3d5e7a7`.

**Next implementation dependency:** review the now-qualified running-model and transition facts through their exact source-kind selectors and persistence/recovery owners. Keep current session evidence undated, preserve configured opt-in, and ensure later cognition receives only the verified model lineage while any historical v1 stage remains explicitly incomplete.


### New checkpoint — stage recovery verifies durable serving custody

- Resident transition serving now verifies the exact canonical serving receipt and privilege witness after establishment, records their receipt identities in the completed stage, and reopens both during recovery. This binds the durable serving owner receipt to the stage’s activation-history/session evidence without implying that the process remains alive after restart.
- The live transition-status observer now uses the non-mutating serving-session API and carries exact activation state, receipt, predecessor, and history-digest references into the daemon projection. Stale model sessions are omitted without causing a status read to unload them.
- World-State now identifies raw stage rows as digest-valid journal entries, records the controller's semantic recovery posture separately, and carries serving receipt identities. Completion of a journal row remains distinct from effect proof or current runtime status.
- The modified serving, transition, and daemon sources passed AST compilation; remote branch verified at `58856ef32438188b04be37091f48c951ae2f5735`. No runtime or crash recovery was exercised.

**Next implementation dependency:** qualify the model-transition `b_epoch_observed` and `post_restoration_observed` stages. Their generic `advance(evidence=...)` input must not become an authenticated observation or a `supports`/`contradicts` epistemic binding unless a real existing observer owner verifies its source.


### New checkpoint — A/B cognition observations are qualified against durable owners

- The transition controller now requires an observation verifier before it publishes either `b_epoch_observed` or `post_restoration_observed`, and repeats that qualification when reconstructing completed journal stages. Missing or invalid owner qualification leaves the transition interrupted/incomplete; a digest-valid journal row alone cannot attest the cognition event.
- The daemon-composed transition operations explicitly receive the already configured resident developmental-cognition owner. The verifier reopens bounded canonical observation custody through that owner, then validates the observation ID/digest, exact tick, active model identity, and the persisted governed inference receipt through the serving installation's read-only receipt path. It binds the receipt's request identity and resident serving admission/session linkage to the exact durable session journaled for B or restored A.
- B-epoch evidence additionally reconciles the exact durable developmental record, writeback receipt, candidate identity and candidate inference receipt. Record correlation, operation, snapshot, model/session, and output-digest links must agree with the B cognition observation. Restored-A evidence must match its exact durable cognition observation/receipt and its retrieved record ID/digest arrays; each retrieved history record is reopened and checked, including the B-epoch record.
- Stage evidence has bounded exact field shapes. The rehearsal now supplies the authenticated observation identities and its real-owner adapter verifies the same receipt/history contracts. It also provides the historical activation and serving verifiers required by controller recovery.
- These observations are evidence of the configured resident owners' recorded cognition and history handoff only. They do not establish independent world truth, physical consequence, learning, quality, or consciousness continuity.
- Modified Python source files passed `py_compile`; bounded source review found no trailing whitespace. No tests, model transition rehearsal, runtime, restart/crash, Windows, external-provider, or production verification was performed. Work remains unverified for production.

**Next implementation dependency:** trace the newly qualified transition-stage identities into the World-State and later-cognition projections. Ensure a completed observation stage is distinguished from a merely digest-valid journal row, and carry the verified B writeback and restored-A retrieval references as historical evidence without promoting them to current truth or authority.


### New checkpoint — semantic stage qualification is projected into World-State

- Transition recovery now returns a bounded list of journal-entry digests that passed the controller's stage-semantic reconstruction. A completed observation stage is included only after the developmental owner reopens the canonical cognition observation, governed invocation receipt, exact serving session, and B writeback or restored-A retrieved history chain.
- The daemon matches those qualified digests to exact journal rows. World-State marks observation stages as `owner_verified_durable_cognition_history_handoff` only when the specific entry digest is present in the controller's verified set. Legacy, incomplete, or blocked rows remain explicitly `unqualified_or_incomplete`; their caller-supplied evidence identities are not copied into the observation payload.
- Qualified B rows preserve exact tick, cognition-observation, developmental-record, and writeback-receipt identities. Qualified restored-A rows preserve the cognition observation/inference receipt and exact retrieved history ID/digest pairs. Existing configured source-kind and epistemic selectors still control whether these historical records are consumed; qualification supplies provenance, not truth, authority, goals, or currentness.
- The verified digest list is bounded to the newest 128 journal entries, matching the daemon's bounded transition projection. Older valid history remains in durable journal custody but is not individually emitted by this bounded World-State view.
- The changed transition-controller and daemon sources passed `py_compile`. No runtime, crash/restart, cognition, World-State builder execution, tests, model activation, or production verification was performed. Work remains unverified for production.

**Next implementation dependency:** inspect the longitudinal self-model and resident epistemic consumers for preservation of the new transition-observation qualifiers. Ensure later cognition can distinguish an authenticated owner handoff from an interpretation of the handoff while retaining existing opt-in and next-tick gates. Then continue into model/software cross-generation continuity and adjacent causal owner gaps.


### New checkpoint — qualified transition lineage stays historical downstream

- Resident epistemic development now recognizes the B-epoch and restored-A cognition handoff rows as historical transition observations. It preserves the journal stage event time while labeling it explicitly as not the underlying cognition/inference event time. A completed owner-qualified handoff binds context only, has unknown freshness, and is excluded from the current-evidence path even when a newly built snapshot calls its source fresh. Unqualified or incomplete transition observations remain contextual and unverified.
- The longitudinal self-model now offers a single compact, source-digest-bound `resident_model_transition.cognition_history_handoff` claim when the exact World-State source row has the owner-qualified posture. The claim carries either B's cognition → developmental record → writeback receipt, or restored-A cognition → inference receipt → retrieved record ID/digest set. It keeps predecessor/successor and protocol identity separate, distinguishes journal stage time from cognition time, and declares historical-only, no truth/effect/authority. Existing predicate allowlists still determine consumption.
- The resident cognition current projection already carries the configured World-State fact payload; its deterministic selection key prioritizes transition and succession evidence among eligible sources. The new self-model claim supplies a grouped lineage view only when explicitly configured for the corresponding predicate.
- Both changed Python files passed `py_compile`. No epistemic runtime, state mutation, self-model reconciliation, cognition, tests, restart/crash, model transition, or production verification was run. Construction remains unverified for production.

**Next implementation dependency:** review software-generation transition and chat restart lineage alongside model activation/serving history. Connect their separate verified predecessor and successor references into one historical transition interpretation only where exact owner evidence supports the relation; keep process overlap, model continuity, and running-generation claims unknown without their respective runtime observers.


### New checkpoint — transition events stay historical in epistemic and self-model paths

- The epistemic adapter now treats all model and software transition journal rows as historical event context. It preserves a valid journal event time but labels it as a transition-stage time; for the B/restored-A observation rows it explicitly says that time is not the cognition/inference event time. These events never gain `current` freshness from a fresh snapshot. Their evidence relation is contextual and dependency remains unknown; only the exact qualified observation rows receive the more specific owner-verified historical reliability posture.
- The longitudinal self-model assigns historical interpretation scope to transition journal dispositions rather than representing a past completed stage as current state. It records the per-stage qualification flag/posture as lineage and only forms a grouped cognition-history claim from an exact owner-qualified source row.
- Resident cognition now prioritizes only semantically verified transition journal rows. Unqualified transition and recovery records fall back behind other exact current identities and causal evidence.
- Three modified Python files passed `py_compile`; no runtime integration or tests were executed. Construction remains unverified for production.

**Next implementation dependency:** inspect and compose the existing software-generation and chat-recovery lineage with model succession. Preserve their distinct event owners and process-generation evidence, and create only source-bound historical context where a real shared binding exists. If no owner can prove a cross-lineage relation, keep the chains separate and identify the missing issuer/binding.


### New construction checkpoint — chat process generation follows the invocation receipt

- The hardened chat child already verifies its own installation-scoped launcher handoff before inference. `ProductionServingInferenceController.generate()` now captures that exact child handoff once in request linkage and rechecks it under both the pre-effect and post-effect guards. A detected process/source-generation change makes the invocation non-completed through the existing receipt path; no maintenance-daemon commit or model identity is substituted for the chat child.
- The read-only production chat resource observer now validates any present invocation software-generation linkage against the exact stored chat-process handoff. Historical receipts with no linkage and the explicit unavailable posture remain unknown; malformed, substituted, or missing stored handoffs degrade the selected source. Successful resource-linked invocation rows carry exact receipt, request, model, allocation, attempt, consumption, installation/provisioning, chat process-instance, handoff, and source-generation identities into World-State.
- Each independently verified completed chat invocation also emits a bounded World-State source record that keeps process and model identities separate. Its compact handoff summary preserves exact handoff and predecessor digests; full canonical handoff custody remains the source for independent recovery verification. It preserves the handoff-bound startup time but sets the World-State event time to unknown because invocation-receipt observed_at is custody metadata outside the receipt digest. Recovery time is kept as retrieval metadata and cannot make the historical call fresh. No effects or authority are claimed.
- Existing resident cognition selection can prioritize this exact resource-governor source kind, and the longitudinal self-model retains the attribution as lineage. This remains subject to the existing explicitly configured source selector and development rules; it does not add a learning rule or authority.
- The model-transition daemon and separately operating chat process remain distinct owners. The captured chat handoff binds only chat invocations; no daemon software identity is used as chat evidence, and no relation between an unrelated resident-model transition and chat process is inferred.
- Construction work is untested and unverified for production. Syntax compilation and source/diff review are the only checks in this pass.

**Next implementation dependency:** inspect the authenticated chat generation predecessor handoff chain and resident model/software succession projection for a common installation-level history owner. Preserve the chat handoff’s explicit direct_predecessorship=not_proven, overlap_status=unknown, and unknown intervening generations; do not join those process handoffs to model transitions without an exact shared transition binding.


### New construction checkpoint — same invocation binds software, model, and resource identities

- The chat invocation projection now carries one compact lineage object that links its exact invocation/request digests and process-generation handoff to the receipt-bound active model and serving-lifetime identities, plus allocation, attempt, and consumption receipt references. The complete installation handoff remains recoverable by its immutable ID/digest; only bounded predecessor references are copied into World-State.
- The grouped claim is selectable through existing resident cognition configuration and retained by the existing longitudinal self-model as historical lineage. The source record does not represent a current running process or model, a consequence outside local inference, user memory, or new authority.
- Changed Python files compiled successfully. Source whitespace review passed. No tests or runtime execution were performed; work remains unverified for production.

**Next implementation dependency:** inspect the chat recovery phase predecessor/successor receipts against these invocation-bound serving identities. Reconstruct the strongest historical relation the existing owners prove, and retain unknown status if a serving lifetime or transition stage cannot be linked to the exact chat process handoff.

### New construction checkpoint — reuse canonical compact chat-generation lineage

- The read-only resource observer now uses the existing conversation-session compact runtime-generation projection after independently verifying the full stored handoff. The resident World-State and durable transcript therefore preserve the same bounded handoff/predecessor identity vocabulary, while the immutable full handoff remains available for source verification.
- This avoids a parallel lineage shape and preserves the explicit unknown direct predecessor/overlap posture from the launcher record.
- The observer module compiled successfully; no runtime or production behavior was exercised.

**Next implementation dependency:** inspect authenticated chat recovery phase receipts and determine whether their interrupted operation identity can be connected to the exact predecessor/successor handoffs already retained in invocation and launcher lineage.

### New checkpoint — persisted chat recovery phases reach historical cognition

- Fresh GitHub branch inspection before edits verified `codex/construct-sentientos` at `8e9f2f2a04e23094fd1ca9ee81a6b270d3370dc5`, tree `201a5ef48d4877526ba75d4e74f635822cc3d14f`.
- The explicitly identified `resident_epistemic_state_mutation.py` recovery-stage issue is already corrected in that source: evidence-binding receipts publish/verify in the `evidence` stage and state-mutation receipts in `state`; Windows recovery accepts only byte-identical existing custody and performs no repair write. No duplicate patch was needed.
- Added a read-only inspector beside the actual local chat-recovery owner. It enumerates bounded installation-scoped attempt/readiness/completion, request, and terminal receipt custody; validates canonical bytes, semantic digests, request/approval binding, phase predecessor digests, historical timestamps, and stored predecessor/successor chat handoffs. It never reauthorizes restart, writes a terminal receipt, resumes the child, or asserts current process liveness.
- Recovery projection now reaches the selected installation resource observer, World-State, the existing runtime-supervisor source selection, epistemic development, and longitudinal self-model as historical transition lineage. Source selectors and proposition/predicate allowlists remain opt-in. Phase decision references are carried as claims, explicitly not re-adjudicated admission; local self-digests are not independent signatures. Historical phase time is distinct from retrieval time, and freshness stays unknown.
- A phase chain without its terminal receipt remains explicitly incomplete. Windows read-only directory-enumeration ambiguity remains unknown rather than being called empty or verified. No model/resource data or user memory is inferred from recovery records.
- The modified sources passed Python AST parsing and had no trailing whitespace at this checkpoint. No runtime, Windows, restart/crash, suite, external provider, model activation, or production verification was performed. Work remains unverified for production.

**Next implementation dependency:** link recovery readiness to the exact successor serving receipt already emitted by the serving owner, then validate that link during recovery projection. Do not infer a live process or model solely from a persisted receipt.


### New checkpoint — recovery readiness binds the successor serving lifetime

- The recovery controller already had a deterministic phase-to-terminal-receipt reconstruction path. Its successful phase result was written only after the immutable phases and startup snapshot had been checked; the observer does not invoke that path. Recovery inspection remains side-effect-free.
- A newly recorded readiness phase now captures the exact serving receipt and session emitted for the replacement serving operation, after the child reports semantic readiness. The phase binds its receipt ID, semantic digest, and session ID alongside the successor process handoff.
- Read-only reconstruction reopens the exact serving receipt from the selected installation, checks canonical bytes/digest, serving admission/loaded posture, installation identity, exact replacement operation, and phase/terminal receipt references. Legacy phases without these fields remain readable but expose a legacy-unbound posture; no receipt is synthesized by the observer.
- When the recovery controller itself reconstructs terminal custody from already durable phases after interruption, its existing idempotent path remains the only publisher. It does not restart the child or replay inference/effects while doing so.
- The exact serving receipt is historical custody plus a readiness-time claim. It does not establish that the serving process is still alive now. No independent cross-process liveness issuer is composed.
- Python AST parsing passed for the modified files. No runtime, crash injection, Windows, or production verification was performed; changes remain untested.

**Next implementation dependency:** determine whether an existing chat supervisor owner can publish a bounded, authenticated current-process observation into the selected installation without exposing its mutable recovery capability to the daemon. If no such issuer exists, preserve currentness as unknown and continue with another owner-level causal gap.


### New checkpoint — compose the chat runtime's bounded point observation

- Source review found the canonical chat runtime already owns both the supervisor and child adapter. The adapter's `current_runtime_handoff()` verifies its live child PID/parent/argv/environment and exact launched-source generation; the maintenance daemon does not own or substitute this identity.
- The selected installation observer previously passed read-only views into stored handoff verification, while that verifier formed mutable-handle-only object paths. The verifier now accepts the existing POSIX and Windows read-only view APIs using fixed relative objects, without exposing writes.
- The canonical runtime now holds one installation-scoped supervisor lock while running, preventing overlapping chat supervisors from racing the current-observation file. At startup and bounded cadence it atomically replaces one selected-installation point-observation image from its direct child check. On a failed check or orderly shutdown it records `not_verified` with the last verified handoff and an explicit reason. A crash leaves the last event time unchanged, so recovery cannot turn it fresh.
- The selected read-only resource observer validates the image digest, installation identity, timestamp, and exact stored handoff. World-State carries it with retrieval time separate from event time; epistemic development keeps it historical/contextual with unknown freshness; later cognition and self-model can preserve it only through existing explicit source/predicate selectors.
- The image is an owner report, not an independent signature or present-time liveness assertion. It records only child process and software-generation identity; it does not tie the maintenance daemon's code generation to the chat child or claim model activation, effect, or quality.
- Python AST parsing passed for nine changed Python sources; trailing-whitespace scan was clean. No runtime, subprocess, concurrency, crash, Windows, behavioral, or production verification was run.

**Next implementation dependency:** inspect runtime observation replay/currentness semantics and exact shutdown/recovery transitions for stale-owner races. Keep the point record historical; if currentness needs an independent issuer or trusted clock that is not present, preserve that unknown state and advance another source-supported integration.


### New checkpoint — startup withdraws stale running claims

- The installation-scoped runtime-owner lock now fences overlapping canonical chat supervisors. A new owner reads the prior point observation before launching a child; if it was previously recorded as running, the new owner atomically replaces it with `not_verified`, tied to the exact stored prior handoff and the new supervisor generation. This says only that the new runtime has not checked that child; it does not claim the old process exited.
- Invalid prior custody is not repaired or overwritten. A process crash leaves its old event timestamp unchanged; the read-only consumer keeps the record historical and epistemic freshness unknown.
- Source review of `chat_service.py` confirms `/readyz` intentionally exposes coarse readiness without serving identity. Current model identity therefore remains unavailable to the parent except through exact serving receipts and completed invocation receipts. The implementation leaves that boundary intact.
- The changed startup module passed Python AST parsing. No runtime, concurrent-owner, orphan-process, restart, or production verification was performed.

**Next implementation dependency:** continue preserving the distinction between a child process observation and a current model-serving observation. No current model identity issuer is exposed by the chat API; retain invocation/serving-receipt lineage and move to another existing owner connection rather than infer it.


### New checkpoint — join runtime observation to exact retained invocations

- The bounded resource World-State projector now groups only retained invocation receipts whose verified chat-process handoff ID, digest, and process-instance ID exactly equal the selected runtime observation. Each linked row carries invocation/request identities, allocation, attempt, consumption and effect-receipt references, plus model identity as observed at that invocation.
- The grouped link is historical lineage. It never asserts that the model is currently loaded, that host-wide resources belong to the process, or that an external effect occurred. Nonmatching or unretained invocations remain unjoined.
- The existing later-cognition selector and longitudinal self-model preserve the grouped IDs/digests as history under their current explicit configuration. Epistemic evidence remains contextual with unknown freshness.
- This joins process observation to actual resource-backed invocation lineage without copying prompts, outputs, or canonical user memory.
- The affected projector and self-model source passed AST parsing; no runtime, inference, recovery, World-State execution, or production behavior was tested.

**Next implementation dependency:** review process-observation record ordering and source-ID retention when the daemon restarts or the chat runtime changes generation. Verify source identity conflicts remain explicit and keep model succession separate when no shared serving receipt proves continuity.


### New checkpoint — projection identities follow monotonic evidence

- Recovery-transition source IDs now bind the strongest currently present phase/terminal digest. An attempt-only record, a later readiness/completion record, and a terminal-receipt record therefore have distinct immutable source identities as custody advances.
- The process-observation projection source ID now binds both its stable observation digest and the exact retained invocation list. Newly retained invocations under the same process handoff create a new lineage fact instead of reusing the old source ID with a changed payload.
- World-State retrieval time remains nonsemantic; identical projection inputs retain the same record digest. This keeps later evidence additions separate from recovery time and avoids false same-ID identity conflicts.
- Python compilation passed for `host_resource_runtime.py`. No World-State execution, replay/recovery exercise, tests, or production verification was performed.

**Next implementation dependency:** re-fetch the branch and compare the actual source files after publication, then review the remaining historical-vs-current serving identity boundary. The existing chat API exposes no current model identity; do not infer it from process readiness.


### New checkpoint — bind process launch to configured serving receipt without a current-model claim

- The canonical chat-process runtime point now carries the exact immutable serving receipt selected by the launched adapter's serving-operation ID, when that receipt is present and unambiguous. The projection binds installation, receipt ID and semantic digest, session ID, operation ID, and the model identity inside the historical load receipt.
- This records configured-operation/load lineage alongside the existing process handoff and source-generation digest. It explicitly does not claim that the receipt proves a currently serving model: `/readyz` remains coarse, and the observer does not infer running model identity from that response, a Git commit, or the maintenance daemon.
- Runtime observation custody moved to schema v2 with exact-field verification; the prior v1 observation schema remains read-compatible. World-State preserves the v2 receipt reference, and longitudinal cognition carries it as historical serving-receipt lineage with current-model claim false.
- Exact serving-receipt recovery is now capped at 256 files and 262,144 bytes per receipt, rejects duplicate JSON keys and noncanonical bytes, and recomputes receipt/session identities before selecting an operation. Over-limit, malformed, missing, or ambiguous custody remains unavailable/invalid rather than guessed.
- The previously identified state-receipt recovery stage issue was checked against current source: evidence-binding receipts publish to `evidence`, state-mutation receipts to `state`; Windows recovery remains read-only and accepts only byte-identical already-published receipts.
- Python compilation passed for the changed Python modules. No runtime, API, subprocess, recovery, Windows, concurrency, World-State execution, or production verification was performed.

**Next implementation dependency:** inspect whether the configured operation ID is preserved in the stored child-launch evidence in a way a later daemon can independently verify, rather than relying on the runtime owner's observation binding. If argv/environment is committed only as a digest, keep the operation-to-process association as an owner claim and pursue another source-supported causal link; do not elevate it to independently observed model continuity.

### New checkpoint — persist the configured serving operation in child launch custody

- New chat-process handoffs use schema v3 and store a bounded exact launch-argument vector alongside its digest. The verifier checks the vector digest and extracts exactly one configured serving-operation ID; the live child still independently checks its own PID, parent, arguments, environment, and source bundle against that handoff before chat configuration.
- The read-only stored-handoff summary now exposes the operation ID only for v3 custody. The runtime observation schema v3 carries that same value and its reader reopens the handoff and requires equality before admitting the configured serving-receipt reference. Parent configuration, handoff, serving receipt, and process/source identity therefore have an exact, recoverable join when produced under the new schema.
- Existing v1/v2 handoffs and runtime-observation v1/v2 records remain readable. Older handoffs have no stored exact argument vector or operation ID, so those histories retain an explicit configured_operation_not_verified posture and do not receive an inferred receipt association.
- The process observation remains historical and owner-produced. It does not prove current model service, independent attestation, inference, effect, or authority. Resource-backed invocation receipts remain the source for model identity at actual invocation.
- Python compilation passed for the updated generation, startup, World-State projection, and longitudinal self-model sources. No subprocess, recovery, schema migration, concurrency, Windows, World-State execution, or production verification was run.

**Next implementation dependency:** inspect model-transition recovery and serving receipt joins for operation-ID reuse or predecessor gaps across process replacement. Keep any handoff continuity distinct from model continuity and carry only observed invocation identity into later cognition.

### New checkpoint — bind interrupted recovery to predecessor and successor serving operations

- Recovery-phase reconstruction now compares a successor handoff's configured operation ID with the replacement operation recorded in the approved recovery intent, and compares any v3 predecessor operation ID with the prior serving operation. Contradictions fail closed.
- Recovered transition rows preserve predecessor and successor operation IDs, exact-versus-legacy binding posture, and the successor receipt's operation-binding strength. A v1/v2 handoff without stored launch arguments stays explicitly unknown; a serving receipt alone no longer upgrades it to process-operation linkage.
- The host World-State projector validates and carries those exact operation links. Longitudinal self-model history retains the operation IDs and binding postures alongside predecessor/successor process and receipt identities, with historical-only/current-truth-false flags unchanged.
- Existing terminal recovery receipts remain readable. Reconstructed rows derive operation linkage from canonical phase and handoff custody; reconstruction does not replay restart, reload, inference, or effects.
- Python compilation passed for recovery, World-State, self-model, startup, and process-generation sources. No recovery replay, child process, transition, Windows, World-State execution, or production behavior was tested.

**Next implementation dependency:** trace actual invocation receipts and transcript lineage across a recovered successor generation. Confirm the exact process handoff and serving operation carried by each invocation, preserve the prior transcript's history linkage, and keep any missing runtime observation explicitly unknown.

### New checkpoint — retain the serving operation in per-turn transcript lineage

- Persistent assistant-turn lineage now retains the serving-operation ID from the verified process handoff alongside its process instance, handoff digest, and exact software-generation digest. The compact prior-generation summary carries the predecessor operation ID and hashes the full predecessor handoff.
- Chat context provenance includes the configured operation ID only as runtime-generation evidence. It does not convert that ID into a model-currentness, model-quality, or authority claim. Invocation receipts remain the evidence for the model actually used by a turn.
- Older transcript entries without the operation field remain readable; absence stays unknown. Stored-vs-recovered lineage checks continue to compare the exact compact projection, so a substituted operation ID breaks continuity instead of being silently accepted.
- Python compilation passed for the conversation-session source. No transcript replay, inference, restart, or production verification was performed.

**Next implementation dependency:** trace persisted assistant-turn linkage against the completed invocation receipt after restart and ensure later chat composition cannot accept a transcript operation ID that is inconsistent with the recovered receipt's process handoff.

### New checkpoint — reject invocation handoffs that name another serving operation

- Production chat configuration now compares the child-verified v3 handoff operation ID with the serving operation passed to the serving owner before establishing the model. New invocations also reject a configured-operation mismatch between the exact handoff and active serving session.
- Restart reconstruction of stored invocation receipts performs the same comparison against the receipt's serving-lifetime binding. Thus transcript and resource evidence for newly produced v3 handoffs cannot join operation A's running source generation to operation B's loaded model session.
- Legacy v1/v2 handoffs without a stored operation ID remain readable, with their model-operation-to-process relation explicitly unavailable. The check does not infer a model identity from current process liveness.
- Python compilation passed for chat-service and serving-inference sources. No model load, inference, transcript replay, process restart, or production verification was run.

**Next implementation dependency:** review the transition controller's crash boundaries between child replacement, successor serving receipt, readiness phase, and snapshot publication. Preserve the current incomplete-phase semantics and close any source-backed gap that could leave an accepted transcript or later cognition with an unbound successor identity.

### New checkpoint — interrupted recovery reserves its serving operation

- Fresh-operation checks now scan the bounded durable recovery-attempt journal before allowing a replacement serving-operation ID. Any prior attempt using that ID blocks reuse even if a crash occurred before a serving receipt was published.
- The scan reopens each matching request and canonical attempt phase, verifies request/intent/phase identities and installation binding, and fails closed on missing or conflicting custody. It caps attempts at 256 entries and total parsed bytes at 16 MiB.
- The active request is excluded only while its own pre-restart freshness check runs; the installation-scoped recovery lock serializes competing requests, and a later attempt sees the earlier durable reservation. A crash before attempt publication has not yet restarted the child and does not reserve an operation.
- This prevents process replacement from replaying an already-attempted operation. It does not retry or complete an interrupted attempt.
- Python compilation passed for recovery custody. No crash injection, lock race, process restart, model load, or production verification was run.

**Next implementation dependency:** inspect the primary serving owner's own crash window between model load and durable serving-receipt publication. Recovery-level attempt reservations protect explicit restart operations; determine whether initial serving operation IDs need the same durable non-replay reservation at the serving owner boundary.

### New checkpoint — publish serving-operation reservations as historical evidence

- The sole serving owner now atomically reserves each admitted serving-operation ID under an installation-scoped lock before entering model loading. A later caller cannot reuse the same operation after a crash even if no successful serving receipt was published. Reusing the current live session under a different requested operation is rejected.
- The bounded immutable marker says only that a model-serving operation was durably reserved before loading. It records operation/activation/model intent digests, the admission reference claim, and reservation time; model-load outcome remains unknown. It has no independent signature, effect authority, inference, resource measurements, or current-model claim.
- The explicit read-only installation observer validates at most 256 markers and supplies them to the existing daemon World-State builder. Their canonical source records keep reservation time separate from retrieval time, mark resource measurements and load outcome unknown, and remain eligible only under existing configured runtime-supervisor selectors. The epistemic adapter classifies them as historical context with source freshness unknown; the longitudinal self-model preserves bounded lineage without treating it as current truth.
- Python compilation passed for the serving owner, read-only observer, daemon composition, World-State projector, epistemic adapter, and longitudinal self-model. No model load, inference, crash, concurrency, Windows, World-State, cognition, or production verification was run.

**Next implementation dependency:** inspect the serving reservation against prior serving receipts and activation lineage on restart; ensure completed receipts consume exactly one reservation and orphaned reservations remain visible without claiming whether loading finished.

### New checkpoint — bind successful serving receipts to durable attempts

- The serving owner now includes the exact reservation ID and digest in each newly published serving-session binding and receipt. It records an owner-observed model-load timestamp only after the expected model identity and activation lineage are rechecked.
- A bounded read-only history reader verifies canonical serving receipts, reconciles operation IDs and operation-intent digests to reservation markers, and returns three truthful states: exact receipt plus reservation, reservation with unknown outcome, and legacy receipt predating reservation custody. A new receipt that names a missing reservation predecessor is rejected; duplicate/conflicting operation receipts are rejected.
- The read-only installation observer supplies reconciled serving history to the existing resource-to-World-State projector. World-State records preserve event time separately from retrieval time and project only compact identity fields. Epistemic development now carries the source event time instead of snapshot time, keeps all of these records historical, and leaves incomplete/legacy states explicit. The longitudinal self-model retains bounded operation, attempt, receipt, activation, and model lineage without treating it as current truth or authority.
- Python compilation passed for the six changed runtime modules. No tests, crash/restart, model load, serving, World-State admission, cognition, Windows, or production verification was run.

**Next implementation dependency:** determine whether the separate chat process's current running software identity has an authenticated process-owned publisher or observer. Continue strengthening only the evidence handoff the existing process owners can support; Git commits, activation state, and the maintenance daemon remain insufficient evidence for that process's running generation.

### New checkpoint — bind invocations to exact serving receipt custody

- The live opaque serving session now carries the exact serving-receipt ID and digest after the canonical receipt is created, alongside the exact operation-attempt ID and digest. The receipt itself remains nonrecursive and immutable.
- New governed inference linkage includes those serving receipt and reservation identities. Restart verification resolves the exact receipt through the bounded history reader and requires the matching reservation, session, operation, and digests before reconstructing a new invocation's serving lineage.
- Canonical transcript turns already persist the full serving identity and its digest, so this addition preserves the receipt/attempt references across context recovery and predecessor verification. The World-State causal projector now retains the same IDs rather than reducing the link to a serving-operation string.
- Historical invocations without these four references remain explicitly historically unbound; partially populated linkage fails closed. No retroactive identity is manufactured.
- Python compilation passed for the serving owner, inference bridge, and World-State resource projector. No tests, model load/inference, recovery, transcript replay, cognition, or production verification was run.

Source review confirms this process handoff and recurring observation path already exist. Its causal interpretation remains conditional on the explicitly configured World-State/epistemic selectors and admission machinery; no selector or admission is created by this continuation.


### Source review — separately operating chat process attribution

- The branch already contains a real explicit publisher path in `sentientos/runtime/local_model_chat_service.py` and `sentientos/runtime/startup.py`: the parent records the spawned child's exact PID/parent PID, argv, environment digest, working directory, interpreter path, source-generation digest, and configured serving operation; the child verifies its own launch handoff before serving; the supervisor checks the Popen child and source again on each observation cycle.
- That source generation is a bounded digest of Python files beneath the selected `sentientos/` and `scripts/` source roots. It is not an identity for every interpreter/dependency binary, and the observation is not independently signed. The existing code reports those limits instead of substituting a Git commit or the maintenance daemon's generation.
- The runtime owner publishes running/not-verified observations and the read-only resource observer projects them. They remain historical at read time; no stronger currentness or independent observation is inferred.



### New checkpoint — preserve exact serving receipt linkage through invocation recovery

- The live serving session exposes its exact receipt ID and digest only after the immutable serving receipt is published, avoiding a self-referential receipt identity. It also carries the already durable attempt ID/digest.
- New invocation receipts bind those identities. Recovery resolves the exact serving receipt in the bounded history projection and verifies the attempt, receipt, operation, and session join. Historical invocation receipts with no such linkage remain readable as historically unbound; partial linkage is rejected.
- Canonical chat turns preserve the complete active serving identity and digest, and the World-State resource lineage record includes the serving receipt and attempt references. This keeps the linkage available to later transcript recovery and configured developmental consumers.
- Python compilation passed for the serving owner, inference bridge, and World-State projector. No test suite, inference, process restart, transcript replay, World-State/epistemic execution, or production verification was run.

**Next implementation dependency:** review the admitted World-State → epistemic-development → developmental-history consumption path for these new exact serving identities, then repair any source-level retention loss without bypassing explicit selectors, mutation authority, or later-tick admission.

### New checkpoint — reject partial serving-attempt references

- Recovery now distinguishes wholly absent pre-reservation linkage from any partially populated serving-attempt reference. Both top-level receipt references and optional receipt-binding references must be complete and match the durable attempt; a receipt that references a missing attempt is rejected.
- This preserves historical compatibility while preventing a digest-only or ID-only fragment from being interpreted as unbound legacy evidence.
- Python compilation passed for the serving owner. No behavioral test, restart, inference, or production verification was run.

**Next implementation dependency:** inspect the exact chat process generation handoff through World-State, configured epistemic source selection, and durable developmental-history reconstruction. Only existing selectors/admission owners may qualify it; source hashes remain narrower than full interpreter/dependency runtime identity.


### New checkpoint — preserve chat-runtime observation time in epistemic evidence

- The World-State adapter now transfers the runtime owner's recorded chat-process observation event time into the epistemic evidence binding. It prefers the canonical projected `event_time`, falling back only to the verified runtime observation's own `observed_at`; missing time remains absent.
- The record remains historical and non-current. World-State retrieval/reconstruction time is not substituted, and this path does not confer truth, authority, liveness, or permission.
- Python compilation passed for the epistemic adapter. No tests, recovery replay, evidence admission, developmental writeback, cognition, or production verification was run.

**Next implementation dependency:** continue the same source-bound review across runtime recovery transitions and downstream durable developmental-history selection for any other event-time or exact-identity loss; configured admission remains the only path to interpretation or state mutation.


### New checkpoint — preserve chat-process recovery phase times

- The epistemic adapter now transfers the source-bound attempt, readiness, and snapshot-advance timestamps from recovered chat-process transition records into historical evidence observation time, selecting only the latest valid recorded phase. Missing phase times remain missing.
- The transition stays historical and non-authorizing; recovery time never completes an interrupted phase or makes it fresh.
- Python compilation passed for the epistemic adapter. No recovery replay, evidence admission, writeback, cognition, or production verification was run.

**Next implementation dependency:** continue source review for developmental-history selection size and lineage loss on these runtime recovery records; retain exact predecessor/successor operation and serving-receipt identities with bounded projections.


### New checkpoint — retain serving lineage in runtime observation history

- The bounded chat-process runtime observation's linked invocation rows now carry serving receipt ID/digest, reservation ID/digest, serving operation ID, and serving-session ID from the authenticated invocation linkage.
- The projector rejects partially populated serving references and marks historical invocations with no such linkage as unbound. The longitudinal self-model copies these exact identities into its historical runtime-generation interpretation.
- Python compilation passed for the World-State projector and longitudinal self-model. No runtime observation, restart, evidence admission, developmental writeback, cognition, or production verification was run.

**Next implementation dependency:** review current transcript/developmental-history recovery boundaries for any remaining source-level loss or ambiguous event ordering in the process-generation chain. Do not convert its bounded source digest into full interpreter/dependency identity or current truth.

### New checkpoint — bound runtime lineage before developmental writeback

- The existing resident developmental-history selector now recognizes the selected runtime-supervisor process observation, recovery transition, and serving-operation history rows. It projects large embedded receipts/handoff bodies into bounded identities while binding each projection to the original World-State fact ID, source-record digest, full source-payload digest, and projected-payload digest.
- Runtime observations retain process/handoff/software-generation identity, exact serving receipt and attempt references, a bounded set of linked invocation/resource IDs, and a digest/count for omitted links. Recovery transitions preserve predecessor/successor handoff IDs/digests and all recorded phase timestamps. Any bounded truncation is explicit; malformed consumption-link shape remains unprojected and therefore cannot silently pass the smaller selection budget.
- Projection recovery checks the projection schema, source class, fact/source identity and projection digest. The existing authorization/admission boundary is unchanged.
- Python compilation passed for the developmental writeback module. No tests, candidate generation, admission, persistence/restart, cognition, or production verification was run.

**Next implementation dependency:** check source-level continuity of these projections through durable candidate recovery and later-tick cognition; ensure projection lineage is revalidated against the original selected World-State snapshot instead of trusting only an admitted projection object.


### New checkpoint — retain invocation event time without upgrading its evidentiary status

- Chat-process invocation World-State rows now carry the source receipt's `observed_at` as event-time metadata, or keep the time unknown. Its posture states explicitly that this timestamp is not part of the invocation receipt's semantic digest.
- The epistemic adapter carries this event time into historical evidence binding while its resource-source freshness remains non-current. It does not use reconstruction time.
- Bounded developmental-history projection now retains this event time, exact serving receipt/attempt and process-generation lineage, and up to eight consumption-receipt digests with a digest/count for any omitted tail. Malformed receipt-digest collections do not get projected.
- Python compilation passed for the World-State projector, epistemic adapter, and developmental writeback owner. No tests, source replay, evidence admission, writeback persistence, cognition, or production verification was run.

**Next implementation dependency:** inspect whether the source-bound projections and timestamps are revalidated from original World-State snapshots when durable developmental records are reconstructed, then continue with any independently fixable identity or ordering defect.


### New checkpoint — use one strict bounded reader for serving replay decisions

- Serving-operation reuse checks now consume the bounded reconciliation reader rather than a weaker second receipt parser. The reader enforces the exact historical receipt shape or exact reservation-linked shape, validates non-effect flags, verifies semantic/filename/session identity, and joins references to the corresponding attempt.
- Historical receipts without reservation fields remain accepted under their legacy field set. New linked receipts require complete typed reservation identity and model-load event time. Partial or unknown fields are rejected.
- Python compilation passed for the serving owner. No tests, replay attempt, model load, or production verification was run.

**Next implementation dependency:** continue bounded source review of persistent developmental-history recovery and configured later-cognition consumption for identity or temporal gaps; no original observation or transition may be reconstructed from retrieval time.


### New checkpoint — distinguish dangling intent-root custody from absence

- Current source review confirms the recovered receipt publication loop already selects `evidence` for `EvidenceBindingMutationReceipt` and `state` for `EpistemicStateMutationReceipt`.
- POSIX recovery now uses `lstat()` before treating an absent intent root as empty, rejecting symlink/non-directory custody and distinguishing a dangling symlink from genuinely absent state. The Windows branch retains its existing bounded read-only custody reader and performs no recovery write.
- Python compilation passed for the mutation controller. No filesystem fixture, crash recovery, or production verification was run.

**Next implementation dependency:** continue review of transactional recovery and predecessor identity checks in the same epistemic mutation path; keep absent, incomplete, corrupt, and conflicting custody distinct.


### New checkpoint — preserve Windows read-only recovery semantics

- POSIX intent-root symlinks and non-directories remain invalid. Both platforms now use read-only `lstat()` to distinguish a genuinely absent directory from dangling-link custody.
- Windows continues to obtain entries only through `read_regular_files`; the change does not add writes, repair, or path-based receipt publication to Windows recovery.
- Python compilation passed for the mutation controller. Windows behavior was source-reviewed but not run.

**Next implementation dependency:** verify current durable-history admission and tick sequencing for the recovered process-lineage projections; continue only where the existing owners expose a concrete repair.


### New checkpoint — reconcile serving lineage before runtime World-State publication

- The chat-process invocation projection now joins each complete serving-receipt/reservation reference against the exact bounded serving-history entry, checking its history digest, receipt ID/digest, attempt ID/digest, operation and session. Partial references or missing/ambiguous/conflicting joins fail closed; invocations from historical schemas with no reservation linkage remain explicitly unbound.
- The canonical World-State builder and causal-introspection read path now both pass the read-only serving history required for this reconciliation.
- The resulting runtime observation and longitudinal interpretation retain the verified join posture alongside exact IDs; developmental writeback carries it in its bounded projection.
- Python compilation passed for the World-State projector, daemon composition, longitudinal self-model, and developmental writeback owner. No tests, live observation, cognition, recovery, or production verification was run.

**Next implementation dependency:** continue cross-owner recovery review for any remaining serving/invocation substitution path; keep identity joins exact before either World-State or durable history publication.


### New checkpoint — reject serving receipt model/activation substitution

- Both World-State projection and stored chat-invocation recovery now compare the invocation's full serving linkage against the matched canonical serving receipt binding: installation, operation/session, activation digest and generation, predecessor, activation receipt, serving admission, authority-map digest, model, artifact, runtime, and loaded-model identity.
- The invocation's direct linkage must also equal its upstream current-serving lifetime mapping. Exact receipt and attempt IDs/digests remain required for linked records; legacy unbound records are not promoted.
- Python compilation passed for the inference bridge and World-State projector. No runtime receipt was reconciled, invocation recovered, or production behavior verified.

**Next implementation dependency:** inspect caller-level recovery paths for legacy invocation and serving records after this stronger join; preserve their explicit unknown posture without allowing incomplete new linkage.


### New checkpoint — bound longitudinal retention for runtime-linked invocations

- Longitudinal self-model history now keeps a bounded subset of linked runtime invocations and consumption receipt digests, plus whole-list digests, totals, and explicit omitted counts/posture. Active model identity is retained by exact digest; serving receipt/attempt, process, software-generation, model, and resource identities remain directly attributable.
- This prevents the previous all-or-nothing value-size check from dropping the entire runtime lineage when retained receipt lists become large. The World-State source record digest still binds the full original list; the history interpretation remains non-authorizing and historical.
- Python compilation passed for the longitudinal self-model. No World-State reconciliation, persistence/restart, cognition, or production verification was run.

**Next implementation dependency:** verify the final remote branch and continue bounded review of source-linked records for any remaining whole-claim drops; preserve explicit omission evidence.


### New checkpoint — bind chat process generation to the serving receipt

- Fresh branch inspection verified remote HEAD `1c50b532e4a20c95fc9e82dcf59ad5da27e12495`, tree `2ae07b730159bfed124c1471e6ee9ba8448997b5`.
- The earlier epistemic recovery publication loop is already stage-specific in current source: evidence-binding receipts publish under `evidence`, state-update receipts under `state`. The requested defect was not present.
- The resource World-State projector now compares the exact persisted request software-generation reference against the process handoff attribution for handoff ID/digest, process instance, source-generation digest, startup timestamp, scope, and configured serving operation. A substituted handoff cannot inherit an unrelated completed invocation.
- Where a linked serving receipt and reservation are present, the projector additionally requires the handoff's configured serving operation to equal the operation in that exact canonical serving receipt. Mismatch rejects the lineage; historical handoffs that predate this operation field remain explicitly unknown instead of being upgraded to a verified serving association.
- The compact developmental writeback retains the new binding posture. Longitudinal self-model now emits a bounded invocation-lineage claim with exact invocation/request, allocation/attempt, process/handoff, model and serving identities, up to four consumption receipt digests, whole-list digest/count/omissions, source record and payload digests, and historical/non-authorizing status. A long receipt list no longer causes the entire invocation lineage claim to be dropped by the 4 KiB self-model claim bound.
- Python compilation passed for `host_resource_runtime.py`, `resident_developmental_writeback.py`, and `longitudinal_self_model.py`. No tests, execution, restart, model serving, cognition, platform, or production verification was performed.

**Next implementation dependency:** continue checking the remaining invocation/runtime attribution joins for any path that still accepts a verified process identity without reconciling it to that invocation's exact serving operation and receipt; then inspect durable later-cognition consumption of the compact invocation claim.

### New checkpoint — carry the process/serving join through runtime-linked history

- Follow-up source review of `chat_service.py` confirmed production turns require `verify_stored_chat_invocation` to reproduce the exact `software_generation_attribution` bound in the persisted invocation request; the transcript layer rejects disagreement before publishing the assistant turn.
- The runtime-observation-to-invocation join now also compares the chat-process handoff's configured serving operation with the invocation request's serving operation. A mismatch is rejected; historical inputs missing either side retain `legacy_handoff_or_invocation_operation_unknown`.
- The linked invocation projection carries that exact-or-unknown posture through the longitudinal self-model and the compact developmental writeback projection, alongside existing receipt, allocation, attempt, process, model and bounded consumption identities.
- Python compilation passed again for the three changed modules. The source review covered the chat turn's stored-invocation verifier handoff; no service execution, receipt recovery, inference, cognition, or production verification was performed.

**Next implementation dependency:** inspect how chat-process runtime observation and invocation source records are selected into configured epistemic development and admitted developmental writeback. Confirm the new operation-binding posture survives those existing selectors without becoming current truth or same-tick cognition; continue with any concrete loss at those handoffs.

### New checkpoint — prevent degraded ledger summaries from supporting epistemic updates

- Selector-path review found that an aggregate `causal_resource_consumption` record can be degraded by lineage findings, incomplete attempts, or bounded-retention omissions, while the epistemic adapter did not classify that subject kind as incomplete resource lineage. A rule explicitly selecting that degraded record could bind its configured `supports` or `contradicts` relation.
- The adapter now treats the aggregate as contextual-only unless its disposition is recorded, lineage posture is verified, the findings collection is present and empty, recovery is complete, and retention is complete. Existing qualified historical resource evidence still flows through the configured rule; freshness remains unknown and no source selector, rule, or admission was activated.
- Empty findings are recognized as either in-memory tuples or decoded lists so a verified positive source does not become falsely degraded because of representation.
- Python compilation passed for `resident_epistemic_development.py`. No tests, actual source admission, epistemic mutation, history writeback, cognition, or production verification was performed.

**Next implementation dependency:** inspect durable candidate selection and later cognition's retained interpretation path for this exact aggregate evidence, especially whether a qualified source's recorded event time and uncertainty survive compacting and restart without promoting it to present truth.

### New checkpoint — keep unbound invocation timestamps out of epistemic event time

- The chat-process invocation record carries `observed_at` from the invocation receipt, but the receipt's semantic digest intentionally excludes that custody metadata. The epistemic adapter previously copied this value into the historical evidence binding's `observation_time`.
- It now retains the labeled timestamp in the source payload while leaving semantic event time unknown unless the source explicitly supplies a semantic-digest-bound event-time posture. Current receipts use `invocation_receipt_observed_at_unbound_metadata`, so none become dated or fresh through this path.
- Python compilation passed for `resident_epistemic_development.py`. No source record was admitted or reconstructed and no temporal behavior was executed.

**Next implementation dependency:** the serving and runtime observation records have digest-bound event times; invocation receipts currently do not. Continue the source review with that limit explicit, and verify the compact historical claim preserves the timestamp's unbound posture while later cognition still receives the exact invocation and software identities.

### New checkpoint — version invocation receipt time without breaking legacy identities

- New local-model invocation receipts now use `sentientos.local_model_invocation_receipt:v2`; their semantic digest binds the owner-recorded `observed_at` as receipt-creation time. This is not asserted to be the exact backend completion instant; measured resource receipt times remain their own separate custody.
- The verifier keeps the old digest field set for receipts with no schema version, preserving historical receipt IDs and signatures. A v2 receipt must carry a timezone-aware `observed_at`, and the timestamp is covered by its digest. Unknown versions and malformed times fail validation.
- Resource World-State marks v2 receipt creation time as digest-bound and old receipt time as unbound. The epistemic adapter preserves only the v2 receipt-creation time as historical observation time; it never marks resource evidence current.
- Python compilation passed for the invocation owner, resource World-State projector, and epistemic adapter. No receipt was created, replayed, admitted, or reconciled; no tests or runtime/production verification were performed.

**Next implementation dependency:** review all post-construction invocation receipt transitions and evidence-sink paths to ensure an immutable receipt's ID/digest never changes after persistence or effect-receipt linkage.

### New checkpoint — keep invocation identity immutable through resource reconciliation failure

- Source review found that when post-backend resource reconciliation failed, the invoker replaced the already-persisted invocation receipt's status in memory. That produced a different receipt ID/digest for the evidence sink/caller while disk retained the original receipt.
- The invoker now propagates the resource-custody error without mutating the canonical inference receipt. Backend execution remains represented by the original receipt; the resource ledger's partial/open attempt remains the truthful failure evidence and is not replayed.
- If a new v2 receipt is found beside a reconciled ledger effect receipt but lacks its final resource-linkage fields, World-State now marks the lineage degraded. Unlinked schema-less historical receipts remain compatible.
- Python compilation passed for the invocation and World-State resource projector. No backend call, failure injection, receipt publication, ledger recovery, or production verification was performed.

**Next implementation dependency:** inspect the downstream caller's handling of the propagated post-effect custody exception to ensure it cannot silently retry or report that inference never occurred; keep the persisted invocation and incomplete resource attempt available as separate evidence.

### New checkpoint — expose post-effect resource-custody failure truthfully to chat callers

- `GovernedLocalModelResourceError` derives from `ValueError`; before this change a post-backend reconciliation failure could be returned by the chat endpoint through its generic 404 path. The invocation owner now raises a dedicated post-effect custody error containing the immutable receipt identity, actual invocation status, and whether persistence was requested, without mutating the receipt.
- The chat endpoint returns a 503 with the exact receipt IDs and `do_not_retry_automatically` posture. It does not claim inference did not happen, and does not add any retry path.
- Python compilation passed for `governed_local_model_invocation.py` and `chat_service.py`. No backend failure, API response, or retry behavior was executed.

**Next implementation dependency:** inspect post-effect persistence and observational-sink exception paths as well; ensure callers receive truthful uncertainty if an invocation has entered the backend but final receipt publication or an optional evidence sink fails.

### New checkpoint — distinguish every post-effect publication failure phase

- Extended the typed post-effect custody result to distinguish invocation receipt publication, resource-ledger reconciliation, resource-linkage construction/publication, and optional evidence-sink failure.
- The chat endpoint reports whether receipt persistence and resource linkage persistence were confirmed separately, includes the exact invocation receipt ID/digest and invocation status, and continues to direct callers not to auto-retry.
- Measurement/clock failures after backend entry are also wrapped as post-effect custody failures; no effect or resource entitlement is restored.
- Python compilation passed for the invocation and chat service modules. No persistence fault, sink fault, HTTP request, inference call, or recovery run was performed.

**Next implementation dependency:** perform the bounded source review of retry/idempotency in the persistent conversation store against these 503 outcomes. Confirm the stored user turn prevents re-entering the same invocation after a post-effect custody error and preserves the pending/incomplete request rather than fabricating an assistant result.

### New checkpoint — confirm transcript retry suppression and strict v1 detection

- Source review confirms the chat service appends a canonical idempotent user-request turn before calling inference. If post-effect custody failure prevents an assistant turn, a retry with that same request ID finds the pending turn and returns `chat_request_interrupted_no_replay`; it does not call inference again.
- The request ID remains optional, so a separately submitted request without it is treated as a new user action. The post-effect 503 warns against automatic retry; the source does not guess that two distinct user messages are duplicates.
- Invocation receipt validation now treats only an omitted `schema_version` as historical v1. An explicit null or unknown version is rejected instead of being routed through legacy digest semantics.
- The stored-invocation verifier and installation observer both call the shared version-aware `validate_receipt`. Python compilation passed for the invocation and chat service modules; no chat turn or retry was executed.

**Next implementation dependency:** inspect the durable resource-ledger receipt publication/recovery contract for the same distinction between a not-yet-published final linkage and a genuinely legacy unlinked invocation; maintain explicit degraded posture across restart.

### New checkpoint — publish resource ledger mutations from candidate state

- Resource-ledger mutation methods previously changed cached allocations, attempts, statuses, or receipt lists before the atomic file replacement. If staging/publication failed, the sole live owner could retain state that the durable observer did not see.
- Mutations now build and validate an isolated candidate, write and atomically replace the ledger file, and only then install the candidate as the in-process state. If replacement completed but directory fsync fails, the candidate remains active: the durable outcome is uncertain, so the live owner does not roll back a possibly published debit/receipt.
- Reservation, begun/restored status, allocation, and consumption-receipt appends use the candidate path. Existing attempt conservation and receipt predecessor checks remain in force.
- Python compilation passed for `governed_local_model_resource_allocation.py`. No filesystem fault injection, restart, allocation, or resource debit was run.

**Next implementation dependency:** verify that the existing restart snapshot treats durable provisional/begun attempts as spent or incomplete, and restored attempts as non-replayed, without recomputing entitlement from only the receipt tail.

## New checkpoint — validate ledger receipt ownership and attempt transitions during recovery

- The previously published read-only ledger verifier authenticated receipt digests and per-attempt predecessor links but did not require each receipt's attempt to exist, match its allocation/principal, or follow a unique allowed transition sequence.
- Recovery validation now indexes canonical allocations and attempts, binds every receipt to the exact allocation and principal digest, and checks each attempt history against its persisted attempt status. Provisional attempts cannot carry receipts; restored attempts require exactly one zero-call not-begun receipt; begun attempts may retain an incomplete boundary, or progress through one backend-entry receipt, one measured outcome, and optional reconciliation in order.
- Duplicate state transitions, orphan/substituted attempts, wrong allocation/principal, invalid debit measurement, or reconciliation substitution reject the snapshot. This is read-only validation; it does not replay a call or restore entitlement. The constructor's existing fail-closed recovery behavior remains in place.
- `py_compile` passed for the edited ledger module. No restart, ledger fixture, allocation, or fault-injection behavior was executed; construction remains unverified for production.

**Next implementation dependency:** inspect the existing resource-ledger read-only snapshot and bounded projection for how validation failure and incomplete begun attempts reach World-State after process restart. Ensure invalid custody is represented as degraded/unavailable rather than dropped as if no resource history existed, and that a valid incomplete attempt remains explicitly incomplete without freshening its historical event time.


## New checkpoint — make attempt status and first receipt one atomic publication

- Backend-entry (`begun` plus its first one-call receipt) and serving-guard rejection (`restored` plus its zero-call receipt) were previously written as two separate atomic ledger images. A crash between those writes could leave a status-only image that the observer rejected entirely.
- Each transition now builds one candidate image containing both status and digest-bound first receipt, validates the complete candidate, and publishes it once. The generic receipt appender also validates from the same locked candidate. A failure before replacement leaves the prior provisional attempt; an uncertain post-replacement fsync keeps the published candidate in memory and on disk without entitlement rollback.
- Recovery continues to accept historical begun-without-receipt and restored-without-receipt images from the old two-write implementation as incomplete custody, rather than rejecting the entire ledger. The existing projection reports those attempts as incomplete/degraded; it never synthesizes receipt evidence. New writes no longer create those split states.
- `py_compile` passed for the edited ledger module. No crash, filesystem, or resource call was executed. Construction remains unverified for production.

**Next implementation dependency:** continue the bounded source review of resource evidence projection and epistemic consumption. Confirm source invalidity, incomplete attempts, and retention omissions stay visible as degraded context, and old ledger event times remain historical after repeated reconstruction. Then inspect the next causal continuity owner exposed by that path.


## New checkpoint — align authoritative ledger size with the bounded observer

- The read-only installation observer already rejects ledger images above 8 MiB, but the single-process writer had no matching read or publication bound. A sufficiently large call history could therefore remain writable by the owner while becoming unavailable to the resident observer.
- The ledger now shares the observer's 8 MiB maximum: authoritative reads consume at most bound+1 bytes, and candidate images above the same limit are rejected before staging or state replacement. The observer imports that shared limit. Rejection preserves the previous durable state and cannot restore spent entitlement; post-effect publication failure is still surfaced by the invocation's custody error.
- Source review also confirmed the World-State record digest omits retrieval timestamps, while the epistemic adapter takes historical consumption event times only from ledger receipts, never the tick's reconstruction time. Incomplete/retained resource records remain contextual and cannot become current evidence.
- `py_compile` passed for the ledger and read-only observer modules. No oversized image, restart, or production behavior was executed.

**Next implementation dependency:** inspect the existing invocation-receipt custody and startup handoff against the same resource-size and retention limits. Ensure a configured observer cannot claim a complete invocation set when the selected installation receipt directory exceeds its explicit enumeration/byte bound, and preserve the omission posture into World-State.


## New checkpoint — reserve bounded ledger capacity before backend entry

- The installation observer's invocation receipt enumeration already fails explicitly after 256 directory entries and bounds each receipt read to 256 KiB; it does not claim a complete set after truncation.
- A resource ledger could still admit an attempt near its 8 MiB limit and then lack room for the post-entry measurement or reconciliation receipt. The authoritative ledger now caps each resource receipt at 16 KiB and reserves three receipt slots for provisional attempts, two after backend-entry receipt publication, and one after the measured outcome. Candidate publication fails before proceeding when aggregate reserved capacity would exceed the ledger bound. Each reservation consumes shared capacity, so concurrent attempts cannot independently promise the same remaining space.
- The reserve is custody space only; it does not change call entitlement, produce measurements, or trigger execution. Historical interrupted ledger images remain readable when structurally valid, while no new backend call may begin without enough room for its terminal lineage.
- `py_compile` passed for the ledger and observer modules. No concurrency, capacity boundary, backend call, restart, or persistence failure was executed.

**Next implementation dependency:** inspect the process-generation handoff and recovered cognition path for the remaining boundary between historical child-reported software identity and an independently observed running chat process. Preserve the explicit unknown state unless a real OS-held process owner can bind the observation; do not substitute the daemon's identity or repository commit.


## New checkpoint — compose supervisor-observed chat process generation

- The chat child adapter already held the exact `Popen` process, checked `poll()`, and could verify the launch argv/environment, child PID/parent PID, executable path, and source-generation bytes. The canonical installation observation writer and resident read-only consumer also existed, but the runtime lifecycle supervisor never invoked that writer.
- `RuntimeSupervisor` now calls an optional adapter observation hook with its own generation during health observation. `LocalModelChatServiceAdapter` uses its held child process and exact supervised handoff to publish `running_observed`; if the child has exited, it publishes `not_verified` against the historical handoff. The existing installation observation reader delivers this row through the resource observer into World-State.
- This is a point observation at the owner-recorded event time. Its digest and installation custody do not independently sign the process, and later reconstruction does not claim the process remains live. The code preserves `independent_signature: false`, no effect authority, and does not infer current serving/model identity from process presence.
- `py_compile` passed for the lifecycle supervisor and chat service adapter. No supervisor, child process, installation writer, or daemon runtime was executed.

**Next implementation dependency:** inspect the lifecycle-to-World-State readback for timestamp posture and duplicate behavior after repeated health observations and daemon restarts. Confirm each new owner observation has a new event identity while replay of one stored observation remains identity-stable and historical; then continue into any directly connected cognition consumer gap.


## Source review — runtime observation readback and replay semantics

- The existing resource observer reads one canonical installation runtime-observation image, validates its semantic digest, and labels it historical (`historically_observed_running` or `historically_not_verified`). The World-State projection uses the observation's own event time and semantic digest in its source identity; replay of the same image is stable, while a new health observation receives a new event identity. The epistemic adapter preserves the event time but treats runtime-observation evidence as contextual, unknown-freshness interpretation.
- The observer's bounded invocation directory rejects entry overflow and per-file byte overflow rather than silently projecting a partial complete set.
- The next source-level recovery gap is the adjacent runtime lifecycle journal: supervisor sequence state and append-only lifecycle receipts are published separately, and recovery currently trusts the state file without reconciling a possibly appended receipt. Inspect and repair sequence/idempotency recovery without replaying service starts or other lifecycle actions.


## New source finding — lifecycle sequence recovery gap

- `RuntimeSupervisor._receipt()` currently increments its in-memory sequence, appends/fsyncs one lifecycle JSONL row, and then atomically persists the sequence snapshot. `_load()` restores only the snapshot's sequence and does not reconcile the durable journal. A crash after journal append but before snapshot replacement can therefore cause the next process to reuse an already durable sequence.
- The lifecycle journal is append-only and not a service-start command queue. Recovery must reconcile identity/sequence only and must not replay starts, restarts, or effects.

**Next implementation dependency:** make lifecycle journal publication and restart sequence recovery idempotent and bounded, preserving legacy receipt rows and fail-closed behavior on malformed/conflicting history.


## New checkpoint — recover lifecycle journal sequence after interrupted snapshot publication

- The lifecycle journal is now scanned on supervisor startup with bounded file/row sizes, exact legacy v1 row shape, canonical serialization, timezone-aware event time, and contiguous sequence validation. The persisted supervisor state remains a cache: restart reconciles to the durable journal's maximum sequence without replaying service lifecycle events.
- If an append was durable but its state snapshot was not, the next process continues after that receipt instead of reusing the sequence. A state snapshot ahead of the journal, generation disagreement at the snapshot's sequence, partial/corrupt rows, or non-registry history without its state anchor fail closed into the existing panic posture. A first-start registry-only journal remains recoverable if interruption preceded its first state image.
- Journal appends now assign sequence only after a complete write+fsync; short/failed writes latch in-process journal failure. The journal itself is capped at 8 MiB and each row at 64 KiB; overflow is explicit and cannot be silently truncated. Existing v1 rows remain readable.
- `py_compile` passed for the lifecycle supervisor. No crash/restart fixture, filesystem fault, service operation, or runtime behavior was executed.

**Next implementation dependency:** inspect the separately persisted supervisor state and lifecycle journal for remaining post-action publication ambiguity (especially start/restart outcome custody). Ensure a receipt-write failure cannot be mislabeled as a failed service start and trigger an automatic duplicate child launch; preserve manual/runtime recovery truthfully without replay.


## New checkpoint — keep start-result custody failure from becoming a false start failure

- `RuntimeSupervisor._start()` previously caught both the adapter's start operation and publication of the following success receipt in one block. If the child started but the receipt/state publication failed, it then appended a `start_failed` transition and could enter a duplicate restart path.
- The start-request transition is still persisted before calling the adapter. The actual start exception is handled separately. Once the adapter reports a successful start, failure to publish its outcome now latches lifecycle uncertainty and returns without rewriting the result as failure, probing into automatic restart, or starting a duplicate child.
- `py_compile` passed for the supervisor module. No service adapter or receipt failure was exercised.

**Next implementation dependency:** close the symmetric shutdown path where a failed stop-request receipt currently prevents the authorized stop, and where a post-stop receipt failure can be misread as a stop failure. Preserve actual stop outcome separately from journal publication certainty, with no duplicate stop/start inference.


## New checkpoint — separate stop and restart effects from their receipts

- Shutdown no longer lets a failed stop-request receipt prevent the adapter's already authorized stop. It attempts graceful stop, then the existing force-stop fallback, records the actual return posture separately, and does not retry a stop merely because terminal receipt publication failed.
- Restart no longer swallows a failed predecessor `force_stop` and unconditionally starts a successor. Force-stop failure now exhausts that service's restart path; successful force-stop must receive a durable completion receipt before `_start(restarting=True)` can launch anything. Receipt uncertainty leaves the service degraded/panic-latched without replay.
- `py_compile` passed for the supervisor module. No child process, failure path, or lifecycle operation was run.

**Next implementation dependency:** verify from source that the new runtime observation writer and lifecycle journal sequence recovery preserve source identities through the daemon's exact restart configuration, then inspect any remaining owner composition gap. Any actual process identity beyond parent-owned `Popen`/launch custody remains externally unverifiable without a stronger OS issuer; preserve that limitation.


## Correction — canonical chat runtime-observation composition was already present

- A later complete read of `sentientos/runtime/startup.py` showed that the canonical owner already calls `LocalModelChatServiceAdapter.current_runtime_handoff()` and publishes the full runtime observation, including the selected configured serving receipt, after startup, on each cadence, when current handoff verification fails, and during shutdown. The resource observer and World-State projection already consume that record.
- The generic `RuntimeSupervisor._observe()` hook and duplicate adapter method added in the preceding checkpoint were redundant and could overwrite a richer serving-bound observation between canonical publications. They have been removed. The runtime observation path remains the pre-existing explicit startup owner path; this pass does not claim a new connection there.
- `py_compile` passed for the cleaned adapter and supervisor files. No runtime or process behavior was executed.

**Next implementation dependency:** continue from the genuine lifecycle receipt and resource-ledger durability changes; inspect any remaining bounded custody or post-effect uncertainty gaps without duplicating the canonical runtime observation owner.


## New checkpoint — align invocation receipt writer with read-only custody bounds

- The installation observer caps invocation receipt custody at 256 regular directory entries and 256 KiB per receipt. The serving receipt sink previously published without either matching writer-side constraint.
- The entry-count and byte limits now come from the invocation owner. Before inference, the serving bridge serializes and bounds the receipt request envelope, then holds a process-local capacity lock while checking the exact installation receipt directory and completing the invocation/receipt publication. It rejects a full or uninspectable directory before model entry, preventing normal writes from pushing the selected source beyond the observer's entry bound. The evidence sink independently rejects any serialized receipt above 256 KiB.
- If an unexpected oversize receipt is discovered after model entry, the existing post-effect custody error reports the phase and no retry is introduced. The reserved request-envelope headroom is intended to make this an exceptional fallback; it is not proof of runtime behavior.
- `py_compile` passed for the invocation owner, serving inference bridge, and read-only observer. No receipt limit, concurrent call, provider, or production behavior was executed.

**Next implementation dependency:** continue source review of the durable chat request/history boundary with the new preflight outcome: ensure capacity refusal creates no pending user turn that later appears as successful cognition, and preserves existing same-request no-replay semantics after genuine post-effect failures.



## New checkpoint — recover restart-budget debits from lifecycle journal

- The durable lifecycle journal can contain a restart schedule receipt whose state snapshot replacement was interrupted. The prior recovery path attempted timestamp-based duplicate detection; equal timestamps from a coarse or injected clock could collapse distinct retry operations and undercount the restart budget.
- Restart recovery now uses the validated journal sequence and snapshot sequence as the publication boundary. It restores every in-window `restart_scheduled` receipt newer than the snapshot exactly once, while rows already covered by the snapshot are not replayed. Equal timestamps remain distinct receipt identities.
- Recovery rejects invalid/non-finite clocks, schedule timestamps, and restart-history values into the supervisor's existing panic/degraded recovery posture. It does not execute stop or restart effects during reconstruction.
- `python -m py_compile` passed for the changed supervisor source. No runtime service behavior or test suite was executed; construction remains unverified for production.

**Next implementation dependency:** continue bounded source review of supervisor restart-state persistence and lifecycle receipt recovery, focusing on validating the durable state snapshot's shape and restart-history values before they influence service retry decisions.


## New checkpoint — bound and validate supervisor state recovery

- Supervisor state snapshots are now read with an 8 MiB cap and must match the canonical serialized form and exact v1 field set. Service-state, health, retry-history, exhausted-service, and latest-reason maps are checked against the registered service set before recovery uses any values.
- Restart-history entries must be finite numeric timestamps and cannot exceed the service's configured retry budget. The atomic state writer applies the same byte cap and rejects non-finite JSON values before replacing the snapshot.
- Invalid or contradictory state continues to use the existing panic recovery posture; lifecycle actions are not replayed. The restart journal remains the source for sequence recovery and only post-snapshot scheduled events restore retry debits.
- `python -m py_compile` passed for the supervisor source. No runtime behavior or production recovery was executed; this construction work is unverified.

**Next implementation dependency:** review the supervised chat process handoff and later resident evidence consumer against actual restart and source-generation semantics; preserve its bounded point-observation claim and explicitly unknown independent runtime identity where no OS issuer exists.


## New checkpoint — validate process-generation boundaries in lifecycle recovery

- Lifecycle receipt recovery already validates bounded canonical rows and contiguous sequence. It now also requires every new supervisor generation after the first recorded generation to begin with exactly one `registry_snapshot` bound to the active registry digest; generation IDs cannot reappear after a later generation. A legacy journal may retain a first generation without an explicit anchor, but later generation changes cannot silently splice into it.
- This is a custody/lineage check only. Recovery does not replay process actions or infer that an old service remains active.
- Rechecked the requested mutation-receipt recovery defect at this source: `EvidenceBindingMutationReceipt` is published under `evidence`, and `EpistemicStateMutationReceipt` under `state`; no correction was needed. The Windows path continues bounded read-only receipt inspection.
- Re-read the actual chat generation path. The runtime adapter checks its exact child `Popen`, launch identity, and measured `sentientos/` plus `scripts/` Python source manifest at an observation event. Installation World-State projection binds matching invocation receipts to that handoff, and resident epistemic adaptation labels the projection historical rather than current liveness. This remains an owner-produced point observation, not independent OS attestation.
- Installation-scoped handoff publication remains explicitly unsupported outside POSIX, and no independent cross-platform process issuer exists in the inspected source. That dependency is left unknown rather than substituting the maintenance daemon's generation or a Git/model identity.
- `python -m py_compile` passed for the supervisor source. No tests, runtime observations, process actions, or production verification were run.

**Next implementation dependency:** determine whether the installation-scoped chat launch/runtime observation can be made truthful on Windows using an existing write-capable owner contract. If not, preserve explicit unsupported/degraded posture and continue the broader downstream causal-history path without claiming cross-platform running-generation proof.


## New checkpoint — verify predecessor provenance before chat inference

- `PersistentConversationService.chat()` previously assembled the prompt and called inference using `predecessor_runtime_lineage` before the variable was initialized and before the prior invocation receipt was verified later in the same call.
- The service now verifies the prior assistant invocation, exact receipt and digest, prior user turn, model identities, output lineage, software-generation attribution, and any retained client-request digest before reconstructing the prompt. Only the verified historical runtime attribution is passed into prompt assembly and bound into the new invocation caller linkage.
- Missing or conflicting prior provenance remains unknown; the transcript may still provide ordinary conversation context but cannot establish a model/software predecessor. Idempotent interrupted requests still exit through the existing no-replay recovery path before inference.
- Source review covered the current continuation record, `AGENTS.md`, the project thesis, persistent-conversation architecture note, chat service, and the invocation verifier. The Windows installation-state owner remains read-only, so no authorized Windows handoff issuer was found.
- `python -m py_compile` passed for `sentientos/chat_service.py`. No tests or inference/runtime behavior were executed. This is unverified construction.

**Next implementation dependency:** trace the newly pre-inference predecessor evidence through invocation receipt validation, transcript recovery, and subsequent-turn verification; identify and close any remaining lineage loss without widening retained user memory or changing model authority.


## New checkpoint — bind idempotent recovery to software-generation custody

- The pre-inference prior-turn verifier checks the source user turn and any recorded client-request digest before making its software-generation attribution available to prompt assembly.
- The interrupted-request recovery path now compares the assistant transcript's stored software-generation attribution with the exact invocation receipt's recovered attribution, accepting the existing compact representation and historical records where the field was absent. A conflicting present attribution cannot be returned as verified idempotent response state.
- This does not replay inference or retention work, and it does not promote the transcript into canonical retained user memory.
- `python -m py_compile` passed for `sentientos/chat_service.py`. No behavioral tests or invocation were run.

**Next implementation dependency:** inspect conversation transcript publication/recovery for atomicity between completed invocation receipts and assistant-turn persistence. Preserve the no-replay contract when the invocation completed but transcript publication was interrupted.


## New checkpoint — retain exact invocation-to-invocation predecessor identity

- A verified predecessor software handoff now travels with the exact prior invocation receipt ID, receipt digest, request ID, and source user-turn ID in the next invocation's caller linkage. The assistant transcript retains the same bounded reference.
- The serving receipt verifier now returns its digest-bound caller linkage. Subsequent-turn verification and idempotent response recovery compare the transcript's predecessor reference against that immutable invocation linkage; historical turns without the new field remain compatible.
- The added references are identifiers/digests only; no prompt text, retained memory, allocation authority, or model-transition authority is added.
- `python -m py_compile` passed for `sentientos/chat_service.py` and `sentientos/local_model_serving_inference.py`. No tests, inference, or restart behavior was executed.

**Next implementation dependency:** review bounded transcript persistence and invocation receipt recovery around the post-inference/pre-assistant-append interruption window. Preserve the existing no-replay behavior where private output is not durably available, and avoid claiming a response was reconstructed when only its digest remains.


## New checkpoint — carry predecessor receipt lineage into World-State

- The exact previous invocation receipt reference added to the new chat invocation is now included in the read-only chat-process software-generation World-State projection.
- The projector checks reference shape and, when the predecessor is present in the bounded invocation receipt set, reconciles receipt ID/digest, request ID, completed inference status, same session, and source user-turn identity. A missing predecessor from the bounded projection is explicitly marked as an unreconciled receipt-bound reference; malformed or contradictory references fail closed.
- The source record's canonical digest covers the new linkage and posture. Resident epistemic adaptation continues to receive this as historical evidence, not current liveness or permission.
- `python -m py_compile` passed for `sentientos/host_resource_runtime.py`. No World-State execution, invocation, or production behavior was run.

**Next implementation dependency:** inspect transcript publication interruption semantics. The invocation receipt intentionally retains output digest rather than response text, so preserve truthful no-replay/incomplete state instead of reconstructing a response from digest-only custody.

## New checkpoint — reconcile direct predecessor receipts across allocation scope

- The installation observer already scans and validates the bounded receipt directory, but its allocation-scoped output discarded completed predecessor receipts from other allocations. The World-State projector consequently could only report the exact predecessor link as outside its bounded projection.
- The observer now retains only direct predecessor receipts referenced by the selected allocation's verified invocation receipts, in a separate bounded field. These records remain corroboration only: they are not merged into allocation-scoped invocation receipts, generation-attribution counts, resource debits, or consumption-event counts.
- The projector accepts that separate verified parent set, rejects duplicate or conflicting identities, and reconciles the referenced receipt digest, request ID, completed local-model effect, session, and source user turn. The exact predecessor reference and its resulting posture remain in the digest-bound World-State payload. Missing direct parents remain explicitly unreconciled, and the daemon reports degraded custody for that case.
- Both resident World-State construction call sites pass the separate parent evidence. No authority, allocation behavior, freshness, or effect path changed.
- `python -m py_compile` passed for the changed observer, projector, and daemon source snapshots. No tests, fixture, inference, runtime, or production behavior was run. Construction remains unverified for production.

**Next implementation dependency:** inspect the chat's durable user-turn and completed-invocation publication boundary. Preserve interrupted requests as incomplete and no-replay; do not reconstruct private response content from a digest.

## New checkpoint — serialize per-session chat inference and transcript publication

- The chat service previously took a session snapshot, appended a user turn, performed inference, and appended an assistant turn without a session-wide request lock. Two concurrent requests to one session could overlap inference and publish assistant turns in an order that did not match the predecessor/context snapshots.
- Existing per-file locks protect each atomic transcript write but not the full read-context/infer/append sequence. Added a separate held-handle process lock for the complete request on an existing session. It is released on normal return, exceptions, or process death; existing per-write locks remain independent, so no nested-lock deadlock is introduced.
- A lock wait timeout is reported as a chat request-state conflict rather than misattributed to inference failure. New sessions are created privately before their first request and need no contention lock.
- This preserves same-session predecessor verification and no-replay recovery while preventing concurrent requests from consuming or claiming a later request's history. It does not make invocation-receipt and transcript publication atomic across their separate owners.
- `python -m py_compile` passed for the session and chat source snapshots. No concurrency fixture or runtime execution was performed; construction remains unverified.

**Next implementation dependency:** make the bundled browser client use the existing request-idempotency contract so transport retries carry the same request identity across a lost response and cannot silently invoke inference again.

## New checkpoint — make browser chat retries carry stable request identity

- The bundled browser client previously omitted the API's existing request ID, so a transport retry could append another user turn and call inference again. Its first request also had no session ID, while the server correctly requires an existing session for idempotent identity.
- Added an explicit empty-session creation endpoint that records only the current conversation model identity. The browser persists that session ID before sending the first request, then supplies a UUID request ID for all chat turns.
- Before sending, the browser stores only the request ID under a session/message-digest key; it does not retain the message text in this idempotency record. A retry of the same text in the same session reuses the request ID. The key is removed only after a successful response; interrupted or transport-uncertain calls therefore cannot silently start a second invocation when retried.
- Session creation can leave an empty orphan if its response is lost, but performs no inference or external effect. This closes the browser's first-request identity gap without changing optional API compatibility.
- `python -m py_compile` passed for the chat and session source snapshots. Browser execution and retry behavior remain untested.

**Next implementation dependency:** improve recovery's evidence classification for a durable user request with no assistant turn. Use the exact session/user-turn binding in the existing verified invocation receipt owner to distinguish “no completed invocation receipt found” from “completed invocation exists but response text is not retained,” while preserving no-replay.

## New checkpoint — classify interrupted chat requests from receipt custody

- A durable user turn with no assistant turn previously had only one recovery posture, even though the installation-scoped invocation receipt may show that inference completed. The output body is intentionally not retained there, so recovery cannot safely reconstruct the response from its digest.
- The production serving inference owner now performs a read-only, bounded scan of the exact installation receipt directory, requiring canonical receipt bytes and the existing receipt verifier. It matches only the exact session, user-turn, and optional client-request digest; duplicate matching receipts, malformed records, and byte/entry overflow fail closed.
- The resource-backed inference adapter exposes this owner operation to the chat service. Idempotent recovery now distinguishes completed inference with non-retained response content, a matching incomplete invocation receipt, no matching verified receipt, and unavailable/contradictory custody. Every case remains no-replay; none imply that no backend entry occurred unless a verified record supports that statement.
- The scan returns identifiers/status/digest only and never attempts to recover or regenerate response text. It does not turn a receipt into an assistant transcript.
- `python -m py_compile` passed for the serving inference, resource adapter, and chat source snapshots. No receipt fixtures, restart simulation, inference, or runtime path was executed.

**Next implementation dependency:** inspect whether the typed chat transcript verifier also checks sequence/predecessor ordering and catches duplicate or orphan assistant linkage after restart; preserve legacy transcript compatibility and explicit incomplete state.

## New checkpoint — validate transcript predecessor links on write and recovery

- Session recovery validated turn payload digests and contiguous sequence numbers but did not validate linked assistant turns against an earlier user turn. Duplicate assistants for one source request, missing predecessors, or future-pointing links could therefore survive reload and influence the chat's context scan.
- Added one relation validator used both during session reconstruction and before writing new turns. Any present assistant source reference must identify an earlier user turn, and at most one assistant can link to that source turn. New assistant appends must include the source user-turn identity.
- Historical assistant rows that predate source-turn linkage remain readable as ordinary transcript context, but cannot qualify as a verified predecessor because the existing chat lineage verifier requires the exact linkage.
- Turn sequence and revision fields now require actual integers, excluding booleans that Python otherwise compares equal to integers.
- `python -m py_compile` passed for the changed session-store source snapshot. No transcript fixtures or restart behavior were exercised.

**Next implementation dependency:** continue tracing transcript identities through context snapshots and historical invocation verification; check whether session creation and reload validate top-level lifecycle timestamps and source identity consistently, without making legacy transcript rows unreadable.

## New checkpoint — validate recovered conversation lifecycle metadata

- The session reader validated each turn's timestamp but accepted malformed or offset-free top-level creation/activity times and unchecked lifecycle metadata. These fields are consulted by session listing and recovery-facing UI even though they do not carry a separate whole-session digest.
- Reload now requires timezone-aware ISO timestamps for both top-level time fields, a nonempty lifecycle-state string, and a string-or-null title. It does not assume timestamps are monotonic, because wall-clock correction can legitimately move time backward.
- Existing generated sessions and turn records retain their schema; the change rejects incomplete or malformed custody without claiming tamper-proof authentication.
- `python -m py_compile` passed for the session-store source snapshot. No session fixtures or restart behavior were run.

**Next implementation dependency:** inspect whether World-State's invocation evidence consumer uses the new direct-parent receipt posture, then continue through adjacent transcript/model-history attribution only where an authenticated owner provides evidence.

## New checkpoint — keep unreconciled chat predecessors contextual in epistemic adaptation

- The World-State projector now includes predecessor receipt references and their reconciliation posture, but the resident epistemic adapter did not distinguish a missing/substituted predecessor from a reconciled reference for `chat_process_software_generation_invocation`.
- The adapter now marks a chat invocation's lineage incomplete whenever a predecessor reference is present without the exact `exact_predecessor_receipt_and_source_turn_reconciled` posture, and when that exact posture conflicts with a missing/non-mapping reference. Existing rules therefore receive it as contextual/unknown-dependency evidence rather than qualified support.
- First invocations with no predecessor reference remain compatible. Exact reconciled parent references remain eligible for configured rules, but the source remains historical and cannot become a current observation.
- `python -m py_compile` passed for the epistemic adapter source snapshot. No configured rule execution or evidence-state mutation was run.

**Next implementation dependency:** trace the World-State source digest and event-time identity for the extended invocation payload through configured epistemic rules and persisted evidence binding; verify that historical re-projection remains identity-stable and does not gain freshness.

## New checkpoint — preserve semantic source identity across re-projection

- Traced the new predecessor field from the invocation receipt through the read-only installation scan, `record_digest`, World-State fact identity, and the configured epistemic adapter. The parent reference is part of the record payload and therefore changes its digest/fact identity; retrieval clocks are excluded. The invocation event time is taken only from a v2 receipt whose digest binds `observed_at`. Resource evidence remains historical with unknown/stale freshness, not current merely because it is reprojected.
- Tightened the adapter's “exact predecessor reconciled” acceptance from a mapping check to the precise four-field reference schema and the receipt/request/turn identity formats. A malformed mapping, inconsistent exact posture, or non-recorded chat invocation remains contextual/incomplete.
- First invocations without a parent link remain compatible. The exact request/receipt evidence remains in the digest-bound World-State payload; persisted evidence binds the resulting fact ID and source digest; no automatic evidence rule or state transition was added.
- `python -m py_compile` passed for the epistemic adapter. No runtime projection, configuration, or epistemic mutation was exercised.

**Next implementation dependency:** continue from the bounded recovery source and inspect the existing model/software succession evidence owners for any same-tick or restart path that treats a candidate, activation receipt, or history record as proof of an observed running successor.

## New checkpoint — expose owner-verified current resident software identity

- Succession review found that World-State emitted only the launch-time software baseline from `MaintenanceResidentRuntimeAdoptionController`. Its existing `current_execution_provenance()` verifier, which rechecks the same process instance, environment, executable/entrypoint, canonical generation, and clean exact repository state, was never composed into the resident snapshot.
- The daemon now emits a separate point observation only when that exact owner verifier succeeds. It has a unique observation source identity and observation timestamp, binds process instance, provenance, running generation, commit/tree, and startup identity, and carries no effect or authority claim. The startup baseline remains a distinct historical event.
- Resident epistemic adaptation accepts this current observation only with its exact subject, disposition, digest formats, owner-currentness posture, event-time posture, and false effect/authority fields. Malformed claims become context-only with unknown time/freshness; historical startup records remain historical.
- This is source-owner evidence, not independent operating-system attestation. No source commit or model artifact by itself is used as proof of a running process.
- `python -m py_compile` passed for the daemon and epistemic adapter. No process, Git probe, World-State runtime, or production observation was executed; this remains unverified construction.

**Next implementation dependency:** trace the qualified current software observation through configured epistemic admission and durable later-tick cognition, and verify that repeated point observations do not accidentally create same-tick consumption or an unbounded active-evidence path.


## New checkpoint — enforce causal tick identity during developmental recovery

- The fresh branch lookup resolved to `96ca1cf4134e3f28ce21c54cb20ca6fc1aade920`, while the new task text named an earlier `2439ae41` checkpoint. The live remote ref remains the authority; the named checkpoint was not assumed to be present.
- The specifically reported `PersistentConversationService.chat()` ordering issue is already corrected at this source revision. `predecessor_runtime_lineage` is initialized before use and populated only after the historical receipt verifier confirms the exact serving/loaded model identities, receipt/request identity, output lineage, software attribution, and predecessor reference. Prompt construction and request linkage follow those checks. No patch was needed there.
- Same-tick cognition receives the current World-State as present observation by design. This remains separate from the durable temporal path: the daemon captures the earlier self-model and epistemic projections before cognition, and runs epistemic development after cognition. Self-model projection excludes same/later tick records; epistemic projection pairs authenticated state with update events and excludes the latest state when its persisted update tick is at or after the cognition cutoff. Same-tick interpretation cannot flow through these durable channels into same-tick cognition.
- A genuine temporal fail-open remained in resident developmental cognition. An invalid or naive incoming tick was silently treated as no prior history by `_prior_projection()`; persisted completed/incomplete rows accepted arbitrary nonempty tick strings, and recovered writeback correlation could supply such a tick. That could suppress prior history while allowing a cycle to appear valid.
- Added one strict timezone-aware tick parser. New ticks are checked before state access and publication; saved completion/interruption rows, recovered history correlations, and recovered observation ticks are checked before they can define ordering. Malformed temporal identity now fails closed instead of silently removing earlier context. Normal daemon ticks are emitted using aware UTC ISO timestamps.
- The edited module passed Python source compilation through the tool environment. No behavioral, restart, or runtime checks were run. Construction remains unverified.

**Next implementation dependency:** inspect the independent tick/correlation producers and downstream history consumers for any accepted tick identity that is not the daemon's aware ISO form, then move to the next causal succession or observed-consequence gap.

## Correction — preserve opaque tick identities while retaining causal order

- Source review of the existing resident cognition contract found that tick_id is an opaque owner identity, not a datetime API. Existing owner-level callers supply identities such as tick-n and tick-n-plus-one, and the longitudinal self-model owner supports opaque ordered tick names. The earlier strict timestamp-only parser would have broken that contract; it was not run or behaviorally tested.
- Replaced that overconstraint. Resident composition now requires a nonempty bounded tick identity, while prior developmental history is selected from the digest-verified durable completed-checkpoint sequence. This sequence records commits that existed before the current cycle; the current tick is rejected if already completed/incomplete and is persisted as in-progress before cognition. Thus same-tick writeback cannot enter the prior projection, without requiring wall-clock-formatted identifiers.
- Removed timestamp parsing from history selection. Stored event/creation times remain provenance and are not rewritten; temporal ordering for this owner path comes from durable checkpoint order. Historical/recovered tick identities are still required to be nonempty strings, and repeated exact identities remain conflicts.
- Construction correction is explicitly untested. The follow-up compilation and source checks are pending; no tests were run.


## New checkpoint — harden session-lock custody before transcript access

- Before this increment the remotely verified branch was a98104c79d06e2c9131cc2e694fe22f72fc64c01 (tree b9e038efa56e55f70d15df7db37b481deb0ffb32).
- The session-ID validation in the transcript path occurred after lock-path construction in the per-session data lock. A malformed session ID could therefore influence a filesystem path before the canonical session validator ran. The lock path also had two implementations: the per-write lock followed a final symlink, while the whole-request lock used O_NOFOLLOW but did not prove a regular, single-link target.
- Centralized both lock acquisitions through one bounded POSIX opener. It validates the session ID before path construction, requires flock and O_NOFOLLOW, opens nonblocking/close-on-exec, requires a regular single-link file owned by the current service user, and narrows its mode to 0600 before acquiring the existing independent lock. Windows remains fail-closed because the established lock owner lacks flock mutation support there.
- Session data, request identity, inference admission, transcript publication, and retention boundaries are unchanged. The edit only protects the synchronization custody for those existing operations.
- Python source compilation and whitespace inspection passed for the changed module. No concurrency, symlink, runtime, or Windows execution was performed.
- The chat-process generation publisher itself requires the existing mutable POSIX InstallationStateHandle; Windows exposes only the read-only installation view and has no equivalent atomic publication owner. That remains an exact unsupported dependency. No mutation capability was added to Windows.
- Construction is unverified. Next inspect recovery of transcript/session files and request reconciliation for identity substitutions that remain independently fixable without retaining response output or widening memory.


## New checkpoint — bind chat source-generation scans to directory handles

- The prior remotely verified head was 3fe972e15e0214981910a446d6da133a3475f0c0 (tree f6ca88e04ec58df8e9c6bc9fa952edcc14910ea5).
- The chat runtime handoff computes a bounded source-generation digest over the sentientos and scripts trees, then uses it as process-generation attribution. Its POSIX source scanner previously enumerated by path and only no-follow-opened the final source file. A concurrent replacement of an interior directory could redirect a bounded read outside the intended source tree while still producing a plausible generation digest.
- POSIX source generation now opens the root and the two declared source roots as held directory descriptors, walks them with follow_symlinks disabled, validates directory entries relative to those held descriptors, and opens each Python member relative to its held parent with O_NOFOLLOW. It retains per-file identity/size checks, aggregate file/directory bounds, deterministic path ordering, and the same digest shape. The existing non-POSIX read-only fallback remains unchanged; it does not establish a Windows publisher.
- This hardens the evidence scope for the existing chat-process generation owner without treating the resulting source digest as proof of loaded code or OS attestation.
- Python compilation and whitespace inspection passed. No concurrent filesystem mutation, process launch, runtime, or platform experiment was performed. Construction remains unverified.
- Next inspect invocation receipt provenance and source-generation summaries for any consumers that overstate an authenticated source snapshot as actual loaded code; preserve the strongest bounded claim while moving to other constructible source gaps.


## New checkpoint — use self-model generation as the later-cognition cutoff

- The previous remotely verified head was 1cdd456d210a9e952cc931bd8e7862268cf524d4 (tree 86e43986ac33883b37a9c809909e3c1c2dfb71bb).
- Bounded source review found that longitudinal self-model reconciliation already validates a monotonic generation/previous-reconciliation chain, yet its cognitive projection ignored that durable order and required all tick IDs to parse as timestamps. Opaque owner tick IDs therefore could not reach later cognition, and a wall-clock reversal could exclude a prior committed generation.
- Cognitive projection now selects the latest committed reconciliation before the exact tick boundary using that verified generation chain. If the requested tick already appears in history, its first matching generation is a mechanical cutoff: only earlier generations are exposed. Otherwise the stored generation chain predates this projection call, which the daemon makes before current reconciliation. Tick IDs are required to be nonempty bounded strings; no timestamp is invented or used as the causal ordering source.
- Reconciliation recovery now validates the stored tick identity shape while preserving opaque IDs. The projection remains a bounded, non-authoritative self-model view and keeps exact source generation, evidence, and reconciliation digests.
- The existing source-level owner fixtures use opaque labels and expect a prior reconciliation to project to the next label; they were inspected but not executed. Python compilation and whitespace inspection passed. No tests or runtime checks were run.
- Next trace this generation-based cutoff against daemon startup/restart ordering and the persistent epistemic-state cutoff, then proceed to any remaining substantive succession or consequence connection.


## New checkpoint — fail closed on incomplete source-generation walks

- The prior remotely verified head was cd5b5f41ec4eec69fcbea097b792730b0d5e0358 (tree e339c78846d2211a17fa74fcdc2b5fbda2a0adf6).
- Follow-up review of the new descriptor-relative POSIX scanner found that os.fwalk, like os.walk, can ignore traversal errors when no onerror callback is supplied. A permission or race error in an interior subtree could therefore omit files and still produce a digest that looked like a complete software generation.
- The POSIX scanner now supplies a fail-closed walk-error callback. Any directory traversal failure prevents generation publication or current-process verification; it cannot yield a partial digest as complete. Existing source-directory, file, byte and symlink checks remain in force. The non-POSIX fallback remains unchanged and is still not a writable Windows issuer.
- Python compilation passed; no filesystem fault injection or runtime source scan was performed. This remains unverified.
- Next check transaction ordering and process-liveness evidence around the runtime observation owner, then proceed to another implementable continuity gap.


## New checkpoint — compose supervisor liveness into chat runtime observation

- The prior remotely verified head was 136465687028303a401dd00ed7f4837feb3c56f3 (tree c308718c31c757e769e469ce0918c9e9521361f3).
- Source tracing found that the installation-scoped runtime-observation writer and read-only World-State consumer existed, but no code called the writer. The supervised chat adapter already owned the child PID, verified its source-bound handoff, and had a readiness probe; the RuntimeSupervisor already owned a distinct generation identity. The missing edge left otherwise configured observers at unknown_missing.
- RuntimeSupervisor now binds its exact generation to adapters that explicitly support that optional owner method. The chat adapter uses its existing child and readiness checks, verifies the exact current handoff/source while running, then calls the existing installation owner publisher. A successful observation is bound to supervisor generation, handoff/process/source identity, and observation time.
- When the child is gone or readiness cannot be established, the adapter publishes only the existing not_verified posture with a bounded reason code; it does not claim that inference or model serving occurred. Stop/force-stop also records not_verified after observed child exit. Missing supervisor generation, missing handoff, or publication failure cannot be reported as a verified runtime observation; health reports runtime_observation_unavailable for the composed owner path.
- The read-only resource observer and World-State composition already consume this current.json owner record as historical owner observation, not independent liveness or current truth. No Windows write path, serving authority, provider call, or effect was added.
- Python compilation and whitespace inspection passed for both changed modules. No process launch, health probe, installation publication, concurrent supervisor, Windows, or production run was executed.
- Next inspect whether the new observation’s lifecycle replaces old running status truthfully across supervisor generations and interruptions, then continue the next causal gap.


## New checkpoint — connect supervised chat readiness to installation runtime custody

- The prior remotely verified head was 07ef4b4807f8d8b0d0f4a333618610a95bf4a755 (tree 8f9d5386512f8b29323ac201b65843a59f030cfb).
- Source tracing found a concrete composition omission: publish_chat_process_runtime_observation existed and the installation observer/World-State consumer already read it, but no caller published it. The supervisor verified child liveness and the chat adapter verified readiness and source-bound handoff, yet this owner evidence stopped at the service health object.
- RuntimeSupervisor now sends its own journaled generation identity to an adapter that implements the explicit binding hook. LocalModelChatServiceAdapter uses the bound generation and its existing installation handle to publish the existing point-observation record only after child process, source handoff, and loopback readiness checks succeed. The runtime owner writer re-verifies historical handoff custody before replacing the observation image.
- Missing process, failed readiness, and orderly observed exit write the existing not_verified posture with bounded reason codes; they do not assert that inference happened or that the child is definitely absent beyond the process check. The read-only downstream observer classifies the point as historical, not current liveness. Publication failure is reflected as unavailable health for the owner-composed runtime path; it does not stop or replay inference.
- The optional hook leaves other service adapters unchanged. It adds no effect authority, Windows write support, provider access, or runtime activation.
- Both changed Python modules compiled and passed whitespace inspection. No child process, readiness endpoint, installation write, supervisor restart, Windows path, or runtime behavior was exercised.
- Next inspect transition behavior when a new supervisor generation starts while the prior chat child may have survived; the old point record remains historical, but predecessor/overlap evidence must come only from an actual owner source. Continue elsewhere if that evidence source is unavailable.


## New checkpoint — read supervisor lifecycle custody through bounded held-file verification

- The prior remotely verified checkpoint was 9c77f8b90bb1de67b099b640963f040a06cecd9f (tree b68362aca5e4295eae05a624151594f63453fe86).
- The lifecycle supervisor already bounds and canonicalizes its state snapshot and journal, but read them through `Path.exists()` and ordinary path opens. A final/interior symlink or concurrent replacement could therefore supply a different bounded file to restart-budget and service-state recovery.
- Recovery now uses the existing `read_explicit_file` custody owner for both the state snapshot and lifecycle journal. It holds and verifies path components and file identity, rejects links/non-regular files and changed-during-read data, and preserves the existing byte bounds and canonical/journal reconciliation. Missing explicit files remain distinguishable from invalid custody. A custody failure flows into the supervisor's existing panic-stopped recovery posture.
- No state schema, lifecycle authority, retry policy, or Windows write capability changed. This connects the supervisor's durable recovery path to the repository's existing safe read contract; concurrent multi-process supervisor ownership still has no shared transaction lock and is not established by this increment.
- Python compilation of the changed supervisor module passed. No tests, fault-injection, filesystem race, Windows execution, process launch, or runtime behavior were exercised. Construction remains unverified.
- Next inspect durable lifecycle transaction serialization and other independently implementable recovery gaps; keep any concurrency claim bounded to source evidence.


## New checkpoint — serialize POSIX supervisor journal and snapshot publication

- The prior remotely verified checkpoint was e13f54ff54a2769965c93357916db1430a39ba3f (tree eff0d9eb0e96dd708fa6dc260f3ab0d00813d400).
- The safe-read increment left supervisor state and lifecycle-journal publication using path-based writes. POSIX construction now holds the configured state directory by descriptor, requires a same-owner non-group/world-writable root, performs bounded no-follow descriptor reads, and verifies regular single-link same-owner file identity and stable metadata.
- State snapshots publish through an exclusive descriptor-relative temporary file and replace within that held directory; the directory is fsynced. Journal append opens the exact child relative to the held directory with no-follow, validates custody, takes the existing POSIX flock mechanism, replays the complete canonical journal, and rejects a stale sequence or superseded supervisor generation. It keeps the journal lock through durable append and snapshot publication, then fsyncs both file and directory. Concurrent stale owners therefore fail closed before service lifecycle publication.
- Non-POSIX/Windows publication behavior is unchanged; no Windows write authority was added. Existing bounded schemas and recovery reconciliation remain unchanged.
- Python compilation of `sentientos/runtime/supervisor.py` passed. No tests, process-concurrency/fault injection, filesystem race, Windows execution, service launch, or runtime behavior was exercised. This remains construction, unverified for production.
- Next trace supervisor generation rejection against interrupted lifecycle recovery and the separately operating chat child; process overlap remains unknown unless an existing independent owner can establish it.


## New checkpoint — create conversation sessions without replacement

- The prior remotely verified checkpoint was a3be65f68cd23151a0acb084460772da1a3ecfcb (tree 857831151860a95ba5ef5031ef2dcf575fd0e428).
- Session creation checked whether a random session path existed, then used the same atomic replace operation used for legitimate updates. The check and replacement were separate, so a collision/race could replace an existing session transcript instead of preserving the prior identity.
- The existing atomic JSON publisher now has an explicit create-only mode for initial session publication. It fsyncs the temporary file, atomically links it to the final name without following links, removes the temporary name, and fsyncs the directory. Existing sessions continue using atomic replacement for their validated updates. The path-existence precheck is removed; an identity collision now fails without replacing prior custody.
- Transcript scope, request identities, explicit retention, and model/invocation admission are unchanged.
- Python compilation of `sentientos/conversation_session.py` passed. No collision injection, concurrent creator, tests, or runtime session operation was executed. Construction remains unverified.
- Next review whether the durable transcript’s retained-memory result is revalidated against its independent retention owner on idempotent response recovery; do not treat transcript metadata alone as proof of memory admission.


## New checkpoint — distinguish recovered memory artifact from admission proof

- The prior remotely verified checkpoint was 63f58efa6b38403d52b1aa40ef6a05cdf8d21554 (tree 7ca1b1f98f5ef511936a403c4c11bbc731832fce).
- Idempotent conversation recovery returned the transcript's stored retention receipt verbatim. The canonical user-memory writer had no read-only verifier, and its gate receipt is not durably stored as an independently recoverable owner record. Transcript metadata therefore could be presented as proof of retained memory and historical admission without checking the artifact.
- The existing retention writer now offers a bounded, exact-ID, explicit-file read that verifies the canonical memory record digest and binds its session, user turn, text digest, operation, admission-digest field and storage root to the retained transcript turn. It performs no write, admission replay, or memory retrieval.
- Recovered chat responses no longer echo stored retention receipts as current proof. They report a verified artifact separately from `admission_status: not_independently_recoverable`; missing/conflicting artifacts remain unverified, and interrupted/failed retention remains non-replayed. Canonical user memory remains separate from resident developmental history.
- Python compilation passed for `sentientos/canonical_memory.py` and `sentientos/chat_service.py`. No tests, memory-store runtime reads, retention operations, collision injection, or behavioral verification were run.
- Remaining exact gap: no durable independent issuer/custody exists for the historical retention-admission decision. Do not infer that a matching memory artifact proves admission occurred. Continue on other causal continuity work without adding memory authority.


## New checkpoint — keep canonical runtime observation single-owner

- The fresh remote source at the start of this correction was `eb816f5b3d54d8b2793318938bcf4f25bba7ee94` (tree `4dbfa7a3a0078ec054903668a324c29c415ee9a8`).
- Source comparison confirmed two publishers targeted the same replaceable installation record, `local-model/chat/runtime-observations/current.json`, through `publish_chat_process_runtime_observation()`. The canonical loop in `sentientos/runtime/startup.py` binds observations to its supervisor generation and validated source handoff, and selects the exact configured serving receipt only when its operation matches the handoff. Its projection preserves the serving receipt ID/digest, model identity, and selection posture. The adapter's health/stop publisher had only the handoff and supervisor generation, so it could overwrite the richer record, including replacing it with `not_verified` after readiness failure.
- Removed runtime-observation publication from `LocalModelChatServiceAdapter`. Its service health now reflects the actual child-process check and loopback readiness probe only; optional observation I/O cannot turn a ready service unhealthy. The canonical startup owner continues publishing point observations and shutdown/recovery posture, while RuntimeSupervisor retains its durable per-service health and lifecycle journal.
- Kept handoff publication/verification intact; it is distinct input custody used by startup. No serving, inference, allocation, or effect authority changed.
- Python compilation passed for the modified adapter. No tests, runtime process, readiness endpoint, installation publication, or production behavior were exercised. This source construction remains untested and unverified for production.

**Next implementation dependency:** continue tracing canonical startup recovery and runtime observation consumers for any remaining lifecycle ambiguity or evidence-status overstatement; do not restore an adapter-side writer to the replaceable observation image.


## New checkpoint — reconcile explicit retention artifacts after interruption

- Freshly verified remote source before this increment: `8427eda351c5967695c6c0b37891777206d07d45` (tree `3acf6f9fe2a849d2853f7ee890f3507f204e34b1`).
- The campaign attachment's predecessor-lineage ordering defect does not reproduce at this source: `predecessor_runtime_lineage` begins absent, and is populated only inside the path that verifies the prior invocation receipt, request identity, serving/loaded model identities, output lineage, runtime attribution and predecessor reference. It is not merely initialized to suppress an exception.
- Windows process-generation publication remains explicitly unsupported: the chat adapter requires the existing mutable POSIX installation handle, while Windows installation access is read-only. No issuer or mutation authority was invented.
- Closed a separate interruption gap in explicit user-memory retention. If the canonical memory artifact was atomically present but the conversation turn still said `requested`, recovery previously returned interrupted without checking that exact artifact. The writer now reads the deterministic operation artifact through the bounded explicit-file reader, verifies its source/session/turn identity and canonical record, recomputes the existing default-deny gate decision from the artifact-bound candidate, and compares the receipt digest. Only an exact match reconciles the conversation receipt; it performs no memory write and reports `policy_recomputed_not_execution_attested`, not proof that the original gate invocation ran. Missing/custody-invalid artifacts remain interrupted; malformed, conflicting, or gate-mismatched evidence is not reconciled.
- Existing retained responses now distinguish artifact verification plus deterministic policy recomputation from unverified admission and from an admission digest conflict. User memory remains canonical product memory, separate from resident developmental history.
- Python compilation and trailing-whitespace checks passed for `canonical_memory.py` and `chat_service.py`. No tests, filesystem fault injection, memory write, runtime request, or production verification was performed. Construction remains untested.

**Next implementation dependency:** inspect and harden the canonical memory artifact write transaction itself. Current writer still uses a path-existence/read/replace sequence and does not durably fsync the containing directory; preserve collision safety, exact root custody, and no-write recovery semantics while correcting it.


## New checkpoint — publish explicit memory artifacts without replacement races

- Fresh remote source before this increment: `441b962c190444b7f0f63b39fcae7c40f6abf06a` (tree `305ba4aab0eb4ea510a9b640077806f4bafa0ce3`).
- The previous memory writer used `Path.exists()`, an unbounded path read for retries, and `os.replace()`; two concurrent requests or a symlink/collision could replace an artifact for the deterministic retention operation. Its file was fsynced, but directory publication was not.
- Retention execution now rechecks the exact default-deny gate result and binds operation/session/turn/request/text identities before writing. POSIX publication opens the configured raw directory by a no-follow held descriptor, requires current-user ownership, narrows the directory to owner-only access, writes a bounded-mode exclusive temporary file, fsyncs it, publishes by create-only hardlink, and fsyncs the directory. Existing artifacts are bounded-read through the held directory, require regular single-link current-user custody and owner-only file permissions, and are reusable only when operation-bound content matches. A different record at the same deterministic identity fails closed.
- No memory write is replayed during recovery; the preceding interruption reconciler can still attest only that the deterministic policy recomputes from the stored candidate, not that its original invocation ran. Windows mutation remains fail-closed because no equivalent existing atomic write owner is available.
- Python compilation and whitespace inspection passed for `canonical_memory.py`. No tests, runtime memory writes, crash injection, concurrency test, or Windows execution was performed.

**Next implementation dependency:** make bounded canonical-memory retrieval use the explicit-file custody reader while preserving legacy raw-fragment compatibility; the current `_records()` path still enumerates and reads with unbounded `glob`/`read_text` operations.


## New checkpoint — bound canonical memory retrieval

- Fresh remote source before this increment: `eb5cc2113066cfca92993f8f669308d8724bf4d6` (tree `1de1da537cc8132d7b7ff9121c46094a4f68551a`).
- Explicit user memory was the retrieval source for later chat context, but `CanonicalMemoryStore._records()` used unbounded `glob()` and `read_text()`; symlinked, oversized, or changing files could enter prompt memory without a bounded custody posture.
- POSIX retrieval now enumerates a held no-follow directory descriptor with entry and record caps, then reads each selected record relative to that descriptor with regular-file, single-link, same-owner, size, and stable-identity checks. Windows uses the existing reparse-safe bounded directory reader. Aggregate bytes and per-record bytes are bounded. Legacy JSON record shapes remain readable; malformed records are omitted with a partial posture, while custody/bound failures return no memory records rather than using a partial untrusted set.
- The retrieval snapshot digest now binds the scan posture. Chat responses expose that posture and retain it in assistant linkage for idempotent recovery. Memory remains explicit canonical user memory, outside resident developmental history.
- Python compilation and whitespace inspection passed for `canonical_memory.py` and `chat_service.py`. No tests, runtime retrieval, Windows execution, filesystem race, or production behavior was exercised.

**Next implementation dependency:** inspect how the shared legacy raw-memory writer publishes fragments into this reader's directory, then either compose it through the same bounded custody contract or keep its records explicitly segregated. Do not claim the broader legacy memory manager is covered by this chat-path hardening.


## Correction — recover the create-only publication crash window

- Fresh remote source before correction: `970427376dee3d9fa59bf90704698db630036466` (tree `15609366636954e35b86e7f6afefb1a1ac405e20`).
- Source review of the new create-only hardlink publisher found a crash window: termination after linking the staged file to its final name but before unlinking the staging name leaves link count two. The prior verifier correctly rejects multi-link artifacts, so recovery would have treated this already-published record as invalid.
- Retention staging names are now deterministic by operation. Recovery accepts the two-link shape only when exactly one bounded-scanned staging name points to the same held-directory inode and contains the exact same canonical record; it then removes only that duplicate name and fsyncs the directory before applying the usual one-link receipt/source/gate checks. A lone staging file is not promoted or replayed; conflicting or unresolvable hardlinks remain unverified.
- Python compilation and whitespace inspection passed for `canonical_memory.py`. No crash, filesystem, hardlink, concurrency, or runtime test was run.

**Next implementation dependency:** finish the legacy raw-memory interop review. `memory_manager.py` still writes shared raw fragments through path-based `write_text` and its forgetting path can mutate/delete files; determine a bounded owner boundary that protects explicitly retained artifacts without silently changing legacy memory authority or conflating that memory with resident developmental history.


## Correction — keep retrieval link-count validation local

- Fresh remote source before correction: `daf6c01ece2bba19fefca74deee02a47cccec7dd` (tree `6b045892def9cd26a9fcd6c707003ad65c6ceebc`).
- Review caught that the hardlink-recovery allowance was accidentally applied to the ordinary retrieval helper, where `max_links` was undefined. Ordinary retrieval now again requires exactly one link. The allowance of one or two links remains limited to the write-artifact recovery reader, which checks the link count stays stable while reading and reconciles the deterministic same-inode temporary entry before normal verification.
- The correction was Python-compiled only. No tests, hardlink exercise, filesystem fault injection, or production verification was performed.

**Next implementation dependency:** continue the bounded shared legacy-memory review below; specifically identify whether legacy fragment writes can mutate canonical retained artifacts and define the narrowest safe compatibility boundary before changing behavior.


## New checkpoint — isolate explicit retention from legacy fragment mutation

- Fresh remote source before this increment: `3b416d9af72e9f0f9d6e61d0c4414f210ed0a85b` (tree `ae04c85a9a85a0458c6d9a5bbd2293f9ddd8c28b`).
- The canonical chat-memory writer stores deterministic `memory-<24 hex>.json` artifacts under the same default `memory/raw` directory used by root-level `memory_manager.py`. Legacy append IDs are 16-hex hashes, but its generic raw scans included every JSON file: the age/count purge could delete explicitly retained records; retrieval/distillation could treat them as legacy fragments; and generic fragment writes could target the reserved namespace if handed such an ID.
- Added an explicit filename namespace boundary. Legacy fragment enumeration, lookup, raw scans, and purge now omit `memory-*.json`; generic legacy writes to that namespace fail closed. Canonical chat retrieval and its existing explicit retention gate remain the only owner path for those records. Legacy 16-hex fragments retain their existing format and admission behavior; resident developmental history remains a separate owner and store.
- Python compilation passed for `memory_manager.py`. No pytest, runtime memory operation, file deletion, filesystem race, or production verification was performed. This remains untested for production.

**Next implementation dependency:** inspect bounded runtime consumers of canonical memory and its optional legacy sidecar compatibility path. Ensure startup diagnostics do not follow or overstate unverified sidecar custody, and keep malformed or inaccessible legacy state distinct from admitted canonical records.


## New checkpoint — make legacy-sidecar posture non-following and explicit

- Fresh remote source before this increment: `54995f49a3c8ac3c55fbcf4fb6400db7011f34e0` (tree `45a0e7dace1d763df3470e22500359cf4369554d`).
- The canonical-memory retrieval API exposed `legacy_sidecar_present` based on `Path.is_file()`, which follows symlinks, and omitted this posture from its snapshot digest. The sidecar is not ingested; it is diagnostic compatibility metadata only.
- The store now uses `lstat` metadata to distinguish missing, inaccessible, non-regular, multi-link, wrong-owner, oversized, and present-but-unverified sidecars without opening or following the path. The legacy boolean remains for compatibility and is true only for the bounded metadata-qualified posture. The returned retrieval snapshot and digest bind the explicit posture, avoiding any claim that a present sidecar was validated or admitted.
- Python compilation passed for `canonical_memory.py`. No sidecar file was opened, runtime retrieval executed, tests run, or production behavior verified.

**Next implementation dependency:** inspect whether conversation/session recovery should carry the sidecar posture into assistant linkage. It is currently a retrieval snapshot attribute but only selected memory identities and the snapshot digest are persisted; determine whether that is sufficient for interruption replay to preserve the same retrieval provenance.


## New checkpoint — persist sidecar posture through chat recovery

- Fresh remote source before this increment: `6e64b7023fc795d4b3ec7516089dd840e2572720` (tree `630335cbc953504edb10b9b4ddbc462b4fa234c2`).
- The canonical-memory snapshot digest now binds sidecar status, but chat assistant linkage and its recovered response only persisted the digest and the general retrieval posture. The digest preserved identity, yet recovery could not report the same qualified status transparently.
- Chat assistant lineage now persists the exact `legacy_sidecar_posture` returned by the memory store. Normal and recovered response context carries it; old transcripts and injected legacy memory adapters remain compatible through an explicit `unknown_legacy` posture. This remains diagnostic metadata only and does not admit sidecar content into prompt memory.
- Python compilation passed for `chat_service.py`. No chat request, restart, test suite, or production verification was performed.

**Next implementation dependency:** inspect the persistent conversation-session writer/recovery contract for canonical linkage publication behavior. Confirm exact atomicity and idempotent update semantics for retained metadata; preserve incomplete states if a crash occurs between assistant-turn publication and its metadata finalization.


## New checkpoint — make retention metadata updates monotonic and idempotent

- Fresh remote source before this increment: `80f474c7d533a84aac5e0c86942af55327acdd1d` (tree `49f3d7e22671d40b5776a83c67c34df9383363d8`).
- The session owner publishes whole-session JSON atomically on POSIX with a same-directory private temp, file fsync, atomic replace/create-only link, and directory fsync. Appending a second assistant for one user turn is already rejected by source-lineage validation. A crash after assistant append but before retention metadata update leaves the user turn in its truthful `requested` state for the existing no-replay artifact reconciler.
- The metadata updater itself previously overwrote any existing retention state/receipt and rewrote the session timestamp even for exact repeats. It now allows only `requested → retained|retention_failed`, requires a user turn and mapping receipt, rejects state/receipt substitution, and treats an exact same-state/same-receipt repeat as a no-op.
- Python compilation passed for `conversation_session.py`. No session write, fault injection, replay, or runtime validation was performed. Windows conversation publication remains unsupported by its existing owner.

**Next implementation dependency:** inspect the exact chat request recovery path around an already-published assistant response. Confirm it verifies the persisted source turn and receipt before returning a response after restart, and that any incomplete request remains no-replay rather than creating a duplicate assistant turn.


## New checkpoint — sample legacy-sidecar status at retrieval time

- Fresh remote source before this increment: `329d1442cedc5820ba162830e7c78c0bf4d20965` (tree `6d67c142bf3ee959548a8d3f8ba9edc60491cd38`).
- The previous sidecar custody posture was captured once when `CanonicalMemoryStore` was constructed and reused on later retrievals. A sidecar created, removed, or replaced after service startup would therefore be reported from stale metadata.
- Sidecar status is now sampled by non-following `lstat` at each retrieval, alongside the retrieval posture. The response and snapshot digest use that same sampled posture; no sidecar content is opened or admitted. The existing status remains explicitly `present_unverified` when only basic metadata qualifies.
- Python compilation passed for `canonical_memory.py`. No runtime sidecar changes or retrieval tests were performed.

**Next implementation dependency:** continue source review of the current chat recovery path and runtime-generation evidence boundary, then advance to the next concrete owner integration without revisiting the already reconciled competing observation publisher.


## New checkpoint — validate persisted retention-state shape on session recovery

- Fresh remote source before this increment: `a366907022b70ad0c94a71c83731c42555e9395a` (tree `0a91463ad59cc737e66e15869cf11b8007e63ec4`).
- The session reader verified turn text and lineage but accepted arbitrary retention-state values and non-mapping receipts. Such records would fall through to an ambiguous recovery posture rather than being identified as malformed custody.
- Session recovery now validates the retained-state vocabulary and receipt shape. Missing state remains compatible with older records as `not_requested`; receipts are disallowed for assistant turns and for user turns still `not_requested` or `requested`. Completed historical states without a receipt remain loadable but are still reported as unverified by chat recovery.
- Python compilation passed for `conversation_session.py`. No session parsing tests or runtime recovery were performed.

**Next implementation dependency:** the current chat recovery path was source-reviewed: production responses require a stored invocation verifier, exactly one assistant per source user turn, model/runtime lineage comparison, and no-replay error postures when the invocation response is missing or incomplete. Continue into the next owner integration; platform-backed or production transition evidence remains unverified.


## New checkpoint — verify stored memory text digests before retrieval

- Fresh remote source before this increment: `0b89702790ff712fd2966558809acc0418a14353` (tree `ff54f4f916d0968a6ae056580d5a2c8effb94479`).
- Bounded canonical-memory retrieval accepted a JSON text record even when its optional `text_digest` contradicted the actual text, then used that stored digest in selected-memory identity. A changed text could therefore be represented by a stale digest in the prompt's provenance snapshot.
- Retrieval now verifies any present text digest against the actual text before admitting the record. Legacy records without a `text_digest` remain compatible and receive the existing content-derived identity. Mismatches are excluded and produce a partial retrieval posture; the snapshot digest continues to bind that posture and selected records.
- Python compilation passed for `canonical_memory.py`. No records were loaded or prompt constructed; tests and production verification were not performed.

**Next implementation dependency:** continue bounded identity review across memory records: ensure duplicate fragment IDs with conflicting content cannot be silently selected as separate context items, while preserving legacy compatibility and not turning retained user memory into developmental history.


## New checkpoint — deduplicate memory identities and reject conflicts

- Fresh remote source before this increment: `f1cbb9fa65d491625588a72363a076f1de2dc490` (tree `15a187192d1799a84b5ef49cb737832a44853968`).
- Bounded retrieval could return multiple records with the same non-empty memory ID. Different text under one ID could then appear twice in one prompt even though the snapshot recorded each digest separately; identity conflict was not surfaced.
- Retrieval now deduplicates repeated IDs with the same content identity and excludes every record for an ID whose texts conflict. The posture reports either duplicate records or a duplicate identity conflict, and that posture remains bound into the snapshot digest. Anonymous historical records remain compatible and are still individually content-digest-bound.
- Python compilation passed for `canonical_memory.py`. No memory files or prompts were read and no runtime/tests were performed.

**Next implementation dependency:** inspect selection and context-budget behavior after identity filtering. Ensure an omitted or malformed record cannot silently make the selected-memory list look complete, and then continue to the next causal owner boundary.


## New checkpoint — bind bounded memory-selection omissions

- Fresh remote source before this increment: `07513a1564f1a88e975de18425712b1407d5a7b4` (tree `28aacd4a29f0f6fc6a0009e095d0b341514fba21`).
- Retrieval can complete its bounded directory scan while still omitting matching items due to the item limit or text budget. Previously the response had a successful scan posture and selected IDs, but did not distinguish a complete scan from a complete selection, nor bind omitted candidate identities.
- The memory snapshot now records separate selection posture/count and binds each omitted ID plus text digest and omission reason into its digest, without storing omitted text in chat linkage. Assistant linkage and normal/recovered response context preserve the same posture/count; older adapters report `unknown_legacy`.
- Python compilation passed for `canonical_memory.py` and `chat_service.py`. No retrieval, prompt assembly, chat, tests, or production validation was performed.

**Next implementation dependency:** inspect the bounded prompt assembler to verify that its consumed memory set matches the canonical store's selected IDs and digest, and that text-budget clipping cannot silently alter retained memory provenance.


## New checkpoint — bound conversation-session listing work

- Fresh remote source before this increment: `c10b8c5f029bcdeb3094c1e842616ba14142d6ea` (tree `3ef08a5691a7f83d47e8454e8a92a5e7b12b8843`).
- `list_recent()` applied an output limit only after globbing and loading every matching session, so an arbitrarily large session directory or aggregate transcript set could consume unbounded scan and parse resources.
- Listing now caps directory entries at 4096, caps aggregate session bytes at 32 MiB before reads, and rejects non-regular, multi-link, or wrong-owner session entries rather than following them. The existing per-session reader still validates each loaded record; malformed sessions remain skipped as before.
- Python compilation passed for `conversation_session.py`. No session directory was scanned and no runtime/test/production verification was performed.

**Next implementation dependency:** continue reviewing session and memory persistence consumers for bounded metadata exposure and exact retrieval provenance; retain fail-closed states when a directory exceeds its source bounds.


## Correction — do not present malformed session listings as complete

- Fresh remote source before this increment: `4679670286680f23f0bf5380232b7272f62052e3` (tree `26bee16a4827f1404aa7a16a0dc7848599c6ef53`).
- After bounding listing work, malformed or custody-invalid matching session files were still silently skipped, which made an incomplete listing indistinguishable from a complete one. A genuine concurrent deletion remains skippable; other load failures now fail the listing with an explicit invalid-record posture.
- Python compilation passed for `conversation_session.py`. No directory listing or runtime session read was performed.

**Next implementation dependency:** inspect consumers of `list_recent()` and determine whether they can surface its explicit degraded error without falsely reporting an empty or complete session list.


## New checkpoint — surface bounded session-list failures as degraded service

- Fresh remote source before this increment: `e64e12de3827684256d26626745cbd740c834eda` (tree `9203141594d5d85f8ddeec566df4f7cb9e38b1f2`).
- The `GET /sessions` route directly returned the store list; new custody/bound errors would become generic server failures, while callers could not distinguish an unavailable/degraded listing from a complete empty list.
- The route now maps bounded/custody list failures to HTTP 503 with a non-sensitive degraded detail. It returns the normal session list only on a completed scan.
- Python compilation passed for `chat_service.py`. No API/runtime request or tests were performed.

**Next implementation dependency:** inspect the related single-session inspection endpoint and runtime-generation evidence shown there. Keep it bounded and ensure read failures remain distinguishable from a genuinely missing session.


## New checkpoint — distinguish missing sessions from invalid custody

- Fresh remote source before this increment: `58527dfce0c42efa3f1b298976bfdedf615ac34d` (tree `367ac8a64c42ca71bfa8bef949a65fc4f3c31e58`).
- The single-session endpoint exposed store exceptions as generic server errors. The owner distinguishes a missing transcript from malformed or inaccessible custody.
- `GET /sessions/{session_id}` now returns 404 for a genuinely absent session and 503 for invalid/unavailable session custody, with generic non-sensitive details. Successful output remains the existing bounded summary fields.
- Python compilation passed for `chat_service.py`. No API call, runtime session read, or tests were performed.

**Next implementation dependency:** continue through adjacent session API composition, checking that historical session summaries are not mistaken for verified runtime/model evidence and that output links preserve the receipt-backed distinction.


## New checkpoint — label session model identity as creation-time only

- Fresh remote source before this increment: `7327a80a5ff084707e4797bc9b3606fb0fc95d46` (tree `091e584d4917973ff69ed48607a68d248dada064`).
- Session list and inspect responses exposed the immutable `model_identity_digest` captured at session creation without stating that scope. Later model replacement could make a historical baseline look like current runtime identity.
- Both summaries now include `model_identity_scope=session_creation_snapshot_only`. The existing digest is preserved for compatibility; it is not represented as current serving or running model evidence.
- Python compilation passed for `conversation_session.py` and `chat_service.py`. No API or runtime session operation was performed.

**Next implementation dependency:** continue into the UI/API consumer of these session summaries and preserve the explicit historical model scope when rendered; do not infer current model status from session creation metadata.


## New checkpoint — carry prior memory provenance into later chat context

- Fresh remote source before this increment: `6f9c1cdb38258d8671ab7ba45a42bc181e5ecdf3` (tree `0902181c34a63f57f6fc0b85531b7a370509c20b`).
- Conversation history carried prior model/runtime lineage into the next prompt but omitted the assistant turn's stored memory snapshot and retrieval/selection posture. A later response could therefore see the prior answer without the bounded memory context identity that accompanied it.
- Prompt assembly now carries those digest-bound memory provenance fields alongside model provenance, including sidecar uncertainty, selection omissions, and legacy-compatible unknown state. It does not inject prior user-memory contents or place user memory into developmental history; all history remains labeled untrusted data.
- Python compilation passed for `conversation_session.py`. No prompt was assembled and no inference/runtime validation occurred.

**Next implementation dependency:** continue source review of the resident epistemic consumer paths. Confirm that conversation-only memory provenance does not cross into World-State or developmental memory without an existing explicit selector and source admission contract.


## New checkpoint — reject dual resource projection owners

- Fresh remote source before this increment: `e36242c8593ea149a0a6b62f7784b8b2c4a00` (tree `acd5e60f42659633b635691c08a6441f92c8b635`).
- `RuntimeMaintenanceSurfaces.build_world_state_board()` projected resource consumption once from the optional direct ledger and again from the richer read-only observation owner when both were configured. The base projection uses one semantic source ID while the observation path also binds installation/provisioning/source identity; the World-State verifier would therefore see conflicting digests for one source identity.
- Constructor composition now rejects simultaneous direct-ledger and resource-observation-owner inputs. The normal daemon configuration supplies the observation owner; the direct ledger remains an alternative compatibility composition. This avoids duplicate projection and ambiguous custody without changing either owner.
- The complete 202,979-byte `sentientosd.py` fetched at this checkpoint was Python-compiled after the edit. No daemon was started, board built, tests run, or production behavior verified.

**Next implementation dependency:** verify the explicit resource-observation owner remains the sole runtime composition path, then continue to adjacent World-State consumers; do not reintroduce the direct mutable ledger as a second observer.


## New checkpoint — sort session activity by absolute time

- Fresh remote source before this increment: `759b4f75ad56c1fe097594ac7307db99195c3508` (tree `206d8cb4ef27d680cfcd51332f946bbcd126a06e`).
- Session loading accepts any timezone-aware ISO timestamp. The bounded `list_recent()` then sorted these timestamp strings lexicographically, which is not chronological when persisted offsets differ.
- Sorting now parses the already-validated timestamps and normalizes them to UTC before ordering; the stored and returned event times are unchanged.
- Python compilation passed for `conversation_session.py`. No timestamps or session listing were executed.

**Next implementation dependency:** continue source review of World-State and resident epistemic composition after confirming the explicit resource-observation owner is the only production route. No direct chat-memory linkage currently enters those owners; retain that separation absent a configured source/admission contract.


## New checkpoint — unify canonical and legacy memory roots

- Fresh remote source before this increment: `d0b04f4f48798f08994a0ad388c4f0103d5cad3b` (tree `0d95a7b27d453b862d0cfa4c7e80e47896ecc5c3`).
- The chat canonical-memory store defaulted to `sentientos_data_dir()/memory`, while root-level `memory_manager.py` separately honored `MEMORY_DIR` and only `SENTIENTOS_DATA_DIR`. When `MEMORY_DIR` or the supported `SENTIENTOS_DATA_ROOT` was used, the two owners could silently read and write different raw-memory stores, defeating the intended shared-directory compatibility boundary.
- Added one canonical memory-directory resolver honoring `MEMORY_DIR` first, then the same data-root fallback as the legacy manager. Production and development chat composition now use it; the legacy manager recognizes `SENTIENTOS_DATA_ROOT` too. The reserved canonical-artifact namespace protections continue to apply wherever the roots coincide.
- Python compilation passed for `canonical_memory.py`, `memory_manager.py`, and `chat_service.py`. No environment configuration or memory files were accessed at runtime.

**Next implementation dependency:** inspect the configured data-root behavior for conversation transcripts and resource custody separately; do not merge installation-scoped evidence or resident developmental history into the user-memory directory.


## New checkpoint — normalize legacy memory roots consistently

- Fresh remote source before this increment: `8f18803dfc7d1f80821848bbdffba71cc567b0d3` (tree `2df18f59c913a3698347a0bf8caaf711e2a7ec91`).
- The shared root selection was aligned, but the legacy manager still left `MEMORY_DIR` relative and did not expand `~` in either override or data-root variables, while the canonical resolver expands and resolves paths. Those valid configurations could still make the two memory owners diverge.
- The legacy manager now expands and resolves both selected roots before deriving `RAW_PATH`, matching the canonical resolver's filesystem path semantics.
- Python compilation passed for `memory_manager.py`. No environment roots or local files were accessed.

**Next implementation dependency:** continue checking path-custody semantics at the shared memory root boundary; preserve explicit user-memory custody without sharing mutable owner assumptions with installation-scoped transcripts or resident development state.


## New checkpoint — enforce private canonical user-memory custody

- Fresh remote source before this increment: `2f1dc79cabeb8311cf109db7a83507da4f148431` (tree `818ba762152f83d3bf299220e5e468d85ea36638`).
- POSIX canonical-memory retrieval accepted group/world-readable raw directories and files. The shared raw-directory opener also changed directory permissions while verifying/recovering retained artifacts, making a nominal read alter custody metadata.
- POSIX retrieval now rejects raw directories and files with any group/world permissions. Read/recovery no longer chmods the directory; permission repair is restricted to the explicit retention write path, which verifies the held owner directory after tightening it to 0700. Existing legacy artifacts with broader file modes remain unavailable to canonical retrieval until their authorized owner rewrites them safely.
- Python compilation passed for `sentientos/canonical_memory.py`. No memory directory was opened or changed; no behavioral tests or production verification were performed. The Windows reader still has no native ACL inspection in this owner and is not represented as permission-verified.
- **Next implementation dependency:** make the legacy `memory_manager.py` raw-fragment writer preserve the same owner-only directory and 0600 file posture, without changing its separate Administrator/Lumos authorization or allowing it to rewrite canonical retained artifacts. Then review its readers against that shared raw-root boundary.



## New checkpoint — align legacy raw-memory writes with private custody

- Fresh remote source before this increment: `877015f421f6d1a11a7cc0ca5702ea4b6a6826db` (tree `574dd2b26af1081e246b4d2ea3074e3d94f60301`).
- The root-level legacy memory manager shared the canonical user-memory raw directory but wrote fragments with ordinary `Path.write_text` permissions and path-following semantics. It could create group/world-readable records that canonical retrieval now correctly rejects.
- The canonical store now exposes its held raw-directory opener as the shared custody owner. Legacy raw-fragment writes preserve the existing Administrator/Lumos authorization, use that descriptor-bound directory, reject path traversal, symlinks, hardlinks and wrong-owner files before truncation, and create or rewrite records with owner-only 0600 permissions. Canonical retained `memory-*.json` artifacts remain excluded from legacy mutation. Legacy raw writes fail closed on platforms without the POSIX custody operations used here.
- Python compilation passed for `canonical_memory.py` and `memory_manager.py`. No memory files were opened, changed, or created; no behavior tests or production verification were performed.
- **Next implementation dependency:** harden legacy raw-fragment enumeration and reads against symlinks and permission-incompatible files, preserving bounded behavior and leaving canonical retained artifacts, installation-scoped transcripts, and resident developmental history separate. Then inspect the other memory-root write paths for any direct raw writes that bypass `_write_fragment`.



## New checkpoint — make legacy raw-memory reads descriptor-safe

- Fresh remote source before this increment: `5cf3c0db3f6e409152217af5d7557658c8dd5b4f` (tree `46ab29705b2ab3314ca4835ff3f3345cdb32a58b`).
- Legacy fragment enumeration used `Path.glob` and its readers followed paths with `read_text`; the canonical chat-memory reader had stronger no-follow checks, but legacy retrieval, search, purge selection, summary generation, and recent-reflection consumers could still traverse a replaced or aliased path.
- The canonical store can now open an existing raw root without creating it. Legacy raw-memory enumeration is bounded by entry, per-record, and aggregate-byte limits and uses a held directory descriptor; reads reopen each selected basename without following links, check owner/type/link count/private mode and size, and verify descriptor stability before parsing. Canonical `memory-*.json` artifacts remain outside legacy reads. Missing custody is no longer created as a side effect of legacy enumeration.
- Python compilation passed for `canonical_memory.py` and `memory_manager.py`. No memory roots were opened or modified; no behavioral tests or production verification were performed. These source paths use POSIX custody. Windows ACL-based access checks remain unavailable here, so Windows permission assurance is still an explicit dependency.
- **Next implementation dependency:** move legacy forget/purge deletion to the same held raw-directory owner, and audit how permission/custody failures surface through memory callers. Then decide whether to implement Windows ACL inspection or keep the canonical memory path explicitly unavailable where ACL privacy cannot be verified.



## New checkpoint — keep legacy forgetting inside raw-root custody

- Fresh remote source before this increment: `c7b9deffca7e29c912de31a78daa46a3e8c6c14a` (tree `ae982d255a1de364c597cf56c39a6b30d296bb98`).
- Legacy age/file-count purge and forgetting used path-based `unlink`; file-count selection also followed `Path.exists()` after the bounded descriptor scan. These deletion paths did not use the new owner-held raw directory.
- Legacy fragment deletion now authorizes first, opens the existing private raw root through the shared custody owner, validates the exact basename as a same-owner, single-link, private regular file without following links, unlinks relative to the held descriptor, and fsyncs the directory. Purge accounting no longer performs a path-following existence check and only counts a deletion that occurred.
- Python compilation passed for `memory_manager.py`. No memory data was accessed or deleted; no behavioral or production verification was performed.
- **Next implementation dependency:** inspect and tighten the canonical-memory Windows read path: its bounded handle reader does not establish private ACL custody. Either add same-handle ACL verification or make the store report an explicit unavailable posture until it can establish that boundary. Then review any surfaced memory-custody failure handling without mixing user memory into transcripts or resident development history.



## New checkpoint — verify private Windows ACL custody on the same handles

- Fresh remote source before this increment: `fbf947d2fb1ee6207bbe7c2f1c9bced20391b8df` (tree `f6596aab641df435de86864dee03101579fc89b5`).
- The Windows bounded reader established reparse-safe handle identity but did not inspect ACL ownership or grants, so canonical user memory could not claim private permission custody on that platform.
- The existing handle reader now optionally verifies owner and DACL from the exact raw-directory and record handles it reads. It requires the current token user as owner, bounds ACL/ACE parsing, accepts data-read grants only for that user, LocalSystem, or local Administrators, and fails closed for broad readers, null/unavailable DACLs, conditional/object ACE forms, or malformed SID bindings. Canonical-memory Windows reads opt into this check; other custody readers retain their prior contract.
- Python compilation passed for `windows_handle_custody.py` and `canonical_memory.py`. Windows API behavior was not executed or tested, and this remains unverified for production. The raw-memory legacy writer remains POSIX-only because the repository has no equivalent safe Windows publisher.
- **Next implementation dependency:** review how explicit-retention/retrieval callers surface custody-unavailable postures, and ensure a permission-degraded memory result is not presented as a complete successful retrieval. Keep transcript and developmental-history owners separate.



## New checkpoint — defer raw-root creation until authorized writes

- Fresh remote source before this increment: `f3f946a37c46a1630777d592bd68bc1ff88e3377` (tree `00cf1b6c7198e05f2b1b64db24ff4959007cc27e`).
- `CanonicalMemoryStore` construction created the shared raw directory even when the caller only intended read-only retrieval or custody inspection. That was an avoidable filesystem mutation during chat composition.
- Store construction is now path-only. The raw directory is created by the held POSIX directory opener only when called with `prepare_for_write=True`; the canonical retention writer reaches that mode after its existing admission gate, and the legacy writer reaches it after its existing Administrator/Lumos authorization. Read and recovery paths do not create the root.
- The chat owner persists `memory_retrieval_posture`, selection posture and omissions in both assistant linkage and the API response; optional retention failure is persisted as `retention_failed`, rather than reported as retained. No change to those consumer contracts was needed.
- Python compilation passed for `canonical_memory.py` and `memory_manager.py`. No store was instantiated and no filesystem state was changed; no runtime, behavior, or production verification was performed.
- **Next implementation dependency:** inspect the remaining legacy memory-root sidecars/indexes/tomb files for their own owner/mode and bounded-read contracts, without widening canonical raw-memory scope or mixing chat transcripts/developmental history. Revisit callers that collapse raw-custody exceptions into empty results and preserve a degraded indication where an existing output contract allows it.



## New checkpoint — secure the shared legacy memory root

- Fresh remote source before this increment: `bb989a1a433b80d2d78644856d49e8c747fb17f9` (tree `1534398385af00e5301f8774f0fd816ce8091d86`).
- Raw-fragment custody was private, but legacy indexes, tombs, observations, goals and other sidecars share the configured `MEMORY_DIR`. Writes could create or use a group/world-accessible top-level root.
- The canonical owner now exposes a no-follow, owner-verified opener for the shared memory root. On authorized POSIX writes it creates/tightens that root to 0700, creates the raw child relative to the held root, and fsyncs the parent when that child is new. Read-side opening never creates or repairs permissions. Legacy writes are constrained to the configured root and secure it after the existing authorization gate; root-backed index, tomb, observation, curiosity and goal readers verify existing root custody before reading.
- Python compilation passed for `canonical_memory.py` and `memory_manager.py`. No memory files/directories were accessed or changed; no behavior or production verification was performed. The root owner/read contract remains POSIX-only; legacy memory-manager access on Windows fails closed.
- **Next implementation dependency:** give legacy sidecar reads explicit bounded, no-follow file custody instead of verifying the root and then using path-based reads. Preserve existing per-record compatibility and surface malformed/oversized custody as degraded or unavailable through existing callers.



## Correction — repair duplicate raw-root fsync branch

- The remote Python compilation check at `19a30ced4074592d7212896a3c1a24ce50825346` found a duplicated `else` branch in the new canonical raw-directory creation path.
- Removed the duplicate branch and recompiled the corrected remote `canonical_memory.py` successfully before publication. No runtime or behavior checks were run.



## New checkpoint — bind legacy sidecar reads to root handles

- Fresh remote source before this increment: `5e35bd3b450865179faf02d2dc62ac122a1f06d4` (tree `2e7ea3010b3ee73112d50a0b294b42f1f4588cd0`).
- Root-level memory indexes, tombs, observations, curiosity records, and goals checked the configured root but then reopened files by path without no-follow, owner, link-count, stability, or size checks.
- These legacy sidecar readers now open one configured-root child relative to the verified held root, reject links/non-regular or wrong-owner files, enforce an 8 MiB read bound, and verify the opened file did not change while read. Missing files remain a distinct empty/missing result; malformed JSON retains each consumer's prior behavior. The owner-root custody check remains read-only.
- Python compilation passed for `memory_manager.py`. No sidecar files were accessed or modified; no runtime or production verification was performed.
- **Next implementation dependency:** make generic legacy sidecar write preparation verify and create nested directories descriptor-relatively, rejecting preexisting symlink/hardlink targets before any path-based writer runs. Preserve the existing authorization gate and fail closed on unsupported Windows mutation.



## New checkpoint — prepare legacy sidecar targets through held directories

- Fresh remote source before this increment: `ffad006830e5010fd3b34cc171622dee077b0d37` (tree `ee2adca844a68aafb9c9db76b5fbc04820af29d3`).
- Generic legacy write preparation secured the shared root but created nested directories and accepted existing targets by path. A preexisting symlink or hardlink in a sidecar path could still redirect a later authorized writer.
- `_prepare_write` now authorizes first, constrains the target beneath the configured memory root, creates/opens every parent relative to held no-follow directory descriptors, verifies owner/type, tightens nested directories to 0700, and rejects non-regular, aliased, or foreign-owned targets before path-based writers proceed. Existing regular target files are changed to 0600 only inside this authorized mutation path. Unsupported Windows mutation remains fail-closed.
- Python compilation passed for `memory_manager.py`. No directories/files were opened or changed; no behavioral or production verification was performed.
- **Next implementation dependency:** inspect the whole legacy memory-manager API for callers that convert custody exceptions into empty/success results, and verify the transcript/developmental-history path separation remains intact under the now-private shared root. Continue with any direct adjacent custody gap found.



## New checkpoint — surface raw-memory custody failures

- Fresh remote source before this increment: `7643d9e12509bf9bb9aea0fb936d2f2b787161a6` (tree `bd098abfe8a46f285477bac7a1accaae96ef76f6`).
- Several legacy raw-fragment callers caught every exception and silently skipped the record. A no-follow, owner, link-count, mode, or size failure could therefore look like an ordinary missing memory.
- The raw-fragment retrieval/search/purge/summary/recent-history callers now re-raise `PermissionError` from custody validation while preserving existing compatibility for malformed JSON and unrelated historical parse errors. Callers that already return a chat response continue to expose canonical-store retrieval posture; legacy APIs without a posture field now fail explicitly on custody denial.
- Python compilation passed for `memory_manager.py`. No memory contents or callers were executed; no runtime or production verification was performed.
- **Next implementation dependency:** verify source-level separation among shared user memory, installation-scoped chat transcripts, and resident developmental history at current HEAD. Then continue with the remaining sidecar write-path race (target replacement between preparation and path-based open) or another directly consequential shared-root boundary.



## New checkpoint — publish legacy sidecars through held targets

- Fresh remote source before this increment: `af503bc9eabd742af81664dd60f39837dc6892b6` (tree `54d842701e20d4c1fad07b4c82ff979243b2180e`).
- Generic sidecar writes still performed a path-based open after a separate preflight check, leaving a target-replacement window. This also left the older preparation helper as a second, easier-to-misuse write path.
- Index, tomb, observation, curiosity, summary, session/turn, and goal sidecar writers now open/create the target relative to held, owner-verified, no-follow directories after the existing mutation authorization. Existing targets are validated before truncation; created/re-written files are 0600; append descriptors use `O_APPEND`. The superseded path-preparation helper was removed. Specialized raw-fragment writes retain their own identity and canonical-retention protections.
- Python compilation passed for `memory_manager.py`. No authorization, memory operation, or file publication was invoked; no behavioral or production verification was performed.
- **Next implementation dependency:** review the existing memory-manager callers and chat/World-State wiring for truthful unavailable states and confirm that user-memory artifacts remain outside installation transcript and resident developmental-history custody. Then proceed to any direct adjacent owner gap surfaced by that review.

