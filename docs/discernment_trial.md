# Blind comparative discernment trial

The `sentientos.discernment_trial.v1` protocol is a participant-neutral evaluation
instrument. It does **not** declare SentientOS a co-author. It accumulates evidence
over unresolved real decisions so Allen can decide whether SentientOS judgment is
independently useful. Source identity is revealed only after judgment results are
frozen because the experiment tests judgment, not reputation.

## Custody and phases

One manifest binds one question and initial evidence snapshot, their digests, opaque
slots, nonce, horizon, observation namespace, custody root, and a no-authority
posture. Every registration receipt repeats the same question and snapshot digests;
there are no participant-specific hints. Arbitrary trials of at least two
participants are supported and opaque IDs have no precedence.

Identity records and blind artifacts are separate. Before every expected judgment
is sealed, the JSON API returns only the submitter's receipt plus aggregate counts;
peer inspection, evidence, comparison, and reveal fail closed. The completed set is
digest-frozen and cannot be replaced. This is a procedural repository-custody
guarantee, not cryptographic secrecy from a filesystem owner who can manually open
raw custody files.

Only after that freeze can canonical observation records be recorded. Observation
keys must use the manifest namespace. Review code computes expected and
disconfirming hits by exact set intersection between prospectively declared keys and
later observed keys, then passes only those derived hits into the existing generic
outcome-review API. The trial CLI accepts no witnessed-hit checkbox. An undeclared
later fact remains evidence but never becomes retrospective forecast credit.

Reviews and the comparison use opaque IDs only. The comparison preserves stance,
confidence, classifications, forecast/disconfirmation hits, requested evidence,
objections, revisions, suspensions, contradictions, consequences, unique prospective
observations, and overlap as separate dimensions. It emits no winner, loser, rank,
intelligence/trust/co-author score, or weighted composite. Reveal is a new sealed
artifact after all reviews and the comparison exist; it never rewrites their bytes.

The module only reads and writes explicit artifacts under its caller-selected
custody root. It has no execution, maintenance, memory, goal, Git, publication,
scheduler, provider invocation, network, or authority effect. An external GPT result
is a structured submission created outside this runtime; no provider is automated.

## First intended experiment

For one unresolved SentientOS architecture question:

1. Create one question and evidence snapshot with three opaque slots.
2. Allen/operator independently writes a structured judgment.
3. SentientOS independently uses its already-governed local discernment surface.
4. An external peer GPT independently produces a structured judgment outside SentientOS.
5. Import each submission without showing peers; in particular, do not expose another
   judgment to SentientOS before its own is sealed.
6. Freeze all three judgments, then continue normal project work.
7. Later record canonical observations and freeze all blind reviews.
8. Freeze the blind dimensional comparison.
9. Reveal which opaque participant was Allen/operator, SentientOS, and external GPT.

Three successful trials would still not establish co-authorship. The purpose is a
long-running body of blinded evidence across genuinely unresolved decisions.

## JSON CLI

Run `python -m scripts.discernment_trial --root ROOT` with `create-trial`,
`register-participant`, `submit`, `trial-state`, `record-evidence`, `review`,
`compare`, `reveal`, or `inspect`. Request-bearing commands read JSON objects from
`--request`; output is JSON only. `inspect judgment --opaque-id SLOT` is unavailable
until the complete judgment set is frozen.
