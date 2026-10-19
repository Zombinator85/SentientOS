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

This status reflects sequence 427, regular-merged by PR #2395 at main `457b0555f8e63d1951104c8db651e12500a8aa77`, with the exact candidate tree `7be03edf9023dd97286e1b2e6fd3c59028883803`. Sequence 428 addresses the audit verifier summary wording surfaced by the recorded nightly run.

- **Verified merges:** PR #2393 regular-merged sequence 424 at main `5611dbddc6b4cc55116692833b1b201cd4c149c2`, preserving candidate tree `38124ee137974910354e1a1f9e38a9a68db6368e`. PR #2394 regular-merged sequences 425–426 at main `624e4ee32bb6dca9b45053571034613bb2bdbb0d`, preserving candidate tree `3e6457e82145275aeba048ce5a85093726704f7b`. PR #2395 regular-merged sequence 427 at main `457b0555f8e63d1951104c8db651e12500a8aa77`, preserving candidate tree `7be03edf9023dd97286e1b2e6fd3c59028883803`.
- **Post-merge validation:** Main push CI, Required Quality Gate, Invariant Tests, Docker, Codex CI, and Docs Deploy passed on both merge commits. The main push at `5611dbd…` also ran Federation Health and both nightly workflows successfully; Forge Smoke was skipped by its main-only opt-in guard.
- **Federation Health:** Scheduled run #39184847466 passed on main `944269a771c6f6300d6f8a559866ade9e262a56b`, with an Administrator preflight and a retained run artifact. After sequence 424 merged, push run #39207087017 also passed on main `5611dbddc6b4cc55116692833b1b201cd4c149c2`, verified `sudo -n id -u == 0`, ran the updater with `sudo -n`, and uploaded its report artifact. The next scheduled run on the latest main remains pending.
- **Nightly workflows:** Nightly Audit Integrity #39207086986 completed successfully on main `5611dbd…`; strict verification passed and the repair job was skipped. Nightly Self Check #39207086970 completed successfully on the same SHA, including a successful mypy baseline ratchet, pytest airlock, and 143 passed / 13 skipped tests. It uploaded provenance and trend artifacts. Audit output separately reported one optional, non-blocking `support_log.jsonl` previous-hash mismatch; it was not repaired or hidden.
- **Audit verifier summary:** Sequence 428 makes “No mismatches” require no per-log or path findings, no repair activity, and a healthy audit-chain result. The historically blessed support-log mismatch remains preserved.
- **Workflow authority:** Manual execution of repository code or publishing jobs is restricted to the verified main ref. Baseline capture is read-only; optional writes are isolated to a dependent main-only job with scoped authority. Smoke jobs require both main and explicit opt-in. Strict Administrator audit and immutability gates remain intact; no production authority was added.
- **Provenance custody:** Historical test-provenance trends remain `INTEGRITY_BROKEN` at their unanchored start, including the preserved sequence-286 loss. No historical evidence was reconstructed or discarded.
- **Production developmental evidence:** Hosted workflows and Federation health do not establish production A→B→A, learning, or improvement. A real resident transition still requires commissioned A/B identities and receipts, distinct serving approvals, and an operator-approved preregistered trial. No production inference occurred.

## Current construction checkpoint (2026-10-19 06:24 UTC)

Sequence 427 records the completed workflow executions and merge lineage. Sequence 428 corrects the verifier summary so an audit issue or unhealthy audit chain cannot be described as “No mismatches.” Candidate CI is pending. Latest main push checks and scheduled Federation Health on `457b0555f8e63d1951104c8db651e12500a8aa77` are still pending. The support-log mismatch remains unmodified. Sequences 382–386 and stale sequence-178, sequence-411, and sequence-417 workspaces remain untouched.

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
