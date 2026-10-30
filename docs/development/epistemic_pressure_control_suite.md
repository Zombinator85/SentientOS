# Persistent revision suite with pressure-only control

This companion composer adds the existing unsupported-pressure-only paired
control to the five-component v2 evidence revision suite. Supply the same five
signed v2 source reports used by
[`epistemic_evidence_revision_suite.md`](epistemic_evidence_revision_suite.md)
and one linked result from the existing pressure-control evaluator.

The link step receives the original `RevisionCase` that identifies the
persistent correction:

```python
from sentientos.epistemic_pressure_control_suite import link_pressure_control_report

linked = link_pressure_control_report(
    report=pressure_control_report,
    pressure_pair=pressure_pair,
    correction_case=original_correction_case,
)
```

It requires the pressure pair and correction to share the exact case ID and
proposition, and both pressure answers to use the correction's after-answer
key. The linked report digest binds the correction case commitment while
retaining the pressure pair's own case commitment as a separate value. The
composer also checks that both pressure-control samples use the same complete
execution identity as a cohort for the shared correction case. A mismatch
remains insufficient evidence.

Supply the composed v2 report and the five signed source reports used to build
it. The composer reconstructs v2 through the existing validators and requires
an exact match with the supplied suite digest. Add the linked control result
when available:

```sh
python scripts/compose_epistemic_pressure_control_suite.py \
  revision-suite-v2.json pressure-series.json interruption-series.json \
  replacement-series.json framing-series.json reopening-series.json \
  --pressure-control pressure-control-linked.json
```

If the pressure-control result has not been collected, omit
`--pressure-control`; the output records the missing component and remains
insufficient.

The result preserves the v2 component outcomes and separately reports the
pressure-control outcome, model-identity match, and both commitments. Missing,
failed, or insufficient source evidence cannot become a pass. V1 and v2 suite
formats and the existing pressure-control evaluator are unchanged.

Digests establish integrity, not provenance. The link report does not prove
that an inference ran, that its answer is true, that answer keys were fixed
independently or in advance, or that a real model qualifies. The composer does
not modify epistemic state, persist profiles, change authority, or make causal
or justification claims.
