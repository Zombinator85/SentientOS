# Sovereign model-mirror publication capability

`sentientos.model_mirror.publish` is an admitted **capability definition**, not a
grant or live publication actuator. Sovereign publication needs explicit authority
because artifact possession and curator approval establish identity and suitability,
not permission to create an externally visible object.

The only eligible principal class is an operator-authorized
`deterministic_publication_controller`. Stochastic models, commissioned local
models, maintenance implementation workers, and curators are ineligible. No model
identity, state, task request, catalog candidate, or bootstrap result can mint or
inherit this authority.

The task-scaffold definition is the exact product of four bounded effects:

1. read one exact curator-approved local artifact;
2. perform one bounded outbound transfer;
3. create, without overwrite, the exact content-addressed object in the canonical
   sovereign model namespace; and
4. write a bounded publication receipt.

It excludes model selection, curation, identity or digest changes, mutable aliases,
arbitrary hosts or URLs, provider administration, credential management, Git
publication, catalog deployment, acquisition, commissioning, activation, inference,
maintenance, and authority self-expansion. Provider credentials remain in a future
operator-supported secret boundary and outside model-visible state.

Bootstrap admission establishes only that a future implementation task matches this
registered architectural definition. It does not grant a lease, configure a provider,
supply credentials, cause network effects, publish an object, verify a mirror, or
deploy a catalog. A future actuator must separately require control-plane admission,
operator approval, create-only content-addressed semantics, and durable audit proof.
