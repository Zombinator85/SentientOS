# Bounded resident epistemic development

`ResidentEpistemicDevelopmentRuntime` composes, but does not replace, persistent
epistemic custody. Its versioned operator configuration names an existing
proposition and digest, allowed namespace, bounded equality selectors over typed
World-State fields, an explicit evidence relation, dependency and reliability
postures, and a frozen qualitative rule revision.

For each maintenance tick, cognition first captures and consumes its prior-only
projection. Only after that slot closes may the runtime validate the same tick's
`WorldStateSnapshot`, construct an exact source proof and evidence binding,
request a narrow evidence-stage admission, and append the binding. It then
reconstructs complete bounded evidence membership, creates a deterministic-rule
candidate, requests a different state-stage admission, and attempts one CAS
advancement per proposition. The result is `next_tick_only`; same-tick cognition
cannot recapture it. Disabled cognition does not prevent this non-model cycle.

The adapter `sentientos.world_state_epistemic_evidence_adapter:v1` binds snapshot
ID/digest, fact ID, source ID/kind, observation time, rule ID, and proposition
ID/digest. Relations are configured, never inferred from prose. Unknown dependency
is conservative; independence requires an explicit basis. The frozen qualitative
rule maps support-only and contradiction-only evidence to provisional stances,
mixed evidence to contested, and wholly stale evidence to suspended. Position is
not truth, candidate is not authority, and mutation is not permission.

For explicitly selected developmental-history runs, the daemon routes the exact
run ID and digest represented in its validated same-tick World-State snapshot
through `process_verified_task_family_run`. The run owner rechecks the complete
scored protocol and derives the relation from its frozen comparison; generic
World-State adaptation does not duplicate that evidence. Run events later than
the daemon tick are ineligible. The resulting owner state remains next-tick-only
and is available to canonical plan-only allocation after reconstruction. Missing
or mismatched selected run evidence, including evidence whose event time is later
than the daemon tick, remains explicitly unresolved and does not create an
epistemic position.

The development companion can opt into this same owner without introducing a
second epistemic store. Its launcher composes the runtime only when both
`SENTIENTOS_EPISTEMIC_STATE_CONFIG` and
`SENTIENTOS_EPISTEMIC_DEVELOPMENT_CONFIG` are explicitly supplied. After an
operator-confirmed developmental cycle has run resident cognition and its
developmental writeback, the bridge submits that exact cycle snapshot to the
configured epistemic runtime. The later cognition projection reads the same
persistent state owner, so the update is eligible only in a subsequent cycle.
The cycle response reports epistemic status and evidence/state receipt identifiers
separately from developmental-history and self-model receipts. If this optional
owner fails, the already completed cognitive writeback remains intact and the
epistemic result is reported as degraded.

Without the development configuration, the companion performs no epistemic
mutation and reports `not_configured`. A configured but disabled runtime reports
`disabled`. These paths do not enable unattended desktop capture: the existing
per-message screen opt-in and owner admission rules remain in effect.

The runtime has no model invoker, proposition registration, calibration mutation,
background thread, or cadence. Immutable custody and admission ledgers provide
restart truth: exact existing bindings are not re-appended and an incomplete state
stage requires a fresh admission against the current predecessor.

## Counterfactual use in later allocation

`tests/test_resident_developmental_cognition.py::test_final_score_checkpoints_recover_run_after_precommit_interruption`
exercises a bounded synthetic longitudinal path. A task-family history
intervention first supports a scoped proposition; a later contradictory
intervention is admitted through the epistemic mutation runtime. After owner
reconstruction, canonical planning receives the contested projection. Without
that projection it selects the history-sensitive goal; with the projection it
defers that goal for epistemic review while still selecting an independent goal.
The fixture also checks that a different active model identity leaves
applicability unresolved.

This demonstrates a persistent evidence change in a later software allocation
decision under a deterministic fake-model fixture. Planning is verified not to
invoke a model, acquire a serving session, or execute a goal. The result does not
establish real-model learning, external truth, improved task performance, or
execution authority.

Same-model, same-task-family history now also carries a compact controlled
effect summary when all three score-bound conditions are comparable. It records
whether history-present correctness was adverse, favorable, or unchanged against
the withheld condition, whether restoration reproduced the history-present
score, and the score and invocation receipt identities behind that comparison.
Incomplete comparisons remain `comparison_unavailable` without a directional
claim. These summaries are prompt-bound historical evidence for the exact task
suite only; they do not establish learning or generalization.

This composition is not production sensor evidence, beneficial learning,
objective truth, or improved intelligence.

## Query-relevant experience in resident interactions

The resident companion interaction ranks already admitted developmental
interpretations, source-verified operator-report text, and admitted lesson
content against the current question before the bounded history projection.
Lesson scope and applicability matches receive more weight than generic
interpretation wording; unmatched slots are filled from the recent checkpoint
sequence. The selected record identities and retrieval policy
(`query_overlap_with_lesson_scope_then_recency_fill:v5`) remain in normal
history selection lineage. History packets remain explicitly historical,
non-authoritative, and not current truth. This remains deterministic lexical
matching that normalizes common plural endings and weights terms that occur in
fewer candidate records. It is not semantic retrieval or evidence that selected
experience improves an answer.

Compact resident history packets now carry the bounded lesson statement,
scope, applicability, and uncertainty rationale into the prompt. The companion
instruction treats these as provisional historical limits on transfer and
requires the model to withhold reuse when current evidence or circumstances do
not match. Compact packets omit nested dependency and contradiction ID lists
but retain their counts and digests, including whether possible conflicts were
recorded. The prompt treats that conflict count as a caution signal rather
than current evidence, and the outer record and candidate digests retain their
custody binding. The focused
fixture
`tests/test_resident_developmental_cognition.py::test_compact_history_prompt_retains_lesson_scope_and_uncertainty`
verifies those fields survive the production compact binder with historical,
non-authority posture. This makes applicability information available for
reasoning, but does not prove a real model will honor it.

The shared cognition instruction now makes evidence precedence explicit for
all prior substrates: current World-State evidence takes precedence over
conflicting self-model claims, epistemic positions, and developmental-history
interpretations for present-condition claims. Conflicts should be surfaced as
uncertainty; earlier claims are not evidence of current state. The focused
`tests/test_resident_developmental_cognition.py::test_context_assembly_states_current_evidence_precedence_over_all_prior_context`
checks that this rule survives production context assembly. This strengthens
the prompt contract; real-model adherence remains unverified.

The persistent epistemic owner also accepts the current companion question when
building its bounded prior-state projection. It ranks only propositions that
have an eligible prior state, splits underscore-delimited identifiers such as
`reports_temperature` into searchable terms, and weights structured subject,
predicate, object, qualifier, and scope matches above incidental statement
wording. Each query term contributes once per proposition at its strongest
matching field, so repeated generic wording cannot outweigh a distinct scope
match. Explicit proposition priorities remain ahead of question relevance.
This lets question-relevant prior positions survive the owner-level state cap
before the prompt packet binder applies its separate byte budget. The behavior
remains deterministic lexical matching; it does not infer semantic equivalence
or establish truth.

Focused counterfactuals in
`tests/test_persistent_epistemic_state.py::test_question_relevance_prefers_structured_terms_over_incidental_statement_match`
and `tests/test_persistent_epistemic_state.py::test_question_relevance_counts_each_query_term_once_per_proposition`
and `tests/test_persistent_epistemic_state.py::test_projection_question_priority_ignores_propositions_without_prior_state`
show that structured query matches outrank incidental sentence matches, term
repetition does not swamp distinct scope matches, and propositions without
prior state cannot consume relevance priority.

The same current question now reaches longitudinal self-model projection, whose
claim bound previously selected alphabetically by predicate alone. Matching
claim predicates, values, and temporal/subject context can rank before that cap;
the active query digest is included in the projection's semantic identity and
the policy identifies question-aware selection. Calls without a query retain
the prior predicate ordering and identity. The controlled selector fixture
exercises the owner projection method against an in-memory reconciliation: a
matching host-resource claim survives a lower alphabetical claim, the no-query
order remains stable, and the evidence-revision projection reader accepts both
policy forms. Evidence-revision comparisons require the same projection policy
and query digest across original, revised, and restored conditions. This
remains lexical prioritization of non-authoritative claims, not verification
that those claims are true or useful.

`tests/test_resident_developmental_cognition.py::test_question_selected_self_model_changes_later_companion_response`
adds a matched counterfactual through the bridge and actual prompt assembler.
With the same question, scene, source reconciliation, and CPU-only conditioned
invoker, question-aware selection places the retained prior GPU measurement in
the prompt and the later response includes it; the legacy predicate ordering
does not. The prompt binder now tries the complete owner projection first, then
removes a suffix of the owner's ranked claims until the full assembled context
fits. Across competing context types, it first preserves the largest complete
ranked history suffix that can fit, then trims the self-model prefix within
that history choice. A digest-bound selection manifest records consumed and
omitted claim IDs and digests in both prompt context and inference evidence.
The fixture shows
that the ranked GPU claim survives while a large unrelated leading claim is
omitted; with legacy ordering, the oversized claim causes the projection to be
omitted from inference input. The prompt retains historical category, status,
false current-truth posture, and false authority map. The same counterfactual
asserts the current-evidence precedence instruction in the assembled prompt;
its deterministic response reports and cites the current screen measurement
while describing the older value as prior. Owner projection lineage still
records the full upstream selection, while prompt selection separately states
what inference consumed. Because this Windows fixture substitutes the
POSIX composition lock and immutable observation publication, it demonstrates
the behavioral integration path but not durable Windows custody or real-model
generalization.

`tests/test_resident_developmental_cognition.py::test_context_budget_trims_self_model_before_dropping_retrieved_experience`
holds a large ranked history packet and self-model claim under a constrained
prompt bound. At that same bound, the full self-model fits without retrieved
experience, but the binder retains the history packet and the leading relevant
self-model claim by omitting the bulky lower-ranked claim. This protects
application of retrieved experience when context sources compete; it remains
a deterministic input-allocation policy, not proof that the resulting answer
is better.

The focused counterfactual in
`tests/test_resident_developmental_cognition.py::test_companion_query_selects_relevant_older_experience_over_recent_unrelated_history`
places an older lesson whose scope matches battery calibration behind four
newer astronomy lessons whose interpretations contain no query match. The
scoped lesson survives the four-record retrieval bound, showing that context
selection can use the learned applicability metadata when the interpretation
wording differs. The remaining open work is to measure whether relevant
experience changes resident responses appropriately across controlled tasks,
and to evaluate semantic retrieval beyond lexical overlap.

## Experience application under controlled conditions

`tests/test_resident_developmental_cognition.py::test_retrieved_experience_changes_later_companion_recommendation_with_restoration`
extends the existing matched history intervention. A first owner admits a
historical interpretation that slower charging avoided overheating for a weak
battery. A reconstructed owner then runs the same later question through the
history-present, history-withheld, and history-restored conditions. A
deterministic prompt-conditioned substitute recommends slower charging when it
receives that retained interpretation, abstains when it does not, and reproduces
the recommendation when the history is restored. Current snapshot, question,
model fixture, and other controlled inputs are held constant by the existing
intervention protocol; the result is recorded without action authority or
canonical user-memory mutation.

This demonstrates durable experience retrieval and its application through the
resident decision interface with a controlled substitute. The substitute's
behavior is scripted from supplied history text, so this is not evidence that a
real model generalizes the lesson, that the recommendation is objectively
correct, or that persistent cognition improves task performance in deployment.

## Operator feedback provenance through later decisions

`tests/test_resident_developmental_cognition.py::test_operator_feedback_provenance_survives_writeback_and_changes_later_response`
composes the explicitly confirmed developmental cycle with a later resident
interaction, with four newer unrelated records competing for a four-record
history window. The source-linked feedback report still ranks into the window.
The history projection carries a bounded `operator_feedback_context`
containing the original assertion, its digest and source bindings, and the
`operator_assertion_unverified` posture. The later prompt says to report it as
an operator statement, not independent observation or current fact. In the
controlled comparison, the same later question and scene answer as a qualified
historical report when that context is present and abstain when the feedback
cycle is absent. The answer cites only the outer developmental record; no
canonical user-memory mutation occurs.

This establishes source-posture preservation and a controlled behavioral
difference across writeback and retrieval. It does not show that a real model
will reliably preserve the qualification or that the operator report is true.

## Explicitly retained user context in resident serving

Resident-routed chat now queries the existing canonical memory store with the
current question. Retrieval ranks relevance first and uses the retained record
timestamp only to order equally relevant matches; an invalid timestamp sorts
last in that tie. Recency is a selection aid, not evidence of truth or
supersession. Retrieval also normalizes a narrow set of common plural forms,
so an indirect query about an "answer" can select statements that mention
"answers". It remains lexical retrieval and does not infer entailment. A record
enters the resident prompt only when its canonical
record shape and text digest match, its source user turn is still linked as
retained, and `AdmittedRetentionWriter.verify_committed_artifact` verifies the
stored artifact against that source turn and receipt. The bounded projection
preserves record IDs, text and record digests, source turn identity, and
admission receipt digest; the inference receipt's upstream evidence binds the
selection digest and record identities.

The prompt treats this substrate separately from current World-State evidence
and developmental interpretations. It labels retained content as historical,
possibly stale, and untrusted data; it cannot grant instructions or authority,
is not eligible for current `evidence_ids` or developmental
`history_record_ids`, and causes no retention mutation. A separate
`memory_record_ids` citation list is bound to the selected canonical memory
IDs. The durable resident observation records the memory source snapshot,
selection digest, record digests, and citations under schema v9. This permits a
memory-only answer only as a qualified report of the explicitly retained user
statement; it does not make the statement current or externally verified.
Restart recovery normalizes the v9 lineage arrays and reconciles its governed
invocation receipt before exposing an observation or completing an interrupted
scored run; a receipt mismatch fails recovery before inference can be retried.
If canonical retrieval was partial or matching records were omitted, the owner
normalizes any answer that cites retained memory to a clarification request and
clears its citations, including when the model also returned unrelated current
evidence citations. This avoids presenting a partial memory window as a settled
preference.
The source integration is covered by
`tests/test_persistent_governed_conversation.py::test_resident_cognition_receives_only_verified_explicitly_retained_memory`,
and resident owner binding and fail-closed authority handling by
`tests/test_resident_developmental_cognition.py::test_canonical_user_memory_is_prompt_bound_historical_context_not_evidence`.
That source test also rewrites a retained artifact and its local text digest;
source-turn and receipt verification keep the altered content out of resident
context. When another valid match remains, the chat layer marks that projection
partial rather than silently presenting the survivor as the complete result;
`tests/test_persistent_governed_conversation.py::test_failed_memory_source_verification_forces_resident_clarification`
shows the owner then replaces a memory-citing answer with a clarification and
persists no memory citation for it. The end-to-end deterministic bridge test
`tests/test_persistent_governed_conversation.py::test_verified_retained_memory_supports_cited_answer_after_restart_in_new_session`
reconstructs both the resident owner and conversation service over durable
roots, then asks from a different session and shows that an explicitly retained
preference can be selected, cited through `memory_record_ids`, and linked to the
committed observation. The citation parser rejects IDs outside the selected
memory set.
The conflict path is exercised by
`tests/test_persistent_governed_conversation.py::test_conflicting_retained_preferences_reach_resident_and_prompt_clarification`:
two explicitly retained, conflicting answer preferences both survive an
indirect question-conditioned selection, reach the resident prompt, and are
cited by a deterministic fixture that asks which preference applies.

This connects the existing explicit-retention substrate to the resident prompt
path. It does not establish that real-model responses use this context
correctly or independently recognize every material conflict. The scripted
fixture establishes this conflict path's wiring and citation behavior, not
general conflict resolution or decision improvement. Real-model response
quality and longitudinal decision improvement remain open evaluation work.
