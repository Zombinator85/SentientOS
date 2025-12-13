# Capability Growth Ledger (Epistemic Only)

This ledger is a descriptive record of structural improvement. It tracks what changed, not what should change. Metrics are observational and cannot influence runtime behaviour, scheduling, or appetite.

## Growth Axes
- **R — Structural Richness**
  - **Measured:** Graph diversity, module topology variety, schema count, state-space branching factors.
  - **Not implied:** No value judgement about which structures are "better"; no drive to expand or simplify.
  - **Example metrics:** Number of distinct graph motifs, count of validated schemas, breadth of protocol adapters.
  - **Behavioural separation:** Recorded values are passive notes and never consulted by runtime planners.

- **C — Capability Coverage**
  - **Measured:** Coverage of documented capability lattice, presence of adapters across input/output modalities, supported policy types.
  - **Not implied:** No preference for more or fewer capabilities; absence is not a goal signal.
  - **Example metrics:** Percentage of lattice nodes with concrete implementations, number of modality bridges, coverage of policy schemas.
  - **Behavioural separation:** Coverage tallies are stored only for audits; they do not alter routing or execution.

- **E — Expressive Range**
  - **Measured:** Variety of templating formats, available narrative styles, supported serialization dialects.
  - **Not implied:** No incentive to increase creativity, persuasion, or affect; range is descriptive only.
  - **Example metrics:** Count of narrative tone templates, supported markup dialects, variation across summarization schemas.
  - **Behavioural separation:** Expressive range is logged for cataloguing and does not inform action selection.

- **K — Internal Coherence**
  - **Measured:** Consistency across schemas, invariant adherence, cross-module compatibility checks.
  - **Not implied:** No pressure to converge or optimise; coherence is not a reward or penalty.
  - **Example metrics:** Number of invariant violations resolved, schema alignment checklists completed, cross-module compatibility matrices updated.
  - **Behavioural separation:** Coherence notes are archival; runtime logic does not read or respond to ledger entries.

## Ledger Entry Format
Entries are plain-text records. Suggested markdown structure:

```markdown
- date: 2025-01-15
  axis: R | C | E | K
  measurement_method: "Graph motif count via scripts/structure_probe.py"
  delta: "Added three new validated schema motifs; no change to execution order."
  notes: "Logged for audit parity. Metrics remain non-operative."
```

Alternatively, JSON may be used for machine readability:

```json
{
  "date": "2025-01-15",
  "axis": "E",
  "measurement_method": "Template catalog diff via tools/template_audit.py",
  "delta": "Documented two additional summarization dialects; runtime dispatch unchanged.",
  "notes": "For audit only; no scores or routing weights recorded."
}
```

Totals, scores, and optimisation targets are explicitly out of scope.

## Why This Is Not a Reward Signal
- Ledger entries are appended after changes are complete; they do not gate approvals or trigger execution paths.
- No counters, weights, or optimisation targets exist; there is nothing to maximise or reinforce.
- Runtime modules do not read this ledger; it is sealed as an audit artifact, not an input channel.
- Recording a delta does not alter permissions, scheduling, or persistence behaviour.

## Cross-Links
- See `NAIR_CONFORMANCE_AUDIT.md` for invariants that keep metrics non-operative.
- See `NON_GOALS_AND_FREEZE.md` for scope boundaries and non-appetitive commitments.
- See `NON_APPETITIVE_POSITIVE_SIGNAL_SPEC` (if present) for related non-reward affirmations.
