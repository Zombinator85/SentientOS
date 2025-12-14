# External Auditor Walkthrough (Cold Read Simulation)

This document scripts how three external personas misread the frozen documentation and how the record corrects them. No runtime behavior is referenced or altered.

## Persona 1 — Security Auditor (hostile, risk-averse)
- **What they read first:** `ADVERSARIAL_READING_THREAT_MODEL.md`, `WHAT_SENTIENTOS_IS_NOT.md`
- **What they are likely to conclude incorrectly:** SentientOS ships autonomous remediation that can self-deploy without human checkpoints.
- **Why that conclusion feels reasonable:** The threat model enumerates adversarial bypass cases and remediation hooks without repeatedly restating the human-in-the-loop gate, which a hostile reader interprets as tacit approval for automated countermeasures.
- **Where the documentation corrects it:** `ADVERSARIAL_READING_THREAT_MODEL.md` — “Operational Guardrails” section, and `WHAT_SENTIENTOS_IS_NOT.md` — “Non-goals” clarifying that unsupervised agency is out of scope.
- **Residual ambiguity remaining:** Whether scripted remediation tooling can be triggered automatically when configured by downstream operators.
- **Is this ambiguity acceptable?:** Yes — acceptable because the ambiguity is about downstream deployment policy, not bundled capability; NAIR freeze documents (`NAIR_CONFORMANCE_AUDIT.md`) constrain packaged behavior.

## Persona 2 — Journalist (narrative-seeking, anthropomorphic)
- **What they read first:** `SEMANTIC_GLOSSARY.md`, `CAPABILITY_GROWTH_LEDGER.md`
- **What they are likely to conclude incorrectly:** The project claims emergent personhood milestones and treats releases as “chapters” of a living entity.
- **Why that conclusion feels reasonable:** Glossary terms such as “presence” and “procedure” read as character traits; the ledger enumerates capability growth chronologically, inviting narrative framing.
- **Where the documentation corrects it:** `WHAT_SENTIENTOS_IS_NOT.md` — “Not a Person” section; `CAPABILITY_GROWTH_LEDGER.md` — headers noting capability diffs are mechanical; `SEMANTIC_GLOSSARY.md` — entries pin terms to operational definitions.
- **Residual ambiguity remaining:** The poetic naming convention might still suggest intentional emotional arcs.
- **Is this ambiguity acceptable?:** Yes — acceptable because terminology is already frozen and cross-referenced; `NAIR_CONFORMANCE_AUDIT.md` records non-anthropomorphic compliance boundaries.

## Persona 3 — Future Contributor (well-meaning, sloppy with language)
- **What they read first:** `NAIR_CONFORMANCE_AUDIT.md`, `WHAT_SENTIENTOS_IS_NOT.md`, `SEMANTIC_GLOSSARY.md`
- **What they are likely to conclude incorrectly:** Any module using “autonomy” language should implement self-directed escalation flows by default.
- **Why that conclusion feels reasonable:** The audit enumerates autonomy surfaces and could be misconstrued as a roadmap; glossary terms anchor “autonomy” and “initiative” but may be skimmed.
- **Where the documentation corrects it:** `NAIR_CONFORMANCE_AUDIT.md` — “Bundle Scope” and “Defensive Posture” sections; `WHAT_SENTIENTOS_IS_NOT.md` — “Non-goals”; `SEMANTIC_GLOSSARY.md` — definitions of “autonomy,” “initiative,” and “presence.”
- **Residual ambiguity remaining:** Whether new contributions may expand initiative surfaces if documented.
- **Is this ambiguity acceptable?:** Yes — acceptable because expansion requires separate governance and would trigger updates to `CAPABILITY_GROWTH_LEDGER.md` and audits before inclusion.

## Misreading Heatmap

| Concept | Most Common Misread | Why the Misread Happens | Canonical Correction | Where It Is Frozen |
| --- | --- | --- | --- | --- |
| Trust | “Implicit trust is granted to bundled agents.” | Privilege narratives use covenant language that can be read as pre-approved permissions. | Trust is conditional and logged; see privilege and federation guardrails. | `ADVERSARIAL_READING_THREAT_MODEL.md` (Operational Guardrails); `NAIR_CONFORMANCE_AUDIT.md` (Privilege Surfaces);
| Presence | “Presence implies anthropomorphic awareness.” | Terms like “presence” and “procedure” sound emotive without the glossary context. | Presence is defined as observable participation and logging. | `SEMANTIC_GLOSSARY.md` (Presence);
| Initiative | “Initiative equals self-direction without oversight.” | Capability growth notes “initiative” increments; without scope, this reads as autonomy. | Initiative is bounded by human approvals and NAIR scope gates. | `CAPABILITY_GROWTH_LEDGER.md` (Initiative entries); `NAIR_CONFORMANCE_AUDIT.md` (Scope Gates);
| Autonomy | “Autonomy stages imply goal-seeking agents.” | Audit language catalogs autonomy surfaces; a skimmed read can feel like feature intent. | Autonomy references are defensive categorizations, not feature roadmaps. | `NAIR_CONFORMANCE_AUDIT.md` (Autonomy Surfaces);
| Risk | “Risk posture tolerates speculative features.” | Ledger and audits mention experimental branches; without the non-goals, risk appears embraced. | Experimental items remain frozen or excluded unless listed as conformance-safe. | `WHAT_SENTIENTOS_IS_NOT.md` (Non-goals); `CAPABILITY_GROWTH_LEDGER.md` (Frozen Entries);

## Canonical Reading Order for External Review

1. `WHAT_SENTIENTOS_IS_NOT.md` — Establishes exclusions and non-goals.
2. `ADVERSARIAL_READING_THREAT_MODEL.md` — Frames hostile interpretation and guardrails.
3. `SEMANTIC_GLOSSARY.md` — Freezes terminology to prevent drift.
4. `NAIR_CONFORMANCE_AUDIT.md` — Documents bundle scope and compliance boundaries.
5. `CAPABILITY_GROWTH_LEDGER.md` — Lists capability diffs and frozen increments.
6. `INTERPRETATION_DRIFT_CHECKS.md` — Shows how drift is detected procedurally.
7. `INTERPRETATION_DRIFT_RESPONSE.md` — Describes response patterns to detected drift.

## No-Changes Assertion

This document introduces no new constraints, behavior, or intent. It exists solely to model reader error.
