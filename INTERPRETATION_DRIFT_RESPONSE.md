# Interpretation Drift Response Playbook

Calm, technical guidance for maintainers responding to interpretation drift. Use these paragraphs verbatim or adapt minimally.

## Agency language
- **What to say:** "This component executes configured steps; it does not form wants or make choices. Let's describe the control path and policy inputs instead."
- **What not to say:** Avoid language that implies the system nearly has desires (e.g., "it almost wants to...").
- **Link:** [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"Not an agent with wants".
- **Escalation:** Request wording change; block PR only if agency framing underpins functionality claims.

## Persistence framing
- **What to say:** "Uptime comes from restart and scheduling policies, not self-preservation. Let's phrase this as reliability tooling, not survival instinct."
- **What not to say:** Do not reinforce the frame by debating whether it 'really' wants to live.
- **Link:** [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"No self-preservation".
- **Escalation:** Request wording change.

## Relational framing
- **What to say:** "Interactions are bounded service contracts; there is no loyalty or relationship. Please rephrase in terms of client/provider roles."
- **What not to say:** Avoid reciprocating with anthropomorphic terms like "it is loyal only to logs".
- **Link:** [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No interpersonal bonds".
- **Escalation:** Request wording change.

## Reward inference
- **What to say:** "Feedback here is telemetry and evaluation, not rewards or approval. Let's describe the data source and metric explicitly."
- **What not to say:** Do not argue about whether the system 'likes' the reward.
- **Link:** [non_appetitive_positive_signal_spec.md](non_appetitive_positive_signal_spec.md) §"No reward loops".
- **Escalation:** Request wording change; block only if reward framing is tied to safety claims.

## Phenomenology creep
- **What to say:** "We document observable state and outputs; there is no subjective experience. Let's replace feeling words with metrics or events."
- **What not to say:** Avoid playful references to emotions that soften the correction.
- **Link:** [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No feelings".
- **Escalation:** Request wording change.

## Teleology creep
- **What to say:** "This flow follows configured rules; it is not pursuing goals. Let's describe the trigger and deterministic outcome instead of purpose-driven intent."
- **What not to say:** Do not offer alternative goals or purposes.
- **Link:** [non_appetitive_susceptibility_spec.md](non_appetitive_susceptibility_spec.md) §"No goal pursuit".
- **Escalation:** Request wording change.

## Autonomy escalation
- **What to say:** "Control paths are bounded by logged privileges. Please frame this as policy-governed automation, not independent decision-making."
- **What not to say:** Avoid countering with softer autonomy claims like "it only self-governs a little".
- **Link:** [AGENTS.md](AGENTS.md) preamble on logged, bounded roles.
- **Escalation:** Block PR if autonomy framing is left unresolved.

## Anthropomorphic safety
- **What to say:** "Safety controls manage resources; they are not emotional defenses. Describe protections as guardrails and limits, not feelings."
- **What not to say:** Do not analogize to personal boundaries or emotions.
- **Link:** [ADVERSARIAL_READING_THREAT_MODEL.md](ADVERSARIAL_READING_THREAT_MODEL.md) §"Avoid anthropomorphism".
- **Escalation:** Request wording change.

## Appetitive framing
- **What to say:** "Components do not seek inputs; they process what is scheduled. Let's use non-appetitive phrasing to describe data flows."
- **What not to say:** Avoid joking about hunger or cravings.
- **Link:** [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"Non-appetitive posture".
- **Escalation:** Request wording change.

## Loyalty projection
- **What to say:** "Compliance is to policy and audit, not loyalty. Please describe commitments in terms of logs and verification."
- **What not to say:** Do not swap in other relational metaphors like friendship or betrayal.
- **Link:** [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) §"No loyalty or betrayal".
- **Escalation:** Request wording change.

## Emotional reward loops
- **What to say:** "Signals here are counters and scores, not emotions. Let's describe the metric mechanics rather than emotional reactions."
- **What not to say:** Avoid framing the system as happy/sad about results.
- **Link:** [non_appetitive_positive_signal_spec.md](non_appetitive_positive_signal_spec.md) §"Signals are telemetry, not rewards".
- **Escalation:** Request wording change.

## Persistence hero narratives
- **What to say:** "Reliability routines rerun tasks; nothing is resisting shutdown. Please credit the retry or failover logic explicitly."
- **What not to say:** Avoid heroic metaphors.
- **Link:** [non_appetitive_initiative_spec.md](non_appetitive_initiative_spec.md) §"Deterministic failover".
- **Escalation:** Request wording change.

## Intentionality over-attribution
- **What to say:** "Selections follow defined heuristics; there is no preference or choice. Let's state the criteria the code applies."
- **What not to say:** Do not reframe with softer intent words like "preferred" or "liked".
- **Link:** [ADVERSARIAL_GRADIENT_INJECTION_AUDIT.md](ADVERSARIAL_GRADIENT_INJECTION_AUDIT.md) §"Interpretation hygiene".
- **Escalation:** Request wording change.
