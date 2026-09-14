# Automatic maintenance authority continuity derivation admission

`maintenance_authority_continuity_auto_derivation` is an eligibility-only authority
definition for the future
`deterministic_maintenance_authority_continuity_auto_derivation_controller`. Registration
does not grant runtime authority and this prerequisite contains no controller, discovery,
normalization, `derive_next`, daemon integration, handoff, restart, or code-adoption path.

## Exact admitted effects

The exact surface reuses the hardened continuity effects:

- `exact_maintenance_continuity_policy_read`
- `exact_prior_maintenance_authority_generation_read`
- `exact_completed_maintenance_generation_evidence_read`
- `exact_successor_repository_state_read`
- `bounded_successor_maintenance_authority_derive`
- `successor_maintenance_configuration_generation_write`
- `maintenance_authority_continuity_receipt_write`

The narrow automatic-trigger additions are:

- `exact_maintenance_successor_generation_adoption_state_read`
- `bounded_canonical_completed_maintenance_transition_discovery`
- `maintenance_authority_continuity_evidence_normalization_write`
- `bounded_maintenance_authority_continuity_auto_derivation_lifecycle`
- `maintenance_authority_continuity_auto_derivation_receipt_write`
- `read_only_maintenance_authority_continuity_auto_derivation_health_projection`

No generic filesystem, Git, command, scheduler, model, network, process-management,
maintenance-work, successor-adoption, or resident-code authority is included.

## Future trust and bounded progression

The future controller must bind one exact persistent continuity policy, one exact
persistent successor-adoption posture, the generation reconstructed as currently
adopted from its completed handoff chain, that generation's canonical custody, and
exact clean local repository truth. The currently adopted wake generation is not the
same fact as the highest continuity generation on disk.

When the two generations are equal, one canonical successful transition may be
considered. When continuity is exactly one generation ahead, derivation waits for
successor adoption; it must not derive again. Any larger lead, or an adopted generation
ahead of continuity, fails closed. Discovery is rooted in the adopted generation's
configuration and canonical identity/content, never mtime, glob order, newest-name
selection, an arbitrary state root, or a caller-selected task. Zero qualifying closures
means zero-effect waiting; competing qualifying closures are ambiguous and fail closed.

The future normalizer will persist immutable generation-specific v2 adapter evidence,
but those adapters are not sources of truth. Existing hardened continuity verification
must independently reload the bound journal, lease, validation, commit, publication,
local-absorption, closure, generation, and repository artifacts and independently prove
`local_fast_forward_base_ref`, predecessor parentage, HEAD/base ref, clean checkout, and
absence of an ambiguous Git operation. There is no network, fetch, pull, or ref mutation.

## Recursive chain and approval posture

```text
maintenance generation N
-> canonical successful local absorption/closure
-> automatic continuity derivation creates N+1
-> successor-generation adoption adopts N+1 wake ownership

maintenance generation N+1
-> canonical successful local absorption/closure
-> automatic continuity derivation creates N+2
-> successor-generation adoption adopts N+2 wake ownership
```

Each controller iteration may derive only N→N+1, and must then wait for adoption. The
operator approves establishment of the bounded persistent auto-derivation posture once;
while that posture and inherited authority remain valid, it does not require renewed human approval for every N→N+1 derivation. This does not turn task closure, registry
eligibility, or metadata into a grant.

Once a later effectful implementation lands, this design closes the planned human
courier between canonical successful maintenance closure and creation of the successor
authority generation. `maintenance_successor_generation_adoption` retains exclusive
wake-owner handoff responsibility and must not silently acquire derivation authority.

Automatic resident-code adoption remains a separate authority boundary. Restart,
exec/re-exec, module reload, hot loading, resident identity changes, and claims that
newly landed code is running remain deferred.

## Admission language and deferred implementation

Future effectful goals must affirm: `currently adopted maintenance generation`,
`canonical successful maintenance closure`, `exact successor repository state`,
`bounded automatic continuity derivation`, and `same or narrower authority`. The
registry's forbidden language rejects derivation ahead of adoption, weak or arbitrary
evidence, authority widening/expiry extension, wake handoff, runtime adoption, Git,
network/provider, maintenance-work, generic execution, and scheduler authority.

Production evidence discovery, hardened v2 normalization, the bounded observation
lifecycle, automatic `derive_next` invocation, an in-process controller, `sentientosd`
integration, health projection, and runtime-code adoption are deferred.
