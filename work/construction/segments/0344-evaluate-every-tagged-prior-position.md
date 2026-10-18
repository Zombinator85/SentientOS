# Sequence 344: review every tagged historical position during canonical planning

## Source change and integration

Canonical epistemic planning now examines every tagged prior position. A verified positive position can no longer short-circuit a later adverse, omitted, or unresolved position. Any unresolved applicable history defers the goal; otherwise adverse or unreviewed positions continue to require epistemic review. Planning remains separate from execution and grants no additional authority.

Candidate `37aa76097d4f8b61e3285063ae1c66887102977e`, tree `30fb63bb1777ca5facd69974697c0dca6a0144cd`, was merged normally through PR #2334 as main `520c02fa09366c14ceb1b4c741c7821fa802a3b8`, tree `1acf5eeb682b9d98aca18c61c6c313044cd12c89`. The merge preserved the source branch history.

## Verification

On the exact committed local source (`1c6064dd2e995ea52b77296be61b03589f9b9060`), the canonical runner passed 40/40 planner, allocator, and plan-only tests with no skips. Compileall, diff checks, and the Mypy ratchet passed (0 new diagnostics, 1,050 existing matches, 40 retired). Superseded runner attempts remain recorded as failures; only the corrected exact-tree run is counted as passed.

Candidate checks passed: CI `39091970397`, Required Quality Gate `39091970366`, Docker `39091970356`, invariants `39091970304`, Codex CI `39091970345`, Lint Benchmark `39091970368`, Release `39091970454`, and Gradient `39091970383`. QG ran with actual Administrator UID 0, strict audit and immutability verification passed, and its exact acceptance/finalizer steps completed. QG artifact `12122827607` has GitHub SHA-256 `0453ffc68d4ee9de895ab6f2749a017577e6ae7c142c98ef2f3e43dbe68a0965`; finalizer artifact `12122668124` has SHA-256 `f41ad94289858ae5c5a6b25a831f321438427b690f183b670672a7b2cbfd904c`.

Post-merge main CI `39092230965`, Required Quality Gate `39092230936`, Docker `39092230962`, invariants `39092230949`, Codex CI `39092230952`, and Docs Deploy `39092230960` passed on exact main `520c02fa09366c14ceb1b4c741c7821fa802a3b8` and tree `1acf5eeb682b9d98aca18c61c6c313044cd12c89`. Forge Smoke `39092230955` was skipped by configured workflow conditions. Post-merge QG artifact `12123252214` is bound to the exact main SHA and has GitHub digest `206348b9f60ab05562adfb07bbc2515695e4a66919b3034171532fba295f25b6`.

## Boundaries

No inference, execution, model transition, or production developmental outcome is claimed. The post-merge feedback invitation workflow failed on run `39092230858` because its fixed comment step lacked the issue-comment permission. Sequence 346 addresses that workflow defect with only the narrow permission needed and a regression test; it is not included in this source increment.
