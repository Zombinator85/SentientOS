# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

GitHub branch inspection most recently verified `1206aa182e7e59ee5d01224196432df68191303c` (tree `8a993201935bb24228635589fc86d898957e329c`, parent `6dfdbfb91cd3690e09c604cc24405616098a4427`). Local Git `HEAD` is historical and is not the remote branch identity. Continue with GitHub Git-data commits plus compare-and-swap ref publication.

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
- Python compilation and whitespace checks only; no behavior tests or production verification. Next inspect whether the authenticated activation receipt chain can establish exact predecessor identity for chat continuation. If it cannot, retain the current unverified transition posture and pursue another existing causal path.
- Session reconstruction now also checks the stored session model-identity digest, turn sequence/IDs, exact text byte/character counts and digest, timezone-aware timestamps, and any persisted active/loaded identity digests. Legacy per-turn records without the newer identity payload remain readable; their predecessor relation stays unverified.
