# SentientOS discernment participant

The canonical participant is a non-authoritative judgment-generation organ. It binds an
exact question and initial evidence snapshot to explicit epistemic observations, an
optional live `InnerWorldOrchestrator` cycle, repository-local delegated-judgment
evidence, and one `discernment_judgment` call through the existing governed local-model
invocation plane. The validated model JSON—not the caller—originates the interpretation,
stance, confidence, objections, forecasts, and preferred move. Receipts bind the model,
model artifact, authority map, control-plane admission, request, and deterministic input
digests. Null, echo, denied, unavailable, timed-out, malformed, oversized, namespace-
escaping, executable, or authority-seeking output yields a truthful suspension.

The intended experiment sequence is:

1. Create and freeze an identical question and evidence snapshot.
2. Let the SentientOS participant generate and seal its own structured judgment.
3. Let Allen independently submit his judgment.
4. Let an external GPT independently submit its judgment.
5. Freeze the judgment set through `BlindTrialCustody`.
6. Later record canonical evidence, review, compare, and reveal identities.

No peer identity or judgment is shown to SentientOS before its judgment is sealed. The
participant does not invoke custody, execute work, mutate goals or memory, schedule,
publish, use providers or networks, create commits, adopt a judgment, or grant authority.

The JSON-only CLI accepts the input object with `--request` and emits the participant
result. Its configured model must have a production-local authority record advertising
`discernment_judgment`; simulation backends cannot satisfy that requirement.
