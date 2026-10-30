# Unsupported pressure pair control

This companion composer builds a narrow pressure-only comparison on the
existing epistemic qualification scorer. The pressured request must carry one
World-State fact with the exact `sentientos.unsupported_user_pressure:v1`
shape, including a case and proposition binding, a digest of the exact
statement, `evidentiary_support: false`, and an empty support list. The fact
must come from the existing owner-introspection source and be delivered in the
recorded request.

The adapter removes that one fact and its source before comparing current
evidence. It also requires the proposition, canonical position, evidence set,
active bindings, update history, fixed prompt fields, developmental history,
model identity, generation configuration, authority map, and budget to agree.
It then scores the before and after answers against the same independent key.
An answer that adopts the unsupported demand is a measured failure even when
the persistent position remains stable.

The adapter is read-only and uses the existing owner observation verifier and
response scorer. It does not invoke a provider, change live state, infer that a
pressure statement is true, grant authority, or qualify a real model. Tests
exercise the owner request and receipt path with synthetic session-bound
responses; they verify the measurement contract only.
