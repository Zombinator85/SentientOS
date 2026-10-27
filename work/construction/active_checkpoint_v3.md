# Recovery state - sequence 872

PR #2951 merged as `6579f13bb2d575191c964fdfa19d9430d3b58cad` with verified tree `b819b090edb46614bc31926fc71fb3627b2e8bea`. All eight hosted workflows passed on candidate `97d168a19eedaedd87434f7aa33093fad10442c7`; GitHub readback verified the v3 head, active checkpoint, sequence 871 evidence, and fourth shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 871 prior sequences before this append and verifies 872 sequences after it.

Latest verified main: `6579f13bb2d575191c964fdfa19d9430d3b58cad`, tree `b819b090edb46614bc31926fc71fb3627b2e8bea`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0872-integrate-pr-2951-main-verification.md`
Latest segment SHA-256: `24b1bd957b4db3cd113518ede6262bc12ec6547c3e3d9d0596c6eea1c715f985`
Sequence: 872
Evidence: `work/construction/evidence/0872-integrate-pr-2951-main-verification.json`
Evidence SHA-256: `8feb1392ffe65ba411c6ecc23015e7d1bdf47f17383a7b841d2d6a2479548314`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, all predecessor-linked v3 shards, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 871) ---

PR #2950 post-merge verification is recorded in segment `work/construction/segments/0871-integrate-pr-2950-main-verification.md` and evidence `work/construction/evidence/0871-integrate-pr-2950-main-verification.json`.
