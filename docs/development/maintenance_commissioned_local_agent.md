# Commissioned-local maintenance implementation agent

## Discovered boundary and design review

Before this change, the maintenance watchdog built a sealed implementation request,
bound it to a lease-backed implementation-agent session, and handed it to
`maintenance_local_codex_foreman`.  That foreman created an exact-base detached
worktree, constructed the instruction envelope, supervised `codex exec` JSONL,
measured the real diff, and returned only a candidate for the independent validation
controller.  Correction resumed the recorded Codex thread.  Commit and publication
were already separate deterministic stages.

The generic responsibilities are the sealed request/session contract, lease binding,
exact-base workspace custody, cancellation, observations, workspace measurement, and
handoff to validation.  CLI probing, Codex JSONL, authentication, and Codex thread IDs
are backend-specific.  `ImplementationAgentDriver` is therefore the common descriptor
contract and `execute_implementation_agent` is the explicit, no-fallback effectful
dispatch boundary.  The existing `LocalCodexDriver` still implements it.

The commissioned inference path is an activated production `LocalModel` identity plus
a `LocalModelAuthorityMap`, submitted to `GovernedLocalModelInvoker`.  Requests bind
purpose, caller, lifecycle phase, correlation ID, model/artifact identity, budgets, and
control-plane admission; receipts record inference without granting tools, memory,
actions, repository mutation, or provider networking.  Previously its purpose set had
no maintenance purpose and its one-shot completion API had no iterative tool/session
runtime.

## Local backend

`CommissionedLocalDriver` adds the dedicated `maintenance_implementation` purpose and
keeps capability on the **agent session**, never on the model identity.  Each inference
returns one defensive JSON action.  Malformed output is a bounded no-effect
observation.  Supported mediated tools are file/section reads, bounded literal search,
directory listing, compare-and-replace file edits, Git status/diff inspection, and a
closed argv command allowlist.  There is no shell, Codex, provider, network, commit,
push, ref-write, publication, or fallback path.

Paths must be relative, remain beneath the foreman-owned detached worktree after
resolution, contain no `.git` component, traverse no symlink, and writes must match an
admitted subject path.  Commands use `shell=False`, a minimal environment with proxy
variables disabled, and only repository test/static-check module prefixes.  The lease
is rechecked before every effect.  Tool and inference events are written as bounded
session audit records; model prose never directly causes an effect.

The session retains task, session, lease, exact base, worktree, commissioned identity,
correlation, brief, observations, validation failures, iteration/budget counters, and
terminal state outside model context.  Hard bounds cover iterations, parse recovery,
per-call and total token ceilings, inference/session/command time, reads, observations,
and listings.  Cancellation, expiry, timeout, malformed output, and exhaustion terminate
honestly.  A `candidate_complete` action is only a report: the runtime measures the
actual workspace, and deterministic validation remains the sole acceptance oracle.
Corrective execution reuses the same exact-base worktree and supplies bounded validator
evidence to a governed continuation.

Here, **local means local commissioned model inference**.  It does not mean historical
`local_codex`, which is a locally governed process that can invoke Codex remotely.

## Proof and limitations

CI uses a deterministic commissioned-invoker double to prove tool mediation, workspace
isolation, correction, cancellation, exhaustion, and zero Codex/remote effects.  It is
not evidence that a particular GGUF can solve the fixture.  The opt-in real-runtime
proof is:

```bash
SENTIENTOS_COMMISSIONED_LOCAL_ACTIVATION=/absolute/path/to/activation.json python -m scripts.run_tests -q \
  tests/test_maintenance_commissioned_local_agent.py::test_real_commissioned_local_model_integration_requires_explicit_fixture
```

The test is skipped until an operator supplies a commissioned activation and verifies
that exact model can emit the action protocol; do not claim real-model end-to-end
maintenance success from the deterministic double or this protocol smoke alone.  The
first landed boundary is a reusable driver/session runtime.  Wiring an
operator-selected live driver instance into long-running watchdog configuration remains
the next bounded activation step; the default watchdog continues selecting Codex and
cannot silently select or fall back from commissioned-local mode.
