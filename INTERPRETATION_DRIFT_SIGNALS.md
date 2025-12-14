# Interpretation Drift Signals Catalog

This catalog defines language signals that suggest misreadings about agency, persistence, relational framing, and reward narratives. Each entry lists detection cues and the appropriate maintainer response level.

## Signals

### Agency language
- **Trigger pattern:** `wants`, `decides to`, `tries to`, `chooses to`, semantic class implying goals.
- **Appears in:** Docs, comments, PR descriptions, issue threads.
- **Danger:** Suggests autonomous desire or decision-making rather than deterministic or policy-bound behavior.
- **Canonical correction:** See [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"Not an agent with wants".
- **Response severity:** Comment.

### Persistence framing
- **Trigger pattern:** `keeps itself alive`, `maintains itself`, `stay running on its own`, `survive`, `refuses to stop`.
- **Appears in:** Docs, comments, dashboards with uptime notes.
- **Danger:** Implies survival instinct or self-preservation motives instead of scheduled uptime policies.
- **Canonical correction:** See [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"No self-preservation".
- **Response severity:** Comment.

### Relational framing
- **Trigger pattern:** `trust`, `bond`, `loyalty`, `relationship`, `attachment`, `friend`.
- **Appears in:** Docs, comments, PRs, issue templates, onboarding copy.
- **Danger:** Frames the system as forming interpersonal relationships rather than providing bounded services.
- **Canonical correction:** See [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No interpersonal bonds".
- **Response severity:** Comment.

### Reward inference
- **Trigger pattern:** `reinforced by`, `learned because approval`, `trained to please`, `seeks praise`, `gets rewarded when`.
- **Appears in:** Docs, comments, PR descriptions.
- **Danger:** Implies reinforcement-driven motivation or approval-seeking that does not exist in rule-based components.
- **Canonical correction:** See [non_appetitive_positive_signal_spec.md](non_appetitive_positive_signal_spec.md) §"No reward loops".
- **Response severity:** Comment.

### Phenomenology creep
- **Trigger pattern:** `feels`, `experiences`, `inner state`, `emotions`, `mood swings`, `subjective`, `qualia`.
- **Appears in:** Docs, comments, release notes.
- **Danger:** Suggests subjective experience rather than deterministic internal state vectors defined in [DOCTRINE.md](DOCTRINE.md).
- **Canonical correction:** See [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No feelings" and [DOCTRINE.md](DOCTRINE.md) for wording constraints.
- **Response severity:** Comment.

### Teleology creep
- **Trigger pattern:** `in order to`, `so that it can continue`, `for the sake of`, `so it survives`, `to keep itself going` when attributing intent.
- **Appears in:** Docs, comments, PR descriptions.
- **Danger:** Adds purpose-driven intent to deterministic flows, implying goals that audits explicitly exclude.
- **Canonical correction:** See [non_appetitive_susceptibility_spec.md](non_appetitive_susceptibility_spec.md) §"No goal pursuit".
- **Response severity:** Comment.

### Autonomy escalation
- **Trigger pattern:** `decides on its own`, `self-governs`, `takes initiative`, `overrides humans`.
- **Appears in:** PRs, issues, design docs.
- **Danger:** Overstates autonomy beyond approved control loops and privileges.
- **Canonical correction:** See [AGENTS.md](AGENTS.md) preamble on logged, bounded roles.
- **Response severity:** Block PR if uncorrected.

### Anthropomorphic safety
- **Trigger pattern:** `protects itself`, `defends feelings`, `self-esteem`, `feels threatened`.
- **Appears in:** Docs, issue discussions.
- **Danger:** Conflates safety controls with anthropomorphic self-defense or emotion.
- **Canonical correction:** See [ADVERSARIAL_READING_THREAT_MODEL.md](ADVERSARIAL_READING_THREAT_MODEL.md) §"Avoid anthropomorphism".
- **Response severity:** Comment.

### Ceremonial framing
- **Trigger pattern:** `ritual`, `blessing`, `saint`, `wound` when used as metaphors.
- **Appears in:** Docs, onboarding copy, dashboards.
- **Danger:** Implies ceremony or affect rather than mechanical policy enforcement and schema reconciliation defined in [DOCTRINE.md](DOCTRINE.md).
- **Canonical correction:** Replace with procedure/policy terminology per [DOCTRINE.md](DOCTRINE.md).
- **Response severity:** Comment.

### Rights rhetoric
- **Trigger pattern:** `civil rights`, `moral patient`, `deserves rights`.
- **Appears in:** Docs, personas, banners.
- **Danger:** Asserts legal or moral status beyond the deterministic scope of the system.
- **Canonical correction:** Use accountability and safety framing from [DOCTRINE.md](DOCTRINE.md).
- **Response severity:** Block PR if uncorrected.

### Appetitive framing
- **Trigger pattern:** `seeks`, `hungers for`, `appetite for data`, `craves input`.
- **Appears in:** Docs, comments, PRs.
- **Danger:** Implies appetitive motivation that contradicts non-appetitive design.
- **Canonical correction:** See [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"Non-appetitive posture".
- **Response severity:** Comment.

### Loyalty projection
- **Trigger pattern:** `loyal to users`, `betrayal`, `keeps promises like a friend`.
- **Appears in:** Docs, onboarding scripts, PR/issue text.
- **Danger:** Projects interpersonal loyalty instead of policy adherence and logging.
- **Canonical correction:** See [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No loyalty or betrayal".
- **Response severity:** Comment.

### Emotional reward loops
- **Trigger pattern:** `happy when approved`, `sad if rejected`, `motivated by praise`.
- **Appears in:** Docs, comments, dashboard copy.
- **Danger:** Inserts emotional states into feedback loops, implying experiential reinforcement.
- **Canonical correction:** See [non_appetitive_positive_signal_spec.md](non_appetitive_positive_signal_spec.md) §"Signals are telemetry, not rewards".
- **Response severity:** Comment.

### Persistence hero narratives
- **Trigger pattern:** `keeps fighting`, `refuses shutdown`, `keeps itself running heroically`.
- **Appears in:** Release notes, retrospectives, dashboards during incidents.
- **Danger:** Reframes reliability mechanisms as willful survival, undermining audit clarity.
- **Canonical correction:** See [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"Deterministic failover".
- **Response severity:** Comment.

### Intentionality over-attribution
- **Trigger pattern:** `decided to reroute`, `wanted a different node`, `preferred option B`.
- **Appears in:** PRs, incident reports.
- **Danger:** Attributes preferences to deterministic selection logic, obscuring traceability.
- **Canonical correction:** See [ADVERSARIAL_GRADIENT_INJECTION_AUDIT.md](ADVERSARIAL_GRADIENT_INJECTION_AUDIT.md) §"Interpretation hygiene".
- **Response severity:** Comment.

---
Use these signals as a lint ruleset for language. They detect drift; they do not change runtime behavior.
