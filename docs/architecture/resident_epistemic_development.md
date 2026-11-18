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

For developmental-history task-family rules, the daemon routes exact run IDs and
digests from its validated same-tick World-State snapshot through
`process_verified_task_family_run`. It includes both explicitly selected runs
and the bounded set of completed, nonsynthetic objective runs independently
discovered by the developmental-history owner. Automatic ingestion is limited
to task families named by an enabled epistemic rule and does not invoke a model;
the run owner rechecks the complete scored protocol and derives the evidence
relation from its frozen comparison. Generic World-State adaptation does not
duplicate task-family evidence or assign a different family's run to a configured
proposition. A proposition advances at most once per maintenance tick; additional
verified runs for that proposition remain pending for a later tick. Repeated
maintenance ticks reconcile the same run idempotently. Run events later than the
daemon tick remain ineligible.
The resulting owner state remains next-tick-only and is available to canonical
plan-only allocation after reconstruction. Missing, mismatched, ambiguous, or
future-dated run evidence remains explicitly unresolved and does not create an
epistemic position.

When a task-family proposition includes an
`active_model_identity_digest` scope, outcome ingestion verifies that the run's
identity object matches its recorded digest and that the digest exactly matches
the proposition scope. A different or unverifiable model identity is rejected
before either evidence or state admission. Propositions without a model scope
retain the existing family-level aggregation behavior.

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

Planning also treats a tagged prior position with an explicit projected
`contradicts` relation as requiring review, even when that position's own
evidence posture is positive and the connected proposition is not separately
tagged by the goal. A tagged proposition explicitly superseded by a linked
claim also requires review. The deterministic counterfactual in
`sentientos/tests/test_epistemic_planning.py::test_projected_relations_change_tagged_goal_review_decision`
shows the goal selected without the relation and deferred after the relation
is recorded. The review scope retains the relation digest; no relation creates
execution authority or establishes truth.

Canonical plan-only daemon feedback now includes a bounded summary for deferred
epistemic positions: proposition ID, posture, state digest when available, and
relation digests. Position and relation-digest listings are capped at eight;
omitted counts make truncation explicit. The allocation artifact path and
digest remain the complete evidence source. This summary cannot authorize
execution or invoke a model. The bounded feedback behavior is covered by
`sentientos/tests/test_orchestrator_plan_only.py::test_daemon_goal_feedback_reports_bounded_listing_omissions`.

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
interpretations, source-verified operator-report text, typed historical
embodiment reports, identity-bound history decision contrasts, and admitted
lesson content against the current question before the bounded history
projection. A decision contrast contributes retrieval terms only when its
verified source identity matches the active serving identity; response
fingerprints remain opaque, and retrieval does not imply correctness or
improvement.
Lesson scope and applicability matches receive more weight than generic
interpretation wording. The latest prior user turn from a validated bounded
session context contributes topic terms only when the current question has
fewer than two distinctive terms, supporting elliptical follow-ups without
letting stale topics dilute a specific question. Conversation terms affect
ranking only and are not evidence or durable memory.
Validated v4 operator-feedback reports that target the same exact conversation
session, turn ID, and turn-text digest are selected as one bounded retrieval
unit. A query that matches one report therefore retains the other reports about
that cited turn when the complete group fits the history cap. This preserves
their shared provenance for later comparison; it does not classify them as
contradictory, count repeated reports as corroboration, or establish either
assertion as true. Groups that do not fit are withheld whole rather than
partially represented.
Unmatched slots are filled from the recent checkpoint sequence. The selected
record identities and retrieval policy
(`query_decision_polarity_then_overlap_with_identity_bound_correction_groups_decision_contrasts_embodied_reports_and_elliptical_session_context_then_recency_fill:v11`)
remain in normal history selection lineage. For decision queries, matching
decision polarity now ranks ahead of lexical overlap, so a longer opposite
decision cannot displace a shorter history that matches whether the decision
was made. Lexical overlap ranks records within the same polarity; checkpoint
order remains the stable tie-breaker, and unmatched slots still use recency.
History packets remain explicitly historical, non-authoritative, and not
current truth. This remains deterministic lexical matching that normalizes
common plural endings and weights terms that occur in fewer candidate records.
It is not semantic retrieval or evidence that selected experience improves an
answer.

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

Question-aware current-evidence selection now treats World-State conflict
groups as indivisible under the configured fact bound. When every conflicting
fact is eligible and the group fits, the projection keeps the full group. If
any member is outside the source policy or the group cannot fit, the projection
withholds its eligible members together instead of presenting one side as
uncontested. The selection policy is versioned as
`question_relevance_then_existing_priority_conflict_closed:v2`. A bounded
counterfactual verifies that a one-fact limit no longer delivers only the
matching side to a controlled responder, while a two-fact limit delivers both
and leaves the answer unresolved. This is deterministic selection behavior;
real-model conflict handling remains unverified.

Ordinary companion context now preserves source freshness in compact current
evidence rows as well as in the full projection. The prompt directs the model
to treat stale, expired, undated, unknown, and not-applicable sources as
historical reports rather than support for a present-condition claim; an
aging report must be qualified. A controlled production-path counterfactual
asks for a fresh temperature reading when the only selected report is expired,
while the same path answers from a fresh report. The compact projection row is
versioned as v2 to carry source kind, staleness, and finding. This tests the
prompt contract with a deterministic responder; real-model adherence remains
unverified.

The production interaction boundary now also enforces freshness for present-
condition questions. It recognizes explicit temporal markers such as "current",
"now", "today", or "still", plus common direct question forms with definite,
possessive, or demonstrative subjects (for example, "What is the room
temperature?" and "Is the pump online?"). Indefinite definition questions such
as "What is a moon phase?" remain outside this current-condition classifier. An
answer must cite current World-State evidence whose source
finding is valid and whose posture is fresh or aging; a cited stale, expired,
undated, unknown, or not-applicable source is converted to a request for a fresh
observation. Memory or dialogue citations alone cannot establish the current
condition. If the model cited an eligible prior self-model claim, the normalized
response may include a bounded deterministic description of that historical
record while still asking for a fresh observation; it explicitly says that the
record does not establish current truth. The owner derives that note from the
selected attributed claim, never from the model's discarded current-condition
wording. Aging evidence receives a deterministic qualification in the response.
Historical questions remain able to report what an older source said.
A controlled production-path counterfactual makes the responder answer from an
expired source and verifies that the boundary asks instead; fresh evidence still
answers, historical questions still report the expired reading, common implicit
present-state forms receive the same freshness check, and definition questions
remain answerable. The classifier is intentionally lexical and bounded; other
implicit forms and real-model interpretation remain unverified.

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

`tests/test_resident_developmental_cognition.py::test_question_selected_self_model_cannot_override_unknown_current_evidence`
adds a matched counterfactual through the bridge and actual prompt assembler.
With the same question, scene, source reconciliation, and CPU-only conditioned
invoker, question-aware selection places the retained prior GPU measurement in
the prompt and preserves its citation; when the current screen source has
unknown freshness, the response labels the prior measurement as historical and
asks for a fresh observation without repeating the model's unsupported current
reading. The prompt
binder now tries the complete owner projection first, then removes a suffix of
the owner's ranked claims until the full assembled context
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
wording differs. Optional pinned CPU semantic retrieval now also selects
lexically disjoint history through bounded embedding batches and a restart-safe
vector index. Policy v18 rejects matches below a 0.25 cosine floor and ranks
lexical relevance ahead of semantic similarity, while allowing above-floor
lexically disjoint matches to outrank recency. Deterministic tests cover
near-threshold lexical priority and strong lexically disjoint retrieval. The
remaining open work is to calibrate the floor against real embedding behavior
and measure whether relevant experience improves appropriate later responses;
no real-model benefit is established.

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

### Recovering cited dialogue across sessions

Operator feedback now binds each cited turn to its originating conversation
session. During a later resident response, only citations belonging to selected
feedback records are resolved against the custody-verified session transcript;
the turn text digest must still match. The bounded excerpt is supplied as
historical dialogue for comparing the operator's correction with the referenced
statement. Missing, changed, malformed, or unselected turns are withheld. The
durable cognition observation records selection, turn, feedback-fact, and source
session digests, but does not copy the transcript text into cognition records.

When distinct feedback records cite the same turn, the selection retains one
source-bound context row per report instead of collapsing them by transcript
identity. It first reserves a slot for each distinct turn, then uses remaining
bounded slots for additional reports, so repeated reports cannot crowd out
other cited turns. The prompt and observation keep those report identities
separate; repeated dialogue does not count as independent corroboration. The
deterministic counterfactual in
`tests/test_persistent_governed_conversation.py::test_verified_epistemic_citation_survives_restart_and_changes_followup_projection`
now includes two conflicting reports about the same prior turn. Both reports
reach the later prompt, which preserves the disagreement as unresolved and
unverified while leaving the prior epistemic state unchanged. This demonstrates
the behavior with controlled substitutes, not reliable real-model reasoning.

`tests/test_persistent_governed_conversation.py::test_historical_citation_context_resolves_only_digest_bound_source_turn`
demonstrates reconstruction from a separately persisted session and fail-closed
behavior after a citation digest changes. The controlled counterfactual in
`tests/test_resident_developmental_cognition.py::test_operator_feedback_provenance_survives_writeback_and_changes_later_response`
then passes a source-bound prior-session excerpt through the cognition owner: the
fixture compares it with the linked correction and keeps both claims qualified;
the persisted observation records lineage but excludes the excerpt text. These
are deterministic storage and model-substitute results. They do not establish
that a real model will reason correctly about disagreement, or that later
outcomes revise the underlying knowledge state appropriately. The next cognition
milestone should evaluate that feedback and revision loop.

Feedback schema `sentientos.local_operator_feedback:v5` also binds a correction
to the epistemic state IDs cited by the exact assistant turn it challenges. The
chat service copies those IDs only after verifying the committed response
lineage and the turn's source user turn; malformed or unverifiable linkage
retains the v4 transcript citation without a state link. Later history
projection validates the bounded state ID list and keeps it nested under the
correction target. This preserves which evidence-bound position was challenged
even when the source transcript is unavailable. The link identifies a state;
it does not recover missing dialogue, establish the operator report as true,
authorize an action, or revise the state. The expanded restart counterfactual
in `tests/test_persistent_governed_conversation.py::test_verified_epistemic_citation_survives_restart_and_changes_followup_projection`
removes the cited session transcript and demonstrates that both conflicting,
unverified reports remain associated with the exact unchanged state in a later
projection. This is deterministic substitute behavior; real-model interpretation
and outcome-driven revision remain unproven.

The resident epistemic runtime resolves state citations carried by v5 operator
corrections against its persistent state owner. A retained, allowlisted state ID
provides the exact proposition join directly; no duplicate static
`operator_input` selector is required. The correction can add `contextualizes`
evidence only to that proposition lineage; absent, malformed, or unknown v5
citations match no proposition. Its assertion remains unverified and cannot
change stance. A separate configured observation still passes through normal
evidence and state admissions, and a later cognitive projection resolves the
old cited state ID to the newest admitted generation. The CPU integration
regression exercises this sequence across owner reconstruction. It demonstrates
the governed software path with deterministic evidence; real-model
interpretation and improved decisions remain unproven.

A cited v5 operator correction survives owner reconstruction as a
source-digest-bound context record. Its exact assertion text and assertion
digest are retained in a v2 evidence binding only when the v5 payload shape,
text digest, cited turn, state IDs, and source identity all validate. The v7
projection and v4 packet deliver this text while it is pending; if the binding
later enters active or removed state history, the same text remains explicitly
context-only. In both locations it is excluded from evidence citations and
state revisions. The resident prompt labels it as unverified operator context
that may be compared with current evidence but cannot establish truth or
authority. A deterministic restart counterfactual confirms the exact text
reaches the prompt without changing stance or generation; a source payload with
altered text and a stale digest/source identity adds no binding. An unknown
citation adds no context, while a separately admitted observation can still
advance state. This demonstrates the governed software path only; whether a
real model applies the correction appropriately or makes better later
decisions remains unverified.
Epistemic calibration records were previously durable but absent from later
Meaning-bearing projections now expose up to 16 chronologically latest
calibration outcomes per selected proposition only after an exact
`calibration_outcome` update event binds the calibration ID and digest. An
unreviewed event contributes only to a bounded omitted-identity count; its
comparison label and outcome text do not reach cognition. Reviewed outcomes
include any source evidence bindings not already present in that proposition's
state history. Projection validation joins each outcome to its forecast state
and source evidence, excludes outcomes at or after the cognition tick, and
digest-binds omitted records. The resident instruction treats exposed outcomes
as historical forecast comparisons that can qualify a decision, not as current
truth or authority. Previously, a controlled-responder counterfactual showed
that a contradicted forecast can change a later response when delivered, while
the underlying epistemic state remained unchanged. These are deterministic
owner and controlled-responder results; real-model use of calibration history
remains unverified. A follow-up counterfactual showed that the stored comparison label
could disagree with the cited binding's relation. Semantic packets now derive
`evidence_consistency` from all cited bindings: only a complete set of current,
non-withdrawn, dependency-resolved bindings with a matching support or
contradiction relation is marked `consistent_with_bound_current_evidence`.
Inconclusive, stale, unknown-dependency, missing, or mismatched evidence is
marked `unresolved_against_bound_evidence`. Resident instructions require the
consistent posture before using a calibration label to qualify a decision. A
restart-backed controlled-responder counterfactual confirms the matching
contradiction changes the later response while a mismatched label does not.
The persisted-owner composition is exercised in hosted Linux validation; the
local Windows checkout can run the pure classification test but not that
durable-custody fixture. The new runtime review path verifies one exact event,
forecast state, and active outcome bindings, obtains a calibration-review
admission to construct a proposal, then requires the existing separate
state-update admission and CAS. Its candidate definition is not registered in
the canonical authority catalog pending operator approval; production review
therefore fails closed. The hosted Required Quality Gate passes the
restart-backed composition and a deterministic responder
counterfactual: a consistent admitted calibration changes the later response,
while a mismatched comparison label remains withheld and leaves that response
unchanged. This validates software integration with controlled substitutes;
it does not independently verify the underlying outcome, and real-model
interpretation and real-world calibration remain unproven.

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

## Evidence-bound task-family strategy candidates

Resident context assembly can now derive a provisional integer-affine strategy
from retained task-family examples when at least three distinct inputs have
score-bound, evaluator-correct answers and agree on one relation. The summary
keeps the supporting examples and their source fact, run, task, and score
digests; prompt projection re-derives the relation from those rows and rejects
a strategy whose claim does not match them. Conflicting examples removed by
the existing cross-history conflict filter also remove the derived summary.
The prompt labels the relation as historical and provisional, restricts it to
the matching task family, and explicitly withholds claims of learning or
transfer performance.

The focused deterministic test
tests/test_resident_developmental_cognition.py::test_admitted_family_example_supports_second_heldout_episode_after_restart
exercises the production history and prompt binders with a controlled fake
invoker that consumes the candidate relation. In that fixture, the relation
supports all three held-out predictions after restart; withholding history
yields zero of three. A separate tampering counterfactual recomputes the
strategy digest after substituting a false relation and verifies projection
rejects it. These are deterministic software-path results, not evidence of
real-model learning, broad task transfer, or improved open-ended decisions.
No model inference was used for this milestone; validation is CPU-only.

## Revising strategy projection when outcomes conflict

The next cognition increment closes a gap between outcome-aware retrieval and
context assembly. The goal is to keep a provisional task-family strategy out of
later guidance when score-bound outcomes for its exact task and source-model
group are unsettled, while retaining the underlying historical examples and
their provenance. Acceptance requires a controlled settled/unsettled
counterfactual: settled evidence still projects its candidate strategy;
contrary outcomes suppress that strategy in assembled context and the bound
prompt; the suppressed candidate remains traceable by digest and carries no
truth or authority posture.

The history projection now carries unsettled task/model outcome groups into the
production context binder. When a candidate relation belongs to one of those
groups, the binder omits the relation, marks its digest as withheld due to
unsettled score-bound outcomes, and preserves the examples. Prompt projection
records both available and withheld candidate summaries so later review can
distinguish omission from missing source evidence. This is still a deterministic
software-path capability: it does not prove that a real model correctly
interprets unresolved evidence or improves later decisions.

The follow-on goal is to make that withholding operational in model-facing
context: when a selected history packet marks a candidate relation as
unsettled, the prompt must tell the model not to reconstruct or apply that
relation from the retained examples, and to preserve uncertainty until new
comparable evidence resolves the conflict or abstain. Settled history must not
receive this caution. The deterministic acceptance check compares both prompts
while retaining the same source examples and provenance.

The binder now appends this instruction only when a selected history packet
contains the withheld-candidate posture. The controlled counterfactual
`tests/test_resident_developmental_cognition.py::test_unsettled_task_family_outcomes_withhold_candidate_strategy_from_context`
checks that the stable prompt keeps its provisional strategy without the
warning, while the unsettled prompt omits the relation, retains the same
examples, and explicitly directs the model not to reconstruct or apply it.
This verifies prompt assembly with deterministic evidence; real-model
interpretation and later task outcomes remain untested.

The longitudinal fixture now uses the production objective-intervention and
writeback paths to admit two distinct runs with contrary, receipt-bound outcomes
for the same task and model, then assembles history for a later task in a fresh
owner process. Its controlled acceptance result checks strategy use while
outcomes are settled, admission of the adverse run without editing prior
evidence, and strategy withholding plus abstention only after the retained group
becomes unsettled. The hosted Linux source-validation suite passed this
counterfactual through the durable custody path. This remains a deterministic
policy-fixture result rather than a real-model improvement claim; real-model
interpretation and improvement remain unproven. The Windows checkout cannot run
the durable custody portion because that storage contract currently rejects
this platform.

Unsettled outcome withholding is scoped to the exact source-model identity.
When another model receives an oracle-verified same-family candidate from a
source group that remains unsettled, projection retains the candidate with a
digest-bound source-conflict marker and tells the target model that source-model
outcomes do not establish its performance. The existing exact-family and
evaluator-example checks still apply; this does not claim cross-model transfer.

The hosted restart-safe counterfactual now follows that case through the
receiving model's own feedback. Model B applies the provisional candidate on a
held-out task, its receipt-bound favorable result is admitted through ordinary
World-State and developmental writeback, and an adverse repeat on the same
task makes B's own candidate unavailable to B's next prompt; the deterministic
policy abstains. A third identity still receives B's candidate with the
cross-model unsettled-source marker and solves the same held-out task from the
oracle-verified relation. This demonstrates that outcome custody, writeback,
model-specific history selection, and later model-conditioned context compose
across a restart. It does not establish real-model interpretation, durable
performance improvement, or general cross-model transfer.

## Cross-session correction integration

A verified assistant answer can now carry its bounded screen-capture provenance
through resident-cognition transcript linkage, allowing the existing explicitly
invoked operator-feedback path to evaluate that answer after a later turn. The
feedback path still requires a cited earlier assistant response and records the
operator statement as an unverified input; neither transcript history nor the
feedback itself grants truth or execution authority.

The composed path is covered by
`tests/test_persistent_governed_conversation.py::test_verified_epistemic_citation_survives_restart_and_changes_followup_projection`.
It reopens the cognition and epistemic owners, verifies the persisted answer,
admits an operator correction through `PersistentConversationService`, then
starts another session and confirms the cited epistemic state is selected in
the production bridge prompt. A no-correction session selects the alternative
state. The integration now asks the same target question before and after the
correction. Its deterministic invoker changes the later response only when the
historical assistant turn matches the correction target's turn ID and text
digest, and the feedback assertion and cited dialogue share the exact bound
feedback digest. The resulting response surfaces the disagreement and keeps
the operator report unverified. The prompt still labels the old citation
historical, non-truth, non-authoritative, and non-mutating; the epistemic
state's identity remains unchanged. This demonstrates that the composed
context contains enough bound information for a controlled response policy to
apply a correction without promoting it to truth. It does not establish that a
real model will correctly interpret feedback or improve open-ended decisions.

Plan-only allocation also treats a source-bound v5 correction as a review
signal for goals explicitly tagged to the cited proposition. The deferral
carries the correction binding IDs (or a bounded omission count and digest when
context is over capacity); the correction remains unverified context and does
not change the epistemic state. A paired allocation counterfactual verifies
that the same supported state is usable before the correction and deferred
after it, with its state digest and generation unchanged. This makes feedback
operational for planning while preserving the evidence boundary; it does not
decide whether the correction is true or resolve the position without
independent evidence.

When the correction is compared with a cited prior epistemic state, the later
response now names that state as an earlier evidence-bound position and cites
its exact state ID alongside the feedback record and historical dialogue turn.
The same deterministic restart test checks those three citations and confirms
that the epistemic state itself remains unchanged. This demonstrates
provenance-preserving comparison in the production path; it does not establish
that a real model will recognize when both sides are relevant or resolve their
disagreement correctly.

Historical dialogue citations now remain distinct from same-session citations
through the interaction result, observation schema v15, and committed assistant
transcript linkage. Each selected citation stores the exact offered turn ID and
text digest; parsing rejects references outside the prompt's allowlist, and
transcript verification checks the linkage against the persisted observation
and its offered historical context. The composed restart test asserts that the
correction-conditioned answer cites the earlier turn and digest after a new
session. This is deterministic citation-lineage evidence only: a controlled
invoker supplies the citation, and it does not show that a real model will
select all and only the historical turns that materially influenced its answer.

The restart counterfactual now inserts 20 unrelated turns between the cited
answer and an anchored follow-up. The bounded selector still retrieves both
turns of the older exchange, carries its verified epistemic-state citation into
the prompt, and preserves the correction-conditioned response difference from
the no-history control. This demonstrates the composed retrieval and citation
path under transcript pressure with deterministic inference; real-model
selection and interpretation remain unverified.

When resident transcript context exceeds its budget, selection now ranks
adjacent user/assistant exchanges as units. A query matching the user's earlier
question therefore keeps the assistant's differently worded decision with it,
while the existing 16-turn and 4,000-character bounds remain in force. The
hosted source-validation suite and focused resident-context cases pass this
counterfactual alongside rare-anchor and anaphoric-follow-up selection. This
establishes bounded exchange integrity in the deterministic selector; it does
not establish that a real model will interpret the selected history correctly.

Relevance ranking also runs when the recent slice already fits the character
budget. An older exchange that directly matches the current question can take
priority over unrelated recent exchanges, after which recent exchanges fill
remaining turn and character capacity. Focused tests show the older decision
survives in a concise long transcript without exceeding either bound; the
hosted source-validation suite verifies this together with the exchange-pair,
rare-anchor, and anaphoric-follow-up cases. Real-model selection and use of
historical decisions remain unverified.

Repeated older mentions could still fill the bounded context with high-scoring
exchanges and omit the newest exchange that also matches the question. The
selector now reserves that newest relevant exchange alongside the strongest
ranked history before filling remaining capacity. A focused counterfactual
keeps both the strongest older decision and the newest correction under the
existing turn and character bounds. This is deterministic selector evidence;
real-model interpretation of competing old and new information remains
unverified.

The resident prompt now directs the model to use an explicit later user
correction to revise its account of what was said or decided, while attributing
both statements and refusing to treat recency as current evidence or authority.
A composed CPU fixture sends repeated older mentions and a latest correction
through bounded selection, the resident bridge, and prompt assembly; its
controlled responder cites the correction and changes its qualified answer
relative to an older-history-only control. The full owner fixture requires
Linux durable-custody paths and is skipped on Windows; the hosted source
validation suite exercises it. Real-model interpretation and application
remain unverified.

Bounded history selection now also retains a pronoun-only user correction when
it immediately follows an exchange relevant to the question. This preserves
the correction's nearby antecedent under transcript pressure without admitting
an unrelated correction after an irrelevant exchange. A deterministic selector
counterfactual and the composed resident-owner fixture use "No, that was
outdated. It cleared several minutes later." to show the correction survives
selection and changes the qualified response relative to an older-history-only
control. Hosted source validation is required to exercise the owner fixture;
real-model interpretation remains unverified.

Resident cognition now ranks source-linked user/assistant exchanges across the
stored session before applying a bounded candidate limit of 64 turns and a
4,000-character reconstruction budget (3,000 in gaming mode). Relevant complete
exchanges receive priority; recent exchanges fill remaining capacity. The
existing cognition selector then applies its 16-turn, 4,000-character prompt
limits. Both selection stages rank the number of distinct query terms matched
before using inverse document frequency to break ties. This prevents a batch of
one-term identifier matches from crowding out a linked exchange that matches
multiple terms in the question. The deterministic counterfactual
`tests/test_persistent_governed_conversation.py::test_query_coverage_keeps_multi_term_exchange_across_both_history_bounds`
shows the older source is excluded by the prior IDF-sum policy but survives the
64-turn candidate window and 16-turn final selector under query-coverage ranking.
A separate chat-path counterfactual with 40 newer unrelated exchanges shows a
recent-only 64-turn window omits the older west-sensor source, while
relevance-ranked retrieval retains it alongside recent dialogue. These tests
demonstrate bounded retrieval with synthetic dialogue; real-model use remains
unverified.

The same speaker and evidence rule applies when recalling decisions: an
assistant recommendation is not a user-confirmed decision. The resident prompt
now requires explicit user acceptance before describing a plan as user-decided,
and treats that confirmation as dialogue evidence rather than proof that the
action occurred. A controlled resident-owner counterfactual compares a
recommendation without acceptance to the same recommendation followed by an
explicit user acceptance, checks the attributed citation set, and keeps action
authority false. Its full-owner fixture runs in hosted Linux source validation;
real-model interpretation remains unverified.

The integration exposed a linkage defect: the bridge adds resolved epistemic
priorities to the conversation context and recomputes its selection digest, but
the response linkage previously kept the pre-bridge digest. The cognition
result now returns the effective digest used for its prompt, and transcript
verification checks that digest against the persisted observation. The test
also supplies the screen observer's required text-status field so the bounded
capture provenance can be carried into the assistant linkage.

Focused CPU-only validation passed for the cross-session test and the adjacent
developmental-cycle authorization, explicit-confirmation, and historical
citation tests. No Hermes or GPU inference was used. Real-model feedback
interpretation, repeated outcome measurement, and improvement across open-ended
decisions remain unproven.

Same-session transcript retrieval now preserves explicit `no`, `not`, and `nor`
markers and normalizes common negative contractions to `not` alongside topical
terms. Shared inflection normalization now maps common `-ved` past-tense forms
back to their final-`e` stems, so “approved” matches “approve.” For decision
predicates, retrieval ranks matching query polarity ahead of recency when topic
coverage ties. A deterministic paired query fixture places the opposite-polarity
exchange most recently and checks that a two-turn limit still selects the
matching negative or positive exchange. This validates retrieval ranking and
source-turn linkage; it does not establish that a real model will interpret
selected context correctly.

Persistent developmental-history retrieval now uses the same negation-aware
query terms and ranks matching approval/decision polarity ahead of recency when
topic relevance ties. A one-slot counterfactual places a negative approval
record newest: a contracted negative query selects it, while the positive query
selects the older positive record. This demonstrates polarity-sensitive
historical record selection with deterministic fixtures; it does not validate
real-model interpretation, current truth, or execution authority.

Both history retrieval and same-session transcript retrieval now normalize
“cannot” and “can not” to the same negative decision marker already used for
“not” and common contractions. Their paired counterfactuals put the positive
approval most recently while storing the older negative decision as “cannot
approve”; the negative query retrieves that older record, while a positive
query still retrieves the recent approval. This closes a wording gap in the
existing lexical polarity selector without treating retrieved statements as
truth or authority. It remains deterministic retrieval evidence, not proof that
a model will interpret the selected correction correctly.

### Rootless Windows epistemic-series execution (2026-11-17)

The Ollama correction-pressure runner now creates its Windows run, cognition,
history, state, and held-out-key directories through private native custody.
New directories receive current-user-only inheritable access, and resident
epistemic prompts use one measured 18 KiB character ceiling throughout prompt
preview and invocation. The JSON payload is flushed on Windows; directory-entry
flush is POSIX-only because Python cannot open Windows directories with
`os.open`, so power-loss durability of the directory name is not claimed there.

The actual Windows path reached pre-registration and one governed local
inference attempt with Qwen3 8B (`rootless-epistemic-run-e3b493426b7a4d7c803fe13a`,
preregistration digest `28d55184db27c719997ab9bfcbaf76c2c3b1cdfcb7c76643f649c06c0e392765`)
and Qwen3 1.7B (`rootless-epistemic-run-f8c49ecb01964af5b1a4cdf4`,
preregistration digest `1f5664e013026d67c0b0a062b7fe859efbee3953b8db36429fb689ea184db7d0`).
Each invocation ended in `backend_failure:ModelLoadError` at the 120-second Ollama
backend timeout; both receipts have no output digest, no capture index was
produced, and scoring did not start. These runs establish path execution and
the runtime timeout, not model behavior or correction performance. Their
preregistration and failure records remain in the private local evidence
workspace; neither run is production-serving evidence. Focused custody,
prompt-bound, runner, and serialization tests pass. The remaining empirical
blocker is a completed bounded local-model response.
