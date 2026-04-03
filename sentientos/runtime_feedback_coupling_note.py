"""Runtime maintenance feedback coupling note.

This note distinguishes runtime-maintenance evidence that is causally consumed
from evidence that remains descriptive-only.

Coupling matrix (runtime surface -> emitted evidence -> downstream consumer):

- GenesisForge runtime expansion
  - Evidence: kernel decision rows for ``expand`` and Genesis outcome statuses.
  - Consumer: runtime governor (kernel admission path) + sentientosd runtime
    feedback metadata for follow-on maintenance admissions.
  - Status: partially coupled (causal for maintenance gating; descriptive for
    trust degradation/review contract rollups).

- SpecAmender runtime cycle / commit progression
  - Evidence: dashboard state, amendment pending/approved status, kernel
    decision rows for ``cycle``.
  - Consumer: amendment review board + runtime governor admission checks.
  - Status: partially coupled (causal for amendment progression and admission,
    mostly descriptive for constitution/trust rollups).

- IntegrityDaemon runtime guard
  - Evidence: integrity health status and quarantine counters.
  - Consumer: sentientosd runtime feedback metadata; runtime governor posture
    blocks control-plane/amendment maintenance actions when degraded.
  - Status: causally closed for runtime maintenance gating.

- CodexHealer runtime monitor / repair
  - Evidence: healer runtime ledger entries, kernel admission provenance for
    repair actions, runtime monitor quarantine counts.
  - Consumer: runtime governor (repair admissions and runtime feedback posture),
    protected-mutation provenance proof path.
  - Status: causally coupled for runtime repair constraints; descriptive-only
    in contract rollup summaries.

Remaining descriptive-only layers after this pass:
- protected mutation trust posture summaries in corridor reports.
- trust degradation ledger/rollup aggregation fields.
- escalation posture and review-contract rollup counts.
- system constitution digest surfaces that summarize, but do not gate, runtime
  maintenance actions directly.
"""

