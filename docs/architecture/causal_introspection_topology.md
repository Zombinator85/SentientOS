# Causal introspection topology

SentientOS composes introspection as a bounded collection of owner-local reports,
not as a system narrator. Each provider is explicitly registered and returns a
content-addressed, read-only projection. The compositor validates and orders
those projections mechanically, preserves disagreement, and writes an immutable
predecessor-bound generation. It does not decide which owner is right.

```text
              ┌─ installation
              ├─ model supply
              ├─ serving
              ├─ model/software succession
              ├─ maintenance
              ├─ authority/admission and effects
              ├─ World-State and self-model
              ├─ developmental history and epistemics
OWNERS ───────┼─ memory and causal resources
              ├─ embodiment
              ├─ federation
              └─ runtime supervision
                    │
                    ▼
          owner-local projections
                    │
                    ▼
        immutable bounded snapshot
                    │
           one-generation firewall
                    ▼
             later World-State
                    │
                    ▼
               cognition

       aggregation != synthesis
       observation != authority
```

## Common grammar

`CausalReference` carries a reference kind, identifier, digest, relationship,
schema, and source owner. It is a pointer to evidence—not the referenced grant,
admission, effect, or object. `OwnerObservation` accepts only bounded JSON and
binds an observation class, exact source references, freshness, evidence
posture, and one of `production`, `rehearsal`, `synthetic_test`, `historical`,
or `unknown`. Synthetic capture cannot claim production.

Every `OwnerIntrospectionProjection` has false truth, policy, goal, permission,
execution, admission, adoption, and source-mutation authority. Its semantic
trace carries WHO, WHY, MAY, WHAT_EXECUTED, WHAT_IT_COST, and WHAT_HAPPENED.
Missing dimensions say `not_observed`, `not_composed`, or `unknown`; unknown
cost is never zero-filled. MAY is an evidence reference only.

The validator rejects credential-shaped keys, arbitrary non-JSON values, raw
memory surfaces, allocation claims, synthetic-to-production upgrades, and an
effect-proof boolean without a qualifying effect/receipt reference. Serving
does not imply inference; epistemic state does not imply truth; federation does
not imply local authority or adoption; memory exposes custody metadata only.

## Custody and temporal firewall

`SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG` names an explicit versioned JSON file.
Configuration is absent-by-default, requires an absolute custody root, bounds
provider count, and names enabled and required domains. Providers are injected
explicitly: there is no scanning, reflection, or ambient owner discovery.

Generations are immutable `generation-N.json` objects. Their digests cover the
ordered projection inventory, findings, conflicts, predecessor digest, capture
tick, and optional repository identity. Restart reconstruction verifies every
projection and predecessor. A partial provider failure retains successful
projections but records only a bounded error class/code—never a traceback.

During maintenance tick N, World-State is built first, then cognition,
transition handling, epistemic development, longitudinal reconciliation, and
other closures run. Introspection capture is the final closure. World-State
selects only a verified snapshot whose numeric generation precedes the pending
capture generation; it never parses a tick string for chronology. Thus capture
N can appear only as independently attributable `owner_introspection` evidence
in a later board. Cognition receives it through the ordinary World-State path,
not hidden model context. Introspection itself calls no model and creates no
action bridge.

## Coverage and remaining frontier

The machine-readable `COVERAGE_MANIFEST` in
`sentientos/causal_introspection.py` records implemented and partial domains.
Installation, model supply, software succession, effects, canonical memory,
causal resources, and federation remain deliberately partial where an owner
cannot support broader safe metadata. Partial coverage is not subsystem
absence, health, or readiness.

The remaining frontier is production breadth and independently validated owner
introspection, physical/resource owner coverage where enforcement does not yet
exist, and long-run stability across real software/model succession. Runtime
composition alone is not production evidence.

## Claims deliberately not made

- No omniscient self-model or canonical narrator.
- No objective/current truth, persistent personal identity, consciousness,
  sentience, or personhood from introspection.
- No authority, permission, admission, effect, or owner mutation.
- No resource allocation where only principal attribution exists.
- No physical embodiment from synthetic or renderer-only evidence.
- No inference from serving, adoption from federation receipt, learning from
  developmental history, beneficial development, or production evidence from
  runtime composition.
