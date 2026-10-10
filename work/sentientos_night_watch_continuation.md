# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

Before compacting longitudinal runtime invocation history, GitHub branch inspection verified `febd1d686110aa1c8d8b9c6bc6cf8a15dd7387cc` (tree `20b628c099e9f4fa3ec9c2ee8ce171b1c70a3eac`). Each source commit is published through GitHub Git-data compare-and-swap and verified separately. Local Git `HEAD` is not authoritative. Continue from the current remote branch and exact compare-and-swap ref updates.

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