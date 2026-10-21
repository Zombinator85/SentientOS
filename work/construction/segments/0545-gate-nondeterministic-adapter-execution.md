# Sequence 545 — gate nondeterministic adapters on consensus approval

The experiment chain previously checked `requires_consensus` only when that flag was explicitly set. The Arduino serial and webcam adapters declare themselves nondeterministic, yet a pending experiment with that flag false could reach execution. The runner now also requires active consensus approval for adapters marked nondeterministic. Deterministic adapters retain their existing behavior. Exact regressions cover pending denial, approved execution, and deterministic compatibility, and the three nodes are included in the exact hosted Required Quality Gate acceptance list.

Local source validation: changed Python modules compile; the workflow YAML parses; `git diff --cached --check` is clean. The construction custody verifier passed with 544 prior segments before this append. The canonical targeted test harness was attempted but stopped during its pinned editable-install bootstrap because the sandbox could not reach the package proxy for setuptools; zero tests executed and no local test pass is claimed. Hosted exact-candidate CI and Quality Gate verification are pending.

Verified base: `9e7019bca46b2e6c5e5baf6e4a03f4a0fb512ca0`, tree `b41e5cdf2c73e6dcbc228a185ed3a9b3983ce5f8`
Implementation candidate: `e49438c08efa9d41c1c4c59a8d96fdcae83c2bb6`, tree `a021879d8ce38c4e2a9f95354d4bb5ee549a003f`
Latest construction segment: `work/construction/segments/0545-gate-nondeterministic-adapter-execution.md`
Sequence: 545 (candidate pending hosted verification)

No physical adapter, production model transition, serving, inference, or developmental writeback was executed.
