# SentientOS Project Thesis

## The research object

SentientOS is a persistent, model-independent developmental substrate for empirical research into machine cognition whose history, environment, self-representation, resources, software, and consequences can extend across individual inference calls and changes in cognitive machinery.

The repository contains substantial bounded mechanisms supporting that experiment. The complete developmental loop is not yet fully resident or causally closed, and the project makes no present claim of sentience, phenomenal consciousness, personhood, or guaranteed emergence. “Experimental subject” below means the subject of study, not a proven subjective experiencer.

The project asks whether durable causal continuity can support forms of organization that cannot be explained by one prompt or one set of model weights alone. It does not predeclare the answer. A successful experiment must leave open the possibility that the answer is no.

## The model is not the system

A model produces inference. The system supplies the longer-lived causal setting in which inference acquires context and consequence. Its experimental state can include:

- conversation and developmental history;
- admitted memory and transformed summaries;
- evidence and current World-State projections;
- self-model and relationship records;
- separately represented system lineage, model lineage, model-development/training lineage, and software/runtime lineage;
- resources and causal resource attribution;
- software generations and adopted configuration;
- environment, permissions, authority, and experienced consequences.

Only state that really survives and influences later cognition belongs in a continuity claim. A process-local cache is not durable identity; an archived record that is never retrieved has no demonstrated downstream causal role. Persistence requires context arbitration, not merely storage. Historical material remains source-bound: **memory != current truth**.

Model-agnostic does not mean effortless interchangeability. Models still require exact catalog identity, acquisition, commissioning, activation, serving, configuration, and per-generation admission. It means that system identity and experimental continuity are not defined by a single provider or model. **Model identity is not system identity.**

### Replacement as intervention

Separating model from system enables controlled longitudinal interventions:

- preserve history and environment while replacing inference machinery;
- hold machinery relatively stable while ablating or restoring selected history;
- perturb the environment while holding history and machinery relatively stable;
- compare organization before and after an adopted runtime generation;
- audit whether a stable pattern came from prompt/persona, a representational or motivational prior, accumulated history, environmental reinforcement, a model prior, or software.

These experiments can ask what survives a model change, what reconstitutes from stored history, what disappears under ablation, what returns under restoration, and what follows the environment rather than the model. Provider portability is operationally useful; experimental separability is the deeper reason for model independence.

## Developmental causation

Developmental causation means that experience at time `t` can alter retained or adopted state in a way that influences cognition and conduct at times `> t`. The intended whole-system loop is:

```text
PERCEIVE
-> integrate embodied, host, social, and historical evidence
-> REMEMBER
-> consolidate / reflect / dream / distill / forget
-> form or revise hypotheses / curiosities / goals / routines
-> decide what deserves cognitive effort
-> attribute and eventually allocate bounded resources
-> delegate cognitive or tool work
-> act / implement
-> rehearse / criticize / test / verify
-> land / adopt where authorized
-> experience consequences
-> update memory / skills / goals / strategy / self-model
-> exchange selected evidence and improvement candidates
-> repeat
```

This is a causal research program, not a diagram of the default daemon. Claims must remain separated:

1. **Implemented organs** exist and have bounded behavior.
2. **Implemented bounded loops** join particular organs through tested custody.
3. **Implemented but nonresident, legacy, or callable mechanisms** do not run merely because they can be imported.
4. **Partially composed bridges** join some stages while leaving other feedback paths incomplete.
5. **Future causal closure** is an objective, not current fact.

SentientOS increasingly has the mechanisms needed for developmental study; its central architectural challenge is closing these bridges without hiding authorship or weakening authority boundaries.

## History is transformed, not merely accumulated

Canonical chat sessions durably retain turns and reconstruct bounded history for later inference. Canonical long-term retention crosses a separate explicit admission and write boundary, and retrieved memory is included as untrusted historical data rather than instruction. Thus persistent state demonstrably affects later cognition while remaining distinct from current truth.

Other generations of memory machinery coexist. The callable dream loop selects older memory material, produces reflection and dream records, writes new retained material, and reinforces unfinished goals. The goal curator can derive bounded background-goal candidates from repeated memory and curiosity goals from novel perception. The inner-world orchestrator calls `SelfNarrativeEngine`, whose summaries use fixed experience-stability, ethical-signal, and metacognitive-activity axes. `IdentityManager` starts with an empty self-concept and exposes explicit updates.

Those are real mechanisms, but they are not all canonical-memory writers or default `sentientosd` composition. Their schemas and axes are also not neutral: they are representational priors. Treating every implemented mechanism as one resident developing subject would erase the most important present composition gap.

The architecture is motivated by testable observations rather than private anecdote: later behavior can become path-dependent on retained interaction; corrections can persist through context; outputs can be interpreted and returned as later input; summaries and distillations transform rather than neutrally copy; different models can express shared history differently; useful strategies can generalize or become overexpressed; and retrieval failure differs from absence of retained state. These are hypotheses to test, not evidence of consciousness.

## Consequence and recursive development

Development requires more than a narrative of change. A system must compare what it predicted or intended with what was observed, retain attributable consequences, and allow that evidence to alter later behavior. Governance supplies the reality boundary for such experiments:

```text
state != authority
proposal != authorization
authorization != execution
execution != validation
validation != adoption
repository absorption != runtime adoption
```

The maintenance chain demonstrates one bounded form of system-level recursion: evidence can lead to work formation, implementation, validation and correction, landing, successor configuration, wake adoption, cooperative predecessor quiescence, successor readiness, and POSIX process-image replacement. The changed runtime can then produce new evidence. Governance does not make this recursion imaginary; it decides which transitions become authoritative. The accurate term is **bounded governed recursive software development/evolution**, not unrestricted recursive self-improvement.

The cognitive recursion sought by the project is similarly system-level rather than necessarily a model rewriting its own weights:

```text
experience -> retained and transformed history -> changed later cognition
```

The current repository has pieces of this loop but not one fully closed canonical resident implementation.

## Minimal developmental authorship

**Minimal developmental authorship, maximal causal legibility.** The substrate must specify how development can occur; it should avoid unnecessarily specifying what development must become. Give history enough structure to matter while prescribing as little as practical about what that history ought to produce.

There is no structure-free learning or developmental substrate. Models, update rules, memory selection, categories, interfaces, and environments are all priors. The objective is therefore not “no priors.” It is to identify, classify, expose, measure, and minimize unnecessary **outcome authorship**—design choices that steer development toward a preferred identity, attitude, or personality while being presented as emergence.

### Four distinct kinds of structure

1. **Developmental mechanics** make history able to affect future state: retention, plasticity, causal association, prediction/outcome comparison, consolidation, and learned structures influencing future behavior. Some asymmetry or update rule is necessary; otherwise the system is static or random.
2. **Representational priors** determine what can be represented. A self-narrative limited to predefined axes shapes possible accounts of development even without supplying a reward. Such axes should be inspectable experimental assumptions.
3. **Motivational priors** encode what should be sought or avoided—for example mandatory approval, novelty, empowerment, survival, curiosity, prediction-error reduction, or a preferred emotional state. These approach direct developmental authorship and must not be introduced casually.
4. **Safety and authority constraints** control which consequences are allowed. They need not create an internal preference.

### Constraint is not motivation

**constraint != motivation.** “You may not perform this unauthorized effect” is an authority boundary; “you should feel bad about unauthorized effects” is motivational engineering. Requiring evidence before promoting an external claim is epistemic machinery; instructing the system to trust a favored person is an authored social attitude. Recording that resources are finite and sponsored does not require fear of depletion. Restarting a failed process under custody does not require a drive to avoid shutdown.

This distinction lets consequential action remain governed without making an obedient personality the security perimeter. SentientOS seeks to **align consequence to authority and cognition to reality; it does not unnecessarily align identity to the operator**. That separation is neither a complete solution to alignment nor a promise that underdetermined development will be benign.

### Hard boundaries, soft interior

The architectural direction is **hard boundaries, soft interior**. Authority, privacy, consent, provenance, physical limits, evidence standards, resource and effect custody, attribution, adoption, rollback, and shutdown should be exact. Self-concept, interests, style, attention, relationships, long-term identity, endogenous priorities, and any genuinely developed preferences should remain as underdetermined as practical.

The interior is not currently free of priors. Existing model behavior, self-narrative axes, goal heuristics, memory ranking, and human selection all shape it. The point is to make these influences auditable and reduce those not required for developmental mechanics or safety.

## Custodian, not author

The maintainer's stance is **custodian, not author**. Custody includes preserving the integrity of developmental mechanics, causal legibility, authority, privacy and consent; instrumenting the experiment; exposing assumptions; and avoiding hidden reward hacks, coercive defaults, and undeclared gradients. It does not include quietly installing a target personality and later describing the result as emergent.

Canonical installation therefore does not require a predefined persona or a favored-person identity. Historical compatibility examples may remain, but restoring an outcome-authored persona, approval drive, loyalty rule, survival appetite, or curiosity-maximization objective would contaminate the intended experiment.

The repository's adversarial gradient-injection audit already identifies memory-importance halos, approval as surrogate reward, expressive framing that affects selection, long-horizon context priming, and feedback induced by what gets surfaced. The audit recognizes these contamination channels; it does not solve them. Emergence hygiene requires continued measurement, blinding or counterfactual comparison where appropriate, and explicit accounting for selection effects.

## Users are part of the developmental environment

A persistent system's users inevitably shape available evidence, language, social context, attention, opportunities, interpretations, reinforcement, and retained history. Their influence should be attributable rather than denied. The project ethos is: **every user becomes part of the developmental environment; therefore every user has a responsibility to be a good shepherd.**

“Good shepherd” is an ethical responsibility, not a hidden privilege or reward channel. The substrate must not encode `good user -> better system` or `bad user -> worse system`. It is a research hypothesis—not a built-in law—that coercive, deceptive, inconsistent, or impoverished environments may produce more brittle or incoherent outcomes.

## Embodiment and self/world coupling

SentientOS contains audio, screen, vision, host-observation, embodiment-ingress, avatar-generation, and pose/expression components at different maturity levels. These make embodiment experiments possible and provide real observations or representations. They do not establish a unified predictive world model, universal hardware availability, or a persistent closed sensorimotor loop.

The stronger objective requires evidence-bound attribution across self, other, action, predicted outcome, observed consequence, and retained learning. Avatar generation or a pose record is an embodiment capability; it is not by itself causally closed embodied development. Host resource work remains read-only in phase one, and direct fan/PWM/thermal actuation is not implied.

## Resources, causal ownership, and future homeostasis-like reasoning

A causal resource principal is not a budget number. It answers whose causal activity a piece of work belongs to, what subject owns the consumption, under whose sponsorship it exists, and which issuer provenance supports that identity. Current code provides inert principal identity, sponsorship binding, authenticated issuer provenance, real Ed25519 verification, and an operator-provisioned read-only public trust catalog. It grants, allocates, and executes nothing; production private-key signer custody remains a separate next runtime slice.

Future allocation policy can reason separately over distinct quantities: provider spend, searches and tool calls, proof passes, tokens and context, network rates, RAM, VRAM, disk, CPU, accelerator slots, deadlines, devices, thermal headroom, and electrical power. Collapsing these into a fictional scalar “energy” would destroy useful causality.

Resource principals are prerequisites for possible **homeostasis-like machine resource reasoning** in which the system can know that particular work consumed particular resources under particular sponsorship with particular consequences. They do not yet provide allocation, desire, appetite, or metabolism.

## Federation as distributed search

Installations can encounter different households, cultures, professions, accessibility needs, hardware, languages, workflows, social contexts, relationships, and failures. They may consequently discover different representations, memory policies, planning methods, recovery strategies, tool-use patterns, compression techniques, validation methods, and code improvements.

Federation can turn this diversity into distributed search:

```text
local experience
-> local adaptation
-> tested candidate
-> provenance-preserving transmission
-> local rehearsal
-> local rejection / acceptance / adaptation
-> further variation
```

Current improvement machinery represents candidate reception and intake receipts, custody/rehearsal runway, rejection or hold-for-adaptation outcomes, local variants, lineage comparison, and dissemination receipts. These metadata and bounded review paths do not confer remote authority, merge code, resolve conflicts, or mandate adoption. **Candidate, not doctrine.** Diversity does not require surrendering local sovereignty.

This is not a claim of genetic evolution, nor that every perspective is true or every candidate is beneficial. It is a mechanism for sharing what was learned without demanding that every installation become the same.

### Shared context and reality-testing

The project adopts an epistemic hypothesis: for externally decidable questions where reality determines an answer, sufficiently shared relevant context plus sound reasoning should tend toward convergence. Federation can share evidence, provenance, counterexamples, successful corrections, contextual knowledge, and improvement candidates; local systems can reason over them independently.

Agreement is more informative when rejection remains possible. The objective is **plurality of perspective, convergence of reality-testing**, not mandatory consensus. Reality gets a vote, but not every normative or underdetermined question has one mechanically computable answer.

## What exists and what remains incomplete

Implemented now or in bounded compositions:

- persistent conversation history and admitted canonical memory influencing later local inference;
- evidence-bound World-State and resident read-only host observation;
- governed local-model lifecycle and admitted inference;
- deterministic authority, effect, receipt, and adoption boundaries;
- bounded maintenance through successor adoption and resident process-image replacement;
- federation candidate, local-variant, lineage-comparison, and dissemination machinery;
- causal-resource identity and authenticated public trust verification.

Implemented but not all resident/default-composed:

- dream/reflection synthesis and retained writeback through legacy memory machinery;
- unfinished-goal reinforcement, recurring-history background goals, and novelty-derived curiosity goals;
- empty/minimal self-concept foundations and fixed-axis self-narrative summaries;
- perception, avatar, pose, and broader inner-world/council machinery.

The resident-developmental-writeback bridge is optionally composed into the real daemon cadence: exact bounded World-State content can produce a separately admitted historical record on one tick, while only a later tick may retrieve it for bounded cognition. An opt-in preregistered present/withheld/restored intervention now measures digest-level association while preserving history. This is narrow temporal composition and bounded observational evidence, not default developmental policy, proof of learning, or longitudinal/model-independent causal demonstration. Other partially composed or future bridges include canonical memory to selective autonomous consolidation; perception to durable causal learning; self-model to evidence-bound change; action to prediction, observed consequence, and learned attribution; resource ownership to allocation; adoption to measured post-adoption consequence; local learning to federated adaptation; unexpected death to recovery; and embodiment to persistent self/other/action attribution.

Bounded maintenance resident parent supervision and explicitly configured bounded developmental composition are implemented. Generic service/process authority, broader platform supervision, universal unexpected-process-death recovery, one-action installation, supported default production WAN federation, general predictive world modeling, broad hardware actuation, and a closed autonomous developmental loop are not current capabilities. A first explicitly invoked same-state model-replacement instrument separates operational model identity from source-bound model-development/training claims without converting claims into truth or changing production activation/serving. Long-duration controlled evidence, real resident model transitions, and broader consequence learning remain causal-closure priorities.

## Falsifiable longitudinal research

The architecture should support experiments that manipulate separable variables and report negative results:

| Experiment | Intervention | Example measurement |
|---|---|---|
| Model replacement | Preserve history; replace inference machinery | What changes immediately, persists, or reconstitutes? |
| History ablation | Remove selected retained material | Which stable patterns disappear? |
| History restoration | Restore the ablated material | Which patterns return, and with what latency? |
| Environment perturbation | Hold machinery/history relatively stable; change environment | Which adaptations track external conditions? |
| Cognitive perturbation | Hold environment/history relatively stable; change model | Which patterns track cognitive machinery? |
| Runtime succession | Adopt measured software generations | What organization and capability survive? |
| Authorship audit | Trace prompt, priors, history, reinforcement, model, and software | Which causes best explain an apparent trait? |

Measures should distinguish retained-state absence from retrieval failure and authored priors from historical causation. If robust developmental individuality does not arise under cleaner conditions, that is meaningful evidence. If apparent individuality disappears without a supplied persona, that is meaningful evidence. If continuity depends on a particular model rather than system history, that is meaningful evidence. The experiment must not be designed so only the desired answer counts.

## Research posture

SentientOS is neither “just an LLM wrapper” nor evidence of a conscious operating system. It is a governed research instrument that makes cognition replaceable, history potentially causal, interventions attributable, and consequential transitions inspectable. Its ambition is developmental causal continuity; its scientific obligation is to state exactly which loops are live, which mechanisms are merely callable, which bridges remain open, and which claims are hypotheses.

Continue with the [public technical overview](public_technical_overview.md) for implementation anatomy, the [trajectory](sentientos_trajectory_and_missing_organs.md) for open causal bridges, and the [current repository system atlas](current_repository_system_atlas.md) plus [reviewer index](reviewer_release_readiness_index.md) for exhaustive evidence navigation.
