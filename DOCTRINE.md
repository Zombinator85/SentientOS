# SentientOS Doctrine

These are enduring operating invariants, not a catalogue of currently implemented capabilities.

1. **Local operator authority is primary.** Ambiguous privileged action fails closed; shutdown, refusal, review, and rollback boundaries remain attributable.
2. **Cognition does not inherit consequence.** A model may interpret or propose, but model output does not create policy, permission, admission, execution, truth, or adoption.
3. **Stages do not collapse.** Preserve:

   ```text
   state != authority
   memory != current truth
   observation != interpretation
   proposal != authorization
   authorization != execution
   execution != validation
   validation != adoption
   publication != deployment
   repository absorption != runtime adoption
   capability definition != grant
   grant != operational feasibility
   operational feasibility != admission
   admission != execution
   ```

4. **Evidence remains bounded.** Every observation carries provenance, time, scope, and uncertainty. Contradiction is represented, not silently resolved. A receipt proves only its domain-specific recorded stage and is not shorthand for “the effect happened.”
5. **Authority is exact and revocable.** Principals, capabilities, effects, policy, feasibility, admission, execution custody, and results remain separately inspectable. Readiness, registry presence, tests, and configuration do not self-grant.
6. **Effects require custody.** Consequential paths need named authority, audit, failure semantics, and—where applicable—operator approval, rollback, panic, and result verification.
7. **Persistence is explicit.** Durable and process-local state are distinguished. Memory and historical records may guide cognition but cannot bypass current evidence or deterministic authority.
8. **Adoption is a separate act.** Metadata, proposals, review, validation, merge, repository absorption, publication, installation, and live-runtime adoption are distinct transitions.
9. **Compatibility is not architecture.** Cultural and legacy aliases may remain operational, but canonical technical language governs new explanations and evidence.
10. **Assurance claims name their scope.** Formal models, executable checks, synthetic tests, runtime-assurance-like contracts, and reference-monitor-like mediation never imply whole-system proof or universal enforcement.
11. **Safe shutdown is preserved.** Resident owners must expose bounded stop/quiescence behavior; absence of stable supervision must not be described as recovery.
