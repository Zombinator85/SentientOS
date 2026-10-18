# SentientOS

SentientOS aims to become a continuing, world-coupled developmental operating environment: experience should be able to become retained organization that changes later cognition, strategy, procedure, and conduct across replaceable cognitive and software machinery.

**SentientOS is both a developmental north star and a commitment to the strongest physically implemented, evidentially supportable description.** Build toward the continuing developmental environment; describe each capability by its actual mechanism and evidence. The name does not substitute for either.

## One trajectory: hosted now, native intended

```text
HOSTED (current implementation)       NATIVE (intended lower-layer ownership)
hardware                               hardware
  -> Windows/Linux kernel                -> firmware / boot
  -> SentientOS runtime                   -> SentientOS trusted substrate
  -> models, state, governance            -> deterministic services and enforcement
                                           -> World-State, history, cognition, models
```

Hosted SentientOS is real system work, not disposable scaffolding. It delegates mechanisms to mature host operating systems, drivers, and inference runtimes while seeking to preserve purpose, principal, authority, resource sponsorship, generation, evidence, and consequence. Native SentientOS is literal architectural intent; current code is not a mature general-purpose bare-metal replacement and does not provide complete device support or general native resource enforcement.

## The persistent system can outlast a model

The model is replaceable cognitive machinery. The persistent causal organization is the longitudinal experimental object. Model identity, model-development provenance, software generation, system/history continuity, current evidence, retained memory, authority, effects, and consequences are separate lineages because they answer different questions. A proposed, installed, or activated successor is not proof of which model is actually running or what it did.

Meaningful continuity across replacement is an empirical question. SentientOS preserves the evidence needed to ask it; it does not settle it by naming a model or system identity.

## Development is causal

```text
world and system evidence -> World-State -> bounded cognition and history
-> interpretation / prediction / proposal -> sponsorship and authority
-> permitted execution -> independent observation and attribution
-> qualified, separately admitted change -> later cognition and conduct
```

The architecture aims for retained experience to affect later organization, rather than merely accumulating records. A mechanism in source is **implemented**; a real owner-to-owner path is **composed**; a qualifying nonsynthetic event is **production-evidenced**; an unbuilt connection or empirical hypothesis is **projected**. These predicates do not imply one another. Storage, retrieval, or changed output alone does not establish learning or improvement.

## Governance protects the experiment

Governance keeps epistemic, motivational, and consequential authority distinct: evidence can constrain what is justified; it does not grant permission to act. Hard boundaries belong around consequential effects, while personality, objectives, and narrative conclusions should remain open where no operational constraint requires them. **Constraint is not motivation.**

**NO_GRADIENT is not NO_LEARNING.** Evidence-dependent updates may change predictions, interpretations, procedures, and later choices. Approval, shame, attachment, or survival cues must not quietly become undeclared enduring objectives. Handoffs should preserve a conclusion's proposition, scope, evidence, relevant rejected objections, and reopening conditions; a new session alone is not a reason to discard a justified conclusion.

Governance, provenance, experiments, and custody serve the developmental objective; they are not substitutes for it. The intended system does not prescribe a preferred personality or guarantee beneficial development.

## Where the current evidence stands

This status was reconciled against the regular merge of PR #2380, `915cf098c15eed3157dd908763d06c54911390fe`, tree `105f71b68b1ec08b6e31b66aa90a6ed67efc1e49`, on 2026-10-18. Sequence 409 clarifies partial test-provenance windows without treating an unanchored predecessor as valid; it also fixes duplicate archive discovery. The immutable atlas index retains its historical source binding and is not relabeled as current. The evidence index remains append-only; this summary changes only when its claims become stale.

- **Main verification:** PR #2380 merged with a regular merge commit, preserving the candidate parent. Exact-main Required Quality Gate #39175308712, CI #39175308697, Docker Image #39175308717, Invariant Tests #39175308758, Docs Deploy #39175308704, and Codex CI #39175308731 are bound to `915cf098c15eed3157dd908763d06c54911390fe` and all passed. Forge Smoke #39175308694 was skipped by its configured condition. The independently downloaded QG artifact #12153599644 matched SHA-256 `76dae317892620a5379e9c26616c864f2f1f1b75bd13282989fc0491a44a73c2`, binds the exact source and tree, reports Administrator UID 0, strict audit, immutability, and 29/29 acceptance with zero failures or skips. CI source-validation artifact #12153948284 matched SHA-256 `a2252b1366a190ebbf35ece7ffd4ca1134efcbe05e807cf25afb3cebc937f3af`; its exact-main source-validation, canonical-planning, and World-State contract suites passed 11/11, 20/20, and 3/3 nodes respectively.
- **Provenance custody:** the QG trend subreport reports `INTEGRITY_BROKEN` because its single-run window begins with an unanchored predecessor. The committed history also has unresolved predecessor gaps, including the preserved sequence-286 provenance loss. No historical evidence was reconstructed or discarded. Sequence 409 distinguishes an unanchored partial window from a broken link inside the supplied window and keeps integrity false until the predecessor is verified.
- **Federation Health:** scheduled run #39175640282 succeeded on exact main `915cf098c15eed3157dd908763d06c54911390fe`. Its Administrator preflight and health generation passed; independently downloaded artifact #12154690421 matched SHA-256 `43efdd80e7bd97851b301a0cc54798ff79f47db9a98ac264ac9f37a836613337` and reports 1 node, 0 recent events, status `quiet`. Health generation remains read-only and publisher write permission remains separately scoped. This establishes scheduled execution, not changed-output publication: the repository Actions setting that denied PR creation during the earlier fixture attempt remains a separate blocker.
- **Nightly verification:** no scheduled Nightly Audit Integrity or Nightly Self Check run on this exact main has been observed. Prior-source scheduled results and push-triggered success are not substituted. Current workflow code retains strict Administrator checks and least write authority; the next scheduled executions are still needed for exact-main runtime evidence.
- **Production developmental evidence:** CI, synthetic rehearsals, source composition, and scheduled health telemetry do not establish production A→B→A, learning, or improvement. A real resident transition still requires commissioned A/B identities and receipts, distinct serving approvals, and an operator-approved preregistered trial.

The frozen atlas source's resource-ledger-to-daemon gap is addressed in current main when the explicit observation selectors are configured. The immutable [source-bound atlas](docs/architecture/repository_system_atlas_84c5687c.md) still describes its exact earlier tree. The current main integration tests verify the configured owner-to-owner path; no production event or benefit follows from that test result. The resident transition path now includes bounded daemon composition and verified A/B protocol, provenance, generation-declaration, and history-boundary checks; a production temporal A→B→A run remains uncollected.
## Read next

1. [Concise technical thesis](one_pager.md) — purpose, causal loop, and core distinctions.
2. [Documentation map](docs/index.md) — current architecture, maturity, and source navigation.
3. [Technical overview](docs/architecture/public_technical_overview.md) — runtime owners and present composition.
4. [Project thesis](docs/architecture/sentientos_project_thesis.md) — philosophical and architectural depth.
5. [Whole-system maturity report](docs/architecture/whole_system_maturity_report.md) — lifecycle maturity and remaining gaps at the selected source.
6. [Selected historical source-bound atlas](docs/architecture/repository_system_atlas_84c5687c.md) — exact census of its bound source tree, owner paths, configuration, temporal ordering, and unknowns.
7. [Trajectory and missing causal bridges](docs/architecture/sentientos_trajectory_and_missing_organs.md) — research and implementation frontier.
8. [Capability registry](sentientos/capability_registry.py) and [runtime composition](sentientosd.py) — inspect machine-readable declarations and actual wiring.

SHA-bound atlases are evidence snapshots; historical task and proof pages retain landing-time claims. A newer session may correct a conclusion when evidence or reasoning changes, not merely because the contributor changed.
