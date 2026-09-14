# Maintenance successor-generation adoption authority

`maintenance_successor_generation_adoption` is the separately governed bridge
between two existing maintenance contracts:

- `maintenance_authority_continuity` derives and proves a verified successor
  authority generation; and
- `maintenance_wake_daemon_adoption` identifies the currently active exact bounded
  wake owner and configuration.

This task registers only eligibility for a future
`deterministic_maintenance_successor_generation_adoption_controller`. It grants no
runtime authority and implements no owner handoff, generation derivation, daemon
start, maintenance work, wake continuation, process restart, module reload, or
resident Python-code adoption.

## Canonical inputs and verification boundary

A future controller may consume the exact canonical
`sentientos.maintenance_continuity_policy:v1`,
`sentientos.maintenance_authority_generation:v1`, and
`sentientos.maintenance_authority_continuity_receipt:v1` artifacts, together with
the exact active `sentientos.maintenance_wake_daemon_adoption:v1` document and its
bound maintenance wake configuration and dependency graph. It must verify that N+1:

- belongs to the exact same continuity lineage and is exactly one generation after
  the adopted N (never a caller-selected generation or an N-to-N+2 skip);
- is backed by the exact canonical continuity receipt;
- is same-or-narrower authority, does not extend inherited expiry, and remains
  inside the inherited validity window;
- binds the exact current repository successor state already proven by continuity;
  and
- has not been superseded or ambiguously adopted.

Newest-file or mtime selection and unsigned mutable “current generation” pointers
are never authority. Ambiguity fails closed.

## Persistent lineage posture

Operator approval establishes the bounded lineage-adoption posture. It is distinct
from fresh human approval for every successor handoff: the mature design deliberately
permits repeated, verified N-to-N+1 adoption while inherited authority remains valid.
Thus this boundary will eventually turn:

```text
derive N+1
-> operator manually switches wake configuration
```

into:

```text
derive N+1
-> verify N+1
-> bounded owner handoff
-> wake continues under N+1
```

without a new operator permission slip merely because each proven generation advanced
the repository. None of that runtime behavior exists after this admission task.

## Configuration bridge

The future implementation must reuse the canonical renderers and validators for the
maintenance watchdog, collector, autonomy-cycle, health-probe, wake-cycle, and
wake-daemon adoption artifacts. It must reuse base-independent artifacts when their
current validators permit that, and create new immutable artifacts only where bound
predecessor base or configuration identity requires them. The canonical
`successor_maintenance_configuration_generation_write` effect is reused for this
deterministic bridge; no parallel configuration system is authorized here.

## Target handoff protocol (not implemented)

A future effectful controller must:

1. verify the exact adopted generation and current wake owner;
2. verify exact N+1 and its continuity receipt;
3. construct and verify the successor maintenance configuration closure;
4. durably record handoff intent;
5. cooperatively stop N from starting new work;
6. allow an already-running bounded wake invocation to finish;
7. start N+1 ownership only after N is quiescent;
8. durably record successful successor adoption; and
9. resume bounded wake cadence under N+1.

Two generation owners must never run concurrently for one lineage. Crash ambiguity
fails closed, and successful successor adoption never automatically rolls back to an
older authority generation.

## Runtime-code and effect boundary

Wake/configuration generation adoption is not runtime code adoption. A long-running
`sentientosd` may continue executing generation-N code after repository files advance.
Restart, exec/re-exec, module reload, hot loading, and automatic resident-code adoption
remain separately governed future authority boundaries.

The registered effects confer no authority to widen or invent a generation, create or
admit candidates, issue maintenance leases, implement changes, validate, commit, mutate
Git refs, publish, merge, invoke providers or networks, inspect credentials, install OS
services/schedulers, perform maintenance directly, or restart `sentientosd`. A
continuity receipt alone cannot start a daemon, and eligibility is never a grant.

Future effectful task goals must affirm `verified successor authority generation`,
`exact continuity receipt`, `bounded wake owner handoff`, and `same lineage authority`.
A canonical admissible goal is:

> Implement bounded wake owner handoff to a verified successor authority generation
> with an exact continuity receipt under the same lineage authority.
