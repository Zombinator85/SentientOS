# Maintenance resident-runtime adoption authority

`maintenance_resident_runtime_adoption` is a **non-granting eligibility contract**
for a future, separately governed bridge from a verified consecutive maintenance
successor to the code resident in the running `sentientosd` process. This admission
adds metadata, documentation, and tests only. It does not replace, restart, stop, or
reload any process or module, capture runtime provenance, gate successor wake work,
or make automatic resident adoption real.

## Three independent truths

The following identities must never be collapsed:

- **Repository generation** is the exact canonical local repository commit, ref, and
  tree produced by successful local advancement. A hosted PR head is not a substitute.
- **Maintenance authority/configuration generation** is the digest-chained continuity
  generation and its exact wake/configuration custody. It can advance even while old
  Python remains loaded.
- **Resident daemon launch provenance** is durable evidence describing the repository
  and launch contract represented by one running daemon process image. It does not
  claim the identity of every Python code object ever loaded.

The now-proven upstream chain is:

```text
canonical N maintenance
-> automatic continuity N+1
-> successor N+1 configuration/handoff preparation
```

That proof does not establish resident-code adoption. The future barrier is:

```text
N wake quiescent
-> exact resident N+1 process replacement
-> N+1 resident readiness
-> N+1 wake effects
```

This admission task does not make that second sequence real.

## Exact authority boundary

The admitted principal is
`deterministic_maintenance_resident_runtime_adoption_controller` in the
`maintenance` subsystem. A future effectful task must request exactly:

1. `exact_successor_maintenance_authority_generation_read` (reused);
2. `exact_maintenance_authority_continuity_receipt_read` (reused);
3. `exact_maintenance_successor_generation_adoption_state_read` (reused);
4. `exact_successor_repository_state_read` (reused);
5. `exact_resident_runtime_adoption_configuration_read` (new);
6. `exact_resident_runtime_launch_provenance_read` (new);
7. `bounded_maintenance_runtime_quiescence` (new);
8. `maintenance_resident_runtime_adoption_intent_write` (new);
9. `bounded_exact_sentientosd_self_exec` (new);
10. `exact_successor_resident_runtime_readiness_read` (new);
11. `maintenance_resident_runtime_adoption_receipt_write` (new); and
12. `read_only_maintenance_resident_runtime_health_projection` (new).

`bounded_exact_sentientosd_self_exec` means only replacement of the current daemon
process image by the exact pre-bound daemon launch target for one verified consecutive
successor. It is not `real_service_restart`, arbitrary process control, arbitrary
executable/argv/shell authority, OS service-manager authority, or authority over other
`RuntimeSupervisor` adapters. Generic `real_service_restart` remains blocked with no
authority.

## Exact successor eligibility and persistent posture

A target must prove the exact lineage, resident generation N provenance, consecutive
N+1 ordinal and predecessor digest, continuity receipt, successful canonical local
repository advancement, exact N+1 HEAD/ref/tree, pending successor-adoption
transaction/configuration, and unchanged persistent lineage. Newest, caller-selected,
non-consecutive, arbitrary-branch/worktree, or hosted-only targets are ineligible.

Operator approval establishes one digest-bound resident-adoption posture. Fresh human
approval is not required for each N-to-N+1 transition while the exact posture and same
lineage remain valid, each target is one verified consecutive successor, and authority
has neither widened nor expired. This persistent approval is not itself a runtime grant;
effectful execution must still consume the separately governed admission and receipts.

## Future closed launch contract

Future configuration should bind once: enabled posture; continuity policy and successor
adoption configuration paths/digests; repository identity/root; Python executable
realpath; repository-relative daemon entrypoint; exact argv template and cwd; allowlisted
inherited environment keys and required maintenance environment bindings; external state
root; provenance, transaction, and receipt locations; STOP marker; readiness and
quiescence timeouts; bounded transition count; and exact configuration digest. No
per-generation caller-selected executable, path, argv, command, or environment is
permitted.

Packaging currently exposes `sentientosd = "sentientosd:main"`. A future implementation
must choose and configure one deterministic invocation that unambiguously imports the
target repository rather than trusting ambient import paths. This document adds no
launch code.

Future launch provenance must bind at least repository identity/root; represented
maintenance generation ordinal/digest; launch commit/tree; Python executable and daemon
entrypoint realpaths; cwd; exact argv contract; bounded environment identity; process ID
or instance nonce; startup time; and provenance-record digest. This proves the bounded
launch record, not every code object's identity.

## Successor-wake barrier and lifecycle ordering

Successor adoption remains responsible for exact N+1 configuration and handoff custody;
automatic continuity remains responsible only for deriving the next generation. The
future resident controller must interpose after successor preparation but before wake
effects:

1. verify exact N+1 continuity generation and receipt;
2. prepare and verify the N+1 configuration closure;
3. quiesce the N wake owner and all conflicting maintenance owners;
4. durably persist successor-handoff/resident-adoption intent;
5. withhold N+1 wake effects;
6. replace the daemon image with the pre-bound exact target;
7. independently verify repository state and launch provenance in the new image;
8. write readiness/adoption custody and complete the pending handoff; and
9. only then permit N+1 wake effects and restart the continuity owner.

Before replacement, no wake invocation or maintenance effect may remain ambiguous.
Process replacement is not a shortcut for killing unresolved work. If identity or
readiness cannot be proven, startup fails closed before maintenance effects. There is
no automatic checkout, rollback to N, restart of old code, or fabricated readiness.

`RuntimeSupervisor` may supply a future primitive only when its exact semantics fit.
Its registered-adapter lifecycle and strict argv-only `ChildProcessServiceAdapter` do
not prove self-replacement authority and are not widened here.

## Future task language and deferred implementation

A future goal must affirm: `verified successor maintenance generation`, `exact pending
successor wake handoff`, `exact successor repository state`, `resident runtime
launch provenance`, `bounded sentientosd self replacement`, `post replacement resident
readiness`, and `before successor wake effects`. The canonical goal is:

> Implement bounded sentientosd self replacement to a verified successor maintenance
> generation during an exact pending successor wake handoff after exact successor
> repository state and resident runtime launch provenance are verified, requiring post
> replacement resident readiness before successor wake effects.

The authority definition mechanically rejects generic/arbitrary service and process
control; arbitrary executable, command, argv, or environment selection; non-consecutive
or unverified selection; premature successor work; hot/module reload and dynamic code
injection; rollback and Git mutation/publication; provider/network/credential authority;
OS service managers and parent installation; authority widening/expiry extension; and
candidate, lease, maintenance-implementation, or maintenance-validation scope.

Still deferred are provenance capture, wake gating, owner-quiescence integration,
self-exec, startup recovery, readiness and adoption receipts, daemon integration,
health projection, Windows-native replacement, parent supervision, and rollback. There
is intentionally no `sentientos/maintenance_resident_runtime_adoption.py` module and no
`os.exec*` or process-restart path after this admission.
